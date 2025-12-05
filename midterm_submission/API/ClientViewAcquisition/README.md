# RRM+ Client-View Acquisition Simulation

This project provides a high-fidelity simulation of a Wi-Fi network to test and evaluate an advanced Radio Resource Management (RRM) system. The simulation models a diverse population of client devices and Access Points (APs) to assess the effectiveness of an intelligent RRM scheduler in optimizing the network through client steering.

## Key Features

- **Realistic Client Behavior:** Simulates a variety of client device types (defined in `client_personas.py`) with different capabilities, including support for 802.11v, different operating systems, and unique roaming characteristics.
- **Advanced RRM Scheduler:** The APs implement a sophisticated RRM scheduler that monitors client Quality of Experience (QoE) and AP load to make intelligent steering decisions.
- **Predictive QoE Model:** Utilizes a mock machine-learning model to predict a client's post-roam QoE on a potential new AP, enabling more intelligent, data-driven steering.
- **Active vs. Passive Inference:** Correctly models the two primary RRM strategies:
    - **Active Inference:** Gracefully steering 802.11v-capable clients using BSS Transition Management requests.
    - **Passive Inference:** Monitoring non-802.11v clients and using disruptive actions (forced disconnection) as a last resort.
- **Detailed Reporting:** Generates a detailed markdown report (`acceptance_metrics_report.md`) summarizing the effectiveness of steering actions by device class, OS, and capability.

## Project Structure

The project is organized into several key Python modules:

- `cva_simulation.py`: The main driver script that initializes and runs the entire simulation.
- `persona_generator.py`: A utility script to generate the synthetic AP layout and client population files required for the simulation.
- `environment.py`: Defines the physical simulation environment, managing AP locations, client positions, and global network state like airtime utilization.
- `access_point.py`: Implements the AP, including the core RRM scheduling logic, the QoE prediction model, and client management.
- `client_device.py`: Implements the client device, simulating its movement, QoE calculation, scanning behavior, and response to steering commands.
- `client_personas.py`: A configuration module that defines the characteristics of all simulated client device types.
- `generate_telemetry_schema.py`: A script that generates a markdown file describing the telemetry data that would be collected in a real-world deployment.

## Setup and Installation

The simulation requires Python 3 and a few common libraries.

1.  **Prerequisites:** Ensure you have Python 3 installed.
2.  **Install Dependencies:** Install the required libraries using pip.
    ```bash
    pip install pandas numpy
    ```

## How to Run the Simulation

Running the simulation is a two-step process.

1.  **Generate the Simulation Scenario:**
    First, run the `persona_generator.py` script. This will create the `synthetic_ap_layout.csv` and `synthetic_client_population.csv` files that define the environment for the simulation.
    ```bash
    python persona_generator.py
    ```

2.  **Run the Main Simulation:**
    Once the scenario files are generated, run the main simulation script.
    ```bash
    python cva_simulation.py
    ```
    The simulation will run for a configured duration, and you will see log output in your terminal as it progresses.

## Simulation Outputs

After a successful run, the simulation will generate or update the following files:

- `acceptance_metrics_report.md`: A detailed report containing a summary of RRM KPIs and a breakdown of steering success and failure rates by device class.
- `telemetry_schema.md`: A markdown file outlining the schema for the types of telemetry data this RRM system would generate.
