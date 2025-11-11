import random
from collections import defaultdict, deque

import numpy as np

# --- RRM Scheduler Config (from the new recommendations) ---
POOR_QOE_THRESHOLD = 3.5  # "Problem client" threshold
HIGH_VARIANCE_THRESHOLD = 3.0  # (dB) What counts as "erratic RSSI"
HIGH_AP_LOAD_THRESHOLD = 70.0  # (Airtime %) When the AP becomes "load-aware"

# --- "Adaptive Interval" settings (in simulation steps) ---
# 1 step = 10 seconds
INTERVAL_PROBLEM_CLIENT = 1  # (10s) Check problem clients immediately
INTERVAL_STABLE_CLIENT = 6  # (60s) Normal check for stable clients
INTERVAL_AP_BUSY = 30  # (5m) AP is busy, be quiet and only check stable clients rarely

# --- "Sliding-Window Cache" Config ---
CACHE_WINDOW_STEPS = 3  # (30s) How long a cached 802.11k report is valid


class AccessPoint:
    """
    Represents a virtual Access Point with a high-fidelity RRM scheduler.
    """

    def __init__(self, environment, ap_row):
        self.env = environment
        self.ap_id = ap_row["ap_id"]
        ap_num_hex = f"{int(self.ap_id.split('-')[1]):02X}"
        self.bssid = f"00:AA:{ap_num_hex}:{random.randint(0, 255):02X}:{random.randint(0, 255):02X}:{random.randint(0, 255):02X}"
        self.x = ap_row["x"]
        self.y = ap_row["y"]
        self.band = ap_row["band"]
        self.channel = ap_row["channel"]
        self.connected_clients = []

        # --- NEW: Scheduler State ---
        self.client_rrm_state = {}  # Stores the "dossier" on each client
        self.client_report_cache = {}  # Implements the "sliding-window cache"

        self.steer_attempts = 0
        self.steer_successes = 0
        self.qoe_deltas = []
        self.stats_by_persona = defaultdict(
            lambda: {"attempts": 0, "success": 0, "rejects": 0}
        )

        self.env.register_ap(self)

    def connect_client(self, client):
        """Client associates; AP calculates Post-Roam Delta and init's scheduler state."""
        if client in self.connected_clients:
            return

        self.connected_clients.append(client)
        client.connected_ap = self

        post_roam_qoe = client.calculate_current_qoe()

        # --- NEW: Initialize RRM Scheduler State for this client ---
        self.client_rrm_state[client.client_id] = {
            "last_check_step": -999,  # Set to -999 to force an immediate check
            "current_interval": 1,  # Check immediately
            "rssi_history": deque(
                [client.calculate_current_rssi()], maxlen=6
            ),  # 6 steps = 1 min history
        }
        # --- End New ---

        if client.last_seen_ap_id and client.last_seen_ap_id != self.ap_id:
            pre_roam_qoe = client.last_seen_qoe
            qoe_delta = post_roam_qoe - pre_roam_qoe
            self.qoe_deltas.append(qoe_delta)

            old_ap = next(
                (ap for ap in self.env.all_aps if ap.ap_id == client.last_seen_ap_id),
                None,
            )
            if old_ap:
                old_ap.log_steer_success(client.persona_name)

        client.last_seen_ap_id = None
        client.last_seen_qoe = 0.0

    def disconnect_client(self, client):
        """Client disassociates; AP cleans up scheduler state."""
        if client in self.connected_clients:
            self.connected_clients.remove(client)
            client.connected_ap = None

            # --- NEW: Clean up scheduler state ---
            if client.client_id in self.client_rrm_state:
                del self.client_rrm_state[client.client_id]
            if client.client_id in self.client_report_cache:
                del self.client_report_cache[client.client_id]
            # --- End New ---

    def log_steer_success(self, persona_name):
        """Called by the *new* AP to tell this *old* AP the steer worked."""
        self.steer_successes += 1
        self.stats_by_persona[persona_name]["success"] += 1

    # --- ====================================================== ---
    # --- NEW: HIGH-FIDELITY SCHEDULER (implements the image)
    # --- ====================================================== ---

    def _get_ap_load_level(self):
        """Helper to get AP's own load status."""
        load_pct = self.env.get_ap_load(self.ap_id)["airtime_util_pct"]
        return "high" if load_pct > HIGH_AP_LOAD_THRESHOLD else "low"

    def _update_adaptive_interval(
        self, client_state, client_qoe, rssi_variance, ap_load_level
    ):
        """
        Implements "per-client adaptive intervals" and "load-aware prioritization".
        This function SETS the check interval for the client.
        """

        # 1. "clients with erratic RSSI or poor airtime get shorter intervals automatically"
        if client_qoe < POOR_QOE_THRESHOLD or rssi_variance > HIGH_VARIANCE_THRESHOLD:
            client_state["current_interval"] = INTERVAL_PROBLEM_CLIENT

        # 2. "Integrate AP load-aware prioritization"
        elif ap_load_level == "high":
            # AP is busy, so be quiet. Only check stable clients rarely.
            client_state["current_interval"] = INTERVAL_AP_BUSY

        # 3. Default for stable client on non-busy AP
        else:
            client_state["current_interval"] = INTERVAL_STABLE_CLIENT

    def scheduler_tick(self, client, current_step):
        """
        This function runs for EVERY client on EVERY tick (10s).
        It decides IF it's time to run an RRM check.
        """
        if client.client_id not in self.client_rrm_state:
            return  # Client is disassociating, skip

        client_state = self.client_rrm_state[client.client_id]

        # 1. Update client's state
        current_rssi = client.calculate_current_rssi()
        current_qoe = client.calculate_current_qoe()
        client_state["rssi_history"].append(current_rssi)

        # 2. Calculate variance
        rssi_variance = np.std(client_state["rssi_history"])

        # 3. Get AP load
        ap_load_level = self._get_ap_load_level()

        # 4. Set the "adaptive interval" based on these new stats
        self._update_adaptive_interval(
            client_state, current_qoe, rssi_variance, ap_load_level
        )

        # 5. Decide: Is it time to check this client?
        steps_since_last_check = current_step - client_state["last_check_step"]

        if steps_since_last_check >= client_state["current_interval"]:
            # print(f"[{self.ap_id}]: SCHEDULER: Time to check {client.client_id} (QoE: {current_qoe:.1f}, Var: {rssi_variance:.1f}, Int: {client_state['current_interval']} steps)")
            client_state["last_check_step"] = current_step

            # This function is now the *action*, triggered *by* the scheduler
            self.rrm_action_check(client, current_qoe, current_step)

    # --- ====================================================== ---
    # --- RRM ACTION FUNCTIONS (Called by the Scheduler)
    # --- ====================================================== ---

    def rrm_action_check(self, client, current_qoe, current_step):
        """
        This is the ACTION function, triggered by the scheduler.
        It decides *if* a steer is warranted and which path to take.
        """

        # Scheduler already decided to check, but we only *act* if QoE is poor
        if current_qoe < POOR_QOE_THRESHOLD:
            # print(f"[{self.ap_id}]: RRM: Client {client.client_id} has poor QoE ({current_qoe:.2f}). Initiating steer...")

            self.steer_attempts += 1
            self.stats_by_persona[client.persona_name]["attempts"] += 1
            client.last_seen_qoe = current_qoe
            client.last_seen_ap_id = self.ap_id

            if client.band_support != "Dual" and client.band_support != self.band:
                self.run_passive_inference_and_steer(
                    client, current_step, band_steer=True
                )
            elif client.supports_80211v:
                self.request_active_beacon_report(client, current_step)
            else:
                self.run_passive_inference_and_steer(client, current_step)
            # else:
            # Scheduler check ran, but QoE is fine. Do nothing.
            # print(f"[{self.ap_id}]: RRM: Client {client.client_id} checked, QoE is good ({current_qoe:.2f}). No action.")
            pass

    def request_active_beacon_report(self, client_to_ask, current_step):
        """Simulates the 802.11k request, NOW with caching."""

        # --- NEW: "sliding-window cache" logic ---
        if client_to_ask.client_id in self.client_report_cache:
            cached = self.client_report_cache[client_to_ask.client_id]
            if (current_step - cached["timestamp_step"]) < CACHE_WINDOW_STEPS:
                # print(f"[{self.ap_id}]: RRM: Using CACHED 802.11k report for {client_to_ask.client_id}.")
                self.analyze_active_report_and_steer(client_to_ask, cached["report"])
                return  # Use the cached report
        # --- End Cache Logic ---

        # If no valid cache, request a new report
        # print(f"[{self.ap_id}]: RRM: Cache miss. Requesting NEW 802.11k report from {client_to_ask.client_id}.")
        client_report = client_to_ask.receive_beacon_request_and_scan()

        # Store the new report in the cache
        self.client_report_cache[client_to_ask.client_id] = {
            "timestamp_step": current_step,
            "report": client_report,
        }

        self.analyze_active_report_and_steer(client_to_ask, client_report)

    def analyze_active_report_and_steer(self, client, client_report):
        """Analyzes 802.11k report and sends 802.11v steer command."""
        candidates = []
        for ap_entry in client_report["report"]:
            if ap_entry["ap_id"] == self.ap_id:
                continue
            if (
                client.band_support != "Dual"
                and client.band_support != ap_entry["band"]
            ):
                continue

            global_load = self.env.get_ap_load(ap_entry["ap_id"])
            rssi_score = max(
                0, min(100, (ap_entry["rssi"] - (-85)) / ((-60) - (-85)) * 100)
            )
            load_score = max(0, 100 - global_load["airtime_util_pct"])
            final_score = (0.7 * rssi_score) + (0.3 * load_score)

            candidates.append(
                {
                    "ap_id": ap_entry["ap_id"],
                    "score": final_score,
                    "client_view_rssi": ap_entry["rssi"],
                    "ap_load_airtime": global_load["airtime_util_pct"],
                }
            )

        if not candidates:
            client.clear_roam_memory()
            return

        ranked_list = sorted(candidates, key=lambda x: x["score"], reverse=True)
        acceptance = client.receive_bss_tm_request(ranked_list)

        if not acceptance:
            self.stats_by_persona[client.persona_name]["rejects"] += 1
            client.clear_roam_memory()

    def run_passive_inference_and_steer(self, client, current_step, band_steer=False):
        """Passively infers QoE and forces disassociation."""
        if band_steer:
            self.disconnect_client(client)
            client.find_best_ap_and_associate()
            return

        metrics = client.generate_passive_metrics()
        mcs_score = metrics["uplink_mcs_index"] / 9.0
        retry_score = 1.0 - (metrics["uplink_retry_pct"] / 30.0)
        ack_score = 1.0 - (metrics["ack_variance_ms"] / 2.0)
        estimated_qoe = (mcs_score * 0.5 + retry_score * 0.25 + ack_score * 0.25) * 5.0

        if estimated_qoe < POOR_QOE_THRESHOLD:
            self.disconnect_client(client)
            client.find_best_ap_and_associate()
        else:
            client.clear_roam_memory()

    def get_steering_stats(self):
        """Returns this AP's stats for aggregation."""
        return {
            "attempts": self.steer_attempts,
            "successes": self.steer_successes,
            "qoe_deltas": self.qoe_deltas,
            "by_persona": self.stats_by_persona,
        }
