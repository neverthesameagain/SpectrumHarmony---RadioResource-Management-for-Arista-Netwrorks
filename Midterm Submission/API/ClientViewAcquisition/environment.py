"""
This module defines the Environment class, which represents the simulation world.

The Environment class manages all the Access Points (APs) and Client Devices in the
simulation. It provides the physics of the environment, such as calculating RSSI,
and manages the state of the APs, such as their load. It also manages hidden
node interference.
"""

import math
import random


def calculate_rssi(x1, y1, x2, y2):
    """
    Calculates the RSSI a client at (x1, y1) would see from an AP at (x2, y2).

    Args:
        x1 (float): The x-coordinate of the client.
        y1 (float): The y-coordinate of the client.
        x2 (float): The x-coordinate of the AP.
        y2 (float): The y-coordinate of the AP.

    Returns:
        float: The calculated RSSI in dBm.
    """
    distance = math.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)
    distance_log = 10 * 3.0 * math.log10(distance if distance > 1 else 1)
    rssi = -30 - distance_log + random.uniform(-2, 2)
    return max(-90.0, rssi)


class Environment:
    """
    Holds all "things" and acts as the "world".

    This class provides the physics and AP load state for the simulation.
    It also manages hidden node interference.
    """

    def __init__(self):
        """
        Initializes the Environment object.
        """
        self.all_aps = []
        self.all_clients = []
        self.ap_load_stats = {}

        # Hidden Node State
        self.hidden_nodes = []  # List of active hidden nodes {x, y, radius}

        print("[ENV]: Environment (Physics + AP State) created.")

    def register_ap(self, ap):
        """
        Registers an Access Point in the environment.

        Args:
            ap (AccessPoint): The AccessPoint object to register.
        """
        self.all_aps.append(ap)
        self.ap_load_stats[ap.ap_id] = {"client_count": 0, "airtime_util_pct": 0.0}
        print(
            f"[ENV]: Registered {ap.ap_id} at ({ap.x}, {ap.y}) on Ch: {ap.channel} ({ap.band})"
        )

    def register_client(self, client):
        """
        Registers a Client Device in the environment.

        Args:
            client (ClientDevice): The ClientDevice object to register.
        """
        self.all_clients.append(client)

    def client_scan(self, scanning_client, band_to_scan=None):
        """
        Simulates a client scanning for nearby Access Points.

        This method acts as the physics engine for the simulation, determining
        which APs are visible to the client and at what signal strength.

        Args:
            scanning_client (ClientDevice): The client performing the scan.
            band_to_scan (str, optional): The band to scan ("2.4GHz" or "5GHz").
                                          If None, scans all bands. Defaults to None.

        Returns:
            dict: A dictionary containing the scan results.
        """
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
        """
        Provides the global load data for a given AP.

        Args:
            ap_id (str): The ID of the AP.

        Returns:
            dict: A dictionary containing the load stats of the AP.
        """
        return self.ap_load_stats.get(
            ap_id, {"client_count": 99, "airtime_util_pct": 100.0}
        )

    def update_ap_load(self, ap_id, client_count_delta, airtime_delta):
        """
        Updates the load stats for a given AP.

        Args:
            ap_id (str): The ID of the AP.
            client_count_delta (int): The change in the number of clients.
            airtime_delta (float): The change in airtime utilization.
        """
        if ap_id in self.ap_load_stats:
            self.ap_load_stats[ap_id]["client_count"] += client_count_delta
            self.ap_load_stats[ap_id]["airtime_util_pct"] += airtime_delta
            # Clamp airtime utilization between 0 and 100
            self.ap_load_stats[ap_id]["airtime_util_pct"] = max(
                0, min(100, self.ap_load_stats[ap_id]["airtime_util_pct"])
            )
            # Ensure client count is not negative
            self.ap_load_stats[ap_id]["client_count"] = max(
                0, self.ap_load_stats[ap_id]["client_count"]
            )

    def handle_roam(self, client, new_ap_id):
        """
        Handles the state change of a client moving between APs.

        Args:
            client (ClientDevice): The client that is roaming.
            new_ap_id (str): The ID of the new AP.

        Returns:
            bool: True if the roam was successful, False otherwise.
        """
        new_ap = next((ap for ap in self.all_aps if ap.ap_id == new_ap_id), None)
        if not new_ap:
            return False

        old_ap = client.connected_ap

        # Disconnect from the old AP
        if old_ap:
            old_ap.disconnect_client(client)
            self.update_ap_load(old_ap.ap_id, -1, -1.5)

        # Connect to the new AP
        new_ap.connect_client(client)
        self.update_ap_load(new_ap.ap_id, +1, +1.5)
        return True

    def activate_hidden_node(self, x, y, radius):
        """
        Activates a source of interference that APs cannot see.

        Args:
            x (float): The x-coordinate of the hidden node.
            y (float): The y-coordinate of the hidden node.
            radius (float): The radius of the interference.
        """
        print(
            f"[ENV]: STRESS: Activating hidden node at ({x},{y}) with radius {radius}m"
        )
        self.hidden_nodes.append({"x": x, "y": y, "radius": radius})

    def check_for_hidden_node_interference(self, client_x, client_y):
        """
        Checks if a client is close enough to an active hidden node to be affected.

        Args:
            client_x (float): The x-coordinate of the client.
            client_y (float): The y-coordinate of the client.

        Returns:
            bool: True if the client is affected by interference, False otherwise.
        """
        for node in self.hidden_nodes:
            distance = math.sqrt(
                (client_x - node["x"]) ** 2 + (client_y - node["y"]) ** 2
            )
            if distance < node["radius"]:
                return True  # Client is affected by interference
        return False
