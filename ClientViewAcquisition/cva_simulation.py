import math
import random

# --- Physics & Config (Borrowed from rrmplus simulation generator) ---
RSSI_MIN, RSSI_MAX = -70, -30
RADIUS_M = 10.0


def calculate_rssi(x1, y1, x2, y2):
    """
    A simplified physics function from rrmplus.
    Calculates the RSSI a client at (x1, y1) would
    see from an AP at (x2, y2).
    """
    distance = math.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)

    # Simple model: 0m = -30 dBm, 20m = -70 dBm
    base = RSSI_MAX - (distance / (RADIUS_M * 2)) * (RSSI_MAX - RSSI_MIN)

    # Add some random noise
    rssi = base + random.uniform(-2, 2)
    return max(-90.0, rssi)  # Don't let signal be weaker than -90


class Environment:
    """
    Holds all the "things" in the simulation.
    It's the "world" that our objects live in.
    """

    def __init__(self):
        self.all_aps = []
        self.all_clients = []
        print("[ENV]: Environment created.")

    def register_ap(self, ap):
        self.all_aps.append(ap)
        print(f"[ENV]: Registered {ap.ap_id} at ({ap.x}, {ap.y})")

    def register_client(self, client):
        self.all_clients.append(client)
        print(f"[ENV]: Registered {client.client_id} at ({client.x}, {client.y})")

    def client_scan(self, scanning_client):
        """
        This is the core "physics" simulation.
        The client asks the environment "What can I see?"
        """
        print(f"[ENV]: {scanning_client.client_id} is performing a scan...")
        scan_results = []

        for ap in self.all_aps:
            # The client can't scan for itself on its own channel
            if ap == scanning_client.connected_ap:
                continue

            # Calculate the RSSI from the client's perspective
            rssi = calculate_rssi(scanning_client.x, scanning_client.y, ap.x, ap.y)

            # Only report APs with a usable signal
            if rssi > -85:
                scan_results.append(
                    {"bssid": ap.bssid, "channel": ap.channel, "rssi": round(rssi, 2)}
                )

        return {"report": scan_results}


class AccessPoint:
    """
    Represents a virtual Access Point.
    """

    def __init__(self, environment, ap_id, x, y, channel):
        self.env = environment
        self.ap_id = ap_id
        self.bssid = f"00:AA:00:00:00:{int(channel):02X}"
        self.x = x
        self.y = y
        self.channel = channel
        self.connected_clients = []

        # --- Abstracted Step 1: AP advertises its 802.11k capability ---
        self.rm_capable = True
        self.env.register_ap(self)

    def connect_client(self, client):
        self.connected_clients.append(client)
        client.connected_ap = self
        print(f"[{self.ap_id}]: Client {client.client_id} has associated.")

    def request_beacon_report(self, client_to_ask):
        """
        This is the "AP-initiated" 802.11k request.
        """
        if client_to_ask not in self.connected_clients:
            print(
                f"[{self.ap_id}]: ERROR: Client {client_to_ask.client_id} is not connected to me."
            )
            return

        if not client_to_ask.rm_capable:
            print(
                f"[{self.ap_id}]: NOTE: Client {client_to_ask.client_id} does not support 802.11k."
            )
            return

        # --- Abstracted Step 2: AP crafts & sends Beacon Request ---
        print(
            f"\n[{self.ap_id}]: Sending 'Beacon Request' to {client_to_ask.client_id}..."
        )

        # This function call *is* the simulated protocol.
        # It triggers the client's scanning behavior.
        client_report = client_to_ask.receive_beacon_request_and_scan()

        # --- Abstracted Step 5: AP parses and uses the data ---
        print(
            f"[{self.ap_id}]: SUCCESS! Received 'Beacon Report' from {client_to_ask.client_id}:"
        )
        print("----------------------------------------------------------")
        if client_report["report"]:
            for entry in client_report["report"]:
                print(
                    f"  -> Sees BSSID {entry['bssid']} on Ch {entry['channel']} at {entry['rssi']} dBm"
                )
        else:
            print("  -> Client reported seeing no other APs.")
        print("----------------------------------------------------------")


class ClientDevice:
    """
    Represents a virtual Wi-Fi Client.
    """

    def __init__(self, environment, client_id, x, y):
        self.env = environment
        self.client_id = client_id
        self.x = x
        self.y = y
        self.connected_ap = None

        # --- Abstracted Step 1: Client advertises 802.11k capability ---
        self.rm_capable = True
        self.env.register_client(self)

    def receive_beacon_request_and_scan(self):
        """
        This simulates the client's 802.11k logic.
        """
        # --- Abstracted Step 3: Client receives request & scans ---
        print(
            f"[{self.client_id}]: Received 'Beacon Request' from {self.connected_ap.ap_id}."
        )
        print(f"[{self.client_id}]: Pausing data, starting environment scan...")

        # Ask the environment "what can I see?"
        scan_results = self.env.client_scan(self)

        print(
            f"[{self.client_id}]: Scan complete. Found {len(scan_results['report'])} APs."
        )

        # --- Abstracted Step 4: Client crafts & sends Beacon Report ---
        print(f"[{self.client_id}]: Sending 'Beacon Report' back to AP.")
        return scan_results


# ------------------------------------------------------------------
# --- MAIN SIMULATION SCRIPT ---
# ------------------------------------------------------------------

print("==========================================================")
print("== Starting RRM 802.11k Entity-Based Simulation ==")
print("==========================================================\n")

# 1. Create the "World"
sim_environment = Environment()

# 2. Create the APs (using AP layout from your script)
ap1 = AccessPoint(sim_environment, "AP-1 (Hall)", x=0, y=10, channel=1)
ap2 = AccessPoint(sim_environment, "AP-2 (Office)", x=20, y=10, channel=6)
ap3 = AccessPoint(sim_environment, "AP-3 (Cafe)", x=40, y=10, channel=11)

# 3. Create a Client
#    This client is at (x=12, y=10), so it's physically
#    closest to AP-1 but should also get a decent signal from AP-2.
client1 = ClientDevice(sim_environment, "Client-77", x=12, y=10)

print("\n--- Setup Complete ---\n")

# 4. Associate the Client
ap1.connect_client(client1)

# 5. --- RUN THE SIMULATION (Trigger the 802.11k event) ---
#    AP-1's RRM engine decides it needs the "client-view" from Client-77.
ap1.request_beacon_report(client1)

print("\n\n==========================================================")
print("== Simulation Finished ==")
print("==========================================================")
