WiFi Bayesian Optimization Simulator
-----------------------------------

This folder contains code for simulating and optimizing WiFi performance by
tuning three parameters:
- Transmit Power
- OBSS-PD Threshold
- Channel Width

The optimization is done using an Online Bayesian Optimization (BO) approach.

------------------------------------------------------------
Folder and File Description
------------------------------------------------------------

control_sim.py
    Runs a simple standalone simulation using random values for
    transmit power, OBSS-PD, and channel width.

BO/
    wifi_simulator_single_sample.py
        Simulates the WiFi environment for one configuration
        (Tx power, OBSS-PD, channel width).

    rmm_online_bo.py
        Contains the Bayesian Optimizer and the Policy Engine.
        Selects the next candidate configuration based on model predictions
        and rules.

    LHS_sampling.py
        Generates the initial dataset using Latin Hypercube Sampling (LHS)
        to bootstrap the optimization.

    simulation_driver.py
        Main script for running the complete 20-day BO simulation.
        Uses the initial dataset, calls the BO loop, and logs results.

------------------------------------------------------------
How to Run
------------------------------------------------------------

1. To run the simple simulation with random parameters:
    python control_sim.py

2. To run the full Bayesian Optimization simulation:
    python BO/LHS_sampling.py
    python BO/simulation_driver.py

This will:
- Generate the initial dataset
- Run the BO loop for 20 simulated days
- Log results for each day



