import pandas as pd
import os
import matplotlib.pyplot as plt

# -------------------------------
# 1️⃣ Load and label the datasets
# -------------------------------
paths = {
    "CQL": os.path.join(os.path.dirname(__file__), "results", "results_cql.csv"),
    "Random": os.path.join(os.path.dirname(__file__), "results", "results_random.csv"),
    "Static": os.path.join(os.path.dirname(__file__), "results", "results_static.csv")
}

dfs = []
for policy, path in paths.items():
    df = pd.read_csv(path)
    df["policy"] = policy
    df["avg_throughput"] = df[["p50_throughput_1", "p50_throughput_2", "p50_throughput_3"]].mean(axis=1)
    df["avg_retry"] = df[["p95_retry_1", "p95_retry_2", "p95_retry_3"]].mean(axis=1)
    dfs.append(df)

# Combine all results
df_all = pd.concat(dfs, ignore_index=True)

# Convert timestamp to datetime for sorting
df_all["timestamp"] = pd.to_datetime(df_all["timestamp"])
df_all = df_all.sort_values(by="timestamp")

# -------------------------------
# 2️⃣ Plot comparisons
# -------------------------------
plt.style.use("seaborn-v0_8-whitegrid")
colors = {"CQL": "tab:blue", "Random": "tab:orange", "Static": "tab:green"}

# --- (a) Average Throughput ---
plt.figure(figsize=(10,5))
for policy in paths.keys():
    subset = df_all[df_all["policy"] == policy]
    plt.plot(subset["timestamp"], subset["avg_throughput"], label=policy, color=colors[policy])
plt.title("Average Throughput Over Time")
plt.xlabel("Time")
plt.ylabel("Throughput (Mbps)")
plt.legend()
plt.xticks(rotation=45)
plt.tight_layout()
plt.show()

# --- (b) Average P95 Retry ---
plt.figure(figsize=(10,5))
for policy in paths.keys():
    subset = df_all[df_all["policy"] == policy]
    plt.plot(subset["timestamp"], subset["avg_retry"], label=policy, color=colors[policy])
plt.title("Average P95 Retry Rate Over Time")
plt.xlabel("Time")
plt.ylabel("Retry (95th Percentile)")
plt.legend()
plt.xticks(rotation=45)
plt.tight_layout()
plt.show()

# --- (c) Reward ---
plt.figure(figsize=(10,5))
for policy in paths.keys():
    subset = df_all[df_all["policy"] == policy]
    plt.plot(subset["timestamp"], subset["reward"], label=policy, color=colors[policy])
plt.title("Reward Over Time")
plt.xlabel("Time")
plt.ylabel("Reward")
plt.legend()
plt.xticks(rotation=45)
plt.tight_layout()
plt.show()

# -------------------------------
# 3️⃣ Print quick summary stats
# -------------------------------
summary = df_all.groupby("policy")[["avg_throughput", "avg_retry", "reward"]].mean().round(2)
print("\n📊 Policy Comparison Summary:\n", summary)
