import math
import random
from collections import defaultdict

import pandas as pd
from client_personas import CLIENT_PERSONAS

# --- Physics & Config ---
RSSI_MIN, RSSI_MAX = -70, -30
RADIUS_M = 10.0
POOR_QOE_THRESHOLD = 2.0  # AP will take action if estimated QoE is below this


def calculate_rssi(x1, y1, x2, y2):
    """Calculates the RSSI a client at (x1, y1) would see from an AP at (x2, y2)."""
    distance = math.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)
    base = RSSI_MAX - (distance / (RADIUS_M * 2)) * (RSSI_MAX - RSSI_MIN)
    rssi = base + random.uniform(-2, 2)
    return max(-90.0, rssi)


def calculate_qoe(rssi, airtime_util):
    """Simplified QoE function based on signal strength and AP congestion."""
    s_score = max(0, min(1, (rssi - (-85)) / ((-60) - (-85))))
    l_score = 1 - max(0, min(1, airtime_util / 80.0))
    return 5 * (0.7 * s_score + 0.3 * l_score)


class Environment:
    """
    Holds all "things" and acts as the "world".
    It only provides physics and AP load state.
    """

    def __init__(self):
        self.all_aps = []
        self.all_clients = []
        self.ap_load_stats = {}
        print("[ENV]: Environment (Physics + AP State) created.")

    def register_ap(self, ap):
        self.all_aps.append(ap)
        self.ap_load_stats[ap.ap_id] = {"client_count": 0, "airtime_util_pct": 0.0}
        print(f"[ENV]: Registered {ap.ap_id} at ({ap.x}, {ap.y})")

    def register_client(self, client):
        self.all_clients.append(client)
        print(
            f"[ENV]: Registered {client.client_id} ({client.persona_name}) at ({client.x}, {client.y})"
        )

    def client_scan(self, scanning_client):
        """Physics engine: Client asks 'What can I see?'"""
        scan_results = []
        for ap in self.all_aps:
            rssi = calculate_rssi(scanning_client.x, scanning_client.y, ap.x, ap.y)
            if rssi > -85:
                scan_results.append(
                    {
                        "bssid": ap.bssid,
                        "channel": ap.channel,
                        "rssi": round(rssi, 2),
                        "ap_id": ap.ap_id,
                    }
                )
        return {"report": scan_results}

    def get_ap_load(self, ap_id):
        """Provides the global load data for a given AP."""
        return self.ap_load_stats.get(
            ap_id, {"client_count": 99, "airtime_util_pct": 100.0}
        )

    def update_ap_load(self, ap_id, client_count_delta, airtime_delta):
        """Updates the load stats for a given AP."""
        if ap_id in self.ap_load_stats:
            self.ap_load_stats[ap_id]["client_count"] += client_count_delta
            self.ap_load_stats[ap_id]["airtime_util_pct"] += airtime_delta
            self.ap_load_stats[ap_id]["airtime_util_pct"] = max(
                0, min(100, self.ap_load_stats[ap_id]["airtime_util_pct"])
            )

    def handle_roam(self, client, new_ap_id):
        """
        Handles only the *state change* of a client moving.
        All logging is now done by the APs.
        """
        new_ap = next((ap for ap in self.all_aps if ap.ap_id == new_ap_id), None)
        if not new_ap:
            return False

        old_ap = client.connected_ap

        if old_ap:
            old_ap.disconnect_client(client)
            self.update_ap_load(old_ap.ap_id, -1, -1.5)  # Simulating client leaving

        # The new AP's `connect_client` function will handle the rest
        new_ap.connect_client(client)
        self.update_ap_load(new_ap.ap_id, +1, +1.5)  # Simulating client joining

        if old_ap:
            print(
                f"[ENV]: Client {client.client_id} state moved from {old_ap.ap_id} to {new_ap.ap_id}"
            )

        return True


class AccessPoint:
    """Represents a virtual Access Point with decentralized RRM logic."""

    def __init__(self, environment, ap_row):
        self.env = environment
        self.ap_id = ap_row["ap_id"]
        self.bssid = (
            f"00:AA:00:00:{int(ap_row['channel']):02X}:{random.randint(0, 99):02X}"
        )
        self.x = ap_row["x"]
        self.y = ap_row["y"]
        self.channel = ap_row["channel"]
        self.connected_clients = []

        # Tracks stats for clients *originating* from this AP
        self.steer_attempts = 0
        self.steer_successes = 0

        # Tracks deltas for clients *arriving* at this AP
        self.qoe_deltas = []

        # For the "Acceptance Matrix" deliverable
        self.stats_by_persona = defaultdict(
            lambda: {"attempts": 0, "success": 0, "rejects": 0}
        )

        self.env.register_ap(self)

    def connect_client(self, client):
        """Calculates Post-Roam QoE Delta."""
        if client in self.connected_clients:
            return

        self.connected_clients.append(client)
        client.connected_ap = self

        post_roam_qoe = client.calculate_current_qoe()

        if client.last_seen_ap_id and client.last_seen_ap_id != self.ap_id:
            pre_roam_qoe = client.last_seen_qoe
            qoe_delta = post_roam_qoe - pre_roam_qoe
            self.qoe_deltas.append(qoe_delta)

            print(
                f"[{self.ap_id}]: Client {client.client_id} associated (roam complete)."
            )
            print(f"[{self.ap_id}]: RRM: Logging Post-Roam QoE Delta: {qoe_delta:+.2f}")

            old_ap = next(
                (ap for ap in self.env.all_aps if ap.ap_id == client.last_seen_ap_id),
                None,
            )
            if old_ap:
                old_ap.log_steer_success(client.persona_name)
        else:
            print(
                f"[{self.ap_id}]: Client {client.client_id} associated (fresh connect). QoE: {post_roam_qoe:.2f}"
            )

        client.last_seen_ap_id = None
        client.last_seen_qoe = 0.0

    def disconnect_client(self, client):
        if client in self.connected_clients:
            self.connected_clients.remove(client)
            client.connected_ap = None
            print(f"[{self.ap_id}]: Client {client.client_id} has disassociated.")

    def log_steer_success(self, persona_name):
        """Called by the *new* AP to tell this *old* AP the steer worked."""
        self.steer_successes += 1
        self.stats_by_persona[persona_name]["success"] += 1

    def rrm_check_client(self, client):
        """Main RRM entry point."""
        print(f"\n--- RRM Check for {client.client_id} on {self.ap_id} ---")
        if client not in self.connected_clients:
            print(f"[{self.ap_id}]: RRM: Client {client.client_id} not connected.")
            return

        self.steer_attempts += 1
        self.stats_by_persona[client.persona_name]["attempts"] += 1

        client.last_seen_qoe = client.calculate_current_qoe()
        client.last_seen_ap_id = self.ap_id

        if client.supports_80211v:
            # print(f"[{self.ap_id}]: RRM: Client {client.client_id} supports 802.11k/v. Using ACTIVE probe.")
            self.request_active_beacon_report(client)
        else:
            # print(f"[{self.ap_id}]: RRM: Client {client.client_id} is a legacy device. Using PASSIVE inference.")
            self.run_passive_inference_and_steer(client)

    def request_active_beacon_report(self, client_to_ask):
        """Simulates the 802.11k request."""
        # print(f"[{self.ap_id}]: Sending 'Beacon Request' to {client_to_ask.client_id}...")
        client_report = client_to_ask.receive_beacon_request_and_scan()
        self.analyze_active_report_and_steer(client_to_ask, client_report)

    def analyze_active_report_and_steer(self, client, client_report):
        """Analyzes 802.11k report and sends 802.11v steer command."""
        # print(f"[{self.ap_id}]: RRM: Analyzing (Active) client-view for {client.client_id}...")
        # print(f"[{self.ap_id}]: RRM: Client's pre-roam QoE is {client.last_seen_qoe:.2f}/5.0")

        candidates = []
        for ap_entry in client_report["report"]:
            if ap_entry["ap_id"] == self.ap_id:
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
            # print(f"[{self.ap_id}]: RRM: No viable roaming candidates found.")
            client.clear_roam_memory()
            return

        ranked_list = sorted(candidates, key=lambda x: x["score"], reverse=True)
        # print(f"[{self.ap_id}]: RRM: Crafted ranked neighbor list (Active):")
        # for i, c in enumerate(ranked_list):
        #     print(f"  {i + 1}. {c['ap_id']} (Score: {c['score']:.1f})")

        # print(f"[{self.ap_id}]: RRM: Sending 802.11v BSS-TM suggestion to {client.client_id}...")
        acceptance = client.receive_bss_tm_request(ranked_list)

        if not acceptance:
            # print(f"[{self.ap_id}]: RRM: Client REJECTED roam.")
            self.stats_by_persona[client.persona_name]["rejects"] += 1
            client.clear_roam_memory()

    def run_passive_inference_and_steer(self, client):
        """Passively infers QoE and forces disassociation."""
        metrics = client.generate_passive_metrics()
        # print(f"[{self.ap_id}]: RRM: Passively observed client metrics (MCS: {metrics['uplink_mcs_index']}, Retry: {metrics['uplink_retry_pct']:.1f}%)")

        mcs_score = metrics["uplink_mcs_index"] / 9.0
        retry_score = 1.0 - (metrics["uplink_retry_pct"] / 30.0)
        ack_score = 1.0 - (metrics["ack_variance_ms"] / 2.0)
        estimated_qoe = (mcs_score * 0.5 + retry_score * 0.25 + ack_score * 0.25) * 5.0

        actual_qoe = client.last_seen_qoe
        # print(f"[{self.ap_id}]: RRM: Client's *actual* QoE is {actual_qoe:.2f}/5.0")
        # print(f"[{self.ap_id}]: RRM: AP's *inferred* QoE is {estimated_qoe:.2f}/5.0")

        if estimated_qoe < POOR_QOE_THRESHOLD:
            # print(f"[{self.ap_id}]: RRM: Inferred QoE is below threshold. Forcing disassociation...")
            self.disconnect_client(client)
            client.find_best_ap_and_associate()
        else:
            # print(f"[{self.ap_id}]: RRM: Inferred QoE is acceptable. No action taken.")
            client.clear_roam_memory()

    def get_steering_stats(self):
        """Returns this AP's stats for aggregation."""
        return {
            "attempts": self.steer_attempts,
            "successes": self.steer_successes,
            "qoe_deltas": self.qoe_deltas,
            "by_persona": self.stats_by_persona,
        }


class ClientDevice:
    """Represents a virtual Wi-Fi Client with roaming logic."""

    def __init__(self, environment, client_row):
        self.env = environment
        self.client_id = client_row["client_id"]

        # Get details from the full persona dictionary
        self.persona_key = client_row["persona_key"]
        self.persona = CLIENT_PERSONAS.get(
            self.persona_key, CLIENT_PERSONAS["win7_laptop"]
        )  # Fallback
        self.persona_name = self.persona["name"]

        # Get details directly from the CSV row
        self.oui = client_row["oui"]
        self.os_class = client_row["os_class"]
        self.supports_80211v = client_row["supports_80211v"]
        self.qoe_hysteresis = client_row["qoe_hysteresis"]

        self.x = client_row["x"]
        self.y = client_row["y"]
        self.connected_ap = None

        self.last_seen_ap_id = None
        self.last_seen_qoe = 0.0

        self.env.register_client(self)

    def clear_roam_memory(self):
        """Clears the client's pre-roam state if a steer is aborted."""
        self.last_seen_ap_id = None
        self.last_seen_qoe = 0.0

    def receive_beacon_request_and_scan(self):
        """Simulates 802.11k scan."""
        # print(f"[{self.client_id}]: Received 'Beacon Request'. Scanning...")
        scan_results = self.env.client_scan(self)
        # print(f"[{self.client_id}]: Scan complete. Sending 'Beacon Report'...")
        return scan_results

    def calculate_current_qoe(self):
        """Calculates this client's current QoE based on its connection."""
        if not self.connected_ap:
            return 0.0
        rssi = calculate_rssi(self.x, self.y, self.connected_ap.x, self.connected_ap.y)
        load_stats = self.env.get_ap_load(self.connected_ap.ap_id)
        airtime = load_stats["airtime_util_pct"]
        return calculate_qoe(rssi, airtime)

    def receive_bss_tm_request(self, ranked_list):
        """Simulates the client's decision logic for an 802.11v request."""
        # print(f"[{self.client_id}]: Received 802.11v BSS-TM request.")

        if not self.supports_80211v:
            # print(f"[{self.client_id}]: Decision: REJECT. Persona '{self.persona_name}' does not support 802.11v.")
            return False
        if not ranked_list:
            return False

        best_candidate = ranked_list[0]
        current_qoe = self.last_seen_qoe
        potential_rssi = best_candidate["client_view_rssi"]
        potential_load = best_candidate["ap_load_airtime"]
        potential_qoe = calculate_qoe(potential_rssi, potential_load)
        qoe_threshold = self.qoe_hysteresis

        # print(f"[{self.client_id}]: Persona '{self.persona_name}' checking: Potential QoE ({potential_qoe:.2f}) > Current QoE ({current_qoe:.2f}) + Threshold ({qoe_threshold:.2f})")

        if potential_qoe > (current_qoe + qoe_threshold):
            # print(f"[{self.client_id}]: Decision: ACCEPT. Roaming to {best_candidate['ap_id']}.")
            self.env.handle_roam(self, best_candidate["ap_id"])
            return True
        else:
            # print(f"[{self.client_id}]: Decision: REJECT. New QoE {potential_qoe:.2f} is not significantly better.")
            return False

    def generate_passive_metrics(self):
        """Models the client's uplink transmission stats based on its current QoE."""
        current_qoe = self.calculate_current_qoe()
        qoe_pct = max(0, min(1, current_qoe / 5.0))

        base_mcs = qoe_pct * 9.0
        mcs = int(max(0, min(9, base_mcs + random.uniform(-1, 1))))
        base_retry = 1.0
        max_retry = 30.0
        retry = max_retry - (qoe_pct * (max_retry - base_retry))
        retry = max(0, min(100, retry + random.uniform(-3, 3)))
        base_var = 0.1
        max_var = 2.0
        variance = max_var - (qoe_pct * (max_var - base_var))
        variance = max(0.05, variance + random.uniform(-0.1, 0.1))

        return {
            "uplink_mcs_index": mcs,
            "uplink_retry_pct": retry,
            "ack_variance_ms": variance,
        }

    def find_best_ap_and_associate(self):
        """Simulates a legacy client's logic after being disconnected."""
        # print(f"[{self.client_id}]: Disconnected. Scanning for new AP...")
        best_ap_id = None
        best_qoe = -1.0

        current_qoe = self.last_seen_qoe
        scan_results = self.env.client_scan(self)

        for ap_entry in scan_results["report"]:
            potential_rssi = ap_entry["rssi"]
            potential_load = self.env.get_ap_load(ap_entry["ap_id"])["airtime_util_pct"]
            potential_qoe = calculate_qoe(potential_rssi, potential_load)

            # print(f"[{self.client_id}]: ...sees {ap_entry['ap_id']} (Potential QoE: {potential_qoe:.2f})")

            if potential_qoe > best_qoe:
                best_qoe = potential_qoe
                best_ap_id = ap_entry["ap_id"]

        if best_ap_id and (best_qoe > current_qoe or self.last_seen_ap_id is None):
            # print(f"[{self.client_id}]: Found best AP: {best_ap_id}. Associating...")
            self.env.handle_roam(self, best_ap_id)
        elif best_ap_id:  # Found an AP, but it's no better
            # print(f"[{self.client_id}]: Best AP is {best_ap_id}, but it's not better. Re-associating...")
            self.env.handle_roam(self, best_ap_id)
        else:
            # print(f"[{self.client_id}]: No APs found in scan!")
            self.clear_roam_memory()


def generate_acceptance_matrix_report(all_aps):
    """
    Generates the "Acceptance metrics by device class"
    deliverable by aggregating stats from all APs.
    """
    total_stats = defaultdict(lambda: {"attempts": 0, "success": 0, "rejects": 0})
    all_qoe_deltas = []

    for ap in all_aps:
        ap_stats = ap.get_steering_stats()
        all_qoe_deltas.extend(ap_stats["qoe_deltas"])
        for persona_name, metrics in ap_stats["by_persona"].items():
            total_stats[persona_name]["attempts"] += metrics["attempts"]
            total_stats[persona_name]["success"] += metrics["success"]
            total_stats[persona_name]["rejects"] += metrics["rejects"]

    # --- Start of Markdown Report ---
    report_lines = []
    report_lines.append("# Mid-Term Deliverable: Acceptance Metrics by Device Class")
    report_lines.append(
        f"\nThis report details the effectiveness of RRM steering actions across a simulated environment of **{len(all_aps)} APs** and **{len(sim_environment.all_clients)} clients**."
    )

    # --- Overall KPI Summary ---
    total_attempts = sum(stats["attempts"] for stats in total_stats.values())
    total_successes = sum(stats["success"] for stats in total_stats.values())
    total_rejects = sum(stats["rejects"] for stats in total_stats.values())
    overall_acceptance_rate = (
        (total_successes / total_attempts * 100) if total_attempts > 0 else 0
    )
    avg_qoe_delta = (sum(all_qoe_deltas) / len(all_qoe_deltas)) if all_qoe_deltas else 0

    report_lines.append("\n## Overall RRM KPI Summary")
    report_lines.append(f"- **Total Steering Attempts:** {total_attempts}")
    report_lines.append(f"- **Total Successful Steers:** {total_successes}")
    report_lines.append(
        f"- **Overall Acceptance Rate:** **{overall_acceptance_rate:.1f}%**"
    )
    report_lines.append(
        f"- **Average Post-Roam QoE Delta:** **{avg_qoe_delta:+.2f} points**"
    )

    report_lines.append("\n## Steering Success Matrix (by Device Class)\n")
    report_lines.append(
        "| Device Class (Persona) | OUI | OS Class | 802.11k/v Capable? | Steer Attempts | Steer Successes | Steer Rejects | Acceptance Rate |"
    )
    report_lines.append(
        "| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: |"
    )

    # Iterate over the full persona dictionary to include all device types
    for persona_key, persona_details in CLIENT_PERSONAS.items():
        name = persona_details["name"]
        stats = total_stats[name]  # Get stats for this persona

        attempts = stats["attempts"]
        successes = stats["success"]
        rejects = stats["rejects"]

        if attempts > 0:
            acceptance_rate = (successes / attempts) * 100
            acceptance_rate_str = f"{acceptance_rate:.1f}%"
        else:
            acceptance_rate_str = "N/A"

        capable_str = "✅ Yes" if persona_details["supports_80211v"] else "❌ No"

        report_lines.append(
            f"| {name} | `{persona_details['oui']}` | {persona_details['os_class']} | {capable_str} | {attempts} | {successes} | {rejects} | **{acceptance_rate_str}** |"
        )

    return "\n".join(report_lines)


# ------------------------------------------------------------------
# --- MAIN SIMULATION SCRIPT ---
# ------------------------------------------------------------------

print("==========================================================")
print("== Full-Scale Decentralized RRM Simulation ==")
print("==========================================================\n")

# 1. Create the World
sim_environment = Environment()

# 2. Load APs and Clients from CSV files
try:
    ap_df = pd.read_csv("synthetic_ap_layout.csv")
    client_df = pd.read_csv("synthetic_client_population.csv")
except FileNotFoundError:
    print("ERROR: CSV files not found.")
    print("Please run the `persona_generator.py` script first to generate:")
    print("  - synthetic_ap_layout.csv")
    print("  - synthetic_client_population.csv")
    exit()

print(f"Loading {len(ap_df)} APs and {len(client_df)} clients from CSVs...")

# Instantiate all APs
all_aps = [AccessPoint(sim_environment, row) for _, row in ap_df.iterrows()]
# Instantiate all Clients
all_clients = [ClientDevice(sim_environment, row) for _, row in client_df.iterrows()]

print("\n--- Phase 1: Initial Client Association ---")
# Set a random initial load for all APs
for ap in all_aps:
    sim_environment.ap_load_stats[ap.ap_id]["airtime_util_pct"] = random.uniform(
        5.0, 15.0
    )

# All clients scan and connect to their best AP
for client in all_clients:
    client.find_best_ap_and_associate()

print("\n--- Phase 1 Complete ---")
print("Initial AP Load Distribution:")
for ap in all_aps:
    load = sim_environment.get_ap_load(ap.ap_id)
    print(
        f"  {ap.ap_id}: {load['client_count']} clients (Airtime: {load['airtime_util_pct']:.1f}%)"
    )


print("\n--- Phase 2: Simulating High-Load Stress & RRM Checks ---")
# Artificially create a "stress" scenario
# Find the 3 most populated APs and make them overloaded
ap_by_clients = sorted(
    all_aps,
    key=lambda ap: sim_environment.get_ap_load(ap.ap_id)["client_count"],
    reverse=True,
)
for i in range(min(3, len(ap_by_clients))):
    ap = ap_by_clients[i]
    sim_environment.ap_load_stats[ap.ap_id]["airtime_util_pct"] = 90.0  # <-- STRESS!
    print(f"[ENV]: STRESS: Setting {ap.ap_id} airtime to 90%")


print("\n--- Running RRM Checks on all APs... ---")
# Loop through all APs and have them check their clients
for ap in all_aps:
    # We must iterate over a *copy* of the list,
    # because the list will change during iteration as clients roam.
    clients_to_check = list(ap.connected_clients)

    print(f"--- RRM: {ap.ap_id} checking its {len(clients_to_check)} clients... ---")
    for client in clients_to_check:
        ap.rrm_check_client(client)


print("\n\n==========================================================")
print("== Simulation Finished ==")
print("==========================================================\n")
print("Final AP Load Distribution:")
for ap in all_aps:
    load = sim_environment.get_ap_load(ap.ap_id)
    print(
        f"  {ap.ap_id}: {load['client_count']} clients (Airtime: {load['airtime_util_pct']:.1f}%)"
    )
print("\n==========================================================")

# --- GENERATE DELIVERABLES ---
acceptance_report_markdown = generate_acceptance_matrix_report(all_aps)

# --- Save acceptance_metrics_report.md ---
with open("acceptance_metrics_report.md", "w") as f:
    f.write(acceptance_report_markdown)
print("\n✅ Successfully generated 'acceptance_metrics_report.md'")

# --- Save telemetry_schema.md ---
# This is the static design document.
telemetry_schema_content = """
# RRM+ Telemetry Schema (Mid-Term Deliverable)

This document defines the telemetry schema for the "Client-View Acquisition" phase, as required by the Arista RRM-Plus problem statement. The schema is divided into three main data tables/streams.

## 1. `rrm_steering_events`

This is the primary event log used to track all RRM steering actions (both active and passive) and their outcomes.

| Field Name | Data Type | Units | Description |
| :--- | :--- | :--- | :--- |
| `timestamp` | `Timestamp` | `ISO 8601` | The UTC timestamp when the steering event was *initiated*. |
| `client_id_hash` | `String` | `SHA-256` | Hashed client MAC address to ensure privacy. |
| `client_oui` | `String` | `Hex` | The OUI (first 3 bytes) of the client MAC, for device classification. |
| `client_os_class` | `String` | `Enum` | The inferred OS of the client (e.g., "iOS", "Windows", "IoT/Legacy"). |
| `origin_ap_id` | `String` | - | The ID/BSSID of the AP *initiating* the steer (the "old" AP). |
| `target_ap_id` | `String` | - | The ID/BSSID of the AP the client was *steered to*. |
| `steer_type` | `String` | `Enum` | The method used: `ACTIVE_802_11V` or `PASSIVE_DISASSOC`. |
| `steer_status` | `String` | `Enum` | The outcome: `SUCCESS` (roamed to target), `REJECT` (client refused 802.11v), `REJOIN` (client rejoined old AP). |
| `pre_roam_qoe` | `Float` | `0.0-5.0` | The client's calculated QoE *before* the steering attempt. |
| `post_roam_qoe` | `Float` | `0.0-5.0` | The client's QoE on the *new* AP, logged upon successful association. |
| `qoe_delta` | `Float` | `+/- 5.0` | The calculated `post_roam_qoe - pre_roam_qoe`. |

## 2. `client_view_reports` (Active 802.11k Data)

This table stores the raw "client-view" data received from 802.11k-capable clients.

| Field Name | Data Type | Units | Description |
| :--- | :--- | :--- | :--- |
| `timestamp` | `Timestamp` | `ISO 8601` | The UTC timestamp when the report was *received* by the AP. |
| `reporting_client_hash` | `String` | `SHA-256` | The client that sent this 802.11k report. |
| `reporting_ap_id` | `String` | - | The AP that *requested* and received this report. |
| `neighbor_bssid` | `String` | `MAC` | The BSSID of the neighbor AP the client "saw". |
| `neighbor_rssi` | `Float` | `dBm` | The signal strength (RSSI) *from the client's perspective*. |
| `neighbor_snr` | `Float` | `dB` | The signal-to-noise ratio (SNR) *from the client's perspective*. |
| `neighbor_channel` | `Integer` | - | The channel of the neighbor AP. |

## 3. `passive_inference_logs` (Passive Data)

This table stores the periodic, passively-observed metrics for all connected clients, used by the RRM for inference.

| Field Name | Data Type | Units | Description |
| :--- | :--- | :--- | :--- |
| `timestamp` | `Timestamp` | `ISO 8601` | The UTC timestamp of the observation. |
| `client_id_hash` | `String` | `SHA-256` | The client being observed. |
| `connected_ap_id` | `String` | - | The AP the client is connected to. |
| `uplink_mcs_index` | `Integer` | `0-11` | (Inferred) The uplink MCS index used by the client. |
| `uplink_retry_pct` | `Float` | `%` | (Inferred) The percentage of uplink frames from this client with the retry bit set. |
| `ack_variance_ms` | `Float` | `ms` | (Insferred) The calculated jitter/variance in the client's ACK frame responses. |
| `inferred_qoe` | `Float` | `0.0-5.0` | The AP's *estimated* QoE for the client based on these metrics. |
"""

with open("telemetry_schema.md", "w") as f:
    f.write(telemetry_schema_content)

print("\n✅ Successfully generated 'telemetry_schema.md'")
