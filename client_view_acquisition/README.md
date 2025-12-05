RRM+ Client-View Acquisition Simulation

This project provides a high-fidelity simulation of an enterprise Wi-Fi network. It tests basic connectivity and also generates data for training the AI models (Graph Neural Networks, Causal Inference, and Anomaly Detection).

The simulation models a diverse population of client devices (from iPhones to legacy IoT sensors) and an intelligent Access Point architecture that captures deep telemetry—from Layer 2 MAC stats down to Layer 4 Transport metrics and 802.11mc fine timing.

# Key Features

## 1. Realistic Client & Physics Engine

- **Device Personas:** Simulates specific hardware behaviors (e.g., an iPhone 15 Pro roams differently than a legacy ESP32 sensor).

- **Physics-Based Environment:** Calculates Path Loss, RSSI, SNR, and simulates realistic interference patterns (including Hidden Nodes).

- **Transport Layer Simulation:** Goes beyond Wi-Fi signal strength to simulate TCP/QUIC latency (Bufferbloat), Jitter, and Packet Loss, allowing the system to detect "silent" network issues.

## 2. Intelligent RRM Scheduler

- **Active & Passive Steering:** Uses 802.11v BSS-TM for capable clients and forced dissociation for legacy clients.

- **Predictive QoE:** Uses a mock ML model to rank candidate APs based on predicted post-roam quality.

- **Adaptive Telemetry:** Automatically adjusts polling intervals based on client stability and network load.

## 3. Causal Inference Engine

- **Counterfactual Generation:** The system randomly holds back valid steering actions (creates a "Control Group") to measure the actual uplift of RRM decisions.

- **Closed-Loop Validation:** Logs both the state before an action and the result after a delay, enabling true Uplift Modeling.

## 4. 802.11mc Location Services

- **Fine Timing Measurement (FTM):** Simulates RTT-based distance measurements (with realistic multipath noise) for modern clients, enabling precise interference geolocation.

# The AI Data Ecosystem

This simulation generates three critical datasets for the End-Term AI models. Here is what they are and why they matter:

## A. The "Diagnosis" Dataset (client_transport_qoe.csv)

What it contains: TCP RTT, Jitter, and Retransmission rates correlated with AP Load and SNR.

AI Model Role: Trains Inference / Anomaly Detection Models.

Why: To teach the AI how to distinguish between Coverage holes (Low Signal) and Congestion (Bufferbloat). A client with strong signal but high latency needs a different solution (Load Balancing) than a client with weak signal (Steering).

## B. The "Map" Dataset (client_rtt_measurements.csv)

- **What it contains:** Distance measurements (in meters) between clients and APs.

- **AI Model Role:** Trains Graph Neural Networks (GNN).

- **Why:** By feeding distance + failure rates into a GNN, the system can triangulate "Invisible Interference Hotspots" (e.g., a microwave oven at coordinates X,Y) that are degrading performance for everyone in that specific zone.

## C. The "Judge" Dataset (causal_inference_data.csv)

- **What it contains:** Records of Treatment (Steered) vs. Control (Held Back) events, including Pre_QoE (Baseline) and Post_QoE (Outcome).

- **AI Model Role:** Trains Uplift Models (Causal Forests).

- **Why:** To move beyond simple "Average Improvement." This data teaches the AI to predict exactly how much a specific client will benefit from a steer, filtering out luck and environmental noise.

# Project Structure

- **cva_simulation.py:** The orchestrator. Runs the physics loop, manages the clock, and exports the final AI datasets.

- **client_device.py:** The physics engine. Simulates movement, calculates signal math, and generates the new Transport/RTT telemetry.

- **access_point.py:** The "Brain." Collects telemetry, runs the RRM logic, and manages the Causal Holdout groups.

- **environment.py:** The world state. Manages global interference (Hidden Nodes) and AP load.

- **client_personas.py:** Configuration file defining device capabilities (OUI, OS, 802.11k/v/r support).

- **persona_generator.py:** Utility to create random but realistic office layouts.

# How to Run

## Install Dependencies:

```bash
pip install pandas numpy
```

## Generate the World:

Create a new random office layout and client population.

```bash
python persona_generator.py

```

## Run the Simulation:

This will run the physics engine (default: 1 hour) and generate all reports.

```bash
python cva_simulation.py
```

## Simulation Outputs

After running the simulation, you will find these files in your directory:

- **acceptance_metrics_report.md:** A human-readable report summarizing steering success rates and device compatibility.

- **telemetry_schema.md:** Technical documentation of the database schema for the backend team.

- **client_transport_qoe.csv:** Raw training data for the Inference Model.

- **client_rtt_measurements.csv:** Raw training data for the GNN Location Model.

- **causal_inference_data.csv:** Raw training data for the Causal Uplift Model.
