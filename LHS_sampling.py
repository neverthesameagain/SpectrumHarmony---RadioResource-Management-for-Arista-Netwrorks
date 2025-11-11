from wifi_simulator_single_sample import simulate_wifi_sample
import pandas as pd
import numpy as np
import os
from datetime import datetime

# ----------------------------
# Configuration
# ----------------------------
NUM_SAMPLES = 50                # total samples you want
TX_MIN, TX_MAX = 10, 23         # dBm range
CHANNEL_WIDTHS = [20, 40, 80, 160]   # MHz options
OUT_DIR = "sim_out"

# ----------------------------
# Custom Latin Hypercube Sampling (no pyDOE2)
# ----------------------------
def latin_hypercube_sampling(n_samples, n_dims=1):
    """Generate an n_samples × n_dims Latin Hypercube design in [0,1]."""
    rng = np.random.default_rng(seed=42)
    cut = np.linspace(0, 1, n_samples + 1)
    u = rng.random((n_samples, n_dims))
    lhs = np.zeros_like(u)
    for j in range(n_dims):
        lhs[:, j] = u[:, j] * (cut[1:] - cut[:-1]) + cut[:-1]
        rng.shuffle(lhs[:, j])
    return lhs

# ----------------------------
# Generate Latin Hypercube samples
# ----------------------------
lhs_samples = latin_hypercube_sampling(NUM_SAMPLES, n_dims=1)
tx_powers = TX_MIN + (TX_MAX - TX_MIN) * lhs_samples[:, 0]
widths = np.random.choice(CHANNEL_WIDTHS, size=NUM_SAMPLES)

# ----------------------------
# Generate WiFi samples
# ----------------------------
samples = []
for tx, width in zip(tx_powers, widths):
    row = simulate_wifi_sample(tx, width)
    row["policy_msg"] = "simulated"   # ✅ add the extra column
    samples.append(row)

# ----------------------------
# Save to CSV (timestamped)
# ----------------------------
os.makedirs(OUT_DIR, exist_ok=True)
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
outfile = os.path.join(OUT_DIR, f"ap_aggregates_LHS_{timestamp}.csv")

df = pd.DataFrame(samples)
df.to_csv(outfile, index=False)

print(f"✅ Saved {NUM_SAMPLES} simulated samples to {outfile}")
