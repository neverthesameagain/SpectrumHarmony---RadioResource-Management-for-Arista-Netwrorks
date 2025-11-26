"""
This module defines the ClientDevice class, which simulates a wireless client device
in the simulation environment.

The ClientDevice class represents a mobile device with specific characteristics,
such as its persona, capabilities, and roaming behavior. It interacts with the
environment to scan for Access Points, connect to them, and move around.

UPDATES (End-Term):
- Added 802.11mc RTT simulation (measure_rtt_to_ap).
- Added Transport Layer QoE simulation (generate_transport_metrics).
"""

import math
import random

from client_personas import CLIENT_PERSONAS

# --- Constants for QoE Calculation ---
QOE_MIN_SNR = 10.0
"""float: The minimum SNR for QoE calculation."""

QOE_MAX_SNR = 40.0
"""float: The maximum SNR for QoE calculation."""


def calculate_rssi(x1, y1, x2, y2):
    """
    Calculates the Received Signal Strength Indicator (RSSI) between two points.

    Args:
        x1 (float): The x-coordinate of the first point.
        y1 (float): The y-coordinate of the first point.
        x2 (float): The x-coordinate of the second point.
        y2 (float): The y-coordinate of the second point.

    Returns:
        float: The calculated RSSI in dBm.
    """
    distance = math.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)
    distance_log = 10 * 3.0 * math.log10(distance if distance > 1 else 1)
    rssi = -30 - distance_log + random.uniform(-2, 2)
    return max(-90.0, rssi)


def calculate_qoe(snr, airtime_util):
    """
    Calculates the Quality of Experience (QoE) based on SNR and airtime utilization.
    This is the "Link Layer" QoE.

    Args:
        snr (float): The Signal-to-Noise Ratio (SNR).
        airtime_util (float): The airtime utilization percentage.

    Returns:
        float: The calculated QoE score (from 0 to 5).
    """
    s_score = max(0, min(1, (snr - QOE_MIN_SNR) / (QOE_MAX_SNR - QOE_MIN_SNR)))
    l_score = 1 - max(0, min(1, airtime_util / 80.0))
    return 5 * (0.7 * s_score + 0.3 * l_score)


class ClientDevice:
    """
    Represents a wireless client device in the simulation environment.

    This class models the behavior of a mobile device, including its movement,
    scanning for APs, connecting to APs, roaming decisions, and advanced
    telemetry generation (802.11mc, TCP metrics).
    """

    def __init__(self, environment, client_row):
        """
        Initializes the ClientDevice object.

        Args:
            environment (Environment): The simulation environment.
            client_row (dict): A dictionary containing the client's properties.
        """
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
        self.supports_80211r = self.persona.get("supports_80211r", False)

        # Infer 802.11mc support based on OS/Persona (Modern devices only)
        # Android 9+ and recent iOS usually support RTT.
        self.supports_80211mc = self.supports_80211v and ("IoT" not in self.os_class)

        self.x = client_row["x"]
        self.y = client_row["y"]
        self.home_x, self.home_y = self.x, self.y
        self.connected_ap = None
        self.last_seen_ap_id = None
        self.last_seen_qoe = 0.0
        self.noise_floor_dbm = random.uniform(-98.0, -92.0)

        # Determine band support based on OS class and persona
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
        """
        Simulates the movement of the client.
        The client has a chance to move randomly or return to its home position.
        """
        if random.random() < 0.2:
            self.x += random.uniform(-1.0, 1.0)
            self.y += random.uniform(-1.0, 1.0)
        if random.random() < 0.05:
            self.x, self.y = self.home_x, self.home_y

    def clear_roam_memory(self):
        """Clears the client's memory of its last roam attempt."""
        self.last_seen_ap_id = None
        self.last_seen_qoe = 0.0

    def receive_beacon_request_and_scan(self):
        """
        Receives a beacon request from the AP and performs a scan (802.11k).
        """
        scan_data = self.env.client_scan(self)
        report = []
        for ap_entry in scan_data["report"]:
            rssi = ap_entry["rssi"]
            snr = rssi - self.noise_floor_dbm
            ap_entry["snr"] = round(snr, 2)
            report.append(ap_entry)
        return {"report": report}

    def calculate_current_rssi(self):
        """Calculates the current RSSI to the connected AP."""
        if not self.connected_ap:
            return -90.0
        return calculate_rssi(self.x, self.y, self.connected_ap.x, self.connected_ap.y)

    def calculate_current_snr(self):
        """Calculates the current SNR to the connected AP."""
        if not self.connected_ap:
            return 0.0
        rssi = self.calculate_current_rssi()
        return rssi - self.noise_floor_dbm

    def calculate_current_qoe(self):
        """Calculates the current Link-Layer QoE on the connected AP."""
        if not self.connected_ap:
            return 0.0
        snr = self.calculate_current_snr()
        load_stats = self.env.get_ap_load(self.connected_ap.ap_id)
        airtime = load_stats["airtime_util_pct"]
        return calculate_qoe(snr, airtime)

    # ------------------------------------------------------------------
    # --- NEW: END-TERM TELEMETRY METHODS ---
    # ------------------------------------------------------------------

    def measure_rtt_to_ap(self, target_ap_id):
        """
        Simulates an 802.11mc Fine Timing Measurement (FTM) RTT burst.

        This satisfies the End-Term requirement for "location-aware interference hot-spots".
        Instead of measuring time (nanoseconds), we calculate the true distance and
        add realistic Gaussian noise to simulate multipath/clock jitter.

        Args:
            target_ap_id (str): The ID of the AP to measure RTT against.

        Returns:
            float: The estimated distance in meters. Returns -1.0 if AP unreachable or unsupported.
        """
        if not self.supports_80211mc:
            return -1.0

        # 1. Find the target AP in the environment
        target_ap = next(
            (ap for ap in self.env.all_aps if ap.ap_id == target_ap_id), None
        )

        if not target_ap:
            return -1.0

        # 2. Calculate "Ground Truth" (Perfect) Distance
        true_distance = math.sqrt(
            (self.x - target_ap.x) ** 2 + (self.y - target_ap.y) ** 2
        )

        # 3. Add "Realism" Noise (Simulating Multipath/Jitter)
        # Real 802.11mc is typically accurate to within 1-2 meters.
        # We use a Gaussian distribution: mean=0, std_dev=1.5m
        measurement_error = random.gauss(0, 1.5)

        estimated_distance = abs(true_distance + measurement_error)

        return round(estimated_distance, 2)

    def generate_transport_metrics(self):
        """
        Simulates Layer 4 (Transport) metrics: TCP/QUIC RTT and Retransmissions.

        This satisfies the End-Term requirement to "detect client-side problems
        when MAC counters look clean".

        Logic:
        - Base Internet Latency: Fixed (e.g., 25ms).
        - Congestion (Bufferbloat): Exponential penalty based on AP Airtime.
        - Loss/Retransmission: Correlated with low SNR or Hidden Node interference.

        Returns:
            dict: {tcp_rtt_ms, tcp_retransmits_pct, jitter_ms}
        """
        if not self.connected_ap:
            return {"tcp_rtt_ms": 0.0, "tcp_retransmits_pct": 0.0, "jitter_ms": 0.0}

        # 1. Get Environment Variables
        ap_load = self.env.get_ap_load(self.connected_ap.ap_id)["airtime_util_pct"]
        snr = self.calculate_current_snr()
        is_hidden_node_victim = self.env.check_for_hidden_node_interference(
            self.x, self.y
        )

        # 2. Base Latency (Internet path to server)
        base_rtt = 25.0  # ms

        # 3. Calculate Congestion Delay (Bufferbloat simulation)
        # If airtime > 70%, queues fill up, causing latency to spike exponentially.
        congestion_delay = 0.0
        if ap_load > 70:
            excess_load = ap_load - 70
            # e.g., at 90% load, delay adds ~100ms-200ms
            congestion_delay = (excess_load**1.5) * random.uniform(0.8, 1.2)
        else:
            congestion_delay = random.uniform(1, 5)

        # 4. Calculate Retransmissions (Packet Loss)
        # Starts low, increases with poor SNR or Hidden Nodes
        retransmit_rate = 0.1  # Baseline 0.1%

        if snr < 15:
            retransmit_rate += (15 - snr) * 0.5  # Poor signal penalty

        if is_hidden_node_victim:
            # Hidden nodes cause collisions, forcing TCP to resend frequently (timeouts)
            retransmit_rate += random.uniform(2.0, 8.0)

        # 5. Final RTT Calculation
        # TCP RTT increases significantly if there are retransmissions (waiting for timeout)
        rtt_penalty_from_loss = retransmit_rate * 15.0

        final_rtt = base_rtt + congestion_delay + rtt_penalty_from_loss

        # Add random jitter (variance)
        jitter = random.uniform(0, final_rtt * 0.2)
        final_rtt += jitter

        return {
            "tcp_rtt_ms": round(final_rtt, 2),  # The primary latency metric
            "tcp_retransmits_pct": round(retransmit_rate, 2),  # "Loss" metric
            "jitter_ms": round(jitter, 2),  # Stability metric
        }

    # ------------------------------------------------------------------

    def receive_bss_tm_request(self, ranked_list):
        """
        Receives a BSS Transition Management (BSS-TM) request from the AP.
        """
        if not self.supports_80211v:
            return False
        if not ranked_list:
            return False

        best_candidate = ranked_list[0]
        current_qoe = self.last_seen_qoe
        # Use the predicted QoE from the AP's ML model
        potential_qoe = best_candidate["predicted_qoe"]

        if potential_qoe > (current_qoe + self.qoe_hysteresis):
            self.env.handle_roam(self, best_candidate["ap_id"])
            return True
        return False

    def generate_passive_metrics(self):
        """
        Calculates Ground Truth link metrics (Layer 2) for both Uplink and Downlink.
        """
        # 1. Calculate Base Quality (Physics)
        downlink_snr = self.calculate_current_snr()
        ap_load = self.env.get_ap_load(self.connected_ap.ap_id)["airtime_util_pct"]
        base_qoe_pct = max(0, min(1, calculate_qoe(downlink_snr, ap_load) / 5.0))

        # 2. Check for Interference (Hidden Node affects UPLINK primarily)
        is_near_hidden_node = self.env.check_for_hidden_node_interference(
            self.x, self.y
        )

        # 3. Model Downlink (AP -> Client)
        downlink_mcs = int(max(0, min(9, base_qoe_pct * 9.0 + random.uniform(-1, 1))))
        downlink_retry_pct = max(1, min(15, 15 - (base_qoe_pct * 14)))

        # 4. Model Uplink (Client -> AP)
        uplink_qoe_pct = base_qoe_pct
        ack_variance_ms = 0.5 - (base_qoe_pct * 0.4)

        # ...but gets degraded by Hidden Node interference
        if is_near_hidden_node:
            uplink_qoe_pct = uplink_qoe_pct * 0.2  # Heavy penalty on Uplink
            ack_variance_ms = random.uniform(1.5, 3.0)  # High variance

        uplink_mcs = int(max(0, min(9, uplink_qoe_pct * 9.0 + random.uniform(-1, 1))))
        uplink_retry_pct = max(1, min(70, 70 - (uplink_qoe_pct * 69)))

        return {
            "downlink_mcs_index": downlink_mcs,
            "downlink_retry_pct": downlink_retry_pct,
            "uplink_mcs_index": uplink_mcs,
            "uplink_retry_pct": uplink_retry_pct,
            "ack_variance_ms": ack_variance_ms,
        }

    def find_best_ap_and_associate(self):
        """
        Finds the best AP based on a scan and associates with it.
        """
        best_ap_id = None
        best_qoe = -1.0
        current_qoe = self.last_seen_qoe
        scan_results = self.env.client_scan(
            self, self.band_support if self.band_support != "Dual" else None
        )

        for ap_entry in scan_results["report"]:
            potential_rssi = ap_entry["rssi"]
            potential_snr = potential_rssi - self.noise_floor_dbm
            potential_load = self.env.get_ap_load(ap_entry["ap_id"])["airtime_util_pct"]
            potential_qoe = calculate_qoe(potential_snr, potential_load)

            if potential_qoe > best_qoe:
                best_qoe = potential_qoe
                best_ap_id = ap_entry["ap_id"]

        if best_ap_id and (best_qoe > current_qoe or self.last_seen_ap_id is None):
            self.env.handle_roam(self, best_ap_id)
        elif best_ap_id:
            self.env.handle_roam(self, best_ap_id)
        else:
            self.clear_roam_memory()
