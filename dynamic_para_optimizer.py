#!/usr/bin/env python3
"""
rmm_online_bo.py

Continuous file-driven simulated BO + PolicyEngine loop.

- Watches a CSV (same file) for new rows per-AP.
- Retrains simulator (RF) from full CSV when new data arrives for an AP.
- Runs one BO iteration (GP + EI) for that AP, pre-checks via PolicyEngine.
- Simulates applying candidate and measures simulated metrics.
- Appends simulated observation row into the same CSV (so the file grows).
- Keeps learning incrementally until stopped (Ctrl+C).

This is a simulated demo — replace simulation stubs with real controller APIs
for live deployments.
"""
import os, sys, time, json, argparse, joblib
from datetime import datetime, timezone, timedelta
from copy import deepcopy

import numpy as np
import pandas as pd
from scipy.stats import norm
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import Matern, ConstantKernel as C, WhiteKernel
from sklearn.metrics import r2_score, mean_absolute_error
import warnings
warnings.filterwarnings("ignore")

# ----------------------------
# CONFIG
# ----------------------------
WINDOW_MIN = 10
STABILIZE_MIN = 1            # simulated wait minutes (kept short for online demo)
N_INIT_SYNTH = 8
GP_NOISE = 1e-6
EI_XI = 1e-3
MAX_DELTA_PWR_DB = 2.0
CHANGE_BUDGET_PER_DAY = 3
TX_POWER_MIN = 5.0
TX_POWER_MAX = 20.0
CHANNEL_WIDTHS = [20, 40, 80, 160]
RISKY_REJECT_FACTOR = 0.20
ROLLBACK_TH = 0.10

RANDOM_SEED = 42
np.random.seed(RANDOM_SEED)

# ----------------------------
# Policy engine (keeps constraints)
# ----------------------------
from collections import deque
class PolicyEngine:
    def __init__(self,
                 slo_p95_retries_pct=8.0,
                 changecap_per_day=CHANGE_BUDGET_PER_DAY,
                 max_delta_pwr_db=MAX_DELTA_PWR_DB,
                 rollback_threshold=ROLLBACK_TH,
                 require_manual_approval=False,
                 quiet_hours=None):
        self.slo_p95_retries_pct = float(slo_p95_retries_pct)
        self.changecap_per_day = int(changecap_per_day)
        self.max_delta_pwr_db = float(max_delta_pwr_db)
        self.rollback_threshold = float(rollback_threshold)
        self.require_manual_approval = require_manual_approval
        self.quiet_hours = quiet_hours or []
        self._ap_change_history = {}  # ap_id -> deque of datetimes
        self._ap_cooloff_until = {}

    def _ensure_ap(self, ap_id):
        if ap_id not in self._ap_change_history:
            self._ap_change_history[ap_id] = deque()

    def _prune_old_changes(self, ap_id, now):
        self._ensure_ap(ap_id)
        dq = self._ap_change_history[ap_id]
        cutoff = now - timedelta(hours=24)
        while dq and dq[0] < cutoff:
            dq.popleft()

    def record_change(self, ap_id, when=None):
        when = when or datetime.now(timezone.utc)
        self._ensure_ap(ap_id)
        self._ap_change_history[ap_id].append(when)

    def changes_last_24h(self, ap_id, now=None):
        now = now or datetime.now(timezone.utc)
        self._prune_old_changes(ap_id, now)
        return len(self._ap_change_history.get(ap_id, []))

    def set_cooloff(self, ap_id, until_ts):
        self._ap_cooloff_until[ap_id] = until_ts

    def in_cooloff(self, ap_id, now=None):
        now = now or datetime.now(timezone.utc)
        t = self._ap_cooloff_until.get(ap_id)
        return (t is not None) and (now < t)

    def in_quiet_hours(self, now=None):
        if not self.quiet_hours:
            return False
        now = now or datetime.now()
        h = now.hour + now.minute / 60.0
        for s,e in self.quiet_hours:
            if s <= e:
                if s <= h < e:
                    return True
            else:
                if h >= s or h < e:
                    return True
        return False

    def pre_check_candidate(self, ap_id, current_cfg, candidate, simulator_pred=None, predicted_retries_pct=None, now=None):
        now = now or datetime.now(timezone.utc)
        if self.in_cooloff(ap_id, now):
            return False, f"AP {ap_id} in cooloff until {self._ap_cooloff_until.get(ap_id)}"
        if self.in_quiet_hours(now):
            return False, "Within quiet hours; changes disallowed."
        if self.changes_last_24h(ap_id, now) >= self.changecap_per_day:
            return False, "Change budget exhausted for 24h window."
        if abs(candidate.get('tx_power_dbm', current_cfg.get('tx_power_dbm')) - current_cfg.get('tx_power_dbm')) > self.max_delta_pwr_db + 1e-9:
            return False, f"Delta tx power exceeds max per-change ({self.max_delta_pwr_db} dB)."
        if predicted_retries_pct is not None:
            if predicted_retries_pct > self.slo_p95_retries_pct:
                return False, f"Predicted P95 retries {predicted_retries_pct:.2f}% exceeds SLO {self.slo_p95_retries_pct}%."
        if self.require_manual_approval:
            return False, "Manual approval required by policy."
        return True, "OK"

    def post_check_observation(self, ap_id, baseline_obj, observed_obj, now=None):
        now = now or datetime.now(timezone.utc)
        if observed_obj is None:
            self.set_cooloff(ap_id, now + timedelta(hours=4))
            return False, "Measurement failed - recommend rollback & cooloff"
        if observed_obj < baseline_obj * (1.0 - self.rollback_threshold):
            self.set_cooloff(ap_id, now + timedelta(hours=4))
            return False, f"Observed objective {observed_obj:.4f} below rollback threshold relative to baseline {baseline_obj:.4f}"
        self.record_change(ap_id, now)
        return True, "Accepted"

# ----------------------------
# helpers & core functions
# ----------------------------
def ensure_dir(d):
    if not os.path.exists(d):
        os.makedirs(d)

def fit_simulator(df, feature_cols=None):
    df_local = df.copy()
    df_local['log_num_clients'] = np.log1p(df_local['num_clients'])
    if feature_cols is None:
        feature_cols = ['channel_width_mhz','tx_power_dbm','log_num_clients','sensing_cca_busy_pct','aggregate_neighbor_load_pct','sin_time','cos_time']
    X = df_local[feature_cols].fillna(0.0).astype(float)
    y = df_local['objective_y'].astype(float)
    if len(X) < 10:
        # small data fallback: use medians to create trivial predictor
        from sklearn.dummy import DummyRegressor
        dr = DummyRegressor(strategy='mean')
        dr.fit(X, y)
        return dr, feature_cols
    rf = RandomForestRegressor(n_estimators=100, max_depth=10, random_state=RANDOM_SEED)
    rf.fit(X, y)
    return rf, feature_cols

def latin_hypercube_tx(n_samples, low, high):
    cut = np.linspace(0,1,n_samples+1)
    rng = np.random.RandomState(RANDOM_SEED)
    points = cut[:-1] + rng.rand(n_samples)*(1.0/n_samples)
    txs = low + points*(high-low)
    return txs

def create_initial_dataset(df_hist, simulator, feature_cols, n_synth=N_INIT_SYNTH):
    df = df_hist.copy()
    df['log_num_clients'] = np.log1p(df['num_clients'])
    cont_cols = ['tx_power_dbm','log_num_clients','sensing_cca_busy_pct','aggregate_neighbor_load_pct','sin_time','cos_time']
    widths = CHANNEL_WIDTHS
    enc = OneHotEncoder(categories=[widths], sparse_output=False, handle_unknown='ignore')
    width_reshaped = df[['channel_width_mhz']]
    try:
        enc_mat = enc.fit_transform(width_reshaped)
    except Exception:
        # fallback if insufficient categories
        enc = OneHotEncoder(categories=[widths], sparse_output=False, handle_unknown='ignore')
        enc_mat = enc.fit_transform(pd.DataFrame([widths]*len(df), columns=['channel_width_mhz']))
    cat_names = [f"width_{w}" for w in enc.categories_[0]]
    X_cat = pd.DataFrame(enc_mat, columns=cat_names, index=df.index)
    X_cont = df[cont_cols].astype(float).fillna(0.0)
    X_hist = pd.concat([X_cat, X_cont], axis=1)
    scaler = StandardScaler()
    X_hist_scaled = scaler.fit_transform(X_hist)
    y_hist = df['objective_y'].values.astype(float)
    X_all = X_hist_scaled
    y_all = y_hist
    # synth
    if n_synth > 0:
        txs = latin_hypercube_tx(n_synth, TX_POWER_MIN, TX_POWER_MAX)
        rng = np.random.RandomState(RANDOM_SEED)
        median_ctx = df.median(numeric_only=True)
        X_synth = []
        y_synth = []
        for i in range(n_synth):
            w = int(rng.choice(widths))
            p = float(txs[i])
            ctx = {
                'log_num_clients': float(np.log1p(median_ctx['num_clients'])) if 'num_clients' in median_ctx else 1.0,
                'sensing_cca_busy_pct': float(median_ctx.get('sensing_cca_busy_pct',0.0)),
                'aggregate_neighbor_load_pct': float(median_ctx.get('aggregate_neighbor_load_pct',0.0)),
                'sin_time': float(np.sin(2*np.pi*median_ctx['time_of_day_hour']/24.0)) if 'time_of_day_hour' in median_ctx else 0.0,
                'cos_time': float(np.cos(2*np.pi*median_ctx['time_of_day_hour']/24.0)) if 'time_of_day_hour' in median_ctx else 1.0
            }
            sim_in = np.array([[w, p, ctx['log_num_clients'], ctx['sensing_cca_busy_pct'], ctx['aggregate_neighbor_load_pct'], ctx['sin_time'], ctx['cos_time']]])
            try:
                yhat = float(simulator.predict(sim_in)[0])
            except Exception:
                yhat = np.mean(y_hist) if len(y_hist)>0 else 0.5
            one_hot = [1.0 if w==W else 0.0 for W in widths]
            row = np.array(one_hot + [p, ctx['log_num_clients'], ctx['sensing_cca_busy_pct'], ctx['aggregate_neighbor_load_pct'], ctx['sin_time'], ctx['cos_time']])
            X_synth.append(row)
            y_synth.append(yhat)
        X_synth = np.vstack(X_synth)
        X_synth_scaled = scaler.transform(pd.DataFrame(X_synth, columns=cat_names+cont_cols))
        X_all = np.vstack([X_hist_scaled, X_synth_scaled])
        y_all = np.concatenate([y_hist, np.array(y_synth)])
    metadata = {'onehot_names': cat_names, 'cont_cols': cont_cols, 'scaler': scaler, 'encoder': enc}
    return X_all, y_all, metadata

def fit_gp(X, y):
    kernel = C(1.0, (1e-3, 1e3)) * Matern(length_scale=np.ones(X.shape[1]), nu=2.5) + WhiteKernel(noise_level=GP_NOISE)
    gpr = GaussianProcessRegressor(kernel=kernel, alpha=1e-6, normalize_y=True, n_restarts_optimizer=2, random_state=RANDOM_SEED)
    gpr.fit(X, y)
    return gpr

def expected_improvement(mu, sigma, best, xi=EI_XI):
    sigma = np.maximum(sigma, 1e-9)
    z = (mu - best - xi)/sigma
    ei = (mu - best - xi)*norm.cdf(z) + sigma*norm.pdf(z)
    ei[sigma<=0.0] = 0.0
    return ei

def generate_candidates(current_cfg, n_local=8, n_global=8):
    candidates = []
    widths = CHANNEL_WIDTHS
    p = current_cfg['tx_power_dbm']
    for dp in [0, -1, 1, -2, 2]:
        val = float(np.clip(p + dp, TX_POWER_MIN, TX_POWER_MAX))
        candidates.append({'channel_width_mhz': current_cfg['channel_width_mhz'], 'tx_power_dbm': val})
    for w in widths:
        if w == current_cfg['channel_width_mhz']: continue
        for dp in [0, 1, -1]:
            val = float(np.clip(p + dp, TX_POWER_MIN, TX_POWER_MAX))
            candidates.append({'channel_width_mhz': w, 'tx_power_dbm': val})
    rng = np.random.RandomState(RANDOM_SEED)
    for _ in range(n_global):
        w = int(rng.choice(widths))
        val = float(rng.uniform(TX_POWER_MIN, TX_POWER_MAX))
        candidates.append({'channel_width_mhz': w, 'tx_power_dbm': val})
    uniq = {}
    for c in candidates:
        key = (int(c['channel_width_mhz']), round(float(c['tx_power_dbm']),2))
        uniq[key] = c
    return list(uniq.values())

def build_gp_rows(candidates, median_context, meta):
    rows = []
    for cand in candidates:
        widths = CHANNEL_WIDTHS
        one_hot = [1.0 if int(cand['channel_width_mhz'])==W else 0.0 for W in widths]
        cont = [float(cand['tx_power_dbm']), median_context['log_num_clients'], median_context['sensing_cca_busy_pct'], median_context['aggregate_neighbor_load_pct'], median_context['sin_time'], median_context['cos_time']]
        row = np.array(one_hot + cont).reshape(1,-1)
        row_scaled = meta['scaler'].transform(row)
        rows.append((cand, row_scaled.reshape(-1)))
    X_cand = np.vstack([r[1] for r in rows])
    cand_list = [r[0] for r in rows]
    return cand_list, X_cand

def simulate_apply_and_measure(candidate, simulator, median_context):
    """
    Simulate applying a candidate configuration and measuring resulting performance.
    Returns a dict with objective, throughput, rtt, and retries, without writing to CSV.
    """
    w = int(candidate['channel_width_mhz'])
    p = float(candidate['tx_power_dbm'])
    sim_in = np.array([[w, p,
                        median_context['log_num_clients'],
                        median_context['sensing_cca_busy_pct'],
                        median_context['aggregate_neighbor_load_pct'],
                        median_context['sin_time'],
                        median_context['cos_time']]])
    try:
        yhat = float(simulator.predict(sim_in)[0])
    except Exception:
        yhat = 0.5

    # heuristic mapping from objective to metrics
    base_throughput = 100.0  # Mbps scale
    throughput = np.clip(base_throughput * yhat + np.random.normal(scale=3.0), 1.0, 1000.0)
    rtt = np.clip(10 + (1.0 - yhat)*100 + np.random.normal(scale=5.0), 1.0, 500.0)
    retries = np.clip((1.0 - yhat)*20 + np.random.normal(scale=1.5), 0.0, 100.0)
    objective = float(yhat + np.random.normal(scale=0.01))

    return {
        "objective_y": objective,
        "throughput_mbps": float(throughput),
        "rtt_ms": float(rtt),
        "retries_pct": float(retries)
    }

def simulate_apply_and_measure_realistic(candidate, window_minutes=10):
    """
    Calls your realistic WiFi simulator and returns the same format as before.
    """
    from wifi_simulator_single_sample import simulate_wifi_sample  # import your function

    tx = candidate['tx_power_dbm']
    width = candidate['channel_width_mhz']

    sample = simulate_wifi_sample(tx, width, window_minutes=window_minutes)

    # Map to metrics (throughput, rtt, retries)
    throughput = sample['client_median_throughput_mbps']
    rtt = sample['client_median_rtt_ms']
    retries = 0.01  # or simulate if you have a more detailed model
    objective = sample['objective_y']

    return {
        "objective_y": float(objective),
        "throughput_mbps": float(throughput),
        "rtt_ms": float(rtt),
        "retries_pct": float(retries),
    }


# ----------------------------
# File-watch + online loop
# ----------------------------
def load_and_preprocess_for_online(csv_path):
    df = pd.read_csv(csv_path, parse_dates=['timestamp_start','timestamp_end'])
    df['timestamp_start'] = pd.to_datetime(df['timestamp_start'], errors='coerce')
    df['timestamp_end'] = pd.to_datetime(df['timestamp_end'], errors='coerce')

    # ensure window alignment
    if 'window_minutes' in df.columns:
        df = df[df['window_minutes']==WINDOW_MIN].copy()
    required = ['timestamp_start','timestamp_end','ap_id','channel_width_mhz','tx_power_dbm','num_clients','client_median_throughput_mbps','client_median_rtt_ms']
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    fill_zero = ['sensing_cca_busy_pct','aggregate_neighbor_load_pct','client_video_stalls_frac','client_retries_pct']
    for c in fill_zero:
        if c not in df.columns:
            df[c] = 0.0
    # impute per AP
    impute_cols = ['client_median_throughput_mbps','client_median_rtt_ms','client_retries_pct']
    for col in impute_cols:
        if col in df.columns:
            df[col] = df.groupby('ap_id')[col].transform(lambda x: x.fillna(x.median()))
    if 'time_of_day_hour' not in df.columns:
        df['time_of_day_hour'] = df['timestamp_start'].dt.hour + df['timestamp_start'].dt.minute/60.0
    if 'weekday' not in df.columns:
        df['weekday'] = df['timestamp_start'].dt.weekday
    df['tx_power_dbm'] = df['tx_power_dbm'].clip(TX_POWER_MIN, TX_POWER_MAX)
    # compute objective (same as original)
    df2 = df.copy()
    def minmax_group(x):
        mn, mx = x.min(), x.max()
        if mx - mn < 1e-9:
            return pd.Series(np.zeros(len(x)), index=x.index)
        return (x - mn) / (mx - mn)
    df2['t_n'] = df2.groupby('ap_id')['client_median_throughput_mbps'].transform(minmax_group)
    df2['r_n'] = df2.groupby('ap_id')['client_median_rtt_ms'].transform(minmax_group)
    df2['s_n'] = df2.groupby('ap_id')['client_video_stalls_frac'].transform(minmax_group)
    df2['objective_y'] = 0.6*df2['t_n'] + 0.2*(1 - df2['r_n']) + 0.2*(1 - df2['s_n'])
    df2 = df2.sort_values(['ap_id','timestamp_start'])
    df2['prev_objective_ewma'] = df2.groupby('ap_id')['objective_y'].transform(lambda x: x.shift(1).ewm(alpha=0.2).mean().fillna(method='bfill').fillna(0.0))
    df2['log_num_clients'] = np.log1p(df2['num_clients'])
    df2['sin_time'] = np.sin(2*np.pi*df2['time_of_day_hour']/24.0)
    df2['cos_time'] = np.cos(2*np.pi*df2['time_of_day_hour']/24.0)
    return df2

def append_row_to_csv(csv_path, row):
    df_row = pd.DataFrame([row])
    # keep column order by reading head of file if exists
    if os.path.exists(csv_path):
        df_orig = pd.read_csv(csv_path, nrows=1)
        cols = list(df_orig.columns)
        # ensure all columns exist
        for c in df_row.columns:
            if c not in cols:
                cols.append(c)
        df_row = df_row.reindex(columns=cols)
        df_row.to_csv(csv_path, mode='a', index=False, header=False)
    else:
        df_row.to_csv(csv_path, index=False)

def run_online_loop(csv_path, out_dir, simulate=True, poll_interval=5.0, quiet_hours=None):
    ensure_dir(out_dir)
    policy = PolicyEngine(quiet_hours=quiet_hours or [])
    last_seen = {}  # ap_id -> last timestamp_start seen (datetime)
    models = {}     # ap_id -> dict(simulator, feature_cols, gp, meta, X_used, y_used, current_cfg, baseline)
    print("Starting online loop. Press Ctrl+C to stop.")
    try:
        while True:
            try:
                df = load_and_preprocess_for_online(csv_path)
            except Exception as e:
                print("Failed to read CSV:", e)
                time.sleep(poll_interval)
                continue
            df = df.dropna(subset=['ap_id'])
            df['ap_id'] = df['ap_id'].astype(str)
            ap_ids = sorted(df['ap_id'].unique())
            now = datetime.now(timezone.utc)
            for ap_id in ap_ids:
                print(datetime.now(timezone.utc), "Starting AP", ap_id)
                hist_ap = df[df['ap_id']==ap_id].copy()
                if hist_ap.empty: continue
                latest_ts = hist_ap['timestamp_start'].max()
                if ap_id in last_seen and latest_ts <= last_seen[ap_id]:
                    # no new data for this AP
                    continue
                # new data detected for this AP
                print(f"\n[AP {ap_id}] New data detected (latest {latest_ts}) - retraining & iterating")
                last_seen[ap_id] = latest_ts
                # compute baseline median objective from history
                baseline = float(hist_ap['objective_y'].median())
                # train simulator on full history
                simulator, feature_cols = fit_simulator(hist_ap)
                print(datetime.now(timezone.utc), "Simulator fitted")
                # build warm-start dataset and GP
                X_all, y_all, meta = create_initial_dataset(hist_ap, simulator, feature_cols, n_synth=N_INIT_SYNTH)
                try:
                    gpr = fit_gp(X_all, y_all)
                except Exception as e:
                    print("GP fit failed:", e)
                    gpr = None
                print(datetime.now(timezone.utc), "GP fitted")
                # bookkeeping
                models[ap_id] = {
                    'simulator': simulator,
                    'feature_cols': feature_cols,
                    'gpr': gpr,
                    'meta': meta,
                    'X_used': X_all.copy(),
                    'y_used': y_all.copy(),
                }
                # get current cfg = last observed config
                last_row = hist_ap.sort_values('timestamp_start').iloc[-1]
                current_cfg = {'channel_width_mhz': int(last_row['channel_width_mhz']), 'tx_power_dbm': float(last_row['tx_power_dbm'])}
                median_ctx_row = hist_ap.median(numeric_only=True)
                median_context = {
                    'log_num_clients': float(np.log1p(median_ctx_row['num_clients'])) if 'num_clients' in median_ctx_row else 1.0,
                    'sensing_cca_busy_pct': float(median_ctx_row.get('sensing_cca_busy_pct',0.0)),
                    'aggregate_neighbor_load_pct': float(median_ctx_row.get('aggregate_neighbor_load_pct',0.0)),
                    'sin_time': float(np.sin(2*np.pi*median_ctx_row['time_of_day_hour']/24.0)) if 'time_of_day_hour' in median_ctx_row else 0.0,
                    'cos_time': float(np.cos(2*np.pi*median_ctx_row['time_of_day_hour']/24.0)) if 'time_of_day_hour' in median_ctx_row else 1.0
                }
                # generate candidates & evaluate EI if GP exists
                if models[ap_id]['gpr'] is None:
                    print("No GP available; skipping BO for this AP.")
                    continue
                candidates = generate_candidates(current_cfg)
                cand_list, X_cand = build_gp_rows(candidates, median_context, meta)
                mu, sigma = models[ap_id]['gpr'].predict(X_cand, return_std=True)
                ei = expected_improvement(mu, sigma, best=np.max(models[ap_id]['y_used']))
                order = np.argsort(-ei)
                selected = None
                selected_mu = selected_sigma = selected_yhat = None
                # pick candidate passing pre-checks
                for idx in order:
                    cand = deepcopy(cand_list[idx])
                    # clamp per-change delta
                    if abs(cand['tx_power_dbm'] - current_cfg['tx_power_dbm']) > MAX_DELTA_PWR_DB + 1e-9:
                        cand['tx_power_dbm'] = float(np.clip(cand['tx_power_dbm'], current_cfg['tx_power_dbm'] - MAX_DELTA_PWR_DB, current_cfg['tx_power_dbm'] + MAX_DELTA_PWR_DB))
                    # simulate predicted objective
                    yhat = simulate_apply_and_measure(cand, simulator, median_context)["objective_y"]
                    # (we don't have predicted retries model; leave None)
                    allowed, reason = policy.pre_check_candidate(ap_id, current_cfg, cand, simulator_pred=yhat, predicted_retries_pct=None)
                    if not allowed:
                        # skip
                        # print(f"policy pre-check rejected candidate: {reason}")
                        continue
                    selected = cand
                    selected_mu, selected_sigma = float(mu[idx]), float(sigma[idx])
                    selected_yhat = float(yhat)
                    break
                if selected is None:
                    print("No safe candidate found for AP", ap_id)
                    continue
                print("Selected candidate:", selected, f"pred_mu={selected_mu:.4f}, pred_sigma={selected_sigma:.4f}, sim_yhat={selected_yhat:.4f}")
                print(datetime.now(timezone.utc), "Candidate selected; simulating apply & measure...")
                # apply simulated (we do not call real apply)
                res = simulate_apply_and_measure_realistic(selected)
                y_obj = res["objective_y"]
                throughput = res["throughput_mbps"]
                rtt = res["rtt_ms"]
                retries = res["retries_pct"]

                # post-check via policy
                accepted, action_msg = policy.post_check_observation(ap_id, baseline, y_obj)
                if not accepted:
                    print("Policy post-check failed:", action_msg, "- rolling back / skipping")
                    # record negative sample and retrain next loop
                    # append simulated row with rolled_back flag (still append into CSV)
                    new_row = {
                        'timestamp_start': datetime.now(timezone.utc).isoformat(),
                        'timestamp_end': (datetime.now(timezone.utc) + timedelta(minutes=WINDOW_MIN)).isoformat(),
                        'sin_time': median_context['sin_time'],           # <-- add this
                        'cos_time': median_context['cos_time'],           # <-- add this
                        'ap_id': ap_id,
                        'channel_width_mhz': selected['channel_width_mhz'],
                        'tx_power_dbm': selected['tx_power_dbm'],
                        'num_clients': int(median_ctx_row.get('num_clients',1)),
                        'client_median_throughput_mbps': throughput,
                        'client_median_rtt_ms': rtt,
                        'sensing_cca_busy_pct': median_context['sensing_cca_busy_pct'],
                        'aggregate_neighbor_load_pct': median_context['aggregate_neighbor_load_pct'],
                        'client_video_stalls_frac': 0.0,
                        'client_retries_pct': retries,
                        'window_minutes': WINDOW_MIN,
                        'objective_y': float(y_obj),
                        'rolled_back': False,  # or True if rollback
                        'policy_msg': action_msg
                    }
                    append_row_to_csv(csv_path, new_row)
                    # update local model X_used, y_used
                    widths = CHANNEL_WIDTHS
                    one_hot = [1.0 if int(selected['channel_width_mhz'])==W else 0.0 for W in widths]
                    row = np.array(one_hot + [selected['tx_power_dbm'], median_context['log_num_clients'], median_context['sensing_cca_busy_pct'], median_context['aggregate_neighbor_load_pct'], median_context['sin_time'], median_context['cos_time']]).reshape(1,-1)
                    row_scaled = meta['scaler'].transform(row)
                    models[ap_id]['X_used'] = np.vstack([models[ap_id]['X_used'], row_scaled.reshape(1,-1)])
                    models[ap_id]['y_used'] = np.concatenate([models[ap_id]['y_used'], np.array([y_obj])])
                    # retrain GP with new data
                    models[ap_id]['gpr'] = fit_gp(models[ap_id]['X_used'], models[ap_id]['y_used'])
                    continue
                # accepted -> append new simulated observation into same CSV
                print("Candidate accepted by policy; logging simulated observation.")
                new_row = {
                            'timestamp_start': datetime.now(timezone.utc).isoformat(),
                            'timestamp_end': (datetime.now(timezone.utc) + timedelta(minutes=WINDOW_MIN)).isoformat(),
                            'sin_time': median_context['sin_time'],           # <-- add this
                            'cos_time': median_context['cos_time'],           # <-- add this
                            'ap_id': ap_id,
                            'channel_width_mhz': selected['channel_width_mhz'],
                            'tx_power_dbm': selected['tx_power_dbm'],
                            'num_clients': int(median_ctx_row.get('num_clients',1)),
                            'client_median_throughput_mbps': throughput,
                            'client_median_rtt_ms': rtt,
                            'sensing_cca_busy_pct': median_context['sensing_cca_busy_pct'],
                            'aggregate_neighbor_load_pct': median_context['aggregate_neighbor_load_pct'],
                            'client_video_stalls_frac': 0.0,
                            'client_retries_pct': retries,
                            'window_minutes': WINDOW_MIN,
                            'objective_y': float(y_obj),
                            'rolled_back': False,  # or True if rollback
                            'policy_msg': action_msg
                        }

                append_row_to_csv(csv_path, new_row)
                # update GP training set & retrain
                widths = CHANNEL_WIDTHS
                one_hot = [1.0 if int(selected['channel_width_mhz'])==W else 0.0 for W in widths]
                row = np.array(one_hot + [selected['tx_power_dbm'], median_context['log_num_clients'], median_context['sensing_cca_busy_pct'], median_context['aggregate_neighbor_load_pct'], median_context['sin_time'], median_context['cos_time']]).reshape(1,-1)
                row_scaled = meta['scaler'].transform(row)
                models[ap_id]['X_used'] = np.vstack([models[ap_id]['X_used'], row_scaled.reshape(1,-1)])
                models[ap_id]['y_used'] = np.concatenate([models[ap_id]['y_used'], np.array([y_obj])])
                models[ap_id]['gpr'] = fit_gp(models[ap_id]['X_used'], models[ap_id]['y_used'])
                # save simulator & gp occasionally
                joblib.dump(simulator, os.path.join(out_dir, f"simulator_ap_{ap_id}.joblib"))
                joblib.dump(models[ap_id]['gpr'], os.path.join(out_dir, f"gp_ap_{ap_id}.joblib"))
                time.sleep(STABILIZE_MIN * 1)  # keep short for demo
                print("&&&&&")
            # end per-ap loop
            time.sleep(poll_interval)
    except KeyboardInterrupt:
        print("Interrupted by user. Exiting.")
    except Exception as e:
        print("Unexpected error:", e)
        import traceback
        print("Unexpected error:", repr(e))
        traceback.print_exc()
    finally:
        print("Shutting down.")

# ----------------------------
# CLI
# ----------------------------
def main():
    parser = argparse.ArgumentParser()
    data = os.path.join("sim_out", "ap_aggregates_LHS_20251109_224345.csv")
    out='5';
    simulate=7;
    poll=8;
    quiet_hours=9;
    '''parser.add_argument('--data', required=True, help='Path to CSV file used for training and live updates (same file).')
    parser.add_argument('--out', required=True, help='Output dir for artifacts.')
    parser.add_argument('--simulate', action='store_true', help='Run in simulate mode (recommended).')
    parser.add_argument('--poll', type=float, default=5.0, help='Polling interval seconds for file changes.')
    parser.add_argument('--quiet_hours', nargs='*', help='Optional quiet hours ranges like 9-17 (can specify many).')
    args = parser.parse_args()'''

    csv_path = data
    out_dir = out
    ensure_dir(out_dir)
    quiet_hours = []
    if quiet_hours:
        for rng in quiet_hours:
            if '-' in rng:
                s,e = rng.split('-')
                quiet_hours.append((int(s), int(e)))
    print("Starting online BO with file:", csv_path)
    run_online_loop(csv_path, out_dir, simulate=simulate, poll_interval=poll, quiet_hours=quiet_hours)

if __name__ == "__main__":
    main()
