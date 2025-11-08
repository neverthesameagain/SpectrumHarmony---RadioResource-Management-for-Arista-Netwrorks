# ==============================================================
# ARISTA RRM+ Synthetic Dataset Generator v7.2
# --------------------------------------------------------------
# Key features:
#   • 10-second update frequency
#   • More 2.4 GHz samples (60%) to balance dataset
#   • Each non-Wi-Fi interferer = separate FFT + AP row
#   • Runs 3h (test) or 24h (full) using SIM_HOURS flag
#   • Outputs: fft_dataset.csv, ap_log.csv, client_log.csv
# ==============================================================

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import math

# ---------------- CONFIG ----------------
rng = np.random.default_rng(42)
N_AP, CLIENTS_PER_AP, RADIUS_M = 6, 40, 10.0
RSSI_MIN, RSSI_MAX = -70, -30

SIM_HOURS = 24          # 🔁 set to 24 for full day run
SCAN_PERIOD_S = 10      # ⏱️ every 10 seconds
N_STEPS = int(SIM_HOURS * 3600 / SCAN_PERIOD_S)
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
    band = rng.choice(BANDS, p=[0.6, 0.4])  # ✅ more 2.4 GHz APs
    if band == "2.4":
        ch, width, phy = rng.choice(CH_24), 20, PHY_MAX_24
    else:
        ch, width = rng.choice(CH_5), rng.choice(WIDTHS, p=[0.7, 0.25, 0.05])
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
        x, y = ap.x + r * math.cos(θ), ap.y + r * math.sin(θ)
        clients.append({
            "client_id": f"C_{ap.ap_id}_{k+1}",
            "connected_ap": ap.ap_id,
            "band": ap.band, "channel": ap.channel,
            "x": x, "y": y, "distance_m": r
        })
clients_df = pd.DataFrame(clients)

# ---------------- UTILS ----------------
def rssi_from_distance(d, std=1.5):
    base = RSSI_MAX - (d / RADIUS_M) * (RSSI_MAX - RSSI_MIN)
    return float(np.clip(base + rng.normal(0, std), RSSI_MIN, RSSI_MAX))

def noise_floor(band):
    base = -94.5 if band == "2.4" else -96.0
    return float(base + rng.normal(0, 1.5))

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

# ---------------- NON-Wi-Fi GENERATOR ----------------
def generate_nonwifi_events(band, step):
    events = []
    minute = (step * SCAN_PERIOD_S) / 60.0

    # BLE more common in 2.4
    if band == "2.4" and rng.random() < 0.35:
        events.append(("BLE", 2420 + rng.uniform(-10, 10), 1, rng.uniform(0.3, 0.6), rng.uniform(-65, -55)))

    # ZigBee
    if band == "2.4" and rng.random() < 0.25:
        events.append(("ZigBee", 2450 + rng.uniform(-15, 15), 2, rng.uniform(0.2, 0.7), rng.uniform(-68, -58)))

    # Microwave bursts
    if band == "2.4" and (20 <= (minute % 60) <= 30 or 45 <= (minute % 60) <= 55):
        events.append(("Microwave", 2450.0, 20, 0.9, rng.uniform(-60, -50)))

    # FHSS anywhere (small prob)
    if rng.random() < 0.10:
        center = 5200.0 if band == "5" else 2440.0
        events.append(("FHSS", center + rng.uniform(-25, 25), 1, rng.uniform(0.2, 0.6), rng.uniform(-67, -57)))

    return events

# ---------------- SIMULATION ----------------
ap_rows, client_rows, fft_rows = [], [], []
print(f"🚀 Starting simulation ({N_AP} APs, {CLIENTS_PER_AP*N_AP} clients, {SIM_HOURS}h @ {SCAN_PERIOD_S}s)...")

for step in range(N_STEPS):
    ts = START_TS + timedelta(seconds=step * SCAN_PERIOD_S)
    if step % int(3600 / SCAN_PERIOD_S) == 0:
        print(f" ⏱️ Simulated {step * SCAN_PERIOD_S / 3600:.0f}/{SIM_HOURS} hours")

    for _, a in ap_df.iterrows():
        nf = noise_floor(a.band)
        events = generate_nonwifi_events(a.band, step)
        nonwifi_flag = bool(events)

        # ---------- FFT rows ----------
        bins_base = rng.normal(-90, 3, 64)
        if events:
            for (cls, center, bw, duty, pwr) in events:
                bins = bins_base.copy()
                band_range = [2400, 2500] if a.band == "2.4" else [5150, 5850]
                center_bin = int(np.clip(np.round(np.interp(center, band_range, [8, 56])), 1, 62))
                half_bw = max(1, int(round(bw / (20 / 64))))
                bins[center_bin-half_bw:center_bin+half_bw] += pwr - (-90)
                fft_rows.append({
                    "timestamp": ts.isoformat(), "ap_id": a.ap_id,
                    "band": a.band, "channel": a.channel, "label": cls,
                    "center_mhz": center, "bw_mhz": bw, "duty": duty, "power_dbm": pwr,
                    **{f"fft_bin_{i}": float(v) for i, v in enumerate(bins)}
                })
        else:
            fft_rows.append({
                "timestamp": ts.isoformat(), "ap_id": a.ap_id,
                "band": a.band, "channel": a.channel, "label": "wifi",
                **{f"fft_bin_{i}": float(v) for i, v in enumerate(bins_base)}
            })

        # ---------- Client rows ----------
        ap_clients = clients_df[clients_df.connected_ap == a.ap_id]
        snrs, thrs, rtys, qoes, dists = [], [], [], [], []
        for _, c in ap_clients.iterrows():
            d = c.distance_m
            rssi = rssi_from_distance(d)
            snr = np.clip(rssi - nf, -5, 40)
            retry = retry_pct(snr, nonwifi_flag)
            thr = throughput(snr, a.band, a.channel_width_mhz, retry)
            q = qoe(snr, retry)
            client_rows.append({
                "timestamp": ts.isoformat(), "client_id": c.client_id,
                "connected_ap": a.ap_id, "band": a.band, "channel": a.channel,
                "rssi_dbm": rssi, "snr_db": snr, "throughput_mbps": thr,
                "retry_rate_pct": retry, "qoe": q,
                "x": c.x, "y": c.y, "distance_m": d,
                "affected_nonwifi": nonwifi_flag
            })
            snrs.append(snr); thrs.append(thr); rtys.append(retry)
            qoes.append(q); dists.append(d)

        # ---------- AP rows ----------
        if events:
            for (cls, _, _, _, _) in events:
                ap_rows.append({
                    "timestamp": ts.isoformat(), "ap_id": a.ap_id,
                    "band": a.band, "channel": a.channel,
                    "channel_width_mhz": a.channel_width_mhz,
                    "tx_power_dbm": a.tx_power_dbm, "noise_floor_dbm": nf,
                    "nwifi_detected": True, "nwifi_type": cls,
                    "avg_client_snr_db": np.mean(snrs),
                    "throughput_avg_mbps": np.mean(thrs),
                    "p95_retry_pct": np.percentile(rtys, 95),
                    "mean_qoe": np.mean(qoes),
                    "mean_distance_m": np.mean(dists),
                    "p95_distance_m": np.percentile(dists, 95),
                    "max_distance_m": np.max(dists)
                })
        else:
            ap_rows.append({
                "timestamp": ts.isoformat(), "ap_id": a.ap_id,
                "band": a.band, "channel": a.channel,
                "channel_width_mhz": a.channel_width_mhz,
                "tx_power_dbm": a.tx_power_dbm, "noise_floor_dbm": nf,
                "nwifi_detected": False, "nwifi_type": "wifi",
                "avg_client_snr_db": np.mean(snrs),
                "throughput_avg_mbps": np.mean(thrs),
                "p95_retry_pct": np.percentile(rtys, 95),
                "mean_qoe": np.mean(qoes),
                "mean_distance_m": np.mean(dists),
                "p95_distance_m": np.percentile(dists, 95),
                "max_distance_m": np.max(dists)
            })

# ---------------- SAVE ----------------
client_df = pd.DataFrame(client_rows)
ap_df_out = pd.DataFrame(ap_rows)
fft_df = pd.DataFrame(fft_rows)

client_df.to_csv("client_log.csv", index=False)
ap_df_out.to_csv("ap_log.csv", index=False)
fft_df.to_csv("fft_dataset.csv", index=False)

print("\n✅ Simulation complete! Saved:")
print(" - client_log.csv")
print(" - ap_log.csv")
print(" - fft_dataset.csv")

# ---------------- SUMMARY ----------------
def summarize(df, cols, name):
    print(f"\n📊 {name} Summary:")
    for c in cols:
        print(f"  {c:<22} → min={df[c].min():8.3f},  max={df[c].max():8.3f}")

summarize(client_df, ["rssi_dbm","snr_db","throughput_mbps","retry_rate_pct","qoe","distance_m"], "Client")
summarize(ap_df_out, ["avg_client_snr_db","throughput_avg_mbps","p95_retry_pct","mean_qoe","mean_distance_m","p95_distance_m","max_distance_m"], "AP")
print("\nFFT class balance:", fft_df["label"].value_counts().to_dict())
print(f"\n🚀 Done ({SIM_HOURS}h @ {SCAN_PERIOD_S}s ticks)")
