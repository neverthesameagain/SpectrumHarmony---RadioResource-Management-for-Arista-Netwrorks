# ==============================================================
# ARISTA RRM+ Synthetic Dataset Generator (Typed Non-Wi-Fi version)
# ==============================================================
# Output:
#   - fft_dataset_24h.csv   (Wi-Fi vs BLE/ZigBee/Microwave/FHSS)
#   - ap_log_24h.csv
#   - client_log_24h.csv
# ==============================================================

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import math

# ---------------- CONFIG ----------------
rng = np.random.default_rng(42)
N_AP, CLIENTS_PER_AP, RADIUS_M = 6, 40, 10.0
RSSI_MIN, RSSI_MAX = -70, -30
N_MIN = 24 * 60               # 24h simulation (1-min tick)
START_TS = datetime(2025, 11, 2, 0, 0, 0)

BANDS = ["2.4", "5"]
CH_24 = [1, 6, 11]
CH_5 = [36, 40, 44, 48]
WIDTHS = [20, 40, 80]
PHY_MAX_24, PHY_MAX_5 = 72.0, 200.0
def width_scale(w): return {20: 1.0, 40: 1.7, 80: 3.0}.get(w, 1.0)

# ---------------- AP GRID ----------------
grid_x, grid_y = np.linspace(0, 40, 3), np.linspace(0, 20, 2)
ap_coords = [(x, y) for y in grid_y for x in grid_x][:N_AP]
aps = []
for i, (x, y) in enumerate(ap_coords):
    band = rng.choice(BANDS, p=[0.4, 0.6])
    if band == "2.4":
        ch, width, phy = rng.choice(CH_24), 20, PHY_MAX_24
    else:
        ch, width = rng.choice(CH_5), rng.choice(WIDTHS, p=[0.6, 0.3, 0.1])
        phy = PHY_MAX_5 * width_scale(width)
    aps.append({
        "ap_id": f"AP_{i+1}", "x": x, "y": y, "band": band,
        "channel": int(ch), "channel_width_mhz": int(width),
        "tx_power_dbm": float(rng.integers(14, 21)), "phy_max_mbps": phy
    })
ap_df = pd.DataFrame(aps)

# ---------------- CLIENTS ----------------
clients = []
for _, ap in ap_df.iterrows():
    for k in range(CLIENTS_PER_AP):
        r = RADIUS_M * math.sqrt(rng.uniform())
        θ = rng.uniform(0, 2 * np.pi)
        x, y = ap.x + r * np.cos(θ), ap.y + r * np.sin(θ)
        clients.append({
            "client_id": f"C_{ap.ap_id}_{k+1}",
            "connected_ap": ap.ap_id, "band": ap.band,
            "channel": ap.channel, "x": x, "y": y, "distance_m": r
        })
clients_df = pd.DataFrame(clients)

# ---------------- UTILS ----------------
def rssi_from_distance(d, std=1.5):
    base = RSSI_MAX - (d / RADIUS_M) * (RSSI_MAX - RSSI_MIN)
    return float(np.clip(base + rng.normal(0, std), RSSI_MIN, RSSI_MAX))

def noise_floor(band):
    base = -94.5 if band == "2.4" else -96.0
    return float(base + rng.normal(0, 1.5))

# Typed interferer generator
def generate_nonwifi_interferers(minute, band):
    itfs = []

    # BLE
    if band == "2.4" and rng.random() < 0.30:
        itfs.append({
            "cls": "BLE",
            "center_mhz": float(2420 + rng.uniform(-10, 10)),
            "bw_mhz": 1.0,
            "duty": float(rng.uniform(0.3, 0.6)),
            "power_dbm": float(rng.uniform(-65, -55))
        })

    # ZigBee
    if band == "2.4" and rng.random() < 0.20:
        itfs.append({
            "cls": "ZigBee",
            "center_mhz": float(2450 + rng.uniform(-15, 15)),
            "bw_mhz": 2.0,
            "duty": float(rng.uniform(0.2, 0.7)),
            "power_dbm": float(rng.uniform(-68, -58))
        })

    # Microwave oven bursts
    if band == "2.4" and (20 <= (minute % 60) <= 30 or 45 <= (minute % 60) <= 55):
        itfs.append({
            "cls": "Microwave",
            "center_mhz": 2450.0, "bw_mhz": 20.0, "duty": 0.9,
            "power_dbm": float(rng.uniform(-60, -50))
        })

    # FHSS
    if rng.random() < 0.10:
        center = 5200.0 if band == "5" else 2440.0
        itfs.append({
            "cls": "FHSS",
            "center_mhz": float(center + rng.uniform(-25, 25)),
            "bw_mhz": 1.0,
            "duty": float(rng.uniform(0.2, 0.6)),
            "power_dbm": float(rng.uniform(-67, -57))
        })
    return itfs

def retry_pct(snr, nonwifi=False):
    base = 100 / (1 + np.exp(0.35 * (snr - 18)))
    if nonwifi: base += 8
    return float(np.clip(base + rng.normal(0, 2), 0, 100))

def throughput(snr, band, width, retry):
    phy = PHY_MAX_24 if band == "2.4" else PHY_MAX_5
    phy *= width_scale(width)
    eff = np.clip(snr / 35, 0, 1) * (1 - retry / 120) * (0.9 + rng.uniform(0, 0.15))
    return float(max(0, phy * eff))

def qoe(snr, retry):
    s = np.clip(snr / 35, 0, 1)
    r = 1 - np.clip(retry / 50, 0, 1)
    return float(5 * (0.7 * s + 0.3 * r))

# ---------------- SIMULATION ----------------
ap_log, client_log, fft_log = [], [], []
print(f"🚀 Starting 24-hour simulation ({N_AP} APs, {CLIENTS_PER_AP * N_AP} clients)...")

for minute in range(N_MIN):
    ts = START_TS + timedelta(minutes=minute)
    if minute % 60 == 0:
        print(f" ⏱️ Simulated {minute / 60:.0f} / 24 hours")

    for _, a in ap_df.iterrows():
        nf = noise_floor(a.band)
        itfs = generate_nonwifi_interferers(minute, a.band)
        types_here = [i["cls"] for i in itfs]
        nonwifi_flag = len(itfs) > 0

        # --- FFT Dataset (one row per interferer or Wi-Fi) ---
        bins_base = rng.normal(-90, 3, 64)
        if itfs:
            for itf in itfs:
                bins = bins_base.copy()
                # Map center to bin
                center_bin = int(np.clip(np.round(np.interp(
                    itf["center_mhz"],
                    [2400, 2500] if a.band == "2.4" else [5150, 5850],
                    [8, 56]
                )), 1, 62))
                half_bw = max(1, int(round((itf["bw_mhz"] / (20 / 64)))))
                lo, hi = center_bin - half_bw, center_bin + half_bw
                bins[lo:hi] += itf["power_dbm"] - (-90)
                fft_log.append({
                    "timestamp": ts.isoformat(), "ap_id": a.ap_id, "band": a.band,
                    "channel": int(a.channel), "label": itf["cls"],
                    "center_mhz": itf["center_mhz"], "bw_mhz": itf["bw_mhz"],
                    "duty": itf["duty"], "power_dbm": itf["power_dbm"],
                    **{f"fft_bin_{i}": float(v) for i, v in enumerate(bins)}
                })
        else:
            fft_log.append({
                "timestamp": ts.isoformat(), "ap_id": a.ap_id, "band": a.band,
                "channel": int(a.channel), "label": "wifi",
                "center_mhz": np.nan, "bw_mhz": np.nan,
                "duty": 0.0, "power_dbm": np.nan,
                **{f"fft_bin_{i}": float(v) for i, v in enumerate(bins_base)}
            })

        # --- CLIENT + AP metrics ---
        ap_snr, ap_thr, ap_rty, ap_q, ap_dist = [], [], [], [], []
        ap_clients = clients_df[clients_df.connected_ap == a.ap_id]
        for _, c in ap_clients.iterrows():
            dist = c.distance_m
            rssi = rssi_from_distance(dist)
            snr = np.clip(rssi - nf, -5, 40)
            rty = retry_pct(snr, nonwifi_flag)
            thr = throughput(snr, a.band, a.channel_width_mhz, rty)
            q = qoe(snr, rty)
            client_log.append({
                "timestamp": ts.isoformat(), "client_id": c.client_id,
                "connected_ap": a.ap_id, "band": a.band, "channel": a.channel,
                "rssi_dbm": rssi, "snr_db": snr, "throughput_mbps": thr,
                "retry_rate_pct": rty, "qoe": q,
                "x": c.x, "y": c.y, "distance_m": dist,
                "affected_nonwifi": nonwifi_flag
            })
            ap_snr.append(snr); ap_thr.append(thr); ap_rty.append(rty)
            ap_q.append(q); ap_dist.append(dist)

        ap_log.append({
            "timestamp": ts.isoformat(), "ap_id": a.ap_id, "band": a.band,
            "channel": a.channel, "channel_width_mhz": a.channel_width_mhz,
            "tx_power_dbm": a.tx_power_dbm, "noise_floor_dbm": nf,
            "nwifi_detected": nonwifi_flag,
            "nwifi_types": ",".join(sorted(set(types_here))) if types_here else "none",
            "nwifi_type_count": len(types_here),
            "avg_client_snr_db": float(np.mean(ap_snr)) if ap_snr else 0,
            "throughput_avg_mbps": float(np.mean(ap_thr)) if ap_thr else 0,
            "p95_retry_pct": float(np.percentile(ap_rty, 95)) if ap_rty else 0,
            "mean_qoe": float(np.mean(ap_q)) if ap_q else 0,
            "mean_distance_m": float(np.mean(ap_dist)) if ap_dist else 0,
            "p95_distance_m": float(np.percentile(ap_dist, 95)) if ap_dist else 0,
            "max_distance_m": float(np.max(ap_dist)) if ap_dist else 0,
            "decision_action": "none", "reason_code": "none"
        })

# ---------------- SAVE & SUMMARY ----------------
client_df = pd.DataFrame(client_log)
ap_df_out = pd.DataFrame(ap_log)
fft_df = pd.DataFrame(fft_log)

client_df.to_csv("client_log_24h.csv", index=False)
ap_df_out.to_csv("ap_log_24h.csv", index=False)
fft_df.to_csv("fft_dataset_24h.csv", index=False)

print("\n✅ Simulation complete!")
print(" - client_log_24h.csv")
print(" - ap_log_24h.csv")
print(" - fft_dataset_24h.csv")

# --- Summary stats ---
def summarize(df, cols):
    print("\n📊 Summary Statistics:")
    for c in cols:
        print(f"  {c:<20} → min: {df[c].min():>8.3f},  max: {df[c].max():>8.3f}")

summarize(client_df, ["rssi_dbm", "snr_db", "throughput_mbps", "retry_rate_pct", "qoe", "distance_m"])
summarize(ap_df_out, ["avg_client_snr_db", "throughput_avg_mbps", "p95_retry_pct",
                      "mean_qoe", "mean_distance_m", "p95_distance_m", "max_distance_m"])
print("\nFFT classes:", fft_df["label"].value_counts().to_dict())
