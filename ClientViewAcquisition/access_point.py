"""
This module defines the AccessPoint class, which simulates a virtual Access Point (AP)
with a high-fidelity RRM scheduler.

UPDATES (End-Term):
- Added collection of Transport Layer metrics (TCP/QUIC) in scheduler_tick.
- Added periodic execution of 802.11mc RTT measurements.
"""

import random
from collections import defaultdict, deque

import numpy as np

# --- RRM Scheduler Config ---
POOR_QOE_THRESHOLD = 3.5
HIGH_VARIANCE_THRESHOLD = 3.0
HIGH_AP_LOAD_THRESHOLD = 70.0
INTERVAL_PROBLEM_CLIENT = 1
INTERVAL_STABLE_CLIENT = 6
INTERVAL_AP_BUSY = 30
CACHE_WINDOW_STEPS = 3

# New RRM Config for End-Term
RTT_MEASUREMENT_INTERVAL = 10  # Measure RTT every 10 ticks (simulating overhead)


class MockQoEPredictor:
    """
    Simulates a pre-trained Linear Regression model for predicting Quality of Experience (QoE).
    """

    def __init__(self):
        self.coef_ = [0.1, -0.05, -0.8, 0.4]  # Weights for [SNR, Load, Hysteresis, FT]
        self.intercept_ = 1.5

    def predict(self, features):
        score = self.intercept_
        for i, val in enumerate(features):
            score += val * self.coef_[i]
        return max(0.0, min(5.0, score))


class AccessPoint:
    """
    Represents a virtual Access Point with a high-fidelity RRM scheduler
    and a ML-based predictive model.
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
        self.noise_floor_dbm = random.uniform(-98.0, -92.0)
        self.supports_80211r = True

        # State tracking
        self.client_rrm_state = {}
        self.client_report_cache = {}
        self.steer_attempts = 0
        self.steer_successes = 0
        self.qoe_deltas = []
        self.stats_by_persona = defaultdict(
            lambda: {"attempts": 0, "success": 0, "rejects": 0}
        )

        # New: Store End-Term telemetry for reporting
        self.transport_logs = []
        self.rtt_logs = []

        self.qoe_model = MockQoEPredictor()
        self.env.register_ap(self)

    def connect_client(self, client):
        if client in self.connected_clients:
            return

        self.connected_clients.append(client)
        client.connected_ap = self

        current_rssi = client.calculate_current_rssi()
        current_snr = client.calculate_current_snr()

        # Initialize RRM state with new End-Term history buffers
        self.client_rrm_state[client.client_id] = {
            "last_check_step": -999,
            "current_interval": 1,
            "rssi_history": deque([current_rssi], maxlen=6),
            "snr_history": deque([current_snr], maxlen=6),
            "tcp_rtt_history": deque(maxlen=6),  # New: TCP Latency history
            "rejection_count": 0,
        }

        # Log previous AP delta if applicable
        if client.last_seen_ap_id and client.last_seen_ap_id != self.ap_id:
            post_roam_qoe = client.calculate_current_qoe()
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
        if client in self.connected_clients:
            self.connected_clients.remove(client)
            client.connected_ap = None

            if client.client_id in self.client_rrm_state:
                del self.client_rrm_state[client.client_id]
            if client.client_id in self.client_report_cache:
                del self.client_report_cache[client.client_id]

    def log_steer_success(self, persona_name):
        self.steer_successes += 1
        self.stats_by_persona[persona_name]["success"] += 1

    def _get_ap_load_level(self):
        load_pct = self.env.get_ap_load(self.ap_id)["airtime_util_pct"]
        return "high" if load_pct > HIGH_AP_LOAD_THRESHOLD else "low"

    def _update_adaptive_interval(
        self, client_state, client_qoe, rssi_variance, ap_load_level
    ):
        rejection_count = client_state.get("rejection_count", 0)
        if rejection_count > 0:
            backoff_interval = INTERVAL_STABLE_CLIENT * (2 ** (rejection_count - 1))
            client_state["current_interval"] = backoff_interval
            return

        if client_qoe < POOR_QOE_THRESHOLD or rssi_variance > HIGH_VARIANCE_THRESHOLD:
            client_state["current_interval"] = INTERVAL_PROBLEM_CLIENT
        elif ap_load_level == "high":
            client_state["current_interval"] = INTERVAL_AP_BUSY
        else:
            client_state["current_interval"] = INTERVAL_STABLE_CLIENT

    def _collect_end_term_metrics(self, client, current_step):
        """
        Helper: Collects Transport Layer QoE and RTT data.
        """
        client_state = self.client_rrm_state.get(client.client_id)
        if not client_state:
            return

        # 1. Transport Layer (TCP/QUIC) - Collect frequently
        transport_metrics = client.generate_transport_metrics()
        client_state["tcp_rtt_history"].append(transport_metrics["tcp_rtt_ms"])

        # Store for global telemetry
        self.transport_logs.append(
            {
                "step": current_step,
                "client_id": client.client_id,
                "tcp_rtt": transport_metrics["tcp_rtt_ms"],
                "packet_loss": transport_metrics["tcp_retransmits_pct"],
                "jitter": transport_metrics["jitter_ms"],
            }
        )

        # 2. 802.11mc RTT - Collect periodically (simulate active ping)
        # Only if client supports it and we are on an interval
        if client.supports_80211mc and (current_step % RTT_MEASUREMENT_INTERVAL == 0):
            rtt_distance = client.measure_rtt_to_ap(self.ap_id)
            if rtt_distance > 0:
                self.rtt_logs.append(
                    {
                        "step": current_step,
                        "client_id": client.client_id,
                        "ap_id": self.ap_id,
                        "rtt_distance_m": rtt_distance,
                    }
                )

    def scheduler_tick(self, client, current_step):
        """
        Performs a scheduler tick for a given client.
        """
        if client.client_id not in self.client_rrm_state:
            return

        client_state = self.client_rrm_state[client.client_id]

        # --- Standard Mid-Term Checks ---
        current_rssi = client.calculate_current_rssi()
        current_qoe = client.calculate_current_qoe()
        current_snr = client.calculate_current_snr()

        client_state["rssi_history"].append(current_rssi)
        client_state["snr_history"].append(current_snr)
        rssi_variance = np.std(client_state["rssi_history"])

        # --- New: Collect End-Term Metrics ---
        self._collect_end_term_metrics(client, current_step)

        # --- Update Interval & Check for Action ---
        ap_load_level = self._get_ap_load_level()
        self._update_adaptive_interval(
            client_state, current_qoe, rssi_variance, ap_load_level
        )

        steps_since_last_check = current_step - client_state["last_check_step"]
        if steps_since_last_check >= client_state["current_interval"]:
            client_state["last_check_step"] = current_step
            self.rrm_action_check(client, current_qoe, current_step)

    def rrm_action_check(self, client, current_qoe, current_step):
        # ... (Same logic as before, omitted for brevity) ...
        # Standard steering logic checks current_qoe < POOR_QOE_THRESHOLD
        if current_qoe < POOR_QOE_THRESHOLD:
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

    def request_active_beacon_report(self, client_to_ask, current_step):
        # ... (Same as before) ...
        if client_to_ask.client_id in self.client_report_cache:
            cached = self.client_report_cache[client_to_ask.client_id]
            if (current_step - cached["timestamp_step"]) < CACHE_WINDOW_STEPS:
                self.analyze_active_report_and_steer(client_to_ask, cached["report"])
                return

        client_report = client_to_ask.receive_beacon_request_and_scan()
        self.client_report_cache[client_to_ask.client_id] = {
            "timestamp_step": current_step,
            "report": client_report,
        }
        self.analyze_active_report_and_steer(client_to_ask, client_report)

    def _get_qoe_prediction(self, client, target_ap_stats):
        # ... (Same Mock ML Model) ...
        potential_snr = target_ap_stats["snr"]
        potential_load = target_ap_stats["airtime_util_pct"]
        client_hysteresis_feature = 1.0 if client.qoe_hysteresis > 1.0 else 0.0
        is_ft_roam_feature = (
            1.0
            if (client.supports_80211r and target_ap_stats["supports_80211r"])
            else 0.0
        )

        features = [
            potential_snr,
            potential_load,
            client_hysteresis_feature,
            is_ft_roam_feature,
        ]
        return self.qoe_model.predict(features)

    def analyze_active_report_and_steer(self, client, client_report):
        # ... (Same steering logic) ...
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
            target_ap = next(
                (ap for ap in self.env.all_aps if ap.ap_id == ap_entry["ap_id"]), None
            )
            target_ap_supports_80211r = (
                target_ap.supports_80211r if target_ap else False
            )

            target_ap_stats = {
                "ap_id": ap_entry["ap_id"],
                "snr": ap_entry["snr"],
                "airtime_util_pct": global_load["airtime_util_pct"],
                "supports_80211r": target_ap_supports_80211r,
            }

            predicted_qoe_score = self._get_qoe_prediction(client, target_ap_stats)
            candidates.append(
                {
                    "ap_id": ap_entry["ap_id"],
                    "predicted_qoe": predicted_qoe_score,
                }
            )

        if not candidates:
            client.clear_roam_memory()
            return

        ranked_list = sorted(candidates, key=lambda x: x["predicted_qoe"], reverse=True)
        acceptance = client.receive_bss_tm_request(ranked_list)

        client_state = self.client_rrm_state.get(client.client_id)
        if not acceptance:
            self.stats_by_persona[client.persona_name]["rejects"] += 1
            if client_state:
                client_state["rejection_count"] += 1
            client.clear_roam_memory()
        else:
            if client_state:
                client_state["rejection_count"] = 0

    def run_passive_inference_and_steer(self, client, current_step, band_steer=False):
        # ... (Same passive logic) ...
        if band_steer:
            self.disconnect_client(client)
            client.find_best_ap_and_associate()
            return

        metrics = client.generate_passive_metrics()
        hidden_node_suspicion = 0
        if metrics["downlink_mcs_index"] > (metrics["uplink_mcs_index"] + 2):
            hidden_node_suspicion += 1
        if metrics["uplink_retry_pct"] > (metrics["downlink_retry_pct"] + 20):
            hidden_node_suspicion += 1
        if metrics["ack_variance_ms"] > 1.5:
            hidden_node_suspicion += 1

        if hidden_node_suspicion >= 2:
            self.disconnect_client(client)
            client.find_best_ap_and_associate()
        else:
            client.clear_roam_memory()

    def get_steering_stats(self):
        return {
            "attempts": self.steer_attempts,
            "successes": self.steer_successes,
            "qoe_deltas": self.qoe_deltas,
            "by_persona": self.stats_by_persona,
        }

    def get_advanced_telemetry(self):
        """Returns the accumulated End-Term telemetry."""
        return {"transport_logs": self.transport_logs, "rtt_logs": self.rtt_logs}
