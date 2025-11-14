"""
This module defines the AccessPoint class, which simulates a virtual Access Point (AP)
with a high-fidelity Radio Resource Management (RRM) scheduler and a machine learning-based
predictive model for Quality of Experience (QoE).

The AccessPoint class manages client connections, monitors client performance, and
makes intelligent steering decisions to optimize network performance.
"""

import random
from collections import defaultdict, deque

import numpy as np

# --- RRM Scheduler Config ---
POOR_QOE_THRESHOLD = 3.5
"""float: The QoE threshold below which a client is considered to have poor performance."""

HIGH_VARIANCE_THRESHOLD = 3.0
"""float: The RSSI variance threshold above which a client is considered to be unstable."""

HIGH_AP_LOAD_THRESHOLD = 70.0
"""float: The AP load threshold (in percentage) above which the AP is considered to be busy."""

INTERVAL_PROBLEM_CLIENT = 1
"""int: The interval (in simulation steps) at which to check a client with poor performance."""

INTERVAL_STABLE_CLIENT = 6
"""int: The interval (in simulation steps) at which to check a stable client."""

INTERVAL_AP_BUSY = 30
"""int: The interval (in simulation steps) at which to check clients when the AP is busy."""

CACHE_WINDOW_STEPS = 3
"""int: The number of simulation steps for which a client's beacon report is cached."""


class MockQoEPredictor:
    """
    Simulates a pre-trained Linear Regression model for predicting Quality of Experience (QoE).

    This class mimics the behavior of a machine learning model that predicts a client's
    potential QoE on a target AP based on several features. The model is defined by a
    set of weights and a bias term.

    Model: Predicted_QoE = w1*SNR + w2*Load + w3*Sticky + w4*FT + Bias
    """

    def __init__(self):
        """
        Initializes the MockQoEPredictor with pre-defined weights and bias.

        These "weights" would ideally come from training on historical data.
        """
        self.coef_ = [0.1, -0.05, -0.8, 0.4]  # Weights for [SNR, Load, Hysteresis, FT]
        self.intercept_ = 1.5  # Bias term

    def predict(self, features):
        """
        Predicts the QoE score based on the input features.

        Args:
            features (list): A list of features in the order:
                             [potential_snr, potential_load, client_hysteresis, is_ft_roam]

        Returns:
            float: The predicted QoE score, clamped between 0.0 and 5.0.
        """
        score = self.intercept_
        for i, val in enumerate(features):
            score += val * self.coef_[i]
        return max(0.0, min(5.0, score))  # Clamp between 0 and 5


class AccessPoint:
    """
    Represents a virtual Access Point with a high-fidelity RRM scheduler
    and a ML-based predictive model.

    This class manages client connections, monitors client performance, and
    makes intelligent steering decisions to optimize network performance.
    """

    def __init__(self, environment, ap_row):
        """
        Initializes the AccessPoint object.

        Args:
            environment (Environment): The simulation environment.
            ap_row (dict): A dictionary containing the AP's properties.
        """
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

        self.client_rrm_state = {}
        self.client_report_cache = {}
        self.steer_attempts = 0
        self.steer_successes = 0
        self.qoe_deltas = []
        self.stats_by_persona = defaultdict(
            lambda: {"attempts": 0, "success": 0, "rejects": 0}
        )

        # Initialize the ML Predictor
        self.qoe_model = MockQoEPredictor()

        self.env.register_ap(self)

    def connect_client(self, client):
        """
        Connects a client to this Access Point.

        Args:
            client (ClientDevice): The client to connect.
        """
        if client in self.connected_clients:
            return

        self.connected_clients.append(client)
        client.connected_ap = self

        # Initial state setup
        post_roam_qoe = client.calculate_current_qoe()
        current_rssi = client.calculate_current_rssi()
        current_snr = client.calculate_current_snr()

        self.client_rrm_state[client.client_id] = {
            "last_check_step": -999,
            "current_interval": 1,
            "rssi_history": deque([current_rssi], maxlen=6),
            "snr_history": deque([current_snr], maxlen=6),
            "rejection_count": 0,
        }

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
        """
        Disconnects a client from this Access Point.

        Args:
            client (ClientDevice): The client to disconnect.
        """
        if client in self.connected_clients:
            self.connected_clients.remove(client)
            client.connected_ap = None

            if client.client_id in self.client_rrm_state:
                del self.client_rrm_state[client.client_id]
            if client.client_id in self.client_report_cache:
                del self.client_report_cache[client.client_id]

    def log_steer_success(self, persona_name):
        """
        Logs a successful steering event for a given persona.

        Args:
            persona_name (str): The name of the client's persona.
        """
        self.steer_successes += 1
        self.stats_by_persona[persona_name]["success"] += 1

    def _get_ap_load_level(self):
        """
        Gets the current load level of the Access Point.

        Returns:
            str: "high" if the load is above the threshold, "low" otherwise.
        """
        load_pct = self.env.get_ap_load(self.ap_id)["airtime_util_pct"]
        return "high" if load_pct > HIGH_AP_LOAD_THRESHOLD else "low"

    def _update_adaptive_interval(
        self, client_state, client_qoe, rssi_variance, ap_load_level
    ):
        """
        Updates the adaptive interval for checking a client's performance.

        Args:
            client_state (dict): The RRM state of the client.
            client_qoe (float): The current QoE of the client.
            rssi_variance (float): The variance of the client's RSSI.
            ap_load_level (str): The current load level of the AP.
        """
        rejection_count = client_state.get("rejection_count", 0)
        if rejection_count > 0:
            # Apply exponential backoff if the client has rejected steering attempts
            backoff_interval = INTERVAL_STABLE_CLIENT * (2 ** (rejection_count - 1))
            client_state["current_interval"] = backoff_interval
            return

        if client_qoe < POOR_QOE_THRESHOLD or rssi_variance > HIGH_VARIANCE_THRESHOLD:
            # Check more frequently if the client has poor performance or is unstable
            client_state["current_interval"] = INTERVAL_PROBLEM_CLIENT
        elif ap_load_level == "high":
            # Check less frequently if the AP is busy
            client_state["current_interval"] = INTERVAL_AP_BUSY
        else:
            # Default interval for stable clients
            client_state["current_interval"] = INTERVAL_STABLE_CLIENT

    def scheduler_tick(self, client, current_step):
        """
        Performs a scheduler tick for a given client.

        This method is called at each simulation step to monitor the client's
        performance and trigger RRM actions if necessary.

        Args:
            client (ClientDevice): The client to check.
            current_step (int): The current simulation step.
        """
        if client.client_id not in self.client_rrm_state:
            return

        client_state = self.client_rrm_state[client.client_id]
        current_rssi = client.calculate_current_rssi()
        current_qoe = client.calculate_current_qoe()
        current_snr = client.calculate_current_snr()

        # Update client's RSSI and SNR history
        client_state["rssi_history"].append(current_rssi)
        client_state["snr_history"].append(current_snr)
        rssi_variance = np.std(client_state["rssi_history"])

        # Update adaptive interval based on client's performance and AP load
        ap_load_level = self._get_ap_load_level()
        self._update_adaptive_interval(
            client_state, current_qoe, rssi_variance, ap_load_level
        )

        # Check if it's time to perform an RRM action
        steps_since_last_check = current_step - client_state["last_check_step"]
        if steps_since_last_check >= client_state["current_interval"]:
            client_state["last_check_step"] = current_step
            self.rrm_action_check(client, current_qoe, current_step)

    def rrm_action_check(self, client, current_qoe, current_step):
        """
        Checks if an RRM action is needed for a client.

        If the client's QoE is below the threshold, this method initiates a
        steering attempt.

        Args:
            client (ClientDevice): The client to check.
            current_qoe (float): The current QoE of the client.
            current_step (int): The current simulation step.
        """
        if current_qoe < POOR_QOE_THRESHOLD:
            self.steer_attempts += 1
            self.stats_by_persona[client.persona_name]["attempts"] += 1
            client.last_seen_qoe = current_qoe
            client.last_seen_ap_id = self.ap_id

            if client.band_support != "Dual" and client.band_support != self.band:
                # If the client is on the wrong band, perform a band steer
                self.run_passive_inference_and_steer(
                    client, current_step, band_steer=True
                )
            elif client.supports_80211v:
                # If the client supports 802.11v, request a beacon report
                self.request_active_beacon_report(client, current_step)
            else:
                # Otherwise, perform passive inference
                self.run_passive_inference_and_steer(client, current_step)

    def request_active_beacon_report(self, client_to_ask, current_step):
        """
        Requests an active beacon report from a client.

        If a recent report is cached, it is used. Otherwise, a new report is
        requested from the client.

        Args:
            client_to_ask (ClientDevice): The client to ask for a report.
            current_step (int): The current simulation step.
        """
        if client_to_ask.client_id in self.client_report_cache:
            cached = self.client_report_cache[client_to_ask.client_id]
            if (current_step - cached["timestamp_step"]) < CACHE_WINDOW_STEPS:
                # Use cached report if it's recent enough
                self.analyze_active_report_and_steer(client_to_ask, cached["report"])
                return

        # Request a new report from the client
        client_report = client_to_ask.receive_beacon_request_and_scan()
        self.client_report_cache[client_to_ask.client_id] = {
            "timestamp_step": current_step,
            "report": client_report,
        }
        self.analyze_active_report_and_steer(client_to_ask, client_report)

    def _get_qoe_prediction(self, client, target_ap_stats):
        """
        Uses the MockQoEPredictor to rank candidate APs.

        Args:
            client (ClientDevice): The client to predict QoE for.
            target_ap_stats (dict): The stats of the target AP.

        Returns:
            float: The predicted QoE score.
        """
        # 1. Extract Features for the Model
        potential_snr = target_ap_stats["snr"]
        potential_load = target_ap_stats["airtime_util_pct"]

        # Feature: Is client sticky? (1.0 if yes, 0.0 if no)
        client_hysteresis_feature = 1.0 if client.qoe_hysteresis > 1.0 else 0.0

        # Feature: Is this an FT roam? (1.0 if yes, 0.0 if no)
        is_ft_roam_feature = (
            1.0
            if (client.supports_80211r and target_ap_stats["supports_80211r"])
            else 0.0
        )

        # 2. Pass features to the model
        features = [
            potential_snr,
            potential_load,
            client_hysteresis_feature,
            is_ft_roam_feature,
        ]
        predicted_qoe = self.qoe_model.predict(features)

        return predicted_qoe

    def analyze_active_report_and_steer(self, client, client_report):
        """
        Analyzes a client's beacon report and initiates a steering attempt.

        This method uses the ML model to predict the QoE on candidate APs and
        sends a BSS Transition Management (BSS-TM) request to the client.

        Args:
            client (ClientDevice): The client to steer.
            client_report (dict): The client's beacon report.
        """
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

            # Use ML Model to predict QoE
            predicted_qoe_score = self._get_qoe_prediction(client, target_ap_stats)

            candidates.append(
                {
                    "ap_id": ap_entry["ap_id"],
                    "predicted_qoe": predicted_qoe_score,
                    "client_view_rssi": ap_entry["rssi"],
                    "client_view_snr": ap_entry["snr"],
                    "ap_load_airtime": global_load["airtime_util_pct"],
                }
            )

        if not candidates:
            client.clear_roam_memory()
            return

        # Rank candidates by predicted QoE
        ranked_list = sorted(candidates, key=lambda x: x["predicted_qoe"], reverse=True)
        acceptance = client.receive_bss_tm_request(ranked_list)

        client_state = self.client_rrm_state.get(client.client_id)
        if not acceptance:
            # If the client rejects the steering attempt, log the rejection
            self.stats_by_persona[client.persona_name]["rejects"] += 1
            if client_state:
                client_state["rejection_count"] += 1
            client.clear_roam_memory()
        else:
            # If the client accepts, reset the rejection count
            if client_state:
                client_state["rejection_count"] = 0

    def run_passive_inference_and_steer(self, client, current_step, band_steer=False):
        """
        Performs passive inference and steers the client if necessary.

        In a real AP, this function would look at uplink stats measured at the AP.
        We simulate that by asking the client to 'generate' those stats for us.

        Args:
            client (ClientDevice): The client to steer.
            current_step (int): The current simulation step.
            band_steer (bool, optional): Whether to perform a band steer. Defaults to False.
        """
        if band_steer:
            self.disconnect_client(client)
            client.find_best_ap_and_associate()
            return

        # In simulation, we "ask" the client object for its metrics.
        # In reality, the AP measures these directly from client frames.
        metrics = client.generate_passive_metrics()

        # We use the metrics provided by the client simulation.
        hidden_node_suspicion = 0
        if metrics["downlink_mcs_index"] > (metrics["uplink_mcs_index"] + 2):
            hidden_node_suspicion += 1
        if metrics["uplink_retry_pct"] > (metrics["downlink_retry_pct"] + 20):
            hidden_node_suspicion += 1
        if metrics["ack_variance_ms"] > 1.5:
            hidden_node_suspicion += 1

        if hidden_node_suspicion >= 2:
            # If there is a high suspicion of a hidden node, disconnect the client
            # and let it find a better AP.
            self.disconnect_client(client)
            client.find_best_ap_and_associate()
        else:
            client.clear_roam_memory()

    def get_steering_stats(self):
        """
        Gets the steering statistics for this Access Point.

        Returns:
            dict: A dictionary containing steering statistics.
        """
        return {
            "attempts": self.steer_attempts,
            "successes": self.steer_successes,
            "qoe_deltas": self.qoe_deltas,
            "by_persona": self.stats_by_persona,
        }
