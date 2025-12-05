#!/usr/bin/env python3

import os
import sys
import json
import math
import pickle
from typing import Dict, Tuple, List, Optional

import numpy as np
import pandas as pd

# Paths and script dir
SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))      # ControlLoops folder
CSV_ABS_PATH = os.path.join(SCRIPT_DIR, "data", "interference_edges_balanced.csv")
OUTDIR_ABS = os.path.join(SCRIPT_DIR, "models")
os.makedirs(OUTDIR_ABS, exist_ok=True)

CONFIG_DIR = os.path.join(SCRIPT_DIR, "config")
os.makedirs(CONFIG_DIR, exist_ok=True)
THROUGHPUT_MAP_FILE = os.path.join(CONFIG_DIR, "throughput_map.json")

# Ensure project root on sys.path so ControlLoops package imports resolve
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Robust import of InterferenceGraph
try:
    from ControlLoops.InterferenceGraph import InterferenceGraph
except Exception as e_primary:
    try:
        from InterferenceGraph import InterferenceGraph
    except Exception as e_fallback:
        raise ImportError(
            "Failed to import InterferenceGraph.\n"
            f"Primary error: {e_primary}\nFallback error: {e_fallback}\n"
            f"PROJECT_ROOT used: {PROJECT_ROOT}\nsys.path start: {sys.path[:5]}"
        )

# Try TensorFlow; fallback to sklearn-only if unavailable
USE_TF = True
try:
    import tensorflow as tf
    from tensorflow.keras import layers, Model, regularizers, optimizers, losses
except Exception:
    tf = None
    layers = None
    Model = None
    regularizers = None
    optimizers = None
    losses = None
    USE_TF = False

# sklearn utils
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
from sklearn.linear_model import Ridge
import networkx as nx

# ----------------------------
# Throughput mapping config loader
# ----------------------------
_default_conf = {
    "base_map": {"20": 72, "40": 150, "80": 300, "160": 600},
    "per_band_scale": {"2.4": 1.0, "5": 1.0}
}
# create default config file if missing
if not os.path.exists(THROUGHPUT_MAP_FILE):
    try:
        with open(THROUGHPUT_MAP_FILE, "w") as _f:
            json.dump(_default_conf, _f, indent=2)
    except Exception:
        # if we can't write, proceed with defaults in memory
        pass

def _load_throughput_map() -> Tuple[Dict[int, float], Dict[str, float]]:
    try:
        with open(THROUGHPUT_MAP_FILE, "r") as f:
            conf = json.load(f)
        base_conf = conf.get("base_map", {})
        perband_conf = conf.get("per_band_scale", {})
        base_map = {}
        for k, v in base_conf.items():
            try:
                base_map[int(k)] = float(v)
            except Exception:
                continue
        if not base_map:
            base_map = {20:72, 40:150, 80:300, 160:600}
        perband_map = {}
        for k, v in perband_conf.items():
            perband_map[str(k)] = float(v)
        # ensure keys exist
        if "2.4" not in perband_map: perband_map["2.4"] = 1.0
        if "5" not in perband_map: perband_map["5"] = 1.0
        return base_map, perband_map
    except Exception:
        return {20:72, 40:150, 80:300, 160:600}, {"2.4":1.0, "5":1.0}

BASE_TPUT_MAP, PER_BAND_SCALE = _load_throughput_map()

# ----------------------------
# Throughput calculator (uses configurable map)
# ----------------------------
class ThroughputCalculator:
    @staticmethod
    def _detect_band_key(band_val) -> Optional[str]:
        try:
            if band_val is None:
                return None
            s = str(band_val)
            if "2.4" in s:
                return "2.4"
            if "5" in s and "2.4" not in s:
                return "5"
            try:
                fv = float(band_val)
                if abs(fv - 2.4) < 1e-6:
                    return "2.4"
                if abs(fv - 5.0) < 1e-6:
                    return "5"
            except Exception:
                pass
        except Exception:
            pass
        return None

    @staticmethod
    def calculate_throughput(row: pd.Series) -> float:
        # defensive retrieval and casting
        def to_float(x, default=0.0):
            try:
                return float(x)
            except Exception:
                return float(default)

        channel_width = to_float(row.get('WIDTH_A_MHZ', 20.0), 20.0)
        pathloss = to_float(row.get('PATHLOSS', 0.0), 0.0)
        p95_retry = to_float(row.get('P95_RETRY', 0.0), 0.0)
        airtime_a = to_float(row.get('AIRTIME_A', 0.0), 0.0)
        load_min = to_float(row.get('LOAD_MIN', 0.0), 0.0)

        pathloss_factor = 1.0 / (1.0 + pathloss / 100.0)
        success_rate = max(0.0, 1.0 - p95_retry)
        airtime_efficiency = airtime_a * (1.0 - load_min)

        try:
            max_t = BASE_TPUT_MAP.get(int(channel_width), list(BASE_TPUT_MAP.values())[0])
        except Exception:
            max_t = list(BASE_TPUT_MAP.values())[0]

        band_key = ThroughputCalculator._detect_band_key(row.get('BAND', None))
        scale = PER_BAND_SCALE.get(band_key, 1.0) if band_key is not None else 1.0

        throughput = max_t * scale * pathloss_factor * success_rate * airtime_efficiency
        return float(throughput)

# ----------------------------
# Simple 2-layer matrix GCN (Keras)
# ----------------------------
if USE_TF:
    class SimpleGCNTF(Model):
        def __init__(self, in_feats: int, hidden: int, out_feats: int, dropout: float = 0.3, l2: float = 1e-4):
            super().__init__()
            reg = regularizers.l2(l2) if l2 and l2 > 0 else None
            self.dense1 = layers.Dense(hidden, activation=None, kernel_regularizer=reg, name="dense1")
            self.relu = layers.ReLU()
            self.dropout = layers.Dropout(dropout)
            self.dense2 = layers.Dense(out_feats, activation=None, kernel_regularizer=reg, name="dense2")

        def call(self, X: tf.Tensor, A: tf.Tensor, training: bool = False) -> tf.Tensor:
            h = tf.matmul(A, X)
            h = self.dense1(h)
            h = self.relu(h)
            h = self.dropout(h, training=training)
            out = tf.matmul(A, h)
            out = self.dense2(out)
            return out

        def embed(self, X: tf.Tensor, A: tf.Tensor) -> tf.Tensor:
            h_raw = tf.matmul(A, X)
            h = self.dense1(h_raw)
            h = self.relu(h)
            return h

# ----------------------------
# Helpers: build features, adjacency
# ----------------------------
def build_node_features_and_targets(df_band: pd.DataFrame, nodes_list: List[str]) -> Tuple[np.ndarray, np.ndarray, List[str]]:
    nodes = list(nodes_list)
    N = len(nodes)
    # F = 5 features (we will later add degree)
    X = np.zeros((N, 5), dtype=np.float32)
    y = np.full((N, 1), np.nan, dtype=np.float32)

    for i, ap in enumerate(nodes):
        ap_rows = df_band[(df_band['AP_A'] == ap) | (df_band['AP_B'] == ap)]
        if len(ap_rows) > 0:
            try:
                X[i, 0] = float(ap_rows['WIDTH_A_MHZ'].mean()) if 'WIDTH_A_MHZ' in ap_rows.columns else 0.0
            except Exception:
                X[i, 0] = 0.0
            try:
                X[i, 1] = float(ap_rows['AIRTIME_A'].mean()) if 'AIRTIME_A' in ap_rows.columns else 0.0
            except Exception:
                X[i, 1] = 0.0
            try:
                X[i, 2] = float(ap_rows['TX_A_DBM'].mean()) if 'TX_A_DBM' in ap_rows.columns else 0.0
            except Exception:
                X[i, 2] = 0.0
            if 'RX_POWER_EST_NORM' in ap_rows.columns:
                try:
                    X[i, 3] = float(ap_rows['RX_POWER_EST_NORM'].mean())
                except Exception:
                    X[i, 3] = 0.0
            else:
                X[i, 3] = 0.0
            X[i, 4] = float(len(ap_rows))
            # throughput (we expect a 'throughput' column computed earlier)
            if 'throughput' in df_band.columns:
                try:
                    t = ap_rows['throughput'].mean()
                    if pd.notna(t):
                        y[i, 0] = float(t)
                except Exception:
                    y[i, 0] = np.nan
        else:
            # no rows for this AP — leave zeros and NaN target
            X[i, :] = 0.0
            y[i, 0] = np.nan

    return X, y, nodes

def build_adj_matrix_and_norm(G: nx.Graph, nodes: List[str]) -> np.ndarray:
    idx = {n_: i for i, n_ in enumerate(nodes)}
    N = len(nodes)
    A = np.zeros((N, N), dtype=float)
    for u, v, data in G.edges(data=True):
        if u not in idx or v not in idx:
            continue
        i, j = idx[u], idx[v]
        w = data.get('weight', 1.0)
        try:
            w = float(w)
        except Exception:
            w = 1.0
        A[i, j] += w
        A[j, i] += w
    # add self-loops
    for i in range(N):
        A[i, i] += 1.0
    # normalize
    deg = A.sum(axis=1)
    D_inv_sqrt = np.diag(1.0 / np.sqrt(deg + 1e-12))
    A_norm = D_inv_sqrt @ A @ D_inv_sqrt
    return A_norm.astype(np.float32)

# ----------------------------
# TF training wrapper (improved + saves SavedModel + weights + embeddings + scalers + preds)
# ----------------------------
def train_and_save_tf_gcn_improved(X_np: np.ndarray, A_np: np.ndarray, y_np: np.ndarray,
                                   train_idx: np.ndarray, test_idx: np.ndarray,
                                   scaler_X: StandardScaler, scaler_y: StandardScaler,
                                   nodes: List[str], out_prefix: str,
                                   hidden_units: int = 128, lr: float = 1e-3,
                                   l2_reg: float = 1e-4, dropout: float = 0.3,
                                   patience: int = 30, max_epochs: int = 400) -> Dict:
    """
    Train a 2-layer matrix GCN with TF/Keras on log1p-scaled targets and save artifacts.
    Returns metrics dict including saved model dirs/paths.
    """
    if tf is None:
        raise RuntimeError("TensorFlow not available")

    # Defensive casts
    X_np = np.asarray(X_np, dtype=np.float32)
    A_np = np.asarray(A_np, dtype=np.float32)
    y_np = np.asarray(y_np, dtype=np.float32)
    if y_np.ndim == 1:
        y_np = y_np.reshape(-1, 1)

    device = "/GPU:0" if tf.config.list_physical_devices('GPU') else "/CPU:0"

    X_tf = tf.convert_to_tensor(X_np, dtype=tf.float32)
    A_tf = tf.convert_to_tensor(A_np, dtype=tf.float32)
    y_tf = tf.convert_to_tensor(y_np.reshape(-1,1), dtype=tf.float32)

    model = SimpleGCNTF(X_np.shape[1], hidden_units, 1, dropout=dropout, l2=l2_reg)
    # build variables
    _ = model(X_tf, A_tf, training=False)

    optimizer = optimizers.Adam(learning_rate=lr)
    loss_fn = losses.Huber()
    lr_schedule = optimizers.schedules.CosineDecay(initial_learning_rate=lr, decay_steps=200)
    optimizer.learning_rate = lr_schedule

    best_val = float('inf')
    best_weights = None
    wait = 0
    epochs = max_epochs if X_np.shape[0] < 2000 else int(max_epochs / 2)

    train_idx_tf = tf.constant(train_idx, dtype=tf.int32)
    test_idx_list = [int(i) for i in test_idx]

    for epoch in range(epochs):
        with tf.device(device):
            with tf.GradientTape() as tape:
                preds_all = tf.squeeze(model(X_tf, A_tf, training=True))  # shape [N]
                preds_train = tf.gather(preds_all, train_idx_tf)
                y_train = tf.squeeze(tf.gather(y_tf, train_idx_tf))
                # if all train y are NaN (rare because we imputed for scaler), exit training
                if tf.reduce_all(tf.math.is_nan(y_train)):
                    break
                loss_value = loss_fn(y_train, preds_train)
            grads = tape.gradient(loss_value, model.trainable_variables)
            optimizer.apply_gradients(zip(grads, model.trainable_variables))

            # Validation
            preds_val_all = tf.squeeze(model(X_tf, A_tf, training=False)).numpy()
            y_all_np = y_tf.numpy().flatten()
            # Denormalize preds and y via scaler_y then expm1
            try:
                preds_denorm_log = scaler_y.inverse_transform(preds_val_all.reshape(-1,1)).flatten()
                preds_denorm = np.expm1(preds_denorm_log)
            except Exception:
                preds_denorm = np.expm1(preds_val_all)
            try:
                y_all_denorm_log = scaler_y.inverse_transform(y_all_np.reshape(-1,1)).flatten()
                y_all_denorm = np.expm1(y_all_denorm_log)
            except Exception:
                y_all_denorm = np.expm1(y_all_np)

            valid_test_idx = [int(i) for i in test_idx if not np.isnan(y_all_denorm[int(i)])]
            if len(valid_test_idx) > 0:
                val_loss = float(mean_squared_error(y_all_denorm[valid_test_idx], preds_denorm[valid_test_idx]))
            else:
                val_loss = float('nan')

        # Early stopping
        if not math.isnan(val_loss) and val_loss < best_val:
            best_val = val_loss
            best_weights = model.get_weights()
            wait = 0
        else:
            wait += 1
        if wait >= patience:
            break

    if best_weights is not None:
        model.set_weights(best_weights)

    # Final preds
    preds_all = tf.squeeze(model(X_tf, A_tf, training=False)).numpy()
    try:
        preds_denorm_log = scaler_y.inverse_transform(preds_all.reshape(-1,1)).flatten()
        preds_denorm = np.expm1(preds_denorm_log)
    except Exception:
        preds_denorm = np.expm1(preds_all)
    preds_denorm = np.maximum(preds_denorm, 0.0)

    try:
        y_all_denorm_log = scaler_y.inverse_transform(y_tf.numpy().reshape(-1,1)).flatten()
        y_all_denorm = np.expm1(y_all_denorm_log)
    except Exception:
        y_all_denorm = np.expm1(y_tf.numpy().flatten())

    valid_test_idx = [int(i) for i in test_idx if not np.isnan(y_all_denorm[int(i)])]
    if len(valid_test_idx) > 0:
        mse = mean_squared_error(y_all_denorm[valid_test_idx], preds_denorm[valid_test_idx])
        mae = mean_absolute_error(y_all_denorm[valid_test_idx], preds_denorm[valid_test_idx])
        r2 = r2_score(y_all_denorm[valid_test_idx], preds_denorm[valid_test_idx])
    else:
        mse = mae = r2 = float('nan')

    # Save SavedModel dir and HDF5 weights (both)
    model_dir = out_prefix + "_gcn_model_tf"
    weights_h5 = out_prefix + "_gcn_weights.h5"
    saved_model_ok = False
    weights_ok = False
    try:
        model.save(model_dir, save_format="tf")
        saved_model_ok = True
    except Exception:
        saved_model_ok = False
    try:
        model.save_weights(weights_h5)
        weights_ok = True
    except Exception:
        weights_ok = weights_ok or False

    # Save embeddings (hidden activations)
    emb_npy_path = None
    emb_csv_path = None
    try:
        emb = model.embed(tf.convert_to_tensor(X_np), tf.convert_to_tensor(A_np)).numpy()
        emb_npy_path = out_prefix + "_embeddings.npy"
        np.save(emb_npy_path, emb)
        emb_df = pd.DataFrame(emb, columns=[f"emb_{i}" for i in range(emb.shape[1])])
        emb_df.insert(0, "AP", nodes)
        emb_csv_path = out_prefix + "_embeddings.csv"
        emb_df.to_csv(emb_csv_path, index=False)
    except Exception:
        emb_npy_path = None
        emb_csv_path = None

    # Save scalers (pickle .pkl)
    scaler_X_path = None
    scaler_y_path = None
    try:
        scaler_X_path = out_prefix + "_scaler_X.pkl"
        scaler_y_path = out_prefix + "_scaler_y.pkl"
        with open(scaler_X_path, "wb") as f:
            pickle.dump(scaler_X, f, protocol=pickle.HIGHEST_PROTOCOL)
        with open(scaler_y_path, "wb") as f:
            pickle.dump(scaler_y, f, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception:
        scaler_X_path = None
        scaler_y_path = None

    # Save preds CSV
    csv_path = out_prefix + "_nodes_preds_tf.csv"
    pd.DataFrame({'AP': nodes, 'pred_throughput_mbps': preds_denorm}).to_csv(csv_path, index=False)

    metrics = {
        'mse': float(mse), 'mae': float(mae), 'r2': float(r2),
        'model_dir': os.path.abspath(model_dir) if saved_model_ok and os.path.exists(model_dir) else None,
        'weights_h5': os.path.abspath(weights_h5) if weights_ok and os.path.exists(weights_h5) else None,
        'preds_csv': os.path.abspath(csv_path),
        'embeddings_npy': os.path.abspath(emb_npy_path) if emb_npy_path and os.path.exists(emb_npy_path) else None,
        'embeddings_csv': os.path.abspath(emb_csv_path) if emb_csv_path and os.path.exists(emb_csv_path) else None,
        'scaler_X': os.path.abspath(scaler_X_path) if scaler_X_path and os.path.exists(scaler_X_path) else None,
        'scaler_y': os.path.abspath(scaler_y_path) if scaler_y_path and os.path.exists(scaler_y_path) else None
    }
    return metrics

# ----------------------------
# sklearn fallback trainer (saves model + "embeddings")
# ----------------------------
def train_and_save_ridge(X_np: np.ndarray, A_np: np.ndarray, y_np: np.ndarray,
                         train_idx: np.ndarray, test_idx: np.ndarray,
                         scaler_X: StandardScaler, scaler_y: StandardScaler,
                         nodes: List[str], out_prefix: str, alpha: float = 1.0) -> Dict:
    # y_np here is the scaled log target used for training in pipeline
    y_flat = y_np.flatten()
    nan_mask = np.isnan(y_flat)
    if nan_mask.any():
        if np.all(nan_mask):
            y_flat[:] = 0.0
        else:
            y_flat[nan_mask] = float(np.nanmean(y_flat[~nan_mask]))

    if len(train_idx) == 0:
        return {'error': 'no_train_indices'}

    model = Ridge(alpha=alpha)
    model.fit(X_np[train_idx], y_flat[train_idx])
    preds = model.predict(X_np)

    # Inverse transform preds: scaler_y was fit on log1p(y_for_scaler)
    try:
        preds_denorm_log = scaler_y.inverse_transform(preds.reshape(-1,1)).flatten()
        preds_denorm = np.expm1(preds_denorm_log)
    except Exception:
        preds_denorm = np.expm1(preds)
    preds_denorm = np.maximum(preds_denorm, 0.0)

    try:
        y_denorm = np.expm1(scaler_y.inverse_transform(y_flat.reshape(-1,1)).flatten())
    except Exception:
        y_denorm = np.expm1(y_flat)

    if len(test_idx) > 0:
        mse = mean_squared_error(y_denorm[test_idx], preds_denorm[test_idx])
        mae = mean_absolute_error(y_denorm[test_idx], preds_denorm[test_idx])
        r2 = r2_score(y_denorm[test_idx], preds_denorm[test_idx])
    else:
        mse = mae = r2 = float('nan')

    # save ridge (pickle .pkl) + embeddings + scalers (pickle)
    ridge_pkl = None
    emb_npy = None
    emb_csv = None
    scaler_X_path = None
    scaler_y_path = None
    try:
        ridge_pkl = out_prefix + "_ridge.pkl"
        with open(ridge_pkl, "wb") as f:
            pickle.dump(model, f, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception:
        ridge_pkl = None
    try:
        emb_npy = out_prefix + "_embeddings.npy"
        np.save(emb_npy, X_np)
        emb_df = pd.DataFrame(X_np, columns=[f"emb_{i}" for i in range(X_np.shape[1])])
        emb_df.insert(0, "AP", nodes)
        emb_csv = out_prefix + "_embeddings.csv"
        emb_df.to_csv(emb_csv, index=False)
    except Exception:
        emb_npy = None
        emb_csv = None
    try:
        scaler_X_path = out_prefix + "_scaler_X.pkl"
        scaler_y_path = out_prefix + "_scaler_y.pkl"
        with open(scaler_X_path, "wb") as f:
            pickle.dump(scaler_X, f, protocol=pickle.HIGHEST_PROTOCOL)
        with open(scaler_y_path, "wb") as f:
            pickle.dump(scaler_y, f, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception:
        scaler_X_path = None
        scaler_y_path = None

    csv_path = out_prefix + "_nodes_preds_ridge.csv"
    pd.DataFrame({'AP': nodes, 'pred_throughput_mbps': preds_denorm}).to_csv(csv_path, index=False)

    return {
        'mse': float(mse), 'mae': float(mae), 'r2': float(r2),
        'preds_csv': os.path.abspath(csv_path),
        'ridge_pkl': os.path.abspath(ridge_pkl) if ridge_pkl and os.path.exists(ridge_pkl) else None,
        'embeddings_npy': os.path.abspath(emb_npy) if emb_npy and os.path.exists(emb_npy) else None,
        'embeddings_csv': os.path.abspath(emb_csv) if emb_csv and os.path.exists(emb_csv) else None,
        'scaler_X': os.path.abspath(scaler_X_path) if scaler_X_path and os.path.exists(scaler_X_path) else None,
        'scaler_y': os.path.abspath(scaler_y_path) if scaler_y_path and os.path.exists(scaler_y_path) else None
    }

# ----------------------------
# Main pipeline (per-band)
# ----------------------------
def run_pipeline(use_ensemble: bool = True):
    ig = InterferenceGraph()
    try:
        ig.start()
    except Exception as e:
        print("Warning: ig.start() raised:", e)

    G24 = ig.getGraph_2_4_Ghz()
    G5 = ig.getGraph_5_Ghz()

    if not os.path.exists(CSV_ABS_PATH):
        raise SystemExit(f"CSV not found: {CSV_ABS_PATH}")
    df = pd.read_csv(CSV_ABS_PATH)

    # compute throughput column (if not already present)
    if 'throughput' not in df.columns:
        calc = ThroughputCalculator()
        df['throughput'] = df.apply(calc.calculate_throughput, axis=1)

    results = {}
    for band_label, G, band_val in (("2_4", G24, 2.4), ("5", G5, 5.0)):
        print(f"\nProcessing band {band_label} ...")

        # select band rows (handle BAND values that might be strings or numbers)
        try:
            band_rows = df[df['BAND'].astype(str).str.contains(str(band_val))] if df['BAND'].dtype == object else df[df['BAND'] == band_val]
            if band_rows.shape[0] == 0:
                band_rows = df[np.isclose(df['BAND'].astype(float), float(band_val))]
        except Exception:
            band_rows = df[df['BAND'] == band_val]

        # Build nodes list as UNION of CSV APs and graph nodes
        csv_aps = set(band_rows['AP_A'].dropna().unique()).union(set(band_rows['AP_B'].dropna().unique()))
        graph_nodes = set(G.nodes())
        nodes_union = sorted(list(csv_aps.union(graph_nodes)))

        if len(nodes_union) == 0:
            print(f"No APs for band {band_label}. Skipping.")
            results[band_label] = {'error': 'no_aps_for_band'}
            continue

        # build features and targets in the same order as nodes_union
        X_feats, y_target, nodes = build_node_features_and_targets(band_rows, nodes_union)
        # adjacency normalized
        A_norm = build_adj_matrix_and_norm(G, nodes)

        # add degree as first feature
        degs = A_norm.sum(axis=1).reshape(-1, 1).astype(np.float32)
        X_full = np.hstack([degs, X_feats])  # shape [N, F+1]

        # create scalers
        scaler_X = StandardScaler()
        X_scaled = scaler_X.fit_transform(X_full)

        # Prepare y for scaler: replace NaNs with mean for scaler fitting
        y_flat = y_target.flatten()
        if np.isnan(y_flat).all():
            y_for_scaler = np.zeros_like(y_flat).reshape(-1,1)
        else:
            y_temp = y_flat.copy()
            nan_mask = np.isnan(y_temp)
            if nan_mask.any():
                y_temp[nan_mask] = float(np.nanmean(y_temp[~nan_mask]))
            y_for_scaler = y_temp.reshape(-1,1)

        # Transform target via log1p and clip extremes
        y_for_scaler_clipped = np.clip(y_for_scaler.reshape(-1), a_min=0.0, a_max=None)
        y_log = np.log1p(y_for_scaler_clipped)
        # Clip to [p1, p99] to reduce extreme influence
        if len(y_log) > 2:
            low = np.percentile(y_log, 1)
            high = np.percentile(y_log, 99)
            y_log = np.clip(y_log, low, high)
        scaler_y = StandardScaler()
        y_scaled = scaler_y.fit_transform(y_log.reshape(-1,1)).reshape(-1,1)

        N = X_scaled.shape[0]
        rng = np.random.RandomState(42)
        perm = rng.permutation(N)
        ntrain = int(0.8 * N) if N > 5 else int(0.7 * N)
        train_idx = np.asarray(perm[:ntrain], dtype=np.int64)
        test_idx = np.asarray(perm[ntrain:], dtype=np.int64) if ntrain < N else np.asarray(perm[:max(1, N - ntrain)], dtype=np.int64)

        out_prefix = os.path.join(OUTDIR_ABS, f"gcn_{band_label}")

        tf_metrics = None
        ridge_metrics = None

        # Try TF GCN first
        if USE_TF and tf is not None:
            try:
                tf_metrics = train_and_save_tf_gcn_improved(
                    X_scaled.astype(np.float32), A_norm.astype(np.float32),
                    y_scaled.astype(np.float32), train_idx, test_idx,
                    scaler_X, scaler_y, nodes, out_prefix,
                    hidden_units=128, lr=1e-3, l2_reg=1e-4, dropout=0.3,
                    patience=30, max_epochs=400
                )
            except Exception as e:
                print("TF training failed, falling back to Ridge. Error:", e)
                tf_metrics = None

        # Ridge fallback (always attempt to have a stable fallback)
        try:
            ridge_metrics = train_and_save_ridge(
                X_scaled.astype(np.float32), A_norm.astype(np.float32),
                y_scaled.astype(np.float32), train_idx, test_idx,
                scaler_X, scaler_y, nodes, out_prefix, alpha=1.0
            )
        except Exception as e:
            print("Ridge training failed:", e)
            ridge_metrics = None

        # Optionally create ensemble predictions if both exist
        ensemble_metrics = None
        try:
            if tf_metrics and ridge_metrics and tf_metrics.get('preds_csv') and ridge_metrics.get('preds_csv') and use_ensemble:
                df_tf = pd.read_csv(tf_metrics['preds_csv'])
                df_r = pd.read_csv(ridge_metrics['preds_csv'])
                merged = pd.merge(df_tf, df_r, on='AP', suffixes=('_tf', '_ridge'))
                if not merged.empty:
                    merged['pred_ensemble'] = (merged['pred_throughput_mbps_tf'] + merged['pred_throughput_mbps_ridge']) / 2.0
                    # compute metrics using y from scaler_y inverse transform
                    y_scaled_full = y_scaled.flatten()
                    try:
                        y_all_denorm_log = scaler_y.inverse_transform(y_scaled_full.reshape(-1,1)).flatten()
                        y_all_denorm = np.expm1(y_all_denorm_log)
                    except Exception:
                        y_all_denorm = np.expm1(y_scaled_full)
                    ap_to_idx = {ap: i for i, ap in enumerate(nodes)}
                    idxs = [ap_to_idx[ap] for ap in merged['AP'].values if ap in ap_to_idx]
                    valid_idxs = [i for i in idxs if not np.isnan(y_all_denorm[int(i)])]
                    if len(valid_idxs) > 0:
                        preds = merged['pred_ensemble'].values
                        mse = mean_squared_error(y_all_denorm[valid_idxs], preds[:len(valid_idxs)])
                        mae = mean_absolute_error(y_all_denorm[valid_idxs], preds[:len(valid_idxs)])
                        r2 = r2_score(y_all_denorm[valid_idxs], preds[:len(valid_idxs)])
                    else:
                        mse = mae = r2 = float('nan')
                    merged[['AP', 'pred_ensemble']].to_csv(out_prefix + "_nodes_preds_ensemble.csv", index=False)
                    ensemble_metrics = {
                        'mse': float(mse), 'mae': float(mae), 'r2': float(r2),
                        'preds_csv': os.path.abspath(out_prefix + "_nodes_preds_ensemble.csv")
                    }
        except Exception:
            ensemble_metrics = None

        # Prefer ensemble -> tf -> ridge
        results[band_label] = ensemble_metrics or tf_metrics or ridge_metrics or {'error': 'training_failed'}
        print(f"Finished band {band_label}. Metrics: {results[band_label]}")

    # write summary
    summary_path = os.path.join(OUTDIR_ABS, "summary_metrics_improved.json")
    with open(summary_path, "w") as f:
        json.dump(results, f, indent=2)
    print("\nPipeline finished. Outputs in:", os.path.abspath(OUTDIR_ABS))
    return results

# CLI execution
if __name__ == "__main__":
    run_pipeline()
