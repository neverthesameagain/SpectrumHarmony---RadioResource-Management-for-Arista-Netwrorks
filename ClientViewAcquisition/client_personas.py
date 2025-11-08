"""
RRM+ Client Personas (Single Source of Truth)
-----------------------------------------------
This file contains the master dictionary of all simulated client personas.
It is imported by both the persona_generator.py and the
full_scale_rrm_simulation.py scripts.
"""

CLIENT_PERSONAS = {
    # -------------------------
    # --- Modern Smartphones ---
    # -------------------------
    "iphone_15_pro": {
        "name": "Apple iPhone 15 Pro",
        "oui": "DC:FB:48",
        "os_class": "iOS 17",
        "supports_80211v": True,
        "qoe_hysteresis": 0.15,
    },
    "samsung_s24_ultra": {
        "name": "Samsung Galaxy S24 Ultra",
        "oui": "B8:27:EB",
        "os_class": "Android 14",
        "supports_80211v": True,
        "qoe_hysteresis": 0.25,
    },
    "pixel_8": {
        "name": "Google Pixel 8",
        "oui": "3C:28:6D",
        "os_class": "Android 14",
        "supports_80211v": True,
        "qoe_hysteresis": 0.2,
    },
    "oneplus_12": {
        "name": "OnePlus 12",
        "oui": "9C:93:4E",
        "os_class": "Android 13",
        "supports_80211v": True,
        "qoe_hysteresis": 0.35,
    },
    "xiaomi_13t": {
        "name": "Xiaomi 13T",
        "oui": "A4:77:33",
        "os_class": "Android 12",
        "supports_80211v": True,
        "qoe_hysteresis": 0.4,
    },
    # -------------------------
    # --- Laptops / Workstations ---
    # -------------------------
    "macbook_pro_m3": {
        "name": "MacBook Pro (M3)",
        "oui": "DC:FB:48",
        "os_class": "macOS 14 Sonoma",
        "supports_80211v": True,
        "qoe_hysteresis": 0.25,
    },
    "thinkpad_x1": {
        "name": "Lenovo ThinkPad X1",
        "oui": "00:1A:2B",
        "os_class": "Windows 11",
        "supports_80211v": True,
        "qoe_hysteresis": 0.7,
    },
    "dell_xps_13": {
        "name": "Dell XPS 13",
        "oui": "00:1E:67",
        "os_class": "Windows 10",
        "supports_80211v": True,
        "qoe_hysteresis": 0.9,
    },
    "hp_elitebook": {
        "name": "HP EliteBook",
        "oui": "A0:9C:9F",
        "os_class": "Windows 10",
        "supports_80211v": True,
        "qoe_hysteresis": 0.8,
    },
    "surface_pro_9": {
        "name": "Microsoft Surface Pro 9",
        "oui": "18:5E:0F",
        "os_class": "Windows 11",
        "supports_80211v": True,
        "qoe_hysteresis": 0.6,
    },
    "chromebook_lenovo": {
        "name": "Lenovo Chromebook",
        "oui": "50:EB:F6",
        "os_class": "ChromeOS 120",
        "supports_80211v": True,
        "qoe_hysteresis": 0.3,
    },
    # -------------------------
    # --- Tablets / Wearables ---
    # -------------------------
    "ipad_air": {
        "name": "Apple iPad Air (M2)",
        "oui": "DC:FB:48",
        "os_class": "iPadOS 17",
        "supports_80211v": True,
        "qoe_hysteresis": 0.2,
    },
    "galaxy_tab_s9": {
        "name": "Samsung Galaxy Tab S9",
        "oui": "B8:27:EB",
        "os_class": "Android 14",
        "supports_80211v": True,
        "qoe_hysteresis": 0.25,
    },
    "apple_watch_9": {
        "name": "Apple Watch Series 9",
        "oui": "DC:FB:48",
        "os_class": "watchOS 10",
        "supports_80211v": False,
        "qoe_hysteresis": 2.0,
    },
    # -------------------------
    # --- IoT / Smart Home Devices ---
    # -------------------------
    "tplink_cam": {
        "name": "TP-Link Smart Camera",
        "oui": "F4:F2:6D",
        "os_class": "Linux IoT",
        "supports_80211v": False,
        "qoe_hysteresis": 99.0,
    },
    "nest_thermostat": {
        "name": "Google Nest Thermostat",
        "oui": "3C:28:6D",
        "os_class": "Embedded Linux",
        "supports_80211v": False,
        "qoe_hysteresis": 80.0,
    },
    "esp32_sensor": {
        "name": "ESP32 Sensor Node",
        "oui": "24:6F:28",
        "os_class": "RTOS (ESP-IDF)",
        "supports_80211v": False,
        "qoe_hysteresis": 100.0,
    },
    "raspi_cam": {
        "name": "Raspberry Pi Camera Node",
        "oui": "B8:27:EB",
        "os_class": "Raspbian Linux",
        "supports_80211v": False,
        "qoe_hysteresis": 70.0,
    },
    "echo_dot": {
        "name": "Amazon Echo Dot",
        "oui": "44:65:0D",
        "os_class": "FireOS IoT",
        "supports_80211v": False,
        "qoe_hysteresis": 90.0,
    },
    "smart_tv_lg": {
        "name": "LG Smart TV",
        "oui": "64:BC:0C",
        "os_class": "webOS",
        "supports_80211v": False,
        "qoe_hysteresis": 60.0,
    },
    "roku_stick": {
        "name": "Roku Streaming Stick",
        "oui": "00:0D:4B",
        "os_class": "Linux Embedded",
        "supports_80211v": False,
        "qoe_hysteresis": 55.0,
    },
    # -------------------------
    # --- Console ---
    # -------------------------
    "ps5_console": {
        "name": "Sony PlayStation 5",
        "oui": "00:26:5D",
        "os_class": "OrbisOS",
        "supports_80211v": True,
        "qoe_hysteresis": 0.5,
    },
    # -------------------------
    # --- Legacy Devices ---
    # -------------------------
    "legacy_printer": {
        "name": "HP LaserJet 4000",
        "oui": "00:08:C1",
        "os_class": "Legacy Wi-Fi (802.11g)",
        "supports_80211v": False,
        "qoe_hysteresis": 999.0,
    },
    "old_android": {
        "name": "Samsung Galaxy S7",
        "oui": "B8:27:EB",
        "os_class": "Android 8",
        "supports_80211v": False,
        "qoe_hysteresis": 4.0,
    },
    "old_macbook": {
        "name": "MacBook Air (2015)",
        "oui": "F0:18:98",
        "os_class": "macOS Catalina",
        "supports_80211v": False,
        "qoe_hysteresis": 3.0,
    },
    "win7_laptop": {
        "name": "Dell Latitude Win7",
        "oui": "00:1E:67",
        "os_class": "Windows 7",
        "supports_80211v": False,
        "qoe_hysteresis": 2.5,
    },
}
