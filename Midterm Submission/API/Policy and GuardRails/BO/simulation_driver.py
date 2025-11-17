import os, time
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from wifi_simulator_single_sample import simulate_wifi_sample
from rmm_online_bo import PolicyEngine, run_online_iteration

CSV_PATH = "sim_out/ap_aggregates_LHS_day0.csv"
OUT_DIR = "bo_results"
DAYS = 20                   
SAMPLES_PER_DAY = 24         
HOURS_PER_SAMPLE = 1         
SIM_START_TIME = datetime(2025, 11, 1, 0, 0, 0, tzinfo=timezone.utc)
OBSS_PD_MIN, OBSS_PD_MAX = -82, -62

CHANGE_BUDGET_PER_PERIOD = 1
CHANGE_MONITORING_PERIOD_DAYS = 5
MAX_DELTA_PWR_DB = 2.0
ROLLBACK_TH = 0.10
QUIET_HOURS = None  

policy = PolicyEngine(
    slo_p95_retries_pct = 8.0,    
    changecap_per_day = CHANGE_BUDGET_PER_PERIOD,        
    change_window_days = CHANGE_MONITORING_PERIOD_DAYS,      
    max_delta_pwr_db = MAX_DELTA_PWR_DB,      
    rollback_threshold = ROLLBACK_TH,
    quiet_hours = QUIET_HOURS     
)


import rmm_online_bo_old

SIM_CLOCK = SIM_START_TIME
def get_sim_time(): return SIM_CLOCK
rmm_online_bo_old.datetime_now = get_sim_time
print("Patched rmm_online_bo to use simulated clock")

def next_fake_timestamp(base_time, sample_idx):
    return base_time + timedelta(hours=sample_idx)

current_time = SIM_START_TIME

prev_median_throughput = None
prev_p95_retries = None
THROUGHPUT_DROP_THRESHOLD = 0.03  
RETRIES_INCREASE_THRESHOLD = 0.08  


for day in range(1,DAYS+1):
    print(f"\n Simulating Day {day} (SimTime={current_time.isoformat(sep=' ')})")

    if os.path.exists(CSV_PATH):
        df = pd.read_csv(CSV_PATH)
        last_row = df.sort_values('timestamp_start').iloc[-1]
        tx = float(last_row['tx_power_dbm'])
        width = int(last_row['channel_width_mhz'])
        obss = float(last_row.get('obss_pd_dbm', -72))
    else:
        tx, width, obss = 15.0, 40, -72

    rows = []
    for i in range(SAMPLES_PER_DAY):
        sim_time = SIM_START_TIME + timedelta(days=day, hours=i)
        sample = simulate_wifi_sample(tx, width, obss_pd_dbm=obss, sim_time=sim_time)
        rows.append(sample)

        ts_start = next_fake_timestamp(current_time, i)
        ts_end = ts_start + timedelta(minutes=10)
        sample["timestamp_start"] = ts_start.isoformat(sep=' ')
        sample["timestamp_end"] = ts_end.isoformat(sep=' ')
        sample["policy_msg"] = f"day{day}_hour{i}"
        rows.append(sample)

    df_new = pd.DataFrame(rows)
    os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)
    if os.path.exists(CSV_PATH):
        df_new.to_csv(CSV_PATH, mode='a', index=False, header=False)
    else:
        df_new.to_csv(CSV_PATH, index=False)

    median_thr = df_new["client_median_throughput_mbps"].median()
    p95_retries = np.percentile(df_new["client_retries_pct"], 95)

    print(f"Day {day} summary: median_thr={median_thr:.2f} Mbps, p95_retries={p95_retries:.2f}%")

    trigger_bo = False
    if prev_median_throughput is not None:
        thr_drop = (prev_median_throughput - median_thr) / prev_median_throughput
        retries_increase = (p95_retries - prev_p95_retries) / (prev_p95_retries + 1e-6)

        if thr_drop > THROUGHPUT_DROP_THRESHOLD:
            print(f"Throughput dropped by {thr_drop*100:.1f}% → Trigger BO")
            trigger_bo = True
        elif retries_increase > RETRIES_INCREASE_THRESHOLD:
            print(f"Retries increased by {retries_increase*100:.1f}% → Trigger BO")
            trigger_bo = True
        else:
            print("Performance stable; skipping BO this day.")
    else:
        print("ℹNo previous baseline; skipping BO for first day.")

    prev_median_throughput = median_thr
    prev_p95_retries = p95_retries

    current_time += timedelta(days=1)
    SIM_CLOCK = current_time
    rmm_online_bo_old.datetime_now = get_sim_time

    if trigger_bo:
        print(f"Running Bayesian Optimization for simulated day {day}...")
        run_online_iteration(CSV_PATH, OUT_DIR, policy=policy)
        print(f"Completed BO iteration for day {day}.")
    else:
        print(f"No BO triggered for day {day}.")

    time.sleep(0.3)

print("Simulation complete!")
