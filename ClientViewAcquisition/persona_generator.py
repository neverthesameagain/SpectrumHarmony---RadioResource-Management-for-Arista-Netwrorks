"""
This module generates the synthetic AP layout and client population for the RRM+ simulation.

This script creates two CSV files:
- `synthetic_ap_layout.csv`: Contains the layout of the Access Points.
- `synthetic_client_population.csv`: Contains the population of client devices with
  different personas.

This script imports the `CLIENT_PERSONAS` dictionary from `client_personas.py`.
"""

import random

import numpy as np
import pandas as pd

from client_personas import CLIENT_PERSONAS


def generate_ap_layout(n_aps=12, grid_spacing=15):
    """
    Generates a synthetic layout of Access Points.

    Args:
        n_aps (int, optional): The number of APs to generate. Defaults to 12.
        grid_spacing (int, optional): The spacing between APs in the grid. Defaults to 15.

    Returns:
        list: A list of dictionaries, where each dictionary represents an AP.
    """
    aps = []
    bands = ["2.4GHz", "5GHz"]
    channels_24 = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
    channels_5 = [
        36,
        40,
        44,
        48,  # UNII-1
        52,
        56,
        60,
        64,  # UNII-2 (DFS)
        100,
        104,
        108,
        112,
        116,
        120,
        124,
        128,
        132,
        136,
        140,
        144,  # UNII-2e (DFS)
        149,
        153,
        157,
        161,
        165,  # UNII-3
    ]

    for i in range(n_aps):
        x = (i % 4) * grid_spacing
        y = (i // 4) * grid_spacing
        band = random.choice(bands)
        ch = random.choice(channels_24 if band == "2.4GHz" else channels_5)
        aps.append(
            {
                "ap_id": f"AP-{i + 1}",
                "x": x,
                "y": y,
                "band": band,
                "channel": ch,
                "tx_power_dbm": random.choice([17, 20, 23]),
                "max_clients": random.randint(20, 40),
            }
        )
    return aps


def generate_clients(personas, n_clients=80, area_size=60):
    """
    Generates a synthetic population of client devices.

    Args:
        personas (dict): A dictionary of client personas.
        n_clients (int, optional): The number of clients to generate. Defaults to 80.
        area_size (int, optional): The size of the area where clients are distributed.
                                   Defaults to 60.

    Returns:
        list: A list of dictionaries, where each dictionary represents a client.
    """
    clients = []
    persona_keys = list(personas.keys())

    # Define weights for each persona to create a realistic distribution
    weights = [
        # Smartphones (5) - High
        5,
        5,
        5,
        5,
        5,
        # Laptops (6) - High
        5,
        5,
        5,
        5,
        5,
        5,
        # Tablets (2) - Medium
        3,
        3,
        # Wearable (1) - Low
        1,
        # IoT (7) - Low
        1,
        1,
        1,
        1,
        1,
        1,
        1,
        # Console (1) - Medium
        3,
        # Legacy (4) - Very Low
        1,
        1,
        1,
        1,
    ]

    for i in range(n_clients):
        # Choose a persona based on the defined weights
        persona_key = random.choices(persona_keys, weights=weights, k=1)[0]
        p = personas[persona_key]
        # Distribute clients with a Gaussian distribution around the center of the area
        x = np.clip(random.gauss(area_size / 2, area_size / 3), 0, area_size)
        y = np.clip(random.gauss(area_size / 2, area_size / 3), 0, area_size)
        clients.append(
            {
                "client_id": f"Client-{i + 1:03d}",
                "x": round(x, 2),
                "y": round(y, 2),
                "persona_key": persona_key,
                "oui": p["oui"],
                "os_class": p["os_class"],
                "supports_80211v": p["supports_80211v"],
                "qoe_hysteresis": p["qoe_hysteresis"],
            }
        )
    return clients


def export_topology(aps, clients):
    """
    Exports the generated AP layout and client population to CSV files.

    Args:
        aps (list): A list of APs.
        clients (list): A list of clients.
    """
    pd.DataFrame(aps).to_csv("synthetic_ap_layout.csv", index=False)
    pd.DataFrame(clients).to_csv("synthetic_client_population.csv", index=False)
    print(f"✅ Exported {len(aps)} APs and {len(clients)} clients.")


if __name__ == "__main__":
    # Generate the AP layout and client population
    aps = generate_ap_layout()
    clients = generate_clients(CLIENT_PERSONAS)
    # Export the generated data to CSV files
    export_topology(aps, clients)
