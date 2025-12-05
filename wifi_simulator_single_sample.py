#!/usr/bin/env python3

import math, random, os, argparse
from datetime import datetime, UTC, timedelta
import numpy as np
import pandas as pd

AP_ID = "AP1"
NOISE_FLOOR_DBM = -95.0
PL0_DB = 30.0
ETA = 3.0
SHADOW_STD_DB = 3.0
D0 = 1.0

MAX_CLIENTS = 10
CLIENT_RADIUS_MIN, CLIENT_RADIUS_MAX = 2.0, 50.0
MAC_BASE_EFF = 0.86
MAC_DEGRADE_PER_CLIENT = 0.02

# OBSS-PD related
OBSS_PD_MIN = -82.0
OBSS_PD_MAX = -62.0

RANDOM_SEED = 42
random.seed(RANDOM_SEED)
np.random.seed(RANDOM_SEED)

MCS_TABLE = [
    {"mcs": 0, "M": 2, "r": 1/2, "rate_mbps": 6.5, "snr_threshold_db": 4.0},
    {"mcs": 3, "M": 16, "r": 1/2, "rate_mbps": 26.0, "snr_threshold_db": 13.0},
    {"mcs": 5, "M": 64, "r": 2/3, "rate_mbps": 52.0, "snr_threshold_db": 20.0},
    {"mcs": 7, "M": 64, "r": 5/6, "rate_mbps": 65.0, "snr_threshold_db": 24.0},
]

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
        rate = entry["rate_mbps"] * (channel_width_mhz/20)
        eff = rate*(1-per)
        if eff > best["rate_mbps"]:
            best = {"rate_mbps": rate, "per": per}
    return best

def simulate_wifi_sample(tx_dbm, channel_width_mhz, obss_pd_dbm=None, window_minutes: int = 10, sim_time = None) -> dict:

    if obss_pd_dbm is None:
        obss_pd_dbm = OBSS_PD_MAX
    obss_pd_dbm = float(np.clip(obss_pd_dbm, OBSS_PD_MIN, OBSS_PD_MAX))
    tx_dbm = float(np.clip(tx_dbm, 5, 23))
    channel_width_mhz = int(np.clip(channel_width_mhz, 20, 160))

    now = sim_time if sim_time is not None else datetime.now(UTC)
    hour = now.hour + now.minute / 60.0
    sin_time = math.sin(2 * math.pi * hour / 24)
    cos_time = math.cos(2 * math.pi * hour / 24)

    min_clients, max_clients = 2, MAX_CLIENTS
    frac_load = 0.5 * (1 + math.sin(2 * math.pi * (hour - 6) / 24))  
    expected_clients = int(round(min_clients + frac_load * (max_clients - min_clients)))
    N = max(1, expected_clients + np.random.randint(-3, 4)) 

    mac_eff = max(0.3, MAC_BASE_EFF - MAC_DEGRADE_PER_CLIENT * (N - 1))
    thr, retry_pct = [], []

    aggressiveness = (obss_pd_dbm - OBSS_PD_MIN) / (OBSS_PD_MAX - OBSS_PD_MIN)  
    contention_factor = 1.0 - 0.45 * aggressiveness      
    interference_factor = 1.0 + 1.3 * aggressiveness      

    for _ in range(N):
        dist = random.uniform(CLIENT_RADIUS_MIN, CLIENT_RADIUS_MAX)
        snr = snr_db(tx_dbm, dist)
        res = select_mcs(snr, channel_width_mhz)

        eff_thr = res["rate_mbps"] * (channel_width_mhz / 20) * mac_eff * contention_factor * (1 - res["per"])
        thr.append(eff_thr)
        retry_pct.append(res["per"] * 100 * interference_factor)

    med_thr = np.median(thr)
    med_rtt = np.median([random.uniform(10, 50) for _ in range(N)])
    stalls = np.mean([tp < 3.0 for tp in thr])

    busy = 100 * (1 - mac_eff * contention_factor)
    neighbor = random.uniform(10, 60) * (1.0 + 0.5 * aggressiveness)

    width_factor = channel_width_mhz / 20  
    load_penalty = (N / MAX_CLIENTS) * (width_factor ** 1.2)
    interference_penalty = 0.002 * (tx_dbm - 15) ** 2 + 0.005 * load_penalty
    obss_penalty = 0.05 * aggressiveness ** 2

    y_obj = (
        (med_thr / 100.0)
        - 0.01 * med_rtt
        - 0.6 * stalls
        - interference_penalty
        - obss_penalty
        + np.random.normal(0, 0.015) 
    )

    ts_start = now
    ts_end = now + timedelta(minutes=window_minutes)
    return {
        "timestamp_start": ts_start.isoformat(sep=' '),
        "timestamp_end": ts_end.isoformat(sep=' '),
        "sin_time": sin_time,
        "cos_time": cos_time,
        "ap_id": AP_ID,
        "channel_width_mhz": channel_width_mhz,
        "tx_power_dbm": tx_dbm,
        "obss_pd_dbm": obss_pd_dbm,
        "num_clients": N,
        "client_median_throughput_mbps": med_thr,
        "client_median_rtt_ms": med_rtt,
        "sensing_cca_busy_pct": busy,
        "aggregate_neighbor_load_pct": neighbor,
        "client_video_stalls_frac": stalls,
        "client_retries_pct": np.mean(retry_pct),
        "window_minutes": window_minutes,
        "objective_y": y_obj,
        "rolled_back": False,
        "policy_msg": ""
    }
