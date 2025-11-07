"""
RRM+ Synthetic Environment & Persona Generator — v2
---------------------------------------------------
Generates:
 • synthetic_ap_layout.csv
 • synthetic_client_population.csv
with detailed client personas (OUI, OS, band support, capabilities, behavior).
"""

import random
import pandas as pd
import numpy as np

# ===========================================================
# 1. EXTENDED CLIENT PERSONAS
# ===========================================================

CLIENT_PERSONAS = {
    # --- High-end mobile devices ---
    "iphone_17": {
        "name": "Apple iPhone 17",
        "vendor": "Apple",
        "oui": "DC:FB:48",
        "os_class": "iOS 17",
        "device_type": "Phone",
        "supports_80211k": True,
        "supports_80211v": True,
        "supports_80211r": True,
        "supports_6ghz": True,
        "band_pref": "5GHz",
        "roam_aggressiveness": 0.9,
        "qoe_hysteresis": 0.15,
        "avg_throughput": 100,
        "battery_saver": False,
    },
    "android_flagship": {
        "name": "Samsung Galaxy S24",
        "vendor": "Samsung",
        "oui": "B8:27:EB",
        "os_class": "Android 14",
        "device_type": "Phone",
        "supports_80211k": True,
        "supports_80211v": True,
        "supports_80211r": True,
        "supports_6ghz": True,
        "band_pref": "5GHz",
        "roam_aggressiveness": 0.8,
        "qoe_hysteresis": 0.25,
        "avg_throughput": 85,
        "battery_saver": False,
    },

    # --- Laptops ---
    "macbook_pro": {
        "name": "MacBook Pro M3",
        "vendor": "Apple",
        "oui": "DC:FB:48",
        "os_class": "macOS 14",
        "device_type": "Laptop",
        "supports_80211k": True,
        "supports_80211v": True,
        "supports_80211r": True,
        "supports_6ghz": True,
        "band_pref": "5GHz",
        "roam_aggressiveness": 0.7,
        "qoe_hysteresis": 0.3,
        "avg_throughput": 160,
        "battery_saver": False,
    },
    "win11_laptop": {
        "name": "Dell Latitude Win11",
        "vendor": "Intel",
        "oui": "00:1A:2B",
        "os_class": "Windows 11",
        "device_type": "Laptop",
        "supports_80211k": True,
        "supports_80211v": True,
        "supports_80211r": True,
        "supports_6ghz": False,
        "band_pref": "5GHz",
        "roam_aggressiveness": 0.6,
        "qoe_hysteresis": 0.5,
        "avg_throughput": 140,
        "battery_saver": False,
    },

    # --- Mid-range / older clients ---
    "android_mid": {
        "name": "Xiaomi Redmi Note 10",
        "vendor": "Xiaomi",
        "oui": "A4:77:33",
        "os_class": "Android 12",
        "device_type": "Phone",
        "supports_80211k": True,
        "supports_80211v": False,
        "supports_80211r": False,
        "supports_6ghz": False,
        "band_pref": "2.4GHz",
        "roam_aggressiveness": 0.5,
        "qoe_hysteresis": 0.9,
        "avg_throughput": 45,
        "battery_saver": True,
    },
    "legacy_laptop": {
        "name": "HP EliteBook Win10",
        "vendor": "Intel",
        "oui": "00:1A:2B",
        "os_class": "Windows 10",
        "device_type": "Laptop",
        "supports_80211k": True,
        "supports_80211v": False,
        "supports_80211r": False,
        "supports_6ghz": False,
        "band_pref": "2.4GHz",
        "roam_aggressiveness": 0.4,
        "qoe_hysteresis": 1.0,
        "avg_throughput": 70,
        "battery_saver": False,
    },

    # --- IoT & embedded devices ---
    "iot_camera": {
        "name": "TP-Link SmartCam",
        "vendor": "TP-Link",
        "oui": "F4:F2:6D",
        "os_class": "Linux IoT",
        "device_type": "IoT",
        "supports_80211k": False,
        "supports_80211v": False,
        "supports_80211r": False,
        "supports_6ghz": False,
        "band_pref": "2.4GHz",
        "roam_aggressiveness": 0.0,
        "qoe_hysteresis": 99.0,
        "avg_throughput": 10,
        "battery_saver": True,
    },
    "raspi_sensor": {
        "name": "Raspberry Pi Hub",
        "vendor": "Murata",
        "oui": "60:45:BD",
        "os_class": "Linux Embedded",
        "device_type": "IoT",
        "supports_80211k": False,
        "supports_80211v": False,
        "supports_80211r": False,
        "supports_6ghz": False,
        "band_pref": "2.4GHz",
        "roam_aggressiveness": 0.0,
        "qoe_hysteresis": 99.0,
        "avg_throughput": 8,
        "battery_saver": True,
    },
    "industrial_tablet": {
        "name": "Honeywell Android Tablet",
        "vendor": "Honeywell",
        "oui": "64:5A:04",
        "os_class": "Android 9",
        "device_type": "Industrial",
        "supports_80211k": False,
        "supports_80211v": True,
        "supports_80211r": False,
        "supports_6ghz": False,
        "band_pref": "2.4GHz",
        "roam_aggressiveness": 0.2,
        "qoe_hysteresis": 1.5,
        "avg_throughput": 25,
        "battery_saver": True,
    },
}

# ===========================================================
# 2. AP TOPOLOGY GENERATOR
# ===========================================================

def generate_ap_layout(n_aps=12, grid_spacing=15):
    aps = []
    bands = ["2.4GHz", "5GHz"]
    channels_24 = [1, 6, 11]
    channels_5 = [36, 40, 44, 48, 52, 56, 60, 64, 149, 153, 157, 161]
    for i in range(n_aps):
        x = (i % 4) * grid_spacing
        y = (i // 4) * grid_spacing
        band = random.choice(bands)
        ch = random.choice(channels_24 if band == "2.4GHz" else channels_5)
        aps.append({
            "ap_id": f"AP-{i+1}",
            "x": x,
            "y": y,
            "band": band,
            "channel": ch,
            "tx_power_dbm": random.choice([17, 20, 23]),
            "max_clients": random.randint(20, 40),
        })
    return aps

# ===========================================================
# 3. CLIENT POPULATION GENERATOR
# ===========================================================

def generate_clients(personas, n_clients=80, area_size=60):
    clients = []
    persona_keys = list(personas.keys())
    weights = [5,5,4,4,3,3,2,2,2]  # bias toward mobile/laptop
    for i in range(n_clients):
        persona_key = random.choices(persona_keys, weights=weights, k=1)[0]
        p = personas[persona_key]
        x = np.clip(random.gauss(area_size/2, area_size/3), 0, area_size)
        y = np.clip(random.gauss(area_size/2, area_size/3), 0, area_size)
        clients.append({
            "client_id": f"Client-{i+1:03d}",
            "x": round(x,2),
            "y": round(y,2),
            "persona_key": persona_key,
            "oui": p["oui"],
            "vendor": p["vendor"],
            "device_type": p["device_type"],
            "os_class": p["os_class"],
            "supports_80211k": p["supports_80211k"],
            "supports_80211v": p["supports_80211v"],
            "supports_80211r": p["supports_80211r"],
            "supports_6ghz": p["supports_6ghz"],
            "band_pref": p["band_pref"],
            "roam_aggressiveness": p["roam_aggressiveness"],
            "qoe_hysteresis": p["qoe_hysteresis"],
            "avg_throughput": p["avg_throughput"],
            "battery_saver": p["battery_saver"]
        })
    return clients

# ===========================================================
# 4. EXPORT TO CSV
# ===========================================================

def export_topology(aps, clients):
    pd.DataFrame(aps).to_csv("synthetic_ap_layout.csv", index=False)
    pd.DataFrame(clients).to_csv("synthetic_client_population.csv", index=False)
    print(f"✅ Exported {len(aps)} APs and {len(clients)} clients.")

aps = generate_ap_layout()
clients = generate_clients(CLIENT_PERSONAS)
export_topology(aps, clients)
