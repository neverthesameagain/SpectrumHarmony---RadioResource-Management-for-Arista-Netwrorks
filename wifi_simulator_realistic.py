#!/usr/bin/env python3
"""
wifi_simulator_realistic.py
Enhanced single-AP WiFi simulator compatible with rmm_online_bo.py.
Generates all required columns including objective_y, rolled_back, and time features.
"""

import math, random, os
from datetime import datetime, timedelta, UTC
import numpy as np
import pandas as pd

# -----------------------
# Simulation parameters
# -----------------------
SIM_SECONDS = 60 * 60 * 3  # 3 hours
STEP_SEC = 1
WINDOW_SEC = 600
WINDOW_MIN = WINDOW_SEC // 60

AP_ID = "AP1"
CHANNEL_WIDTH_DEFAULT = 20
P_TX_DBM = 18.0
NOISE_FLOOR_DBM = -95.0
PL0_DB = 30.0
ETA = 3.0
SHADOW_STD_DB = 3.0
D0 = 1.0

PKT_SIZE_MEAN_BYTES = 1500.0
LAMBDA_MIN, LAMBDA_MAX = 0.1, 3.0
MAX_CLIENTS, INITIAL_CLIENTS = 10, 3
CLIENT_JOIN_PROB, CLIENT_LEAVE_PROB = 0.01, 0.005
CLIENT_RADIUS_MIN, CLIENT_RADIUS_MAX = 2.0, 50.0

OUT_DIR = "sim_out"
AP_OUTFILE = os.path.join(OUT_DIR, "ap_aggregates_for_bo.csv")

RANDOM_SEED = 42
random.seed(RANDOM_SEED)
np.random.seed(RANDOM_SEED)

MAC_BASE_EFF = 0.86
MAC_DEGRADE_PER_CLIENT = 0.02
MAX_RETRIES = 3
PKT_OVERHEAD_SEC = 0.0002

# MCS table
MCS_TABLE = [
    {"mcs": 0, "M": 2, "r": 1/2, "rate_20_mbps": 6.5, "snr_threshold_db": 4.0},
    {"mcs": 3, "M": 16, "r": 1/2, "rate_20_mbps": 26.0, "snr_threshold_db": 13.0},
    {"mcs": 5, "M": 64, "r": 2/3, "rate_20_mbps": 52.0, "snr_threshold_db": 20.0},
    {"mcs": 7, "M": 64, "r": 5/6, "rate_20_mbps": 65.0, "snr_threshold_db": 24.0},
]

def ensure_outdir():
    os.makedirs(OUT_DIR, exist_ok=True)

def Q(x): return 0.5 * math.erfc(x / math.sqrt(2.0))
def ber_bpsk_awgn(ebn0_lin): return Q(math.sqrt(2.0 * ebn0_lin))
def ber_mqam_awgn(ebn0_lin, M):
    k = math.log2(M)
    q = Q(math.sqrt((3*k/(M-1))*ebn0_lin))
    return 2*(1-1/math.sqrt(M))/k * q
def per_from_ber(ber, Nbits): return 1-(1-ber)**Nbits

def pathloss_db(d): return PL0_DB + 10*ETA*math.log10(max(d,D0)/D0) + np.random.normal(0, SHADOW_STD_DB)
def snr_db(tx_dbm, dist): return tx_dbm - pathloss_db(dist) - NOISE_FLOOR_DBM

def select_mcs(snr_db, channel_width_mhz):
    best = {"rate_mbps": 0.0, "per": 1.0}
    for entry in MCS_TABLE:
        M, r = entry["M"], entry["r"]
        snr_lin = 10**(snr_db/10)
        ebn0 = snr_lin / (math.log2(M)*r)
        ber = ber_bpsk_awgn(ebn0) if M == 2 else ber_mqam_awgn(ebn0, M)
        per = per_from_ber(ber, 1500*8)
        rate = entry["rate_20_mbps"] * (channel_width_mhz/20)
        eff = rate*(1-per)
        if eff > best["rate_mbps"]:
            best = {"rate_mbps": rate, "per": per}
    return best

class Client:
    def __init__(self, cid, dist):
        self.cid = cid
        self.dist = dist

def run_sim(sim_seconds=SIM_SECONDS, tx_dbm=P_TX_DBM, channel_width_mhz=CHANNEL_WIDTH_DEFAULT):
    ensure_outdir()
    clients = {f"C{i}": Client(f"C{i}", random.uniform(CLIENT_RADIUS_MIN, CLIENT_RADIUS_MAX))
               for i in range(1, INITIAL_CLIENTS + 1)}
    next_cid = INITIAL_CLIENTS + 1
    rows = []
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    window_start_t = 0
    t = 0

    while t < sim_seconds:
        if len(clients) < MAX_CLIENTS and random.random() < CLIENT_JOIN_PROB:
            clients[f"C{next_cid}"] = Client(f"C{next_cid}", random.uniform(CLIENT_RADIUS_MIN, CLIENT_RADIUS_MAX))
            next_cid += 1
        for cid in [cid for cid in clients if random.random() < CLIENT_LEAVE_PROB]:
            del clients[cid]
        active = list(clients.values())
        N = len(active)
        if N == 0:
            t += STEP_SEC
            continue
        mac_eff = max(0.3, MAC_BASE_EFF - MAC_DEGRADE_PER_CLIENT * (N - 1))
        thr = []
        retry_pct = []
        for c in active:
            snr = snr_db(tx_dbm, c.dist)
            res = select_mcs(snr, channel_width_mhz)
            eff_thr = res["rate_mbps"] * mac_eff * (1 - res["per"]) * 0.9
            thr.append(eff_thr)
            retry_pct.append(res["per"] * 100)
        if t - window_start_t >= WINDOW_SEC:
            ts_start = now + timedelta(seconds=window_start_t)
            ts_end = now + timedelta(seconds=t)
            med_thr = np.median(thr)
            med_rtt = np.median([random.uniform(10, 50) for _ in active])
            stalls = np.mean([tp < 3.0 for tp in thr])
            busy = 100*(1 - mac_eff)
            neighbor = random.uniform(5, 30)

            # Derived QoE metric
            y_obj = (med_thr / 100.0) - 0.01 * med_rtt - 0.5 * stalls

            # Time features
            hour = ts_start.hour + ts_start.minute/60.0
            sin_time = math.sin(2*math.pi*hour/24)
            cos_time = math.cos(2*math.pi*hour/24)

            rows.append({
                "timestamp_start": ts_start.isoformat(sep=' '),
                "timestamp_end": ts_end.isoformat(sep=' '),
                "sin_time": sin_time,
                "cos_time": cos_time,
                "ap_id": AP_ID,
                "channel_width_mhz": channel_width_mhz,
                "tx_power_dbm": tx_dbm,
                "num_clients": N,
                "client_median_throughput_mbps": med_thr,
                "client_median_rtt_ms": med_rtt,
                "sensing_cca_busy_pct": busy,
                "aggregate_neighbor_load_pct": neighbor,
                "client_video_stalls_frac": stalls,
                "client_retries_pct": np.mean(retry_pct),
                "window_minutes": WINDOW_MIN,
                "objective_y": y_obj,
                "rolled_back": False,
                "policy_msg": "Simulated policy: static"
            })
            window_start_t = t
        t += STEP_SEC

    df = pd.DataFrame(rows)
    df.to_csv(AP_OUTFILE, index=False)
    print(f"[✓] Saved BO-compatible WiFi simulation data → {AP_OUTFILE}")

if __name__ == "__main__":
    run_sim()