import math
import random

from client_personas import CLIENT_PERSONAS


def calculate_rssi(x1, y1, x2, y2):
    """Calculates the RSSI a client at (x1, y1) would see from an AP at (x2, y2)."""
    distance = math.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)
    distance_log = 10 * 3.0 * math.log10(distance if distance > 1 else 1)
    rssi = -30 - distance_log + random.uniform(-2, 2)
    return max(-90.0, rssi)


def calculate_qoe(rssi, airtime_util):
    """Simplified QoE function based on signal strength and AP congestion."""
    s_score = max(0, min(1, (rssi - (-85)) / ((-60) - (-85))))  # Signal score
    l_score = 1 - max(0, min(1, airtime_util / 80.0))  # Load score (80% is "full")
    return 5 * (0.7 * s_score + 0.3 * l_score)


class ClientDevice:
    """Represents a virtual Wi-Fi Client with roaming logic."""

    def __init__(self, environment, client_row):
        self.env = environment
        self.client_id = client_row["client_id"]
        self.persona_key = client_row["persona_key"]
        self.persona = CLIENT_PERSONAS.get(
            self.persona_key, CLIENT_PERSONAS["iphone_15_pro"]
        )
        self.persona_name = self.persona["name"]
        self.oui = client_row["oui"]
        self.os_class = client_row["os_class"]
        self.supports_80211v = client_row["supports_80211v"]
        self.qoe_hysteresis = client_row["qoe_hysteresis"]
        self.x = client_row["x"]
        self.y = client_row["y"]
        self.home_x, self.home_y = self.x, self.y  # "Home" location
        self.connected_ap = None
        self.last_seen_ap_id = None
        self.last_seen_qoe = 0.0

        if (
            "802.11g" in self.os_class
            or "ESP32" in self.persona_name
            or "TP-Link" in self.persona_name
        ):
            self.band_support = "2.4GHz"
        elif "watchOS" in self.os_class or "Android 8" in self.os_class:
            self.band_support = "5GHz"
        else:
            self.band_support = "Dual"

        self.env.register_client(self)

    def move(self):
        """Simulates a "random walk" for the client to generate RSSI variance."""
        # 80% chance to stay still, 20% chance to move
        if random.random() < 0.2:
            self.x += random.uniform(-1.0, 1.0)  # Move up to 1m
            self.y += random.uniform(-1.0, 1.0)

        # 5% chance to "return home"
        if random.random() < 0.05:
            self.x, self.y = self.home_x, self.home_y

    def clear_roam_memory(self):
        self.last_seen_ap_id = None
        self.last_seen_qoe = 0.0

    def receive_beacon_request_and_scan(self):
        scan_results = self.env.client_scan(self)
        return scan_results

    def calculate_current_rssi(self):
        """Helper to get just the RSSI to the current AP."""
        if not self.connected_ap:
            return -90.0
        return calculate_rssi(self.x, self.y, self.connected_ap.x, self.connected_ap.y)

    def calculate_current_qoe(self):
        if not self.connected_ap:
            return 0.0
        rssi = self.calculate_current_rssi()
        load_stats = self.env.get_ap_load(self.connected_ap.ap_id)
        airtime = load_stats["airtime_util_pct"]
        return calculate_qoe(rssi, airtime)

    def receive_bss_tm_request(self, ranked_list):
        if not self.supports_80211v:
            return False
        if not ranked_list:
            return False

        best_candidate = ranked_list[0]
        current_qoe = self.last_seen_qoe
        potential_rssi = best_candidate["client_view_rssi"]
        potential_load = best_candidate["ap_load_airtime"]
        potential_qoe = calculate_qoe(potential_rssi, potential_load)
        qoe_threshold = self.qoe_hysteresis

        if potential_qoe > (current_qoe + qoe_threshold):
            self.env.handle_roam(self, best_candidate["ap_id"])
            return True
        else:
            return False

    def generate_passive_metrics(self):
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
        best_ap_id = None
        best_qoe = -1.0
        current_qoe = self.last_seen_qoe
        scan_results = self.env.client_scan(
            self, self.band_support if self.band_support != "Dual" else None
        )

        for ap_entry in scan_results["report"]:
            potential_rssi = ap_entry["rssi"]
            potential_load = self.env.get_ap_load(ap_entry["ap_id"])["airtime_util_pct"]
            potential_qoe = calculate_qoe(potential_rssi, potential_load)

            if potential_qoe > best_qoe:
                best_qoe = potential_qoe
                best_ap_id = ap_entry["ap_id"]

        if best_ap_id and (best_qoe > current_qoe or self.last_seen_ap_id is None):
            self.env.handle_roam(self, best_ap_id)
        elif best_ap_id:
            self.env.handle_roam(self, best_ap_id)
        else:
            self.clear_roam_memory()
