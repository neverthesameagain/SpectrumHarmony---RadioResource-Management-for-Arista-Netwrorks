import os, time
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta

from wifi_simulator_single_sample import simulate_wifi_sample

CSV_PATH = "sim_out/random_baseline.csv"
OUT_DIR = "random_baseline_results"
DAYS = 20
SAMPLES_PER_DAY = 24
SIM_START_TIME = datetime(2025, 11, 1, 0, 0, 0, tzinfo=timezone.utc)

TX_POWER_RANGE = [5, 7, 9, 11, 13, 15, 17, 19]            
CHANNEL_WIDTHS = [20, 40, 60, 80, 160]                    
OBSS_PD_RANGE = (-82, -62)                                

def next_fake_timestamp(base_time, sample_idx):
    return base_time + timedelta(hours=sample_idx)

current_time = SIM_START_TIME
os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)
os.makedirs(OUT_DIR, exist_ok=True)

for day in range(1, DAYS + 1):

    RANDOM_TX = float(np.random.choice(TX_POWER_RANGE))
    RANDOM_WIDTH = int(np.random.choice(CHANNEL_WIDTHS))
    RANDOM_OBSS = float(np.random.uniform(*OBSS_PD_RANGE))

    print(f"\nDay {day} — RANDOM CONFIG")
    print(f"   → tx_power_dbm       = {RANDOM_TX}")
    print(f"   → channel_width_mhz  = {RANDOM_WIDTH}")
    print(f"   → obss_pd_dbm        = {RANDOM_OBSS:.2f}")

    rows = []

    for hour in range(SAMPLES_PER_DAY):
        sim_time = SIM_START_TIME + timedelta(days=day, hours=hour)

        sample = simulate_wifi_sample(
            RANDOM_TX,
            RANDOM_WIDTH,
            obss_pd_dbm=RANDOM_OBSS,
            sim_time=sim_time
        )

        ts_start = next_fake_timestamp(current_time, hour)
        ts_end = ts_start + timedelta(minutes=10)

        sample["timestamp_start"] = ts_start.isoformat(sep=" ")
        sample["timestamp_end"] = ts_end.isoformat(sep=" ")
        sample["policy_msg"] = f"RANDOM_day{day}_hour{hour}"
        sample["rolled_back"] = False

        rows.append(sample)

    df_new = pd.DataFrame(rows)
    if os.path.exists(CSV_PATH):
        df_new.to_csv(CSV_PATH, mode="a", index=False, header=False)
    else:
        df_new.to_csv(CSV_PATH, index=False)

    median_thr = df_new["client_median_throughput_mbps"].median()
    p95_retries = np.percentile(df_new["client_retries_pct"], 95)

    print(f"Day {day} summary:")
    print(f"   → Median throughput = {median_thr:.2f} Mbps")
    print(f"   → P95 retries       = {p95_retries:.2f}%")

    current_time += timedelta(days=1)
    time.sleep(0.15)

print("\n RANDOM CONFIG 20-DAY SIM COMPLETE")
print(f"Results saved to: {CSV_PATH}")
