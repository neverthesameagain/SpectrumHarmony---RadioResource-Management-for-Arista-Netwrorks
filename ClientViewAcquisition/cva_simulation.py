import math
import random

# --- Physics & Config (Borrowed from your dataset generator) ---
RSSI_MIN, RSSI_MAX = -70, -30
RADIUS_M = 10.0


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
    # Normalize signal (0-1)
    s_score = max(0, min(1, (rssi - (-85)) / ((-60) - (-85))))
    # Normalize load (0-1, where 1 is good)
    l_score = 1 - max(0, min(1, airtime_util / 80.0))  # 80% is "full"

    # Weighted average
    return 5 * (0.7 * s_score + 0.3 * l_score)


class Environment:
    """
    Holds all "things" and acts as the "central controller"
    storing global state like AP load.
    """

    def __init__(self):
        self.all_aps = []
        self.all_clients = []
        # NEW: Global state of AP load, managed by the controller
        self.ap_load_stats = {}  # { "AP-1": {"client_count": 10, "airtime_util_pct": 30.0}, ... }
        print("[ENV]: Environment created.")

    def register_ap(self, ap):
        self.all_aps.append(ap)
        # Initialize load
        self.ap_load_stats[ap.ap_id] = {"client_count": 0, "airtime_util_pct": 0.0}
        print(f"[ENV]: Registered {ap.ap_id} at ({ap.x}, {ap.y})")

    def register_client(self, client):
        self.all_clients.append(client)
        print(f"[ENV]: Registered {client.client_id} at ({client.x}, {client.y})")

    def client_scan(self, scanning_client):
        """Physics engine: Client asks 'What can I see?'"""
        print(f"[ENV]: {scanning_client.client_id} is performing a scan...")
        scan_results = []
        for ap in self.all_aps:
            if ap == scanning_client.connected_ap:
                continue
            rssi = calculate_rssi(scanning_client.x, scanning_client.y, ap.x, ap.y)
            if rssi > -85:
                scan_results.append(
                    {
                        "bssid": ap.bssid,
                        "channel": ap.channel,
                        "rssi": round(rssi, 2),
                        "ap_id": ap.ap_id,  # Helper for simulation
                    }
                )
        return {"report": scan_results}

    def get_ap_load(self, ap_id):
        """Provides the global load data for a given AP."""
        return self.ap_load_stats.get(
            ap_id, {"client_count": 99, "airtime_util_pct": 100.0}
        )

    def handle_roam(self, client, new_ap_id):
        """Handles the client's transition between APs."""
        new_ap = next((ap for ap in self.all_aps if ap.ap_id == new_ap_id), None)
        if not new_ap:
            return False

        old_ap = client.connected_ap

        # 1. Disconnect from old AP
        if old_ap:
            old_ap.disconnect_client(client)
            self.ap_load_stats[old_ap.ap_id]["client_count"] -= 1

        # 2. Connect to new AP
        new_ap.connect_client(client)
        self.ap_load_stats[new_ap.ap_id]["client_count"] += 1
        print(
            f"[ENV]: Client {client.client_id} successfully roamed from {old_ap.ap_id} to {new_ap.ap_id}"
        )
        return True


class AccessPoint:
    """Represents a virtual Access Point with RRM logic."""

    def __init__(self, environment, ap_id, x, y, channel):
        self.env = environment
        self.ap_id = ap_id
        self.bssid = f"00:AA:00:00:00:{int(channel):02X}"
        self.x = x
        self.y = y
        self.channel = channel
        self.connected_clients = []
        self.rm_capable = True

        # NEW: Metrics for logging (as per the PDF)
        self.steer_attempts = 0
        self.steer_successes = 0
        self.qoe_deltas = []

        self.env.register_ap(self)

    def connect_client(self, client):
        if client not in self.connected_clients:
            self.connected_clients.append(client)
            client.connected_ap = self
            print(f"[{self.ap_id}]: Client {client.client_id} has associated.")

    def disconnect_client(self, client):
        if client in self.connected_clients:
            self.connected_clients.remove(client)
            print(f"[{self.ap_id}]: Client {client.client_id} has disassociated.")

    def request_beacon_report(self, client_to_ask):
        """Simulates the 802.11k request."""
        if client_to_ask not in self.connected_clients or not client_to_ask.rm_capable:
            print(
                f"[{self.ap_id}]: Cannot send 802.11k request to {client_to_ask.client_id}."
            )
            return

        print(
            f"\n[{self.ap_id}]: Sending 'Beacon Request' to {client_to_ask.client_id}..."
        )
        client_report = client_to_ask.receive_beacon_request_and_scan()

        # ** NEW: Instead of just printing, send to the RRM "brain" **
        self.analyze_report_and_steer(client_to_ask, client_report)

    # ------------------------------------------------------------------
    # --- THIS IS THE FUNCTION YOU REQUESTED ---
    # ------------------------------------------------------------------
    def analyze_report_and_steer(self, client, client_report):
        """
        Uses client-view + AP load to craft ranked neighbor lists
        and simulates an 802.11v BSS-TM request.
        """
        print(f"[{self.ap_id}]: RRM: Analyzing client-view for {client.client_id}...")

        # 1. Get Pre-Roam QoE
        pre_roam_qoe = client.calculate_current_qoe()
        print(f"[{self.ap_id}]: RRM: Client's pre-roam QoE is {pre_roam_qoe:.2f}/5.0")

        # 2. Get "Client-View" (the report) and "AP Load" (from env)
        candidates = []
        for ap_entry in client_report["report"]:
            ap_id = ap_entry["ap_id"]
            client_view_rssi = ap_entry["rssi"]

            # --- Fusing Data Sources ---
            # Get the "AP Load" from the central controller (our env)
            global_load = self.env.get_ap_load(ap_id)
            airtime = global_load["airtime_util_pct"]

            # --- Crafting the Score ---
            # We score based 70% on signal strength (client-view)
            # and 30% on AP load (controller-view).
            rssi_score = max(
                0, min(100, (client_view_rssi - (-85)) / ((-60) - (-85)) * 100)
            )
            load_score = max(0, 100 - airtime)  # 100 is best (0% load)

            final_score = (0.7 * rssi_score) + (0.3 * load_score)

            candidates.append(
                {
                    "ap_id": ap_id,
                    "score": final_score,
                    "client_view_rssi": client_view_rssi,
                    "ap_load_airtime": airtime,
                }
            )

        # 3. --- Craft Ranked Neighbor List ---
        if not candidates:
            print(
                f"[{self.ap_id}]: RRM: No viable roaming candidates found for {client.client_id}."
            )
            return

        ranked_list = sorted(candidates, key=lambda x: x["score"], reverse=True)

        print(f"[{self.ap_id}]: RRM: Crafted ranked neighbor list:")
        for i, c in enumerate(ranked_list):
            print(
                f"  {i + 1}. {c['ap_id']} (Score: {c['score']:.1f}, RSSI: {c['client_view_rssi']}, Load: {c['ap_load_airtime']}%)"
            )

        # 4. --- Simulate 802.11v BSS-TM Request ---
        print(
            f"[{self.ap_id}]: RRM: Sending 802.11v BSS-TM suggestion to {client.client_id}..."
        )
        self.steer_attempts += 1

        # The client makes its own decision and returns True (Accepted) or False (Rejected)
        acceptance = client.receive_bss_tm_request(ranked_list)

        # 5. --- Log Client Acceptance Rate & Post-Roam QoE Deltas ---
        if acceptance:
            self.steer_successes += 1
            post_roam_qoe = client.calculate_current_qoe()
            qoe_delta = post_roam_qoe - pre_roam_qoe
            self.qoe_deltas.append(qoe_delta)

            print(f"[{self.ap_id}]: RRM: Client ACCEPTED roam.")
            print(
                f"[{self.ap_id}]: RRM: Post-roam QoE is {post_roam_qoe:.2f}. Delta: {qoe_delta:+.2f}"
            )
        else:
            print(f"[{self.ap_id}]: RRM: Client REJECTED roam.")

    def print_steering_stats(self):
        print(f"\n--- RRM Steering Stats for {self.ap_id} ---")
        if self.steer_attempts > 0:
            acceptance_rate = (self.steer_successes / self.steer_attempts) * 100
            avg_qoe_delta = (
                sum(self.qoe_deltas) / len(self.qoe_deltas) if self.qoe_deltas else 0
            )
            print(
                f"  Acceptance Rate: {acceptance_rate:.1f}% ({self.steer_successes}/{self.steer_attempts})"
            )
            print(f"  Avg. QoE Delta: {avg_qoe_delta:+.2f}")
        else:
            print("  No steering attempts made.")


class ClientDevice:
    """Represents a virtual Wi-Fi Client with roaming logic."""

    def __init__(self, environment, client_id, x, y):
        self.env = environment
        self.client_id = client_id
        self.x = x
        self.y = y
        self.connected_ap = None
        self.rm_capable = True
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

        # Get current signal
        rssi = calculate_rssi(self.x, self.y, self.connected_ap.x, self.connected_ap.y)
        # Get current AP load
        load_stats = self.env.get_ap_load(self.connected_ap.ap_id)
        airtime = load_stats["airtime_util_pct"]

        return calculate_qoe(rssi, airtime)

    def receive_bss_tm_request(self, ranked_list):
        """
        Simulates the client's decision logic for an 802.11v request.
        """
        print(f"[{self.client_id}]: Received 802.11v BSS-TM request.")

        if not ranked_list:
            return False  # Reject if list is empty

        best_candidate = ranked_list[0]
        current_qoe = self.calculate_current_qoe()

        # Calculate the *potential* QoE with the new AP
        potential_rssi = best_candidate["client_view_rssi"]
        potential_load = best_candidate["ap_load_airtime"]
        potential_qoe = calculate_qoe(potential_rssi, potential_load)

        # --- Client's Roaming Logic (Hysteresis) ---
        # Only roam if the new AP is at least 0.5 QoE points better.
        # This prevents "flapping" between two equally good APs.
        if potential_qoe > (current_qoe + 0.5):
            print(
                f"[{self.client_id}]: Decision: ACCEPT. New QoE {potential_qoe:.2f} > Old QoE {current_qoe:.2f} + 0.5"
            )
            self.env.handle_roam(self, best_candidate["ap_id"])
            return True
        else:
            print(
                f"[{self.client_id}]: Decision: REJECT. New QoE {potential_qoe:.2f} is not significantly better than Old QoE {current_qoe:.2f}."
            )
            return False


# ------------------------------------------------------------------
# --- MAIN SIMULATION SCRIPT ---
# ------------------------------------------------------------------

print("==========================================================")
print("== RRM 802.11k/v Simulation with AP Load & Steering ==")
print("==========================================================\n")

# 1. Create the World
sim_environment = Environment()

# 2. Create the APs
ap1 = AccessPoint(sim_environment, "AP-1 (Hall)", x=0, y=10, channel=1)
ap2 = AccessPoint(sim_environment, "AP-2 (Office)", x=20, y=10, channel=6)
ap3 = AccessPoint(sim_environment, "AP-3 (Cafe)", x=40, y=10, channel=11)

# 3. Create a Client
#    This client is at (x=15, y=10), physically closer to AP-2.
#    BUT, we will make AP-2 very busy, so AP-3 becomes a better choice.
client1 = ClientDevice(sim_environment, "Client-77", x=15, y=10)

# 4. Set up the Scenario
#    Client-77 associates with AP-2 (the closest)
ap2.connect_client(client1)

#    NOW, set the "Global AP Load"
sim_environment.ap_load_stats["AP-1 (Hall)"] = {
    "client_count": 5,
    "airtime_util_pct": 20.0,
}
sim_environment.ap_load_stats["AP-2 (Office)"] = {
    "client_count": 35,
    "airtime_util_pct": 90.0,
}  # <-- VERY BUSY!
sim_environment.ap_load_stats["AP-3 (Cafe)"] = {
    "client_count": 10,
    "airtime_util_pct": 30.0,
}  # <-- Much better

print("\n--- Setup Complete (Client on busy AP-2) ---\n")

# 5. --- RUN THE SIMULATION ---
#    AP-2's RRM engine detects its own high load and poor client QoE,
#    so it triggers an 802.11k request to find a better option for Client-77.
ap2.request_beacon_report(client1)


print("\n\n==========================================================")
print("== Simulation Finished ==")
# Print the final metrics as per the PDF
ap2.print_steering_stats()
print("==========================================================")
