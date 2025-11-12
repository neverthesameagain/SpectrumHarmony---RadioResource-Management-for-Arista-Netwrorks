#!/usr/bin/env python3
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

# regulatory / EIRP settings
REGULATORY_EIRP_DBM = 30.0  # regulatory EIRP cap in dBm (adjust for country)
ANTENNA_GAIN_DB = 0.0       # assumed antenna gain (dBi); change if known
WINDOW_MIN = 10
STABILIZE_MIN = 1            # simulated wait minutes (kept short for online demo)
N_INIT_SYNTH = 8
GP_NOISE = 1e-6
EI_XI = 1e-3

# range of tx power (dBm)
TX_POWER_MIN = 5.0
TX_POWER_MAX = 20.0

# possible channel widths (MHz)
CHANNEL_WIDTHS = [20, 40, 80, 160]

# OBSS-PD parameters
OBSS_PD_MIN = -82.0         
OBSS_PD_MAX = -62.0         
MAX_DELTA_OBSS_PD_DB = 3.0  

# default policy parameters
CHANGE_BUDGET_PER_PERIOD = 1
CHANGE_MONITORING_PERIOD_DAYS = 5
MAX_DELTA_PWR_DB = 2.0
ROLLBACK_TH = 0.10

# random seed
RANDOM_SEED = 42

# definition of PolicyEngine
from collections import deque
class PolicyEngine:
    def __init__(self,
                slo_p95_retries_pct=8.0,
                changecap_per_day=CHANGE_BUDGET_PER_PERIOD,
                change_window_days=CHANGE_MONITORING_PERIOD_DAYS,   # 🆕 NEW PARAMETER
                max_delta_pwr_db=MAX_DELTA_PWR_DB,
                rollback_threshold=ROLLBACK_TH,
                require_manual_approval=False,
                quiet_hours=None):
        self.slo_p95_retries_pct = float(slo_p95_retries_pct)
        self.changecap_per_day = float(changecap_per_day)
        self.change_window_days = float(change_window_days)  # 🆕 STORE IT
        self.max_delta_pwr_db = float(max_delta_pwr_db)
        self.rollback_threshold = float(rollback_threshold)
        self.require_manual_approval = require_manual_approval
        self.quiet_hours = quiet_hours or []
        self._ap_change_history = {}  # ap_id -> deque of datetimes
        self._ap_cooloff_until = {}

    # make sure entry exists for that AP in the history
    def _ensure_ap(self, ap_id):
        if ap_id not in self._ap_change_history:
            self._ap_change_history[ap_id] = deque()

    # remove changes older than the monitoring window
    def _prune_old_changes(self, ap_id, now):
        self._ensure_ap(ap_id)
        dq = self._ap_change_history[ap_id]
        cutoff = now - timedelta(days=self.change_window_days)
        while dq and dq[0] < cutoff:
            dq.popleft()
    
    # save timestamp of when last configuration change was made
    def record_change(self, ap_id, when=None):
        when = when or datetime_now()
        self._ensure_ap(ap_id)
        self._ap_change_history[ap_id].append(when)
    
    # counts how many changes in the last monitoring window
    def changes_last_period(self, ap_id, now=None):
        now = now or datetime_now()
        self._prune_old_changes(ap_id, now)
        return len(self._ap_change_history.get(ap_id, []))
    
    # sets a “cooloff” period until a certain time.
    def set_cooloff(self, ap_id, until_ts):
        self._ap_cooloff_until[ap_id] = until_ts
    
    # checks if the ap is currently in cooloff
    def in_cooloff(self, ap_id, now=None):
        now = now or datetime_now()
        t = self._ap_cooloff_until.get(ap_id)
        return (t is not None) and (now < t)
    
    # checks if current time is within quiet hours
    def in_quiet_hours(self, now=None):
        if not self.quiet_hours:
            return False
        now = now or datetime_now()
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
        now = now or datetime_now()
        if self.in_cooloff(ap_id, now):
            return False, f"AP {ap_id} in cooloff until {self._ap_cooloff_until.get(ap_id)}"
        if self.in_quiet_hours(now):
            return False, "Within quiet hours; changes disallowed."
        if self.changes_last_period(ap_id, now) >= self.changecap_per_day:
            return False, "Change budget exhausted."
        if abs(candidate.get('tx_power_dbm', current_cfg.get('tx_power_dbm')) - current_cfg.get('tx_power_dbm')) > self.max_delta_pwr_db + 1e-9:
            return False, f"Delta tx power exceeds max per-change ({self.max_delta_pwr_db} dB)."
        if 'obss_pd_dbm' in candidate and 'obss_pd_dbm' in current_cfg:
            if abs(candidate.get('obss_pd_dbm') - current_cfg.get('obss_pd_dbm')) > MAX_DELTA_OBSS_PD_DB + 1e-9:
                return False, f"Delta OBSS-PD exceeds max per-change ({MAX_DELTA_OBSS_PD_DB} dB)."
        if predicted_retries_pct is not None:
            if predicted_retries_pct > self.slo_p95_retries_pct:
                return False, f"Predicted P95 retries {predicted_retries_pct:.2f}% exceeds SLO {self.slo_p95_retries_pct}%."
        if self.require_manual_approval:
            return False, "Manual approval required by policy."
        return True, "OK"

    def post_check_observation(self, ap_id, baseline_obj, observed_obj, now=None):
        now = now or datetime_now()
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
def datetime_now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)

def ensure_dir(d):
    if not os.path.exists(d):
        os.makedirs(d)

# trains a lightweight surrogate model (Random Forest) that maps features describing the AP/context to the objective objective_y
# if you don’t have enough historical samples (<10), it returns a trivial mean predictor
def fit_simulator(df, feature_cols=None):
    df_local = df.copy()
    df_local['log_num_clients'] = np.log1p(df_local['num_clients'])
    if feature_cols is None:
        feature_cols = ['channel_width_mhz','tx_power_dbm','obss_pd_dbm','log_num_clients','sensing_cca_busy_pct','aggregate_neighbor_load_pct','sin_time','cos_time']
    for c in feature_cols:
        if c not in df_local.columns:
            df_local[c] = 0.0
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

# latin hypercube sampling for synthetic values
def latin_hypercube_tx(n_samples, low, high):
    cut = np.linspace(0,1,n_samples+1)
    rng = np.random.RandomState(RANDOM_SEED)
    points = cut[:-1] + rng.rand(n_samples)*(1.0/n_samples)
    txs = low + points*(high-low)
    return txs

# creates initial dataset for GP training, including synthetic warm-start samples
def create_initial_dataset(df_hist, simulator, feature_cols=None, n_synth=N_INIT_SYNTH, random_seed=RANDOM_SEED):
    # defensive copy
    df = df_hist.copy() if df_hist is not None else pd.DataFrame()

    # ensure num_clients exists
    if 'num_clients' not in df.columns:
        df['num_clients'] = 0
    df['log_num_clients'] = np.log1p(df['num_clients'])

    # Ensure obss exists and is clipped
    if 'obss_pd_dbm' not in df.columns:
        df['obss_pd_dbm'] = OBSS_PD_MAX
    df['obss_pd_dbm'] = df['obss_pd_dbm'].clip(OBSS_PD_MIN, OBSS_PD_MAX)

    # continuous cols (order matters)
    cont_cols = ['tx_power_dbm', 'obss_pd_dbm', 'log_num_clients',
                 'sensing_cca_busy_pct', 'aggregate_neighbor_load_pct',
                 'sin_time', 'cos_time']

    # Ensure cont cols exist (fill with reasonable defaults)
    for c in cont_cols:
        if c not in df.columns:
            df[c] = 0.0

    widths = list(CHANNEL_WIDTHS)
    # fit OneHotEncoder but handle case where df has none of the widths
    enc = OneHotEncoder(categories=[widths], sparse_output=False, handle_unknown='ignore')
    width_values = df[['channel_width_mhz']].copy() if 'channel_width_mhz' in df.columns else pd.DataFrame({'channel_width_mhz': []})
    if len(width_values) > 0:
        try:
            enc_mat = enc.fit_transform(width_values)
        except Exception:
            # if something goes wrong, create zero matrix with shape (len(df), len(widths))
            enc_mat = np.zeros((len(df), len(widths)), dtype=float)
            enc.fit(pd.DataFrame(widths, columns=['channel_width_mhz']))  # to set categories_
    else:
        # no historical widths: make zero matrix and set encoder categories
        enc_mat = np.zeros((len(df), len(widths)), dtype=float)
        enc.fit(pd.DataFrame(widths, columns=['channel_width_mhz']))

    cat_names = [f"width_{int(w)}" for w in enc.categories_[0]]
    X_cat = pd.DataFrame(enc_mat, columns=cat_names, index=df.index)

    X_cont = df[cont_cols].astype(float).fillna(0.0)
    X_hist = pd.concat([X_cat, X_cont], axis=1)

    # If X_hist has zero rows (no history), create a single "median" dummy row for scaler fitting
    if X_hist.shape[0] == 0:
        # create one dummy row with medians/defaults
        median_defaults = {
            'tx_power_dbm': (TX_POWER_MIN + TX_POWER_MAX) / 2.0,
            'obss_pd_dbm': OBSS_PD_MAX,
            'log_num_clients': np.log1p(1.0),
            'sensing_cca_busy_pct': 0.0,
            'aggregate_neighbor_load_pct': 0.0,
            'sin_time': float(np.sin(2*np.pi*12.0/24.0)),
            'cos_time': float(np.cos(2*np.pi*12.0/24.0))
        }
        dummy_cat = [0.0] * len(cat_names)
        dummy_row = pd.DataFrame([dummy_cat + [median_defaults[c] for c in cont_cols]], columns=cat_names + cont_cols)
        X_hist = dummy_row
        y_hist = np.array([0.5])
    else:
        y_hist = df['objective_y'].fillna(method='ffill').fillna(0.5).values.astype(float)

    scaler = StandardScaler()
    X_hist_scaled = scaler.fit_transform(X_hist)

    X_all = X_hist_scaled
    y_all = y_hist

    # synthetic warm-start
    if n_synth and n_synth > 0:
        rng = np.random.RandomState(random_seed)
        txs = latin_hypercube_tx(n_synth, TX_POWER_MIN, TX_POWER_MAX)
        obss_vals = np.linspace(OBSS_PD_MIN, OBSS_PD_MAX, n_synth)
        widths_samp = rng.choice(widths, size=n_synth, replace=True)

        # median context (defensive)
        median_ctx = df.median(numeric_only=True).to_dict() if len(df) > 0 else {}
        def get_ctx(k, default):
            v = median_ctx.get(k, default)
            return default if pd.isna(v) else v

        X_synth = []
        y_synth = []
        for i in range(n_synth):
            w = int(widths_samp[i])
            p = float(txs[i])
            obss = float(obss_vals[i])

            ctx_log_clients = float(np.log1p(get_ctx('num_clients', 1.0)))
            ctx_sensing = float(get_ctx('sensing_cca_busy_pct', 0.0))
            ctx_agg = float(get_ctx('aggregate_neighbor_load_pct', 0.0))
            tod = float(get_ctx('time_of_day_hour', 12.0))
            ctx_sin = float(np.sin(2*np.pi*tod/24.0))
            ctx_cos = float(np.cos(2*np.pi*tod/24.0))

            sim_in = np.array([[w, p, obss, ctx_log_clients, ctx_sensing, ctx_agg, ctx_sin, ctx_cos]])
            try:
                yhat = float(simulator.predict(sim_in)[0])
            except Exception:
                yhat = float(np.mean(y_hist)) if len(y_hist) > 0 else 0.5

            # construct row in same order as X_hist columns: cat_names + cont_cols
            one_hot = [1.0 if int(c) == w else 0.0 for c in enc.categories_[0]]
            cont_vals = [p, obss, ctx_log_clients, ctx_sensing, ctx_agg, ctx_sin, ctx_cos]
            row = np.array(one_hot + cont_vals)
            X_synth.append(row)
            y_synth.append(yhat)

        X_synth = np.vstack(X_synth)
        # check shape
        expected_cols = len(cat_names) + len(cont_cols)
        if X_synth.shape[1] != expected_cols:
            raise ValueError(f"Mismatch synthetic cols ({X_synth.shape[1]}) vs expected ({expected_cols})")

        X_synth_df = pd.DataFrame(X_synth, columns=cat_names + cont_cols)
        X_synth_scaled = scaler.transform(X_synth_df)
        X_all = np.vstack([X_all, X_synth_scaled])
        y_all = np.concatenate([y_all, np.array(y_synth, dtype=float)])

    metadata = {
        'onehot_names': cat_names,
        'cont_cols': cont_cols,
        'feature_names': cat_names + cont_cols,
        'scaler': scaler,
        'encoder': enc
    }
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
    p = current_cfg.get('tx_power_dbm', TX_POWER_MIN)
    obss_cur = current_cfg.get('obss_pd_dbm', OBSS_PD_MAX)
    # small tx neighborhood (keep old behaviors)
    for dp in [0, -1, 1, -2, 2]:
        val = float(np.clip(p + dp, TX_POWER_MIN, TX_POWER_MAX))
        candidates.append({'channel_width_mhz': current_cfg['channel_width_mhz'], 'tx_power_dbm': val, 'obss_pd_dbm': obss_cur})
    # change widths
    for w in widths:
        if w == current_cfg['channel_width_mhz']: continue
        for dp in [0, 1, -1]:
            val = float(np.clip(p + dp, TX_POWER_MIN, TX_POWER_MAX))
            candidates.append({'channel_width_mhz': w, 'tx_power_dbm': val, 'obss_pd_dbm': obss_cur})
    # obss neighborhood
    for do in [0, -1, 1, -2, 2, -3, 3]:
        ob = float(np.clip(obss_cur + do, OBSS_PD_MIN, OBSS_PD_MAX))
        candidates.append({'channel_width_mhz': current_cfg['channel_width_mhz'], 'tx_power_dbm': p, 'obss_pd_dbm': ob})
    # combined small perturbations
    for dp in [1, -1]:
        for do in [1, -1]:
            val = float(np.clip(p + dp, TX_POWER_MIN, TX_POWER_MAX))
            ob = float(np.clip(obss_cur + do, OBSS_PD_MIN, OBSS_PD_MAX))
            candidates.append({'channel_width_mhz': current_cfg['channel_width_mhz'], 'tx_power_dbm': val, 'obss_pd_dbm': ob})
    # global random
    rng = np.random.RandomState(RANDOM_SEED)
    for _ in range(n_global):
        w = int(rng.choice(widths))
        val = float(rng.uniform(TX_POWER_MIN, TX_POWER_MAX))
        ob = float(rng.uniform(OBSS_PD_MIN, OBSS_PD_MAX))
        candidates.append({'channel_width_mhz': w, 'tx_power_dbm': val, 'obss_pd_dbm': ob})
    # deduplicate including obss
    uniq = {}
    for c in candidates:
        key = (int(c['channel_width_mhz']), round(float(c['tx_power_dbm']),2), round(float(c.get('obss_pd_dbm',0.0)),2))
        uniq[key] = c
    return list(uniq.values())

def build_gp_rows(candidates, median_context, meta):
    rows = []
    for cand in candidates:
        widths = CHANNEL_WIDTHS
        one_hot = [1.0 if int(cand['channel_width_mhz']) == W else 0.0 for W in widths]

        # Ensure obss_pd_dbm exists in the candidate, fallback to median or default
        obss_val = cand.get('obss_pd_dbm', median_context.get('obss_pd_dbm', OBSS_PD_MAX))
        obss_val = float(np.clip(obss_val, OBSS_PD_MIN, OBSS_PD_MAX))

        # Maintain consistent feature order as in create_initial_dataset()
        cont = [
            float(cand['tx_power_dbm']),
            obss_val,
            median_context['log_num_clients'],
            median_context['sensing_cca_busy_pct'],
            median_context['aggregate_neighbor_load_pct'],
            median_context['sin_time'],
            median_context['cos_time']
        ]

        row = np.array(one_hot + cont).reshape(1, -1)

        # Scale using the same scaler from metadata
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
    obss = float(candidate.get('obss_pd_dbm', median_context.get('obss_pd_dbm', OBSS_PD_MAX)))
    sim_in = np.array([[w, p, obss,
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
    Calls your realistic WiFi simulator and returns the same format as before,
    now extended to include OBSS-PD as a tunable parameter.

    This assumes your simulate_wifi_sample() function can optionally take
    OBSS-PD as an input argument. If not, it will still work safely by ignoring it.
    """
    from wifi_simulator_single_sample import simulate_wifi_sample  # import your function

    tx = candidate['tx_power_dbm']
    width = candidate['channel_width_mhz']

    # Get OBSS-PD value; if missing, default to OBSS_PD_MAX (most aggressive)
    obss_pd = candidate.get('obss_pd_dbm', OBSS_PD_MAX)
    obss_pd = float(np.clip(obss_pd, OBSS_PD_MIN, OBSS_PD_MAX))

    # Try calling simulator with OBSS-PD parameter (new version)
    try:
        sample = simulate_wifi_sample(tx, width, obss_pd, window_minutes=window_minutes)
    except TypeError:
        # Backward-compatible fallback for old simulator signature (tx, width, window)
        sample = simulate_wifi_sample(tx, width, window_minutes=window_minutes)

    # Map to metrics (throughput, rtt, retries)
    throughput = sample.get('client_median_throughput_mbps', 0.0)
    rtt = sample.get('client_median_rtt_ms', 0.0)
    retries = sample.get('client_retries_pct', 0.01)  # default small retry rate
    objective = sample.get('objective_y', 0.0)

    # Return consistent output including OBSS-PD value (for logging/debugging)
    return {
        "objective_y": float(objective),
        "throughput_mbps": float(throughput),
        "rtt_ms": float(rtt),
        "retries_pct": float(retries),
        "obss_pd_dbm": obss_pd
    }

# ----------------------------
# File-watch + online loop
# ----------------------------

# loads and preprocesses the CSV for online BO (loads entire file)
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

    # NEW: Ensure OBSS-PD column exists and fill defaults if missing
    if 'obss_pd_dbm' not in df.columns:
        df['obss_pd_dbm'] = OBSS_PD_MAX  # default if missing
    # clip OBSS-PD and TX power to safe ranges
    df['tx_power_dbm'] = df['tx_power_dbm'].clip(TX_POWER_MIN, TX_POWER_MAX)
    df['obss_pd_dbm'] = df['obss_pd_dbm'].clip(OBSS_PD_MIN, OBSS_PD_MAX)

    # impute per AP
    # UPDATED: include obss_pd_dbm in the impute list
    impute_cols = ['client_median_throughput_mbps','client_median_rtt_ms','client_retries_pct','obss_pd_dbm']
    for col in impute_cols:
        if col in df.columns:
            df[col] = df.groupby('ap_id')[col].transform(lambda x: x.fillna(x.median()))

    if 'time_of_day_hour' not in df.columns:
        df['time_of_day_hour'] = df['timestamp_start'].dt.hour + df['timestamp_start'].dt.minute/60.0
    if 'weekday' not in df.columns:
        df['weekday'] = df['timestamp_start'].dt.weekday

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
    df2['prev_objective_ewma'] = df2.groupby('ap_id')['objective_y'].transform(
        lambda x: x.shift(1).ewm(alpha=0.2).mean().fillna(method='bfill').fillna(0.0)
    )
    df2['log_num_clients'] = np.log1p(df2['num_clients'])
    df2['sin_time'] = np.sin(2*np.pi*df2['time_of_day_hour']/24.0)
    df2['cos_time'] = np.cos(2*np.pi*df2['time_of_day_hour']/24.0)

    return df2

# appends a single row to the CSV file
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

# the main function to run one iteration of online BO
def run_online_iteration(csv_path, out_dir, policy=None):
    ensure_dir(out_dir)
    if policy is None:
        policy = PolicyEngine()

    models = {}  # per-AP model cache

    print("Running ONE iteration of online BO...")
    try:
        # Load and preprocess CSV
        try:
            df = load_and_preprocess_for_online(csv_path)
        except Exception as e:
            print("Failed to read CSV:", e)
            return

        df = df.dropna(subset=['ap_id'])
        df['ap_id'] = df['ap_id'].astype(str)
        ap_ids = sorted(df['ap_id'].unique())

        for ap_id in ap_ids:
            hist_ap = df[df['ap_id'] == ap_id].copy()
            if hist_ap.empty:
                continue

            print(f"\n[AP {ap_id}] Processing historical data...")
            latest_ts = hist_ap['timestamp_start'].max()

            # compute baseline median objective
            baseline = float(hist_ap['objective_y'].median())

            # train simulator on full history
            simulator, feature_cols = fit_simulator(hist_ap)
            print(datetime_now(), "Simulator fitted")

            # build warm-start dataset and GP
            X_all, y_all, meta = create_initial_dataset(hist_ap, simulator, feature_cols, n_synth=N_INIT_SYNTH)
            try:
                gpr = fit_gp(X_all, y_all)
            except Exception as e:
                print("GP fit failed:", e)
                gpr = None
            print(datetime_now(), "GP fitted")

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
            current_cfg = {
                'channel_width_mhz': int(last_row['channel_width_mhz']),
                'tx_power_dbm': float(last_row['tx_power_dbm']),
                'obss_pd_dbm': float(last_row['obss_pd_dbm'])
                if 'obss_pd_dbm' in last_row and not pd.isna(last_row['obss_pd_dbm'])
                else float(hist_ap['obss_pd_dbm'].median() if 'obss_pd_dbm' in hist_ap else OBSS_PD_MAX)
            }

            # median context
            median_ctx_row = hist_ap.median(numeric_only=True)
            median_context = {
                'log_num_clients': float(np.log1p(median_ctx_row['num_clients'])) if 'num_clients' in median_ctx_row else 1.0,
                'sensing_cca_busy_pct': float(median_ctx_row.get('sensing_cca_busy_pct', 0.0)),
                'aggregate_neighbor_load_pct': float(median_ctx_row.get('aggregate_neighbor_load_pct', 0.0)),
                'sin_time': float(np.sin(2 * np.pi * median_ctx_row['time_of_day_hour'] / 24.0))
                if 'time_of_day_hour' in median_ctx_row else 0.0,
                'cos_time': float(np.cos(2 * np.pi * median_ctx_row['time_of_day_hour'] / 24.0))
                if 'time_of_day_hour' in median_ctx_row else 1.0,
                'obss_pd_dbm': float(median_ctx_row.get('obss_pd_dbm', OBSS_PD_MAX))
            }

            # generate candidates & evaluate EI
            if gpr is None:
                print("No GP available; skipping BO for this AP.")
                continue

            candidates = generate_candidates(current_cfg)
            cand_list, X_cand = build_gp_rows(candidates, median_context, meta)
            mu, sigma = gpr.predict(X_cand, return_std=True)
            ei = expected_improvement(mu, sigma, best=np.max(y_all))
            order = np.argsort(-ei)

            selected = None
            for idx in order:
                cand = deepcopy(cand_list[idx])
                cand_eirp = cand.get('tx_power_dbm', current_cfg['tx_power_dbm']) + ANTENNA_GAIN_DB
                if cand_eirp > REGULATORY_EIRP_DBM:
                    clipped = float(REGULATORY_EIRP_DBM - ANTENNA_GAIN_DB)
                    clipped = float(np.clip(clipped,
                                            current_cfg['tx_power_dbm'] - MAX_DELTA_PWR_DB,
                                            current_cfg['tx_power_dbm'] + MAX_DELTA_PWR_DB))
                    cand['tx_power_dbm'] = float(np.clip(clipped, TX_POWER_MIN, TX_POWER_MAX))
                    cand['_regulatory_clipped'] = True

                if abs(cand['tx_power_dbm'] - current_cfg['tx_power_dbm']) > MAX_DELTA_PWR_DB + 1e-9:
                    cand['tx_power_dbm'] = float(np.clip(cand['tx_power_dbm'],
                                                         current_cfg['tx_power_dbm'] - MAX_DELTA_PWR_DB,
                                                         current_cfg['tx_power_dbm'] + MAX_DELTA_PWR_DB))
                # simulate
                yhat = simulate_apply_and_measure(cand, simulator, median_context)["objective_y"]
                allowed, reason = policy.pre_check_candidate(ap_id, current_cfg, cand,
                                                             simulator_pred=yhat,
                                                             predicted_retries_pct=None)
                if not allowed:
                    continue

                selected = cand
                selected_mu, selected_sigma = float(mu[idx]), float(sigma[idx])
                selected_yhat = float(yhat)
                break

            if selected is None:
                print("No safe candidate found for AP", ap_id)
                continue

            print(f"Selected candidate: {selected}, pred_mu={selected_mu:.4f}, sim_yhat={selected_yhat:.4f}")
            print(datetime_now(), "Candidate selected; simulating apply & measure...")

            res = simulate_apply_and_measure_realistic(selected)
            y_obj = res["objective_y"]
            throughput = res["throughput_mbps"]
            rtt = res["rtt_ms"]
            retries = res["retries_pct"]

            accepted, action_msg = policy.post_check_observation(ap_id, baseline, y_obj)

            new_row = {
                'timestamp_start': datetime_now().isoformat(),
                'timestamp_end': (datetime_now() + timedelta(minutes=WINDOW_MIN)).isoformat(),
                'sin_time': median_context['sin_time'],
                'cos_time': median_context['cos_time'],
                'ap_id': ap_id,
                'channel_width_mhz': selected['channel_width_mhz'],
                'tx_power_dbm': selected['tx_power_dbm'],
                'obss_pd_dbm': selected.get('obss_pd_dbm', median_context.get('obss_pd_dbm', OBSS_PD_MAX)),
                'num_clients': int(median_ctx_row.get('num_clients', 1)),
                'client_median_throughput_mbps': throughput,
                'client_median_rtt_ms': rtt,
                'sensing_cca_busy_pct': median_context['sensing_cca_busy_pct'],
                'aggregate_neighbor_load_pct': median_context['aggregate_neighbor_load_pct'],
                'client_video_stalls_frac': 0.0,
                'client_retries_pct': retries,
                'window_minutes': WINDOW_MIN,
                'objective_y': float(y_obj),
                'rolled_back': not accepted,
                'policy_msg': action_msg
            }
            append_row_to_csv(csv_path, new_row)

            print("Logged simulated observation.")

            # retrain GP with new data
            widths = CHANNEL_WIDTHS
            one_hot = [1.0 if int(selected['channel_width_mhz']) == W else 0.0 for W in widths]
            row = np.array(one_hot + [
                selected['tx_power_dbm'],
                selected.get('obss_pd_dbm', median_context.get('obss_pd_dbm', OBSS_PD_MAX)),
                median_context['log_num_clients'],
                median_context['sensing_cca_busy_pct'],
                median_context['aggregate_neighbor_load_pct'],
                median_context['sin_time'],
                median_context['cos_time']
            ]).reshape(1, -1)
            row_scaled = meta['scaler'].transform(row)
            models[ap_id]['X_used'] = np.vstack([models[ap_id]['X_used'], row_scaled])
            models[ap_id]['y_used'] = np.concatenate([models[ap_id]['y_used'], np.array([y_obj])])
            models[ap_id]['gpr'] = fit_gp(models[ap_id]['X_used'], models[ap_id]['y_used'])

            # Save models
            joblib.dump(simulator, os.path.join(out_dir, f"simulator_ap_{ap_id}.joblib"))
            joblib.dump(models[ap_id]['gpr'], os.path.join(out_dir, f"gp_ap_{ap_id}.joblib"))

        print("\nCompleted one BO iteration for all APs.\n")

    except Exception as e:
        print("Unexpected error during iteration:", e)
        import traceback
        traceback.print_exc()