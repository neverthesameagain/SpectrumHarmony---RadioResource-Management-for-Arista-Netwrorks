
# **ARISTA RRM+ Synthetic Dataset 
### **Overview**

This dataset simulates **Radio Resource Management (RRM)** telemetry for a multi-AP Wi-Fi network in a mixed spectrum environment containing both **Wi-Fi** and **non-Wi-Fi interferers** (BLE, ZigBee, Microwave, FHSS).

It contains three synchronized views:

* 📡 **FFT dataset:** fine-grained power spectral density samples per AP per tick, labeled by signal type (Wi-Fi or non-Wi-Fi class).
* 🖧 **AP log:** per-access-point aggregates including average client SNR, QoE, throughput, retry %, and distance statistics, along with interference type.
* 📱 **Client log:** per-client signal and QoE metrics every 10 seconds.

Each dataset is aligned on the same timestamps and together provides a multi-modal view of Wi-Fi network state suitable for both **ML-based interference classification** and **policy learning**.

---

## 📊 **Schema Definitions**

### 🧠 1. FFT Dataset (`fft_dataset.csv`)

| Column                   | Type     | Description                                                            |
| :----------------------- | :------- | :--------------------------------------------------------------------- |
| `timestamp`              | ISO-8601 | Time of scan (10 s resolution).                                        |
| `ap_id`                  | string   | Access point identifier.                                               |
| `band`                   | {2.4, 5} | Radio band on which FFT was captured.                                  |
| `channel`                | int      | Center channel number.                                                 |
| `label`                  | string   | Signal class → `wifi`, `BLE`, `ZigBee`, `Microwave`, or `FHSS`.        |
| `center_mhz`             | float    | Center frequency of detected signal (MHz).                             |
| `bw_mhz`                 | float    | Bandwidth of detected signal (MHz).                                    |
| `duty`                   | float    | Duty cycle (activity fraction).                                        |
| `power_dbm`              | float    | Average signal power (dBm).                                            |
| `fft_bin_0 … fft_bin_63` | float    | 64-point FFT magnitudes representing received power spectrum snapshot. |

**Purpose:**
Trains the **FFT-based CNN or 1D Conv feature model** for Wi-Fi vs. non-Wi-Fi classification.
Used for fine-grained spectral fingerprinting or anomaly detection.

---

### 🖥️ 2. Access Point Log (`ap_log.csv`)

| Column                | Type     | Description                                                                                                                   |
| :-------------------- | :------- | :---------------------------------------------------------------------------------------------------------------------------- |
| `timestamp`           | ISO-8601 | Simulation tick (10 s).                                                                                                       |
| `ap_id`               | string   | Access point ID.                                                                                                              |
| `band`                | {2.4, 5} | Operating band.                                                                                                               |
| `channel`             | int      | Current AP channel.                                                                                                           |
| `channel_width_mhz`   | int      | Channel width (20, 40, 80).                                                                                                   |
| `tx_power_dbm`        | float    | Transmit power.                                                                                                               |
| `noise_floor_dbm`     | float    | Background noise (includes interferers).                                                                                      |
| `nwifi_detected`      | bool     | Whether any non-Wi-Fi interference was active.                                                                                |
| `nwifi_type`          | string   | **Single interferer type for that row** (BLE, ZigBee, Microwave, FHSS, or wifi). Multiple active types yield duplicated rows. |
| `avg_client_snr_db`   | float    | Average SNR of all clients connected to this AP.                                                                              |
| `throughput_avg_mbps` | float    | Average downstream throughput.                                                                                                |
| `p95_retry_pct`       | float    | 95th-percentile retry rate.                                                                                                   |
| `mean_qoe`            | float    | Mean QoE across clients (0–5).                                                                                                |
| `mean_distance_m`     | float    | Mean client distance (m).                                                                                                     |
| `p95_distance_m`      | float    | 95th-percentile client distance (m).                                                                                          |
| `max_distance_m`      | float    | Maximum distance (m).                                                                                                         |

**Purpose:**
Tabular input for **XGBoost / RandomForest AP-side classifiers** or for regression of performance vs interference.
Used for RRM decision models, guardrail evaluation, or simulation-policy training.

---

### 📲 3. Client Log (`client_log.csv`)

| Column             | Type     | Description                                                   |
| :----------------- | :------- | :------------------------------------------------------------ |
| `timestamp`        | ISO-8601 | Tick time (10 s).                                             |
| `client_id`        | string   | Client identifier (C_AP_xx_yy).                               |
| `connected_ap`     | string   | Serving AP ID.                                                |
| `band`             | {2.4, 5} | Band of connected AP.                                         |
| `channel`          | int      | Channel number.                                               |
| `rssi_dbm`         | float    | Received signal strength indicator.                           |
| `snr_db`           | float    | Signal-to-noise ratio.                                        |
| `throughput_mbps`  | float    | Instantaneous throughput (Mbps).                              |
| `retry_rate_pct`   | float    | Packet retry percentage.                                      |
| `qoe`              | float    | Synthetic QoE (0–5).                                          |
| `x`, `y`           | float    | Client spatial coordinates (m).                               |
| `distance_m`       | float    | Distance to AP (m).                                           |
| `affected_nonwifi` | bool     | Whether any non-Wi-Fi interferer was active during this tick. |

**Purpose:**
Supervised regression or RL state modeling for **client-level QoE prediction**, mobility impact, and link adaptation studies.

---

## 🔍 **Temporal Resolution**

* **Tick interval:** 10 seconds (configurable via `SCAN_PERIOD_S`)
* **Simulation duration:** 3 hours (default) or 24 hours (full day)
* Each AP logs one entry per interferer type per tick.
* Each client logs one entry per tick.
* FFT dataset may contain multiple rows per AP per tick (one per detected signal type).

---

## 🧩 **Intended Model Uses**

| Model                      | Input                                            | Output                               | Dataset           |
| :------------------------- | :----------------------------------------------- | :----------------------------------- | :---------------- |
| **1D CNN / LightCNN**      | 64 FFT bins + metadata                           | {wifi, BLE, ZigBee, Microwave, FHSS} | `fft_dataset.csv` |
| **XGBoost / RF (AP-side)** | [avg SNR, throughput, retry, qoe, noise_floor,…] | interference class / severity        | `ap_log.csv`      |
| **QoE Regressor (Client)** | [RSSI, SNR, retry, distance,…]                   | QoE (0–5)                            | `client_log.csv`  |

---

## ⚙️ **Simulation Parameters**

| Parameter          | Value                        | Meaning                                  |
| :----------------- | :--------------------------- | :--------------------------------------- |
| `N_AP`             | 6                            | Number of Access Points                  |
| `CLIENTS_PER_AP`   | 40                           | Number of clients per AP                 |
| `SCAN_PERIOD_S`    | 10                           | Update interval                          |
| `RADIUS_M`         | 10 m                         | Max AP coverage radius                   |
| `RSSI_RANGE`       | –70 → –30 dBm                | RSSI range for clients                   |
| `2.4 GHz AP share` | 60 %                         | Balances BLE/ZigBee density              |
| `Non-Wi-Fi types`  | BLE, ZigBee, Microwave, FHSS | Classes used for labeling                |
| `FFT bins`         | 64                           | Number of spectral bins per FFT snapshot |

---

## 🧠 **How to Use**

1. **Classification (FFT):**
   Train a 1D-CNN on `fft_dataset.csv` to distinguish non-Wi-Fi signal types.
   Features: `fft_bin_0–63` (+ metadata: band, channel, power).
   Labels: `label`.

2. **AP-side Modeling:**
   Use `ap_log.csv` to correlate `nwifi_type` → `mean_qoe` / `throughput_avg_mbps` degradation.

3. **Client-side Modeling:**
   Use `client_log.csv` for regression of QoE vs. RSSI/SNR/distance.

4. **Cross-Fusion:**
   Align all three by timestamp + AP ID to build a multi-modal model combining spectral (FFT) and telemetry (AP/Client) features.

---

## ⚖️ **Class Distribution (Example 3 h Run)**

| Label       | Approx. Samples | Band Dominance   |
| :---------- | :-------------- | :--------------- |
| `wifi`      | ~55 %           | both 2.4 / 5 GHz |
| `BLE`       | ~15 %           | 2.4 GHz only     |
| `ZigBee`    | ~10 %           | 2.4 GHz only     |
| `Microwave` | ~10 %           | 2.4 GHz only     |
| `FHSS`      | ~10 %           | both bands       |

(Actual ratios vary stochastically per run.)

---

## 🧾 **Example Queries**

```python
# Load data
import pandas as pd
fft = pd.read_csv("fft_dataset.csv")
ap = pd.read_csv("ap_log.csv")
cl = pd.read_csv("client_log.csv")

# Example: mean QoE per interference type
ap.groupby("nwifi_type")["mean_qoe"].mean().sort_values()

# Example: FFT snapshot for BLE vs Wi-Fi
fft.query("label in ['BLE','wifi']").sample(5)
```

---

## 💡 **Summary**

* Simulates realistic AP-Client + Spectrum dynamics under mixed Wi-Fi/non-Wi-Fi interference.
* Aligned multi-modal data streams: *spectral, aggregate, and per-link telemetry*.
* Ready for supervised ML (classification/regression) or RL-based RRM policy research.
* Fully reproducible and configurable (resolution, duration, noise models).

