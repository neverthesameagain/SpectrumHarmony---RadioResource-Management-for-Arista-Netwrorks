import math
import random

# --- Physics & Config (Borrowed from your dataset generator) ---
RSSI_MIN, RSSI_MAX = -70, -30
RADIUS_M = 10.0

# --- 1. CLIENT PERSONAS CONFIG ---
CLIENT_PERSONAS = {
    "default": {
        "name": "Default (Balanced)",
        "supports_80211v": True, # Supports 802.11k/v
        "qoe_hysteresis": 0.5,
    },
    "sticky_laptop": {
        "name": "Sticky Laptop (Corporate OUI)",
        "supports_80211v": True,
        "qoe_hysteresis": 1.5,
    },
    "eager_phone": {
        "name": "Eager Phone (Modern OS)",
        "supports_80211v": True,
        "qoe_hysteresis": 0.1,
    },
    "legacy_device": {
        "name": "Legacy Device (No 11v)",
        "supports_80211v": False, # Does not support 802.11k/v
        "qoe_hysteresis": 99.9,
    }
}


def calculate_rssi(x1, y1, x2, y2):
    """Calculates the RSSI a client at (x1, y1) would see from an AP at (x2, y2)."""
    distance = math.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)
    base = RSSI_MAX - (distance / (RADIUS_M * 2)) * (RSSI_MAX - RSSI_MIN)
    rssi = base + random.uniform(-2, 2)
    return max(-90.0, rssi)


def calculate_qoe(rssi, airtime_util):
    """
    Simplified QoE function based on signal strength and AP congestion.
    Returns a score from 0 to 5.
    """
    s_score = max(0, min(1, (rssi - (-85)) / ((-60) - (-85))))
    l_score = 1 - max(0, min(1, airtime_util / 80.0))  # 80% is "full"
    return 5 * (0.7 * s_score + 0.3 * l_score)


class Environment:
    """
    Holds all "things" and acts as the "central controller"
    storing global state like AP load.
    """

    def __init__(self):
        self.all_aps = []
        self.all_clients = []
        self.ap_load_stats = {}
        
        self.steer_attempts = 0
        self.steer_successes = 0
        self.qoe_deltas = []
        
        print("[ENV]: Environment (RRM Controller) created.")

    def register_ap(self, ap):
        self.all_aps.append(ap)
        self.ap_load_stats[ap.ap_id] = {"client_count": 0, "airtime_util_pct": 0.0}
        print(f"[ENV]: Registered {ap.ap_id} at ({ap.x}, {ap.y})")

    def register_client(self, client):
        self.all_clients.append(client)
        print(f"[ENV]: Registered {client.client_id} ({client.persona['name']}) at ({client.x}, {client.y})")

    def client_scan(self, scanning_client):
        """Physics engine: Client asks 'What can I see?'"""
        print(f"[ENV]: {scanning_client.client_id} is performing a scan...")
        scan_results = []
        for ap in self.all_aps:
            rssi = calculate_rssi(scanning_client.x, scanning_client.y, ap.x, ap.y)
            if rssi > -85:
                scan_results.append(
                    {"bssid": ap.bssid, "channel": ap.channel, "rssi": round(rssi, 2), "ap_id": ap.ap_id,}
                )
        return {"report": scan_results}

    def get_ap_load(self, ap_id):
        """Provides the global load data for a given AP."""
        return self.ap_load_stats.get(
            ap_id, {"client_count": 99, "airtime_util_pct": 100.0}
        )

    def handle_roam(self, client, new_ap_id, pre_roam_qoe, steer_type="Active"):
        """
        Handles the client's transition between APs.
        This is now the central logging point for steering success.
        """
        new_ap = next((ap for ap in self.all_aps if ap.ap_id == new_ap_id), None)
        if not new_ap:
            return False

        old_ap = client.connected_ap

        if old_ap:
            old_ap.disconnect_client(client)
            if self.ap_load_stats[old_ap.ap_id]["client_count"] > 0:
                self.ap_load_stats[old_ap.ap_id]["client_count"] -= 1

        new_ap.connect_client(client)
        self.ap_load_stats[new_ap.ap_id]["client_count"] += 1
        
        if old_ap:
            print(f"[ENV]: Client {client.client_id} successfully roamed from {old_ap.ap_id} to {new_ap.ap_id}")
            
            post_roam_qoe = client.calculate_current_qoe()
            qoe_delta = post_roam_qoe - pre_roam_qoe
            self.qoe_deltas.append(qoe_delta)
            
            print(f"[CONTROLLER]: Steer Success! ({steer_type})")
            print(f"[CONTROLLER]: Pre-Roam QoE: {pre_roam_qoe:.2f} -> Post-Roam QoE: {post_roam_qoe:.2f} (Delta: {qoe_delta:+.2f})")
            
        return True
        
    def print_steering_stats(self):
        """Prints the global RRM steering stats."""
        print(f"\n--- RRM Controller Steering Stats ---")
        if self.steer_attempts > 0:
            acceptance_rate = (self.steer_successes / self.steer_attempts) * 100
            avg_qoe_delta = (
                sum(self.qoe_deltas) / len(self.qoe_deltas) if self.qoe_deltas else 0
            )
            print(f"  Total Steer Attempts (Active + Passive): {self.steer_attempts}")
            print(f"  Success/Acceptance Rate: {acceptance_rate:.1f}% ({self.steer_successes}/{self.steer_attempts})")
            print(f"  Avg. QoE Delta (from all steers): {avg_qoe_delta:+.2f}")
        else:
            print("  No steering attempts made.")


class AccessPoint:
    """Represents a virtual Access Point with RRM logic."""
    
    POOR_QOE_THRESHOLD = 2.0 

    def __init__(self, environment, ap_id, x, y, channel):
        self.env = environment
        self.ap_id = ap_id
        self.bssid = f"00:AA:00:00:00:{int(channel):02X}"
        self.x = x
        self.y = y
        self.channel = channel
        self.connected_clients = []
        self.rm_capable = True
        
        self.env.register_ap(self)

    def connect_client(self, client):
        if client not in self.connected_clients:
            self.connected_clients.append(client)
            client.connected_ap = self
            print(f"[{self.ap_id}]: Client {client.client_id} has associated.")

    def disconnect_client(self, client):
        if client in self.connected_clients:
            self.connected_clients.remove(client)
            client.connected_ap = None 
            print(f"[{self.ap_id}]: Client {client.client_id} has disassociated.")

    def rrm_check_client(self, client):
        """
        Main RRM entry point.
        Checks client capabilities and decides which RRM path to take.
        """
        print(f"\n--- RRM Check for {client.client_id} on {self.ap_id} ---")
        if client not in self.connected_clients:
            print(f"[{self.ap_id}]: RRM: Client {client.client_id} not connected.")
            return

        self.env.steer_attempts += 1
        
        if client.persona["supports_80211v"]:
            print(f"[{self.ap_id}]: RRM: Client {client.client_id} supports 802.11k/v. Using ACTIVE probe.")
            self.request_active_beacon_report(client)
        else:
            print(f"[{self.ap_id}]: RRM: Client {client.client_id} is a legacy device. Using PASSIVE inference.")
            self.run_passive_inference_and_steer(client)

    def request_active_beacon_report(self, client_to_ask):
        """Simulates the 802.11k request."""
        print(f"[{self.ap_id}]: Sending 'Beacon Request' to {client_to_ask.client_id}...")
        client_report = client_to_ask.receive_beacon_request_and_scan()
        self.analyze_active_report_and_steer(client_to_ask, client_report)


    def analyze_active_report_and_steer(self, client, client_report):
        """
        (Modified)
        Uses client-view + AP load to craft ranked neighbor lists
        and simulates an 802.11v BSS-TM request.
        """
        print(f"[{self.ap_id}]: RRM: Analyzing (Active) client-view for {client.client_id}...")
        pre_roam_qoe = client.calculate_current_qoe()
        print(f"[{self.ap_id}]: RRM: Client's pre-roam QoE is {pre_roam_qoe:.2f}/5.0")

        candidates = []
        for ap_entry in client_report["report"]:
            if ap_entry["ap_id"] == self.ap_id:
                continue 
            
            ap_id = ap_entry["ap_id"]
            client_view_rssi = ap_entry["rssi"]
            global_load = self.env.get_ap_load(ap_id)
            airtime = global_load["airtime_util_pct"]
            rssi_score = max(0, min(100, (client_view_rssi - (-85)) / ((-60) - (-85)) * 100))
            load_score = max(0, 100 - airtime)
            final_score = (0.7 * rssi_score) + (0.3 * load_score)

            candidates.append(
                {"ap_id": ap_id, "score": final_score, "client_view_rssi": client_view_rssi, "ap_load_airtime": airtime,}
            )

        if not candidates:
            print(f"[{self.ap_id}]: RRM: No viable roaming candidates found for {client.client_id}.")
            return

        ranked_list = sorted(candidates, key=lambda x: x["score"], reverse=True)
        print(f"[{self.ap_id}]: RRM: Crafted ranked neighbor list (Active):")
        for i, c in enumerate(ranked_list):
            print(f"  {i + 1}. {c['ap_id']} (Score: {c['score']:.1f}, RSSI: {c['client_view_rssi']}, Load: {c['ap_load_airtime']}%)")

        print(f"[{self.ap_id}]: RRM: Sending 802.11v BSS-TM suggestion to {client.client_id}...")
        
        acceptance = client.receive_bss_tm_request(ranked_list, pre_roam_qoe)

        if acceptance:
            print(f"[{self.ap_id}]: RRM: Client ACK'd roam. Controller will log success.")
            self.env.steer_successes += 1
        else:
            print(f"[{self.ap_id}]: RRM: Client REJECTED roam.")

    def run_passive_inference_and_steer(self, client):
        """
        Passively "observes" a client's metrics, estimates its QoE,
        and takes legacy steering action if QoE is poor.
        """
        metrics = client.generate_passive_metrics()
        print(f"[{self.ap_id}]: RRM: Passively observed client metrics:")
        print(f"    Uplink MCS Index: {metrics['uplink_mcs_index']} (0=slow, 9=fast)")
        print(f"    Uplink Retry Pct: {metrics['uplink_retry_pct']:.1f}% (High=bad)")
        print(f"    ACK Variance (ms): {metrics['ack_variance_ms']:.2f}ms (High=bad)")

        mcs_score = (metrics['uplink_mcs_index'] / 9.0)
        retry_score = 1.0 - (metrics['uplink_retry_pct'] / 30.0)
        ack_score = 1.0 - (metrics['ack_variance_ms'] / 2.0)
        
        estimated_qoe = (mcs_score * 0.5 + retry_score * 0.25 + ack_score * 0.25) * 5.0
        pre_roam_qoe = client.calculate_current_qoe()
        
        print(f"[{self.ap_id}]: RRM: Client's *actual* QoE is {actual_qoe:.2f}/5.0")
        print(f"[{self.ap_id}]: RRM: AP's *inferred* QoE is {estimated_qoe:.2f}/5.0")

        if estimated_qoe < self.POOR_QOE_THRESHOLD:
            print(f"[{self.ap_id}]: RRM: Inferred QoE is below threshold ({self.POOR_QOE_THRESHOLD}).")
            print(f"[{self.ap_id}]: RRM: Forcing disassociation (legacy steer) to {client.client_id}...")
            
            self.disconnect_client(client)
            
            new_ap = client.find_best_ap_and_associate(pre_roam_qoe)
            
            if new_ap and new_ap != self:
                print(f"[{self.ap_id}]: RRM: Client {client.client_id} successfully moved to {new_ap.ap_id}.")
                self.env.steer_successes += 1
            else:
                print(f"[{self.ap_id}]: RRM: Client {client.client_id} rejoined this AP.")
        else:
            print(f"[{self.ap_id}]: RRM: Inferred QoE is acceptable. No action taken.")


class ClientDevice:
    """Represents a virtual Wi-Fi Client with roaming logic."""

    def __init__(self, environment, client_id, x, y, persona_key="default"):
        self.env = environment
        self.client_id = client_id
        self.x = x
        self.y = y
        self.connected_ap = None
        self.persona = CLIENT_PERSONAS.get(persona_key, CLIENT_PERSONAS["default"])
        self.rm_capable = self.persona["supports_80211v"] 
        self.env.register_client(self)

    def receive_beacon_request_and_scan(self):
        """Simulates 802.11k scan."""
        print(f"[{self.client_id}]: Received 'Beacon Request'. Scanning...")
        scan_results = self.env.client_scan(self)
        print(f"[{self.client_id}]: Scan complete. Sending 'Beacon Report'...")
        return scan_results

    def calculate_current_qoe(self):
        """Calculates this client's current QoE based on its connection."""
        if not self.connected_ap:
            return 0.0
        rssi = calculate_rssi(self.x, self.y, self.connected_ap.x, self.connected_ap.y)
        load_stats = self.env.get_ap_load(self.connected_ap.ap_id)
        airtime = load_stats["airtime_util_pct"]
        return calculate_qoe(rssi, airtime)

    def receive_bss_tm_request(self, ranked_list, pre_roam_qoe):
        """
        Simulates the client's decision logic for an 802.11v request.
        """
        print(f"[{self.client_id}]: Received 802.11v BSS-TM request.")
        
        if not self.rm_capable:
            print(f"[{self.client_id}]: Decision: REJECT. Persona '{self.persona['name']}' does not support 802.11v.")
            return False
        if not ranked_list:
            return False

        best_candidate = ranked_list[0]
        current_qoe = self.calculate_current_qoe() # This is the same as pre_roam_qoe
        potential_rssi = best_candidate["client_view_rssi"]
        potential_load = best_candidate["ap_load_airtime"]
        potential_qoe = calculate_qoe(potential_rssi, potential_load)
        qoe_threshold = self.persona["qoe_hysteresis"]
        
        print(f"[{self.client_id}]: Persona '{self.persona['name']}' checking: Potential QoE ({potential_qoe:.2f}) > Current QoE ({current_qoe:.2f}) + Threshold ({qoe_threshold:.2f})")

        if potential_qoe > (current_qoe + qoe_threshold):
            print(f"[{self.client_id}]: Decision: ACCEPT. Roaming to {best_candidate['ap_id']}.")
            self.env.handle_roam(self, best_candidate['ap_id'], pre_roam_qoe, steer_type="Active 802.11v")
            return True
        else:
            print(f"[{self.client_id}]: Decision: REJECT. New QoE {potential_qoe:.2f} is not significantly better.")
            return False

    def generate_passive_metrics(self):
        """
        Models the client's uplink transmission stats based on its current QoE.
        """
        current_qoe = self.calculate_current_qoe()
        qoe_pct = max(0, min(1, current_qoe / 5.0))
        
        base_mcs = qoe_pct * 9.0
        mcs = int(max(0, min(9, base_mcs + random.uniform(-1, 1))))
        
        base_retry = 1.0; max_retry = 30.0
        retry = max_retry - (qoe_pct * (max_retry - base_retry))
        retry = max(0, min(100, retry + random.uniform(-3, 3)))
        
        base_var = 0.1; max_var = 2.0
        variance = max_var - (qoe_pct * (max_var - base_var))
        variance = max(0.05, variance + random.uniform(-0.1, 0.1))
        
        return {"uplink_mcs_index": mcs, "uplink_retry_pct": retry, "ack_variance_ms": variance}

    def find_best_ap_and_associate(self, pre_roam_qoe):
        """
        Simulates a legacy client's logic after being disconnected.
        """
        print(f"[{self.client_id}]: Disconnected. Scanning for new AP...")
        best_ap = None
        best_qoe = -1.0
        
        scan_results = self.env.client_scan(self)
        
        for ap_entry in scan_results['report']:
            potential_rssi = ap_entry['rssi']
            potential_load = self.env.get_ap_load(ap_entry['ap_id'])['airtime_util_pct']
            potential_qoe = calculate_qoe(potential_rssi, potential_load)
            
            print(f"[{self.client_id}]: ...sees {ap_entry['ap_id']} (Potential QoE: {potential_qoe:.2f})")
            
            if potential_qoe > best_qoe:
                best_qoe = potential_qoe
                best_ap = ap_entry['ap_id']
                
        if best_ap and best_qoe > pre_roam_qoe: # Only move if it's actually better
            print(f"[{self.client_id}]: Found best AP: {best_ap}. Associating...")
            self.env.handle_roam(self, best_ap, pre_roam_qoe, steer_type="Passive Steer")
            return next((ap for ap in self.env.all_aps if ap.ap_id == best_ap), None)
        elif best_ap: # Found an AP, but it's no better (or it's the same one)
             print(f"[{self.client_id}]: Best AP is {best_ap}, but it's not better. Re-associating...")
             self.env.handle_roam(self, best_ap, pre_roam_qoe, steer_type="Passive Steer (Rejoin)")
             return next((ap for ap in self.env.all_aps if ap.ap_id == best_ap), None)
        else:
            print(f"[{self.client_id}]: No APs found in scan!")
            return None


print("==========================================================")
print("== RRM 802.11k/v + Passive Fallback Simulation ==")
print("==========================================================\n")

# 1. Create the World
sim_environment = Environment()

# 2. Create the APs
ap1 = AccessPoint(sim_environment, "AP-1 (Hall)", x=0, y=10, channel=1)
ap2 = AccessPoint(sim_environment, "AP-2 (Office)", x=20, y=10, channel=6)
ap3 = AccessPoint(sim_environment, "AP-3 (Cafe)", x=40, y=10, channel=11)

# 3. Create Clients with different personas
client_eager = ClientDevice(sim_environment, "Client-Eager", x=15, y=10, persona_key="eager_phone")
client_sticky = ClientDevice(sim_environment, "Client-Sticky", x=15, y.gitignore, persona_key="sticky_laptop")
client_legacy = ClientDevice(sim_environment, "Client-Legacy", x=15, y=10, persona_key="legacy_device")


# 4. Set up the Scenario
ap2.connect_client(client_eager)
ap2.connect_client(client_sticky)
ap2.connect_client(client_legacy)

sim_environment.ap_load_stats["AP-1 (Hall)"] = {"client_count": 5, "airtime_util_pct": 20.0}
sim_environment.ap_load_stats["AP-2 (Office)"] = {"client_count": 35, "airtime_util_pct": 90.0}  # <-- VERY BUSY!
sim_environment.ap_load_stats["AP-3 (Cafe)"] = {"client_count": 10, "airtime_util_pct": 30.0}  # <-- Much better

print("\n--- Setup Complete (3 Clients on busy AP-2) ---\n")

# --- RUN THE RRM HEALTH CHECKS ---
ap2.rrm_check_client(client_eager)
ap2.rrm_check_client(client_sticky)
ap2.rrm_check_client(client_legacy)


print("\n\n==========================================================")
print("== Simulation Finished ==")
# --- Print stats from the controller ---
sim_environment.print_steering_stats()
print("==========================================================")
print(f"Final Client Locations:")
print(f"  {client_eager.client_id}:  {client_eager.connected_ap.ap_id if client_eager.connected_ap else 'None'}")
print(f"  {client_sticky.client_id}: {client_sticky.connected_ap.ap_id if client_sticky.connected_ap else 'None'}")
print(f"  {client_legacy.client_id}: {client_legacy.connected_ap.ap_id if client_legacy.connected_ap else 'None'}")
print("==========================================================")
