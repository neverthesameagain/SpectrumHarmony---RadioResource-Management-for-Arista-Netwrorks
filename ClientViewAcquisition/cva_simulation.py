"""
This module contains the main simulation script for the Client-View Acquisition (CVA) phase
of the RRM-plus project.

This script simulates a wireless network environment with Access Points (APs) and
Client Devices, and runs a full-scale simulation to evaluate the performance of the
Radio Resource Management (RRM) scheduler. It generates an acceptance matrix report
and a telemetry schema as its main outputs.
"""


import random
from collections import defaultdict
import os
import pandas as pd
from access_point import AccessPoint
from client_device import ClientDevice

# --- NEW: Import the single source of truth ---
from client_personas import CLIENT_PERSONAS
from environment import Environment

# --- Physics & Config ---
RSSI_MIN, RSSI_MAX = -70, -30
RADIUS_M = 10.0


def generate_acceptance_matrix_report(all_aps, all_clients):
    """
    Generates the "Acceptance metrics by device class"
    deliverable by aggregating stats from all APs.
    """
    total_stats = defaultdict(lambda: {"attempts": 0, "success": 0, "rejects": 0})
    all_qoe_deltas = []
    ap_qoe_deltas = defaultdict(list)

    for ap in all_aps:
        ap_stats = ap.get_steering_stats()
        all_qoe_deltas.extend(ap_stats["qoe_deltas"])
        ap_qoe_deltas[ap.ap_id].extend(ap_stats["qoe_deltas"])
        for persona_name, metrics in ap_stats["by_persona"].items():
            total_stats[persona_name]["attempts"] += metrics["attempts"]
            total_stats[persona_name]["success"] += metrics["success"]
            total_stats[persona_name]["rejects"] += metrics["rejects"]

    report_lines = []
    report_lines.append("# Mid-Term Deliverable: Acceptance Metrics by Device Class")
    report_lines.append(
        f"\nThis report details the effectiveness of RRM steering actions across a simulated environment of **{len(all_aps)} APs** and **{len(all_clients)} clients**."
    )

    total_attempts = sum(stats["attempts"] for stats in total_stats.values())
    total_successes = sum(stats["success"] for stats in total_stats.values())
    overall_acceptance_rate = (
        (total_successes / total_attempts * 100) if total_attempts > 0 else 0
    )
    avg_qoe_delta = (sum(all_qoe_deltas) / len(all_qoe_deltas)) if all_qoe_deltas else 0

    report_lines.append("\n## Overall RRM KPI Summary")
    report_lines.append(f"- **Total Steering Attempts:** {total_attempts}")
    report_lines.append(f"- **Total Successful Steers:** {total_successes}")
    report_lines.append(
        f"- **Overall Acceptance Rate:** **{overall_acceptance_rate:.1f}%**"
    )
    report_lines.append(
        f"- **Average Post-Roam QoE Delta:** **{avg_qoe_delta:+.2f} points**"
    )

    report_lines.append("\n## AP-Specific QoE Delta")
    report_lines.append("| AP ID | Average QoE Delta |")
    report_lines.append("| :--- | :---: |")
    for ap_id, deltas in ap_qoe_deltas.items():
        avg_delta = (sum(deltas) / len(deltas)) if deltas else 0
        report_lines.append(f"| {ap_id} | {avg_delta:+.2f} |")

    report_lines.append("\n## Steering Success Matrix (by Device Class)\n")
    report_lines.append(
        "| Device Class (Persona) | OUI | OS Class | 802.11k/v Capable? | Steer Attempts | Steer Successes | Steer Rejects | Acceptance Rate |"
    )
    report_lines.append(
        "| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: |"
    )

    for persona_key, persona_details in CLIENT_PERSONAS.items():
        name = persona_details["name"]
        stats = total_stats[name]
        attempts = stats["attempts"]
        successes = stats["success"]
        rejects = stats["rejects"]

        if attempts > 0:
            acceptance_rate = (successes / attempts) * 100
            acceptance_rate_str = f"{acceptance_rate:.1f}%"
        else:
            acceptance_rate_str = "N/A"

        capable_str = "✅ Yes" if persona_details["supports_80211v"] else "❌ No"

        report_lines.append(
            f"| {name} | `{persona_details['oui']}` | {persona_details['os_class']} | {capable_str} | {attempts} | {successes} | {rejects} | **{acceptance_rate_str}** |"
        )

    return "\n".join(report_lines)


# ------------------------------------------------------------------
# --- MAIN SIMULATION SCRIPT ---
# ------------------------------------------------------------------

if __name__ == "__main__":
    print("==========================================================")
    print("== Full-Scale RRM Simulation w/ Smart Scheduler (v4) ==")
    print("==========================================================\n")

    SIM_DURATION_HOURS = 1
    STEP_DURATION_S = 10
    TOTAL_STEPS = int((SIM_DURATION_HOURS * 3600) / STEP_DURATION_S)
    print(
        f"Simulating {SIM_DURATION_HOURS} hour ({TOTAL_STEPS} steps of {STEP_DURATION_S}s each)..."
    )

    # 1. Create the World
    sim_environment = Environment()

    # 2. Load APs and Clients from CSV files
    try:
        ap_df = pd.read_csv("synthetic_ap_layout.csv")
        client_df = pd.read_csv("synthetic_client_population.csv")
    except FileNotFoundError:
        print("ERROR: CSV files not found.")
        print("Please run the `persona_generator.py` script first to generate:")
        print("  - synthetic_ap_layout.csv")
        print("  - synthetic_client_population.csv")
        exit()

    print(f"Loading {len(ap_df)} APs and {len(client_df)} clients from CSVs...")

    all_aps = [AccessPoint(sim_environment, row) for _, row in ap_df.iterrows()]
    all_clients = [
        ClientDevice(sim_environment, row) for _, row in client_df.iterrows()
    ]

    print(f"\n--- Phase 1: Initial Client Association ({len(all_clients)} clients) ---")
    for ap in all_aps:
        sim_environment.ap_load_stats[ap.ap_id]["airtime_util_pct"] = random.uniform(
            5.0, 15.0
        )
    for client in all_clients:
        client.find_best_ap_and_associate()
    print("--- Phase 1 Complete ---")

    print("\n--- Phase 2: Simulating High-Load Stress & RRM Checks ---")
    ap_by_clients = sorted(
        all_aps,
        key=lambda ap: sim_environment.get_ap_load(ap.ap_id)["client_count"],
        reverse=True,
    )
    stressed_aps = []
    for i in range(min(3, len(ap_by_clients))):
        ap = ap_by_clients[i]
        sim_environment.ap_load_stats[ap.ap_id]["airtime_util_pct"] = 90.0
        stressed_aps.append(ap.ap_id)
    print(f"[ENV]: STRESS: Setting {', '.join(stressed_aps)} airtime to 90%")

    # --- NEW: Activate a hidden node ---
    # Place it near the 2nd busiest AP (index 1) to affect its clients
    if len(ap_by_clients) > 1:
        hn_x = ap_by_clients[1].x + (RADIUS_M / 2)  # Place it 5m away from the AP
        hn_y = ap_by_clients[1].y
        sim_environment.activate_hidden_node(x=hn_x, y=hn_y, radius=8.0)  # 8m radius
    # --- End New ---

    print(f"\n--- Running Simulation for {TOTAL_STEPS} ticks... ---")

    for step in range(TOTAL_STEPS):
        if step % (3600 // STEP_DURATION_S) == 0:
            print(f"  Simulating hour {step // (3600 // STEP_DURATION_S) + 1}...")

        for client in all_clients:
            client.move()

        for ap in all_aps:
            for client in list(ap.connected_clients):
                ap.scheduler_tick(client, step)

    print("--- Simulation Ticks Complete ---")

    print("\n\n==========================================================")
    print("== Simulation Finished ==")
    print("==========================================================\n")
    print("Final AP Load Distribution:")
    for ap in all_aps:
        load = sim_environment.get_ap_load(ap.ap_id)
        print(
            f"  {ap.ap_id}: {load['client_count']} clients (Airtime: {load['airtime_util_pct']:.1f}%)"
        )
    print("\n==========================================================")

    # --- GENERATE DELIVERABLES ---
    acceptance_report_markdown = generate_acceptance_matrix_report(all_aps, all_clients)
    with open("acceptance_metrics_report.md", "w") as f:
        f.write(acceptance_report_markdown)
    print("\n✅ Successfully generated 'acceptance_metrics_report.md'")

    os.system("python generate_telemetry_schema.py")

