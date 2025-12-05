#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ARISTA RRM+ Unified Synthetic Data Generator (Final v13, multi-floor, optimized)
-------------------------------------------------------------------------------

Outputs (per floor, combined 3 days):

  • data/floor<F>_all3days/Aplog_all_channels.csv
      → AP-level telemetry (all APs, all bands, all channels)

  • data/floor<F>_all3days/Aplog_<band>_GHz_<ch>.csv
      → per-band / per-channel AP telemetry

  • data/floor<F>_all3days/fft_dataset.csv
      → FFT snapshots with non-Wi-Fi labels (wifi/BLE/ZigBee/Microwave/FHSS/Radar)

  • data/floor<F>_all3days/FFT_<band>_GHz_<ch>.csv
      → per-band / per-channel FFT slices

  • data/floor<F>_all3days/sensing_events.csv
      → per-event table (center freq / bw / duty / class / confidence)

  • data/floor<F>_all3days/interference_edges.csv
      → AP–AP interaction edges over time (subsampled snapshots for scale)

  • docs/floor<F>_all3days/airtime_cost.txt
      → sensing airtime ratio

  • docs/floor<F>_all3days/kpi_summary.csv
      → KPI summary (including edge clients)

  • docs/floor<F>_all3days/schema.md
      → column dictionary and units

Bands: 2.4 GHz + 5 GHz (DFS included)
Non-Wi-Fi classes: BLE, ZigBee, Microwave, FHSS, Radar
Physics: FSPL + log-distance (n≈2.6) + shadowing (σ≈3.5 dB)
Noise: −174 + 10 log₁₀(B) + NF (+ 1 dB jitter)
Airtime: Wi-Fi + non-Wi-Fi + sensing (< 2 % target)
"""

import os
import math
import random
import argparse
import logging
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict

import numpy as np
import pandas as pd

# =============================================================================
# Logging
# =============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("RRMPlusSim")

# =============================================================================
# Constants / Globals
# =============================================================================

SEED = int(os.getenv("RRMPLUS_SEED", "42"))
np.random.seed(SEED)
random.seed(SEED)

OUT = Path("data")
DOCS = Path("docs")
for p in (OUT, DOCS):
    p.mkdir(exist_ok=True, parents=True)

CH24 = list(range(1, 15))
DFS_CH = [52, 56, 60, 64,
          100, 104, 108, 112,
          116, 120, 124, 128,
          132, 136, 140, 144]
CH5 = [36, 40, 44, 48] + DFS_CH + [149, 153, 157, 161]

WIDTHS = [20, 40, 80]
PHY_MAX_24, PHY_MAX_5 = 72.2, 433.0  # nominal single-stream PHY
WIDTH_SCALE = {20: 1.0, 40: 1.7, 80: 3.0}

DEFAULT_SIM_HOURS = 1.0
DEFAULT_SCAN_PERIOD = 10.0
DEFAULT_SENSING_TIME = 0.12
CLIENTS_PER_AP = 20
CELL_R = 12.0

RSSI_MIN, RSSI_MAX = -94.0, -30.0
NF_24, NF_5 = 6.0, 6.5

FFT_CLASSES = ["wifi", "BLE", "ZigBee", "Microwave", "FHSS", "Radar"]

DIURNAL_24 = np.array([
    0.20, 0.18, 0.16, 0.16, 0.18, 0.25,
    0.35, 0.55, 0.70, 0.78, 0.82, 0.85,
    0.88, 0.90, 0.92, 0.95, 0.96, 0.92,
    0.85, 0.75, 0.60, 0.50, 0.40, 0.30
])

# Edge-building performance knob: take one AP–AP snapshot every N ticks
EDGE_SNAPSHOT_STRIDE = 6  # e.g., with 10 s scan → one snapshot per minute

# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class AP:
    id: str
    band: str
    ch: int
    width: int
    tx: float
    x: float
    y: float
    phy: float
    gain: float = 2.0


@dataclass
class Client:
    id: str
    apid: str
    x: float
    y: float
    d: float   # initial radial distance (kept as a “cell radius” proxy)


# =============================================================================
# Helpers
# =============================================================================

def width_scale(w: int) -> float:
    return WIDTH_SCALE.get(w, 1.0)


def ch2mhz(band: str, ch: int) -> float:
    return 2407 + 5 * ch if band == "2.4" else 5000 + 5 * ch


def noise_floor_dbm(band: str, bw_mhz: float) -> float:
    base = -174 + 10 * math.log10(bw_mhz * 1e6)
    nf = NF_24 if band == "2.4" else NF_5
    return base + nf + np.random.normal(0, 1.2)


def fspl_db(d: float, f_mhz: float) -> float:
    # d in meters, f in MHz
    return 20 * math.log10(max(d, 0.1)) + 20 * math.log10(f_mhz) - 27.55


def rssi_dbm_vector(dists: np.ndarray, ap: AP) -> np.ndarray:
    """
    Vectorized approximate RSSI model for all clients of an AP.
    Keeps physics similar to scalar version but faster.
    """
    f = ch2mhz(ap.band, ap.ch)
    eirp = ap.tx + ap.gain
    # Pathloss at 1 m
    pl0 = fspl_db(1.0, f)
    d_eff = np.maximum(dists, 1.0)
    pl = pl0 + 10 * 2.6 * np.log10(d_eff)
    shadow = np.random.normal(0, 3.5, size=dists.shape)
    rssi = eirp - pl + shadow
    return np.clip(rssi, RSSI_MIN, RSSI_MAX)


def retry_pct_from_snr_vec(snr: np.ndarray, interf_index: float) -> np.ndarray:
    base = 100.0 / (1.0 + np.exp(0.38 * (snr - 18.0)))
    noise = np.random.normal(0.0, 2.0, size=snr.shape)
    return np.clip(base + 35.0 * interf_index + noise, 0.0, 100.0)


def throughput_from_snr_vec(snr: np.ndarray, band: str, width: int,
                            retry_pct: np.ndarray) -> np.ndarray:
    phy_base = PHY_MAX_24 if band == "2.4" else PHY_MAX_5
    phy = phy_base * width_scale(width)
    eff = np.clip((snr + 5.0) / 40.0, 0.0, 1.0) * (1.0 - retry_pct / 120.0)
    jitter = 0.9 + np.random.rand(*snr.shape) * 0.12
    thr = phy * eff * jitter
    return np.maximum(thr, 0.0)


def qoe_from_vec(snr: np.ndarray, retry_pct: np.ndarray) -> np.ndarray:
    s = np.clip((snr + 5.0) / 40.0, 0.0, 1.0)
    r = 1.0 - np.clip(retry_pct / 50.0, 0.0, 1.0)
    return 5.0 * (0.7 * s + 0.3 * r)


def uplink_per_from_snr_vec(snr: np.ndarray) -> np.ndarray:
    return 100.0 / (1.0 + np.exp(0.3 * (snr - 15.0)))


def diurnal_frac(ts: datetime) -> float:
    return float(DIURNAL_24[ts.hour])


def overlap_ratio(band: str, ch: int, w: float, cf: float, bw: float) -> float:
    """AP vs event spectral overlap fraction."""
    if bw <= 0:
        return 0.0
    a_center = ch2mhz(band, ch)
    a_lo, a_hi = a_center - w / 2.0, a_center + w / 2.0
    e_lo, e_hi = cf - bw / 2.0, cf + bw / 2.0
    inter = max(0.0, min(a_hi, e_hi) - max(a_lo, e_lo))
    denom = max(a_hi - a_lo, 1e-6)
    return inter / denom


def channel_overlap_ratio_aps(ap_a: AP, ap_b: AP) -> float:
    """Symmetric spectral overlap fraction between two APs on same band."""
    if ap_a.band != ap_b.band:
        return 0.0
    fA = ch2mhz(ap_a.band, ap_a.ch)
    fB = ch2mhz(ap_b.band, ap_b.ch)
    a_lo, a_hi = fA - ap_a.width / 2.0, fA + ap_a.width / 2.0
    b_lo, b_hi = fB - ap_b.width / 2.0, fB + ap_b.width / 2.0
    inter = max(0.0, min(a_hi, b_hi) - max(a_lo, b_lo))
    denom = max(ap_a.width, ap_b.width)
    return float(inter / denom) if denom > 0 else 0.0


# =============================================================================
# AP / Client Generation
# =============================================================================

def gen_aps() -> list[AP]:
    """
    Generate a grid of APs: all 2.4 GHz + all 5 GHz channels (including DFS).
    """
    xs = np.linspace(0, 66, 14)
    ys = np.linspace(0, 44, 8)
    coords = [(float(x), float(y)) for y in ys for x in xs]

    aps: list[AP] = []
    k = 0

    # 2.4 GHz (20 MHz channels)
    for ch in CH24:
        tx = float(np.random.randint(14, 21))
        aps.append(
            AP(
                id=f"AP24_{ch}",
                band="2.4",
                ch=ch,
                width=20,
                tx=tx,
                x=coords[k][0],
                y=coords[k][1],
                phy=PHY_MAX_24
            )
        )
        k += 1

    # 5 GHz (20/40/80 MHz, more conservative on DFS)
    for ch in CH5:
        if ch in DFS_CH and np.random.rand() < 0.9:
            w = 20
        else:
            w = int(np.random.choice(WIDTHS, p=[0.7, 0.25, 0.05]))
        tx = float(np.random.randint(14, 23))
        aps.append(
            AP(
                id=f"AP5_{ch}",
                band="5",
                ch=ch,
                width=w,
                tx=tx,
                x=coords[k][0],
                y=coords[k][1],
                phy=PHY_MAX_5 * width_scale(w)
            )
        )
        k += 1

    return aps


def gen_clients(aps: list[AP]) -> list[Client]:
    """
    CLIENTS_PER_AP per AP, in a disc of radius CELL_R.
    d is stored as initial radius (we keep it as a fixed-scale factor).
    """
    cs: list[Client] = []
    for a in aps:
        for i in range(CLIENTS_PER_AP):
            r = CELL_R * math.sqrt(np.random.rand())
            t = np.random.rand() * 2 * math.pi
            x = a.x + r * math.cos(t)
            y = a.y + r * math.sin(t)
            cs.append(Client(
                id=f"C_{a.id}_{i}",
                apid=a.id,
                x=x,
                y=y,
                d=r
            ))
    return cs


def random_walk(cs: list[Client]) -> None:
    """
    Small Gaussian random walk for each client (per scan tick).
    """
    for c in cs:
        c.x += np.random.normal(0, 0.15)
        c.y += np.random.normal(0, 0.15)


# =============================================================================
# Core Simulator (Single Floor / Single Window)
# =============================================================================

def run(sim_hours: float,
        scan_period: float,
        sense_time: float,
        start_ts: str,
        orchestrated: bool = False) -> None:
    """
    Run a single continuous simulation window (one floor).
    Writes all CSVs into the current OUT/DOCS globals.
    """
    log.info("=" * 80)
    log.info("[RUN] New simulation window")
    log.info("[RUN] Start time      = %s", start_ts)
    log.info("[RUN] Duration        = %.2f hours", sim_hours)
    log.info("[RUN] Scan period     = %.2f s", scan_period)
    log.info("[RUN] Sensing time    = %.3f s", sense_time)
    log.info("[RUN] Orchestrated    = %s", orchestrated)
    log.info("=" * 80)

    # APs and clients
    log.info("[RUN] Generating APs...")
    aps = gen_aps()
    log.info("[RUN] Total APs = %d", len(aps))

    log.info("[RUN] Generating clients...")
    cs = gen_clients(aps)
    log.info("[RUN] Total clients = %d", len(cs))

    # Precompute mapping: AP_ID → indices of clients
    ap_to_client_idx: Dict[str, list[int]] = {ap.id: [] for ap in aps}
    for idx, c in enumerate(cs):
        ap_to_client_idx[c.apid].append(idx)

    n_steps = int(sim_hours * 3600 / scan_period)
    start_dt = datetime.fromisoformat(start_ts)

    ap_rows = []
    fft_rows = []
    event_rows = []

    total_sense = 0.0
    total_time = 0.0

    log.info("[RUN] Starting simulation: %d steps (~%.2f hours)", n_steps, sim_hours)

    for step in range(n_steps):
        # Progress every 5%
        if step % max(1, n_steps // 20) == 0:
            pct = (step / n_steps) * 100.0
            log.info("[RUN] Progress: %5.1f%% (%d / %d steps)", pct, step, n_steps)

        ts = start_dt + timedelta(seconds=step * scan_period)
        random_walk(cs)

        for a in aps:
            idxs = ap_to_client_idx.get(a.id, [])

            # Noise floor per AP
            nf = noise_floor_dbm(a.band, a.width)
            # Diurnal load modifier
            load = np.clip(
                (0.25 + 0.75 * diurnal_frac(ts)) *
                (1.1 if a.band == "2.4" else 1.0) *
                (0.8 + 0.4 * np.random.rand()),
                0.05, 0.98
            )
            busy_wifi = scan_period * load * 0.55

            # Non-Wi-Fi label for this tick
            label = random.choices(
                FFT_CLASSES,
                weights=[0.5, 0.1, 0.1, 0.1, 0.1, 0.1]
            )[0]
            if a.band == "5" and a.ch in DFS_CH:
                p_radar = 0.25 if not orchestrated else 0.12
                if np.random.rand() < p_radar:
                    label = "Radar"

            # FFT bins base (around noise floor)
            bins = np.random.normal(nf - 3.0, 3.0, 64)

            # Event spectral params
            ev_center = ch2mhz(a.band, a.ch)
            ch_bw = 0.0
            ev_duty = 0.0
            ev_power = nf - 10.0

            if label == "Radar":
                ch_bw = float(np.random.choice([1, 5, 10, float(a.width)]))
                ev_duty = float(np.random.uniform(0.02, 0.2))
                ev_power = float(nf + np.random.uniform(-30, 5))
                ev_center = float(ev_center + np.random.uniform(-10, 10))
            elif label == "FHSS":
                ch_bw = float(np.random.uniform(1, 10))
                ev_duty = float(np.random.uniform(0.1, 0.5))
                ev_center = float(ev_center + ((step % 5) - 2) * 5)
                ev_power = float(nf + np.random.uniform(-25, -10))
            elif label != "wifi":
                ch_bw = float(np.random.uniform(1, min(40, a.width)))
                ev_duty = float(np.random.uniform(0.05, 0.8))
                ev_power = float(np.random.uniform(nf - 40, nf - 10))
                ev_center = float(ev_center + np.random.uniform(-30, 30))

            ovl = overlap_ratio(a.band, a.ch, a.width, ev_center, ch_bw)
            ovl_eff = ovl * (0.75 if orchestrated and label != "wifi" else 1.0)
            nonwifi_time = scan_period * ovl_eff * ev_duty * 0.65
            interf_index = float(np.clip(np.random.rand() * (0.7 if orchestrated else 1.0), 0.0, 1.0))

            # Client-side metrics (vectorized)
            if idxs:
                dists = np.array([cs[i].d for i in idxs], dtype=float)
                rssi_arr = rssi_dbm_vector(dists, a)
                snr_arr = rssi_arr - nf
                retry_arr = retry_pct_from_snr_vec(snr_arr, interf_index)
                thr_arr = throughput_from_snr_vec(snr_arr, a.band, a.width, retry_arr)
                qoe_arr = qoe_from_vec(snr_arr, retry_arr)
                per_arr = uplink_per_from_snr_vec(snr_arr)
            else:
                # synthetic placeholder client
                dists = np.array([CELL_R * 0.7], dtype=float)
                rssi_arr = rssi_dbm_vector(dists, a)
                snr_arr = rssi_arr - nf
                retry_arr = retry_pct_from_snr_vec(snr_arr, interf_index)
                thr_arr = throughput_from_snr_vec(snr_arr, a.band, a.width, retry_arr)
                qoe_arr = qoe_from_vec(snr_arr, retry_arr)
                per_arr = uplink_per_from_snr_vec(snr_arr)

            avg_snr = float(np.mean(snr_arr))
            avg_thr = float(np.mean(thr_arr))
            p95r = float(np.percentile(retry_arr, 95))
            mean_qoe = float(np.mean(qoe_arr))
            avg_per = float(np.mean(per_arr))
            mean_rssi = float(np.mean(rssi_arr))

            busy = float(np.clip(busy_wifi + sense_time + nonwifi_time, 0.0, scan_period))
            airtime = busy / scan_period * 100.0

            total_sense += sense_time
            total_time += scan_period

            # FFT row
            fft_row = dict(
                timestamp=ts.isoformat(),
                ap_id=a.id,
                band=a.band,
                channel=a.ch,
                label=label,
                center_mhz=ev_center,
                bw_mhz=ch_bw,
                duty=ev_duty,
                power_dbm=ev_power,
                **{f"fft_bin_{i}": float(b) for i, b in enumerate(bins)}
            )
            fft_rows.append(fft_row)

            # Sensing event row
            conf = float(np.clip(
                np.random.beta(8, 2) if label != "wifi" else np.random.beta(2, 8),
                0.0, 1.0
            ))
            event_rows.append(dict(
                timestamp=ts.isoformat(),
                ap_id=a.id,
                band=a.band,
                channel=a.ch,
                center_freq_mhz=ev_center,
                bandwidth_mhz=ch_bw,
                duty_cycle=ev_duty,
                class_label=label,
                confidence=conf
            ))

            # AP-level telemetry row
            ap_rows.append(dict(
                TIMESTAMP=ts.isoformat(),
                AP_ID=a.id,
                BAND=a.band,
                CHANNEL=a.ch,
                CHANNEL_WIDTH=a.width,
                TX_POWER_DBM=a.tx,
                NOISE_FLOOR_DBM=nf,
                AVG_CLIENT_SNR_DB=avg_snr,
                THROUGHPUT_AVG_Mbps=avg_thr,
                P95_RETRY_PCT=p95r,
                MEAN_QOE=mean_qoe,
                UL_PER=avg_per,
                BUSY_TIME=busy,
                TOTAL_TIME=scan_period,
                AIRTIME_UTILIZATION=airtime,
                NWIFI_DETECTED=(label != "wifi"),
                NWIFI_TYPE=label,
                CLIENTS=len(idxs),
                MEAN_RSSI_DBM=mean_rssi,
                CENTER_MHZ=ch2mhz(a.band, a.ch)
            ))

    # Convert to DataFrames
    ap_df = pd.DataFrame(ap_rows)
    fft_df = pd.DataFrame(fft_rows)
    evt_df = pd.DataFrame(event_rows)

    log.info("[RUN] Completed simulation window: %.2f hours", sim_hours)
    log.info("[RUN] AP rows    = %d", len(ap_rows))
    log.info("[RUN] FFT rows   = %d", len(fft_rows))
    log.info("[RUN] Event rows = %d", len(event_rows))

    # -------------------------------------------------------------------------
    # AP–AP INTERFERENCE EDGES
    # -------------------------------------------------------------------------
    log.info("[RUN] Building AP–AP interference edges (subsample stride=%d)...",
             EDGE_SNAPSHOT_STRIDE)

    ap_static: Dict[str, AP] = {ap.id: ap for ap in aps}
    edge_rows = []

    if not ap_df.empty:
        grouped = ap_df.groupby(["TIMESTAMP", "BAND"])
        for snap_idx, ((ts_str, band), sub) in enumerate(grouped):
            # Subsample snapshots for scale
            if snap_idx % EDGE_SNAPSHOT_STRIDE != 0:
                continue

            sub = sub.reset_index(drop=True)
            n = len(sub)
            if n < 2:
                continue

            for i in range(n):
                rowA = sub.iloc[i]
                ap_id_a = rowA["AP_ID"]
                apA = ap_static.get(ap_id_a)
                if apA is None:
                    continue

                for j in range(i + 1, n):
                    rowB = sub.iloc[j]
                    ap_id_b = rowB["AP_ID"]
                    apB = ap_static.get(ap_id_b)
                    if apB is None:
                        continue

                    if apA.band != apB.band:
                        continue

                    dist = math.hypot(apA.x - apB.x, apA.y - apB.y)
                    freq_mhz = ch2mhz(band, int(rowA["CHANNEL"]))
                    pl = fspl_db(max(dist, 0.1), freq_mhz)

                    airtime_a = float(rowA["AIRTIME_UTILIZATION"]) / 100.0
                    airtime_b = float(rowB["AIRTIME_UTILIZATION"]) / 100.0
                    load_min = min(airtime_a, airtime_b)
                    load_max = max(airtime_a, airtime_b)

                    retry_a = float(rowA["P95_RETRY_PCT"]) / 100.0
                    retry_b = float(rowB["P95_RETRY_PCT"]) / 100.0
                    retry_max = max(retry_a, retry_b)

                    nwifi_a = bool(rowA["NWIFI_DETECTED"])
                    nwifi_b = bool(rowB["NWIFI_DETECTED"])
                    type_a = str(rowA["NWIFI_TYPE"])
                    type_b = str(rowB["NWIFI_TYPE"])
                    radar_penalty = 1.0 if (type_a == "Radar" or type_b == "Radar") else 0.0

                    overlap = channel_overlap_ratio_aps(apA, apB)

                    pr_est = apA.tx + apA.gain - pl
                    pr_norm = float(np.clip((pr_est + 100.0) / 70.0, 0.0, 1.0))

                    dist_score = math.exp(-dist / 30.0)

                    edge_weight = (
                        0.20 * dist_score +
                        0.30 * overlap +
                        0.20 * load_min +
                        0.15 * retry_max +
                        0.10 * pr_norm +
                        0.05 * radar_penalty
                    )

                    edge_rows.append(dict(
                        TIMESTAMP=ts_str,
                        BAND=band,
                        AP_A=ap_id_a,
                        AP_B=ap_id_b,
                        DIST_M=dist,
                        PATHLOSS_DB=pl,
                        CHANNEL_A=int(rowA["CHANNEL"]),
                        CHANNEL_B=int(rowB["CHANNEL"]),
                        WIDTH_A_MHZ=int(rowA["CHANNEL_WIDTH"]),
                        WIDTH_B_MHZ=int(rowB["CHANNEL_WIDTH"]),
                        TX_A_DBM=float(rowA["TX_POWER_DBM"]),
                        TX_B_DBM=float(rowB["TX_POWER_DBM"]),
                        AIRTIME_A=airtime_a,
                        AIRTIME_B=airtime_b,
                        LOAD_MIN=load_min,
                        LOAD_MAX=load_max,
                        P95_RETRY_A=retry_a,
                        P95_RETRY_B=retry_b,
                        NWIFI_DETECTED_A=nwifi_a,
                        NWIFI_DETECTED_B=nwifi_b,
                        NWIFI_TYPE_A=type_a,
                        NWIFI_TYPE_B=type_b,
                        CHANNEL_OVERLAP=overlap,
                        RX_POWER_EST_NORM=pr_norm,
                        DIST_SCORE=dist_score,
                        RADAR_PENALTY=radar_penalty,
                        EDGE_WEIGHT=edge_weight
                    ))

    edges_df = pd.DataFrame(edge_rows) if edge_rows else pd.DataFrame()
    log.info("[RUN] Edge rows = %d", len(edges_df))

    # -------------------------------------------------------------------------
    # CSV OUTPUTS
    # -------------------------------------------------------------------------
    log.info("[RUN] Writing CSV outputs into %s ...", OUT)

    req_cols = [
        "TIMESTAMP", "AP_ID", "BAND", "CHANNEL", "CHANNEL_WIDTH",
        "TX_POWER_DBM", "NOISE_FLOOR_DBM",
        "AVG_CLIENT_SNR_DB", "THROUGHPUT_AVG_Mbps",
        "P95_RETRY_PCT", "MEAN_QOE", "UL_PER",
        "BUSY_TIME", "TOTAL_TIME", "AIRTIME_UTILIZATION",
        "NWIFI_DETECTED", "NWIFI_TYPE"
    ]

    ap_df.to_csv(
        OUT / "Aplog_all_channels.csv",
        index=False,
        columns=req_cols + [c for c in ap_df.columns if c not in req_cols]
    )
    fft_df.to_csv(OUT / "fft_dataset.csv", index=False)
    evt_df.to_csv(OUT / "sensing_events.csv", index=False)
    if not edges_df.empty:
        edges_df.to_csv(OUT / "interference_edges.csv", index=False)

    # Per-band / per-channel splits
    for (band, ch), sub in ap_df.groupby(["BAND", "CHANNEL"]):
        fname = f"Aplog_{band.replace('.', '_')}_GHz_{ch}.csv"
        sub.to_csv(
            OUT / fname,
            index=False,
            columns=req_cols + [c for c in sub.columns if c not in req_cols]
        )

    if not fft_df.empty:
        for (band, ch), sub in fft_df.groupby(["band", "channel"]):
            fname = f"FFT_{band.replace('.', '_')}_GHz_{ch}.csv"
            sub.to_csv(OUT / fname, index=False)

    # -------------------------------------------------------------------------
    # Airtime + KPIs + Schema
    # -------------------------------------------------------------------------
    sense_ratio = total_sense / total_time if total_time > 0 else 0.0
    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "airtime_cost.txt").write_text(
        f"sensing_airtime_ratio={sense_ratio:.4f}\n"
    )

    edge_mask = (ap_df["MEAN_RSSI_DBM"] >= -70) & (ap_df["MEAN_RSSI_DBM"] <= -65)
    edge_sub = ap_df[edge_mask]

    kpi = pd.DataFrame([dict(
        sim_hours=sim_hours,
        tick_seconds=scan_period,
        aps_total=ap_df["AP_ID"].nunique(),
        mean_qoe_all=float(ap_df["MEAN_QOE"].mean()),
        p95_retry_all=float(ap_df["P95_RETRY_PCT"].quantile(0.95)),
        ul_per_all=float(ap_df["UL_PER"].mean()),
        mean_qoe_edge=float(edge_sub["MEAN_QOE"].mean()) if len(edge_sub) else np.nan,
        p95_retry_edge=float(edge_sub["P95_RETRY_PCT"].quantile(0.95)) if len(edge_sub) else np.nan,
        ul_per_edge=float(edge_sub["UL_PER"].mean()) if len(edge_sub) else np.nan,
        sensing_airtime_ratio=sense_ratio,
        orchestrated=int(orchestrated)
    )])
    kpi.to_csv(DOCS / "kpi_summary.csv", index=False)

    schema = f"""# RRM+ Simulator Schema v13

### Global outputs
- Aplog_all_channels.csv         → AP-level telemetry over time
- fft_dataset.csv                → FFT snapshots + labels
- sensing_events.csv             → Non-Wi-Fi / Radar event stream
- interference_edges.csv         → AP–AP interference graph edges over time
- Per-band/per-channel Aplog_*.csv and FFT_*.csv splits
- airtime_cost.txt, kpi_summary.csv, schema.md

### Aplog_all_channels.csv
TIMESTAMP,AP_ID,BAND,CHANNEL,CHANNEL_WIDTH,TX_POWER_DBM,NOISE_FLOOR_DBM,
AVG_CLIENT_SNR_DB,THROUGHPUT_AVG_Mbps,P95_RETRY_PCT,MEAN_QOE,UL_PER,
BUSY_TIME,TOTAL_TIME,AIRTIME_UTILIZATION,NWIFI_DETECTED,NWIFI_TYPE,
CLIENTS,MEAN_RSSI_DBM,CENTER_MHZ

### interference_edges.csv (AP–AP interactions)
TIMESTAMP,BAND,AP_A,AP_B,DIST_M,PATHLOSS_DB,CHANNEL_A,CHANNEL_B,
WIDTH_A_MHZ,WIDTH_B_MHZ,TX_A_DBM,TX_B_DBM,
AIRTIME_A,AIRTIME_B,LOAD_MIN,LOAD_MAX,
P95_RETRY_A,P95_RETRY_B,
NWIFI_DETECTED_A,NWIFI_DETECTED_B,NWIFI_TYPE_A,NWIFI_TYPE_B,
CHANNEL_OVERLAP,RX_POWER_EST_NORM,DIST_SCORE,RADAR_PENALTY,EDGE_WEIGHT
"""
    (DOCS / "schema.md").write_text(schema)

    log.info("Simulation complete. Airtime=%.2f%%  CSVs in %s",
             sense_ratio * 100.0, OUT)


# =============================================================================
# Multi-Floor / Multi-Day Wrapper
# =============================================================================

def run_floor_all_days(
        floors: int = 2,
        days: int = 3,
        hours_per_day: float = 24.0,
        scan: float = DEFAULT_SCAN_PERIOD,
        sense: float = DEFAULT_SENSING_TIME,
        orchestrated: bool = False,
        start_date: str = "2025-11-02"
) -> None:
    """
    Run a continuous multi-day simulation per floor.
    Each floor produces ONE combined dataset for all days:

        data/floor<F>_all<D>days/*
        docs/floor<F>_all<D>days/*
    """
    global OUT, DOCS, SEED

    total_hours = days * hours_per_day

    log.info("=" * 100)
    log.info("[MULTI-FLOOR] Starting multi-floor simulation")
    log.info("[MULTI-FLOOR] Floors       = %d", floors)
    log.info("[MULTI-FLOOR] Days/floor   = %d", days)
    log.info("[MULTI-FLOOR] Hours/floor  = %.2f", total_hours)
    log.info("=" * 100)

    for floor in range(1, floors + 1):
        # Different seed per floor (for variety but reproducible)
        floor_seed = SEED + floor * 100
        np.random.seed(floor_seed)
        random.seed(floor_seed)

        OUT = Path(f"data/floor{floor}_all{days}days")
        DOCS = Path(f"docs/floor{floor}_all{days}days")
        OUT.mkdir(parents=True, exist_ok=True)
        DOCS.mkdir(parents=True, exist_ok=True)

        start_dt = datetime.fromisoformat(start_date).replace(
            hour=0, minute=0, second=0
        )

        log.info("-" * 80)
        log.info("[FLOOR %d] Starting %d-day simulation", floor, days)
        log.info("[FLOOR %d] Output directory = %s", floor, OUT)
        log.info("[FLOOR %d] Start timestamp  = %s", floor, start_dt.isoformat())
        log.info("[FLOOR %d] Total hours      = %.2f", floor, total_hours)
        log.info("-" * 80)

        run(
            sim_hours=total_hours,
            scan_period=scan,
            sense_time=sense,
            start_ts=start_dt.isoformat(),
            orchestrated=orchestrated
        )

        log.info("[FLOOR %d] Finished full %d-day generation.", floor, days)

    log.info("=" * 100)
    log.info("[MULTI-FLOOR] All floors complete.")
    log.info("=" * 100)


# =============================================================================
# CLI
# =============================================================================

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--hours", type=float, default=DEFAULT_SIM_HOURS,
                   help="(Unused in floor-all-days mode; kept for backward compat)")
    p.add_argument("--scan", type=float, default=DEFAULT_SCAN_PERIOD)
    p.add_argument("--sense", type=float, default=DEFAULT_SENSING_TIME)
    p.add_argument("--start", type=str, default="2025-11-02T00:00:00")
    p.add_argument("--orchestrated", type=int, default=0)
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()

    # Your requested mode: 2 floors, 3 days per floor, 24h/day
    run_floor_all_days(
        floors=2,
        days=3,
        hours_per_day=24.0,
        scan=args.scan,
        sense=args.sense,
        orchestrated=bool(args.orchestrated),
        start_date=args.start.split("T")[0]
    )
