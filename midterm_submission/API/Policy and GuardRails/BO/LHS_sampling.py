from wifi_simulator_single_sample import simulate_wifi_sample
import pandas as pd
import numpy as np
import os
from datetime import datetime, timedelta, timezone

NUM_SAMPLES = 24                
TX_MIN, TX_MAX = 10, 23
CHANNEL_WIDTHS = [20, 40, 80, 160]
OBSS_PD_MIN, OBSS_PD_MAX = -82, -62 
OUT_DIR = "sim_out"

def latin_hypercube_sampling(n_samples, n_dims=1):
    rng = np.random.default_rng(seed=42)
    cut = np.linspace(0, 1, n_samples + 1)
    u = rng.random((n_samples, n_dims))
    lhs = np.zeros_like(u)
    for j in range(n_dims):
        lhs[:, j] = u[:, j] * (cut[1:] - cut[:-1]) + cut[:-1]
        rng.shuffle(lhs[:, j])
    return lhs

lhs_samples = latin_hypercube_sampling(NUM_SAMPLES, n_dims=2)  # 2D: tx_power + OBSS-PD
tx_powers = TX_MIN + (TX_MAX - TX_MIN) * lhs_samples[:, 0]
obss_vals = OBSS_PD_MIN + (OBSS_PD_MAX - OBSS_PD_MIN) * lhs_samples[:, 1]
widths = np.random.choice(CHANNEL_WIDTHS, size=NUM_SAMPLES)

samples = []
start_time = datetime(2025, 11, 1, 0, 0, 0, tzinfo=timezone.utc)  # fake UTC start

for i, (tx, width, obss) in enumerate(zip(tx_powers, widths, obss_vals)):
    sim_time = start_time + timedelta(hours=i)  # ⏰ advance 1 hour per sample
    row = simulate_wifi_sample(tx, width, obss_pd_dbm=obss, sim_time=sim_time)
    samples.append(row)

    ts_start = start_time + timedelta(hours=i)
    ts_end = ts_start + timedelta(minutes=10)
    row["timestamp_start"] = ts_start.isoformat(sep=' ')
    row["timestamp_end"] = ts_end.isoformat(sep=' ')
    row["policy_msg"] = f"hour_{i:02d}"
    samples.append(row)

os.makedirs(OUT_DIR, exist_ok=True)
outfile = os.path.join(OUT_DIR, "ap_aggregates_LHS_day0.csv")

df = pd.DataFrame(samples)
df.to_csv(outfile, index=False)

print(f"Saved {NUM_SAMPLES} hourly simulated samples with UTC timestamps to {outfile}")
