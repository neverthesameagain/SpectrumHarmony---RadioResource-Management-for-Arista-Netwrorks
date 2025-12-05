import random
from datetime import datetime, timedelta
import torch
from CQL_Training import QNetwork
from WiFi_Simulator_Modeling import Environment, AccessPoint, Client
from Dataset_Generation import get_state, compute_reward
import pandas as pd
import numpy as np


# policy extraction / inference
# for a given state (numpy array), find a high-scoring action by sampling
# enumerate random combinations of discrete choices (tx,width) and sample a few obss values
# evaluate Q and pick best
def greedy_action_from_q(q_net, state, n_samples=2000):
    tx_power_choices = [8, 11, 14, 17, 20]
    width_choices = [20, 40, 80, 160]
    obss_min, obss_max = -82, -62

    state_t = torch.tensor(state, dtype=torch.float32).unsqueeze(0)  # (1, state_dim)

    best_q = -1e9
    best_action = None

    for _ in range(n_samples):
        # build random action vector for all 3 APs
        a = []
        for _ in range(3):  # 3 APs
            a.append(np.random.choice(tx_power_choices))
            a.append(np.random.choice(width_choices))
            a.append(np.random.uniform(obss_min, obss_max))
        a = np.array(a, dtype=np.float32)
        a_t = torch.tensor(a, dtype=torch.float32).unsqueeze(0)

        q_val = q_net(state_t, a_t).item()

        if q_val > best_q:
            best_q = q_val
            best_action = a

    return best_action, best_q


# apply action vectorto all APs in the environment
def apply_action_to_env(env, action_vec):
    i = 0
    for ap in env.aps:
        tx_power = float(action_vec[i]);   i += 1
        width    = float(action_vec[i]);   i += 1
        obss     = float(action_vec[i]);   i += 1

        ap.configure(
            tx_power_dbm=tx_power,
            channel_width_mhz=width,
            obss_pd_dbm=obss
        )

def make_env():
    # create APs at fixed locations
    ap1 = AccessPoint(ap_id=1, x=10, y=10)
    ap2 = AccessPoint(ap_id=2, x=40, y=10)
    ap3 = AccessPoint(ap_id=3, x=25, y=30)

    # configure each AP (initial state)
    ap1.configure(tx_power_dbm=15, channel_width_mhz=40, obss_pd_dbm=-82)
    ap2.configure(tx_power_dbm=18, channel_width_mhz=20, obss_pd_dbm=-82)
    ap3.configure(tx_power_dbm=15, channel_width_mhz=80, obss_pd_dbm=-82)

    env = Environment(
        width=50,
        height=50,
        aps=[ap1, ap2, ap3],
        start_date="2025-01-01 00:00:00"
    )
    return env


# def constrained_apply_action(env, new_action_vec, prev_action_vec, q_net, state, delta_max=3, epsilon=0.05):
#     """
#     Applies action under a safety budget:
#     - limits the magnitude of configuration changes
#     - ensures no large predicted Q-drop
#     """
#     if prev_action_vec is None:
#         return new_action_vec  # first step — no constraint yet

#     # Action distance constraint
#     diff = np.abs(new_action_vec - prev_action_vec)
#     num_changes = np.sum(diff > 1e-3)  # count parameter changes
#     if num_changes > delta_max:
#         print(f"⚠️ Too many changes ({num_changes}), keeping previous configuration")
#         return prev_action_vec

#     # Reward / Q safety constraint
#     q_prev = q_net(torch.tensor(state, dtype=torch.float32).unsqueeze(0),
#                    torch.tensor(prev_action_vec, dtype=torch.float32).unsqueeze(0)).item()
#     q_new = q_net(torch.tensor(state, dtype=torch.float32).unsqueeze(0),
#                   torch.tensor(new_action_vec, dtype=torch.float32).unsqueeze(0)).item()

#     if q_new < q_prev - epsilon * abs(q_prev):
#         print(f"⚠️ Unsafe downgrade (Q {q_new:.2f} < {q_prev:.2f}), keeping previous configuration")
#         return prev_action_vec

#     # Otherwise, safe to apply
#     return new_action_vec

# import numpy as np
# import torch
# from datetime import datetime

# Define reasonable limits
MAX_DELTA_PWR_DB = 3.0          # max per-change power step (dB)
MAX_DELTA_OBSS_DB = 4.0         # max per-change OBSS-PD step (dB)
CHANGE_BUDGET_PER_DAY = 4       # per-AP change cap per 24h
RETRY_SLO_P95 = 8.0             # max allowed predicted p95 retry (%)
EPSILON_Q_DROP = 0.05           # max tolerated Q degradation (%)

# Track per-AP change count in a simple dict
change_tracker = {}

def constrained_apply_action(env, new_action_vec, prev_action_vec, q_net, state, now=None):
    """
    Safely applies an action under multiple safety constraints:
    1. Per-AP daily change budget
    2. Max ΔTx power and ΔOBSS-PD per change
    3. Predicted retry SLO check
    4. Conservative Q-value degradation threshold
    """

    if prev_action_vec is None:
        # first step — initialize tracker
        for ap in env.aps:
            change_tracker[ap.ap_id] = {"changes_today": 0, "last_date": None}
        return new_action_vec

    # Convert to numpy array for safe math
    new_action_vec = np.array(new_action_vec)
    prev_action_vec = np.array(prev_action_vec)
    num_aps = len(env.aps)

    # -----------------------------
    # (1) CHANGE BUDGET PER AP
    # -----------------------------
    if now is None:
        now = env.current_time if hasattr(env, "current_time") else datetime.now()

    safe_action = prev_action_vec.copy()
    for ap_id, ap in enumerate(env.aps, start=1):
        if ap_id not in change_tracker:
            change_tracker[ap_id] = {"changes_today": 0, "last_date": now.date()}

        tracker = change_tracker[ap_id]

        # Reset daily budget if date has changed
        if tracker["last_date"] != now.date():
            tracker["changes_today"] = 0
            tracker["last_date"] = now.date()

        if tracker["changes_today"] >= CHANGE_BUDGET_PER_DAY:
            print(f"⚠️ AP{ap_id}: Change budget exhausted, keeping previous configuration.")
            continue  # skip changes for this AP

        # Indices in the action vector
        base = (ap_id - 1) * 3
        tx_new, width_new, obss_new = new_action_vec[base:base+3]
        tx_prev, width_prev, obss_prev = prev_action_vec[base:base+3]

        # -----------------------------
        # (2) MAX PARAMETER DELTA CHECK
        # -----------------------------
        if abs(tx_new - tx_prev) > MAX_DELTA_PWR_DB:
            print(f"⚠️ AP{ap_id}: ΔTx power {abs(tx_new - tx_prev):.1f} > {MAX_DELTA_PWR_DB} dB limit.")
            continue
        if abs(obss_new - obss_prev) > MAX_DELTA_OBSS_DB:
            print(f"⚠️ AP{ap_id}: ΔOBSS-PD {abs(obss_new - obss_prev):.1f} > {MAX_DELTA_OBSS_DB} dB limit.")
            continue

        # -----------------------------
        # (3) Q-VALUE CONSERVATISM
        # -----------------------------
        q_prev = q_net(torch.tensor(state, dtype=torch.float32).unsqueeze(0),
                       torch.tensor(prev_action_vec, dtype=torch.float32).unsqueeze(0)).item()
        q_new = q_net(torch.tensor(state, dtype=torch.float32).unsqueeze(0),
                      torch.tensor(new_action_vec, dtype=torch.float32).unsqueeze(0)).item()

        if q_new < q_prev - EPSILON_Q_DROP * abs(q_prev):
            print(f"⚠️ AP{ap_id}: Unsafe downgrade (Q {q_new:.2f} < {q_prev:.2f}). Keeping old config.")
            continue

        # -----------------------------
        # (4) RETRY SLO PREDICTION (optional heuristic)
        # -----------------------------
        # Approximate predicted retry % from OBSS and Tx power heuristics
        predicted_retry_pct = max(1.0, 20 - 0.5 * tx_new + 0.2 * (obss_new + 82))
        if predicted_retry_pct > RETRY_SLO_P95:
            print(f"⚠️ AP{ap_id}: Predicted retries {predicted_retry_pct:.2f}% > SLO {RETRY_SLO_P95}%.")
            continue

        # If all checks passed, accept changes for this AP
        safe_action[base:base+3] = [tx_new, width_new, obss_new]
        tracker["changes_today"] += 1

    return safe_action



def run_policy_simulation(env, policy_type="cql", q1=None,
                          days=20,
                          start_date="2025-01-01 00:00:00",
                          save_path="policy_eval_results.csv",
                          seed=0):
    """
    Simulates WiFi environment using one of three policies:
        - 'cql': uses trained Q-network to pick actions
        - 'random': random valid actions
        - 'static': keeps AP configuration fixed
    Runs for the given number of days (default = 20 days = 480 hours).

    Args:
        env: Environment object
        policy_type: str, one of ['cql', 'random', 'static']
        q1: Trained Q-network (used only for CQL policy)
        days: Number of simulated days (default 20)
        start_date: Simulation start time
        save_path: CSV file to save logged results
        seed: Random seed to ensure comparable client patterns
    """
    assert policy_type in ["cql", "random", "static"]

    np.random.seed(seed)
    random.seed(seed)

    env.current_time = datetime.strptime(start_date, "%Y-%m-%d %H:%M:%S")
    logs = []

    total_hours = days * 24
    print(f"Running {policy_type.upper()} policy for {total_hours} simulated hours...")
    
    prev_action_vec = None 

    for step in range(total_hours):
        timestamp = env.current_time.strftime("%Y-%m-%d %H:%M:%S")

        # Environment update
        n_clients = env.sample_client_count(env.current_time.hour)
        env.spawn_clients(n_clients)
        env.associate_clients()

        # Get current state
        state = get_state(env)

        # Select action based on policy type
        if policy_type == "cql":
            proposed_action, best_q = greedy_action_from_q(q1, state, n_samples=1000)
            action_vec = constrained_apply_action(env, proposed_action, prev_action_vec, q1, state)
            prev_action_vec = action_vec

        elif policy_type == "random":
            tx_power_choices = [8, 11, 14, 17, 20]
            width_choices = [20, 40, 80, 160]
            obss_min, obss_max = -82, -62
            a = []
            for _ in env.aps:
                a.append(np.random.choice(tx_power_choices))
                a.append(np.random.choice(width_choices))
                a.append(np.random.uniform(obss_min, obss_max))
            action_vec = np.array(a, dtype=np.float32)
            best_q = 0.0

        else:
            a = []
            for ap in env.aps:
                a.append(ap.tx_power_dbm)
                a.append(ap.channel_width_mhz)
                a.append(ap.obss_pd_dbm)
            action_vec = np.array(a, dtype=np.float32)
            best_q = 0.0

        # Apply the chosen (and possibly constrained) action exactly once
        if prev_action_vec is None or not np.allclose(action_vec, prev_action_vec, atol=1e-6):
            apply_action_to_env(env, action_vec)
            prev_action_vec = action_vec.copy()


        # Simulate one step
        hour_stats = env.step()

        # Compute reward
        reward = compute_reward(hour_stats)

        # Log AP-level metrics
        ap_metrics = {}
        for i, apstats in enumerate(hour_stats, start=1):
            ap_metrics[f"p50_throughput_{i}"] = apstats["p50_throughput"]
            ap_metrics[f"p95_retry_{i}"] = apstats["p95_retry"]

        # Store log entry
        row = {
            "timestamp": timestamp,
            "num_clients": n_clients,
            "reward": reward,
            "Q_value": best_q,
            "policy": policy_type,
        }

        for ap_id in range(1, len(env.aps) + 1):
            base_idx = (ap_id - 1) * 3
            row[f"tx_power_{ap_id}"] = action_vec[base_idx]
            row[f"width_{ap_id}"] = action_vec[base_idx + 1]
            row[f"obss_pd_{ap_id}"] = action_vec[base_idx + 2]

        row.update(ap_metrics)
        logs.append(row)

        # Advance simulation clock
        env.current_time += timedelta(hours=1)

    # Save results
    df_logs = pd.DataFrame(logs)
    df_logs.to_csv(save_path, index=False)
    print(f"Saved {policy_type.upper()} results ({total_hours} hours) to {save_path}")

    return df_logs

def evaluate_policy_results(csv_paths):
    """
    Given a dict of policy name → CSV path,
    print average throughput, retry, and reward for each.
    """
    results_summary = []

    for policy, path in csv_paths.items():
        df = pd.read_csv(path)

        # Compute averages
        avg_tput = df[[f"p50_throughput_{i}" for i in range(1, 4)]].mean().mean()
        avg_retry = df[[f"p95_retry_{i}" for i in range(1, 4)]].mean().mean()
        avg_reward = df["reward"].mean()

        results_summary.append({
            "Policy": policy,
            "Avg_Throughput": avg_tput,
            "Avg_P95_Retry": avg_retry,
            "Avg_Reward": avg_reward
        })

    # Print in a nice table format
    print("\nPolicy Comparison Summary:")
    print("-" * 70)
    print(f"{'Policy':<10} {'Avg_Throughput(Mbps)':<25} {'Avg_P95_Retry':<20} {'Avg_Reward':<15}")
    print("-" * 70)
    for row in results_summary:
        print(f"{row['Policy']:<10} {row['Avg_Throughput']:<25.2f} {row['Avg_P95_Retry']:<20.2f} {row['Avg_Reward']:<15.2f}")
    print("-" * 70)

    return pd.DataFrame(results_summary)

# load trained q1
q1 = QNetwork(state_dim=14, action_dim=9)
q1.load_state_dict(torch.load("C:/Users/gayat/OneDrive/Desktop/Academics/Inter_IIT_Tech_Meet/Post_Mid_Term/cql_q1.pt", map_location="cpu"))
q1.eval()

seed = 123
days = 20

save_path_cql = "C:/Users/gayat/OneDrive/Desktop/Academics/Inter_IIT_Tech_Meet/Post_Mid_Term/results_cql.csv"
save_path_random = "C:/Users/gayat/OneDrive/Desktop/Academics/Inter_IIT_Tech_Meet/Post_Mid_Term/results_random.csv"
save_path_static = "C:/Users/gayat/OneDrive/Desktop/Academics/Inter_IIT_Tech_Meet/Post_Mid_Term/results_static.csv"

df_cql    = run_policy_simulation(make_env(), policy_type="cql",    q1=q1, days=days, save_path=save_path_cql,    seed=seed)
df_random = run_policy_simulation(make_env(), policy_type="random", q1=None, days=days,save_path=save_path_random, seed=seed)
df_static = run_policy_simulation(make_env(), policy_type="static", q1=None, days=days, save_path=save_path_static, seed=seed)


# summarize the results
csv_paths = {"CQL": save_path_cql, "Random": save_path_random, "Static": save_path_static}

summary_df = evaluate_policy_results(csv_paths)
summary_df.to_csv("policy_comparison_summary.csv", index=False)
print("Saved summary to policy_comparison_summary.csv")
