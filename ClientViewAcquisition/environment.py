import math
import random


def calculate_rssi(x1, y1, x2, y2):
    """Calculates the RSSI a client at (x1, y1) would see from an AP at (x2, y2)."""
    distance = math.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)
    distance_log = 10 * 3.0 * math.log10(distance if distance > 1 else 1)
    rssi = -30 - distance_log + random.uniform(-2, 2)
    return max(-90.0, rssi)


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
        print(
            f"[ENV]: Registered {ap.ap_id} at ({ap.x}, {ap.y}) on Ch: {ap.channel} ({ap.band})"
        )

    def register_client(self, client):
        self.all_clients.append(client)

    def client_scan(self, scanning_client, band_to_scan=None):
        """Physics engine: Client asks 'What can I see?'"""
        scan_results = []
        for ap in self.all_aps:
            if band_to_scan and ap.band != band_to_scan:
                continue
            rssi = calculate_rssi(scanning_client.x, scanning_client.y, ap.x, ap.y)
            if rssi > -85:
                scan_results.append(
                    {
                        "bssid": ap.bssid,
                        "channel": ap.channel,
                        "rssi": round(rssi, 2),
                        "ap_id": ap.ap_id,
                        "band": ap.band,
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
            self.ap_load_stats[ap_id]["client_count"] = max(
                0, self.ap_load_stats[ap_id]["client_count"]
            )

    def handle_roam(self, client, new_ap_id):
        """Handles only the *state change* of a client moving."""
        new_ap = next((ap for ap in self.all_aps if ap.ap_id == new_ap_id), None)
        if not new_ap:
            return False

        old_ap = client.connected_ap

        if old_ap:
            old_ap.disconnect_client(client)
            self.update_ap_load(old_ap.ap_id, -1, -1.5)

        new_ap.connect_client(client)
        self.update_ap_load(new_ap.ap_id, +1, +1.5)
        return True
