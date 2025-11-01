
---

##  RRM+ Synthetic Environment Simulator

This repository contains the **Arista RRM+ Synthetic Data Generator**, a physics-driven simulation designed to emulate Wi-Fi and non-Wi-Fi spectrum interactions for multi-AP (Access Point) wireless networks.
It produces **realistic telemetry and spectral data** suitable for machine-learning models, spectrum sensing research, and QoE prediction pipelines.

---

### Overview

The simulator models a **6-AP, 240-client indoor wireless environment** operating over 24 hours (1-minute resolution).
It captures both **Wi-Fi communication dynamics** and **non-Wi-Fi interference** (BLE, ZigBee, microwave, FHSS), generating detailed per-minute logs for Access Points, Clients, and FFT spectral data.

The goal is to provide a reproducible dataset foundation for:

* Spectrum sensing & classification (Wi-Fi vs non-Wi-Fi)
* QoE estimation models (RSSI → SNR → Retry → Throughput → QoE)
* RRM policy development and safe decision optimization

---

###  Features

✅ **Hybrid RF Environment**

* 6 Access Points (mixed 2.4 GHz / 5 GHz)
* 40 Clients per AP (≤ 10 m radius)
* RSSI constrained to [−70, −40] dBm

✅ **Non-Wi-Fi Interference**

* Random BLE, ZigBee, FHSS, and microwave events
* Dynamic noise-floor penalties and FFT energy bursts

✅ **Per-Entity Telemetry**

* **Clients:** RSSI, SNR, Throughput, Retry %, QoE, Position, Distance, Non-Wi-Fi flag
* **APs:** Channel utilization, Noise floor, Overlap, Mean SNR, Mean/95th Distance, QoE
* **FFT:** 64-bin power spectrum labeled *Wi-Fi* / *Non-Wi-Fi*

✅ **Physically Grounded Models**

* Distance-based path loss
* SNR = RSSI − (Noise + Interference)
* Throughput ≈ PHY × Efficiency(SNR, Retry)
* QoE = f(SNR, Retry) ∈ [0, 5]

✅ **Progress + Validation**

* Live progress bar every 100 minutes
* End-of-run min/max summaries for RSSI, SNR, Throughput, Retry, QoE, Distance

---

### 🧩 Output Files

| File                  | Description                                                     |
| --------------------- | --------------------------------------------------------------- |
| `client_log_24h.csv`  | Per-minute metrics for all 240 clients                          |
| `ap_log_24h.csv`      | Aggregated AP-level telemetry (QoE, overlap, distances)         |
| `fft_dataset_24h.csv` | FFT-bin spectra labeled as `wifi` or `non_wifi` for ML training |

---

### 📊 Schema Summary

#### **Client Log**

| Field                                      | Description                               |
| ------------------------------------------ | ----------------------------------------- |
| `timestamp`                                | Minute timestamp                          |
| `client_id`, `connected_ap`                | IDs                                       |
| `band`, `channel`                          | AP radio band/channel                     |
| `rssi_dbm`, `snr_db`                       | Link quality metrics                      |
| `throughput_mbps`, `retry_rate_pct`, `qoe` | Performance indicators                    |
| `x`, `y`, `distance_m`                     | Spatial position & proximity              |
| `affected_nonwifi`                         | Whether exposed to non-Wi-Fi interference |

#### **AP Log**

| Field                                                 | Description               |
| ----------------------------------------------------- | ------------------------- |
| `noise_floor_dbm`, `channel_utilization_pct`          | Radio conditions          |
| `nwifi_detected`, `nwifi_count`, `overlap_score`      | Interference context      |
| `avg_client_snr_db`, `throughput_avg_mbps`            | Aggregate link quality    |
| `mean_qoe`, `p95_retry_pct`                           | AP performance indicators |
| `mean_distance_m`, `p95_distance_m`, `max_distance_m` | Spatial coverage metrics  |

#### **FFT Dataset**

| Field                      | Description                   |
| -------------------------- | ----------------------------- |
| `fft_bin_0` – `fft_bin_63` | Power spectral density values |
| `label`                    | `"wifi"` / `"non_wifi"`       |

---

### Running the Simulation

#### **Requirements**

```bash
python >= 3.10
pip install numpy pandas
```

#### **Run**

```bash
python rrmplus_simulation.py
```

#### **Console Output**

```
 Starting 24-hour simulation (6 APs, 240 clients)...
 Progress: minute 100/1440 (1.6 hrs simulated)
...
 Summary Statistics:
  rssi_dbm             → min:  -74.144,  max:  -27.899
  snr_db               → min:   10.555,  max:   40.000
  throughput_mbps      → min:    3.787,  max:  629.999
  retry_rate_pct       → min:    0.000,  max:  100.000
  qoe                  → min:    1.055,  max:    5.000
  distance_m           → min:    0.858,  max:    9.996

 Summary Statistics:
  avg_client_snr_db    → min:   23.549,  max:   38.825
  throughput_avg_mbps  → min:   37.431,  max:  581.884
  p95_retry_pct        → min:    1.715,  max:   98.493
  mean_qoe             → min:    2.858,  max:    4.964
  mean_distance_m      → min:    6.173,  max:    7.217
  p95_distance_m       → min:    9.141,  max:    9.799
  max_distance_m       → min:    9.698,  max:    9.996
```

---



---

### 📂 Repository Structure

```
├── rrmplus_simulation.py   # main simulation script
├── README.md               # this file
├── client_log_24h.csv      # generated dataset
├── ap_log_24h.csv
└── fft_dataset_24h.csv
```

---

