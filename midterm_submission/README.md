# Team28 – Arista HP4 Platform

This repository captures the end-to-end prototype we built for the Arista mid-term milestone: a simulated Wi-Fi environment, closed-loop policy automation, sensing orchestration, and supporting dashboards/results. Each major subsystem is isolated in its own folder with a dedicated README so you can explore or extend the components independently.

## Repository Layout

| Path                             | Description                                                                                                                                                                                               |
| -------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `API/`                         | Source for all four core services (Client View Acquisition, Non-WiFi Classifier, Policy & GuardRails, and Sensing Orchestra). Each subdirectory has a detailed README plus runnable scripts or notebooks. |
| `All the results/`             | Raw artifacts generated from the latest simulation and optimization runs (logs, CSV exports, classifier reports, etc.).                                                                                   |
| `Dashboard/`                   | PNG assets for the presentation/dashboard (KPI trends, Bayesian optimization traces, classifier confusion matrix).                                                                                        |
| `acceptance_metrics_report.md` | Markdown report summarizing RRM KPIs from the Client View Acquisition simulation.                                                                                                                         |
| `telemetry_schema.md`          | Canonical schema for telemetry produced by the simulated environment and consumed by downstream APIs.                                                                                                     |

## Getting Started

1. **Pick a subsystem** under `API/` and follow its README for specific dependencies (TensorFlow for the classifier, NumPy/Pandas for ClientViewAcquisition, etc.). Using one virtual environment per subsystem keeps heavier stacks isolated.
2. **Run the flow end-to-end** (recommended order):
   1. `ClientViewAcquisition` – generate personas, run `cva_simulation.py`, and produce telemetry + acceptance metrics.
   2. `NonWiFi Classifier` – train or validate the FFT classifier, export `model/best_model.h5`, and run `nonwifiinference.py`.
   3. `Policy and GuardRails` – simulate Online Bayesian Optimization via `BO/simulation_driver.py`.
   4. `SensingOrchestra` – orchestrate scanning, ingest classifier predictions, and log DFS-aware channel actions.
3. **Review artifacts** in `All the results/` to validate the latest run before sharing with stakeholders or the dashboard.

## Results & Dashboards

- **All the results**: contains BO logs (`First_BO_guardrails_log.csv`), sensing event traces (`SensingOrchestra_events.log`), channel metrics, and classifier evaluation exports (`NonWifi_Classifier_results/` with confusion matrix PNG, classification report, inference CSV, and CPU/RAM measurements).
- **Dashboard**: static images that back the mid-term review slides (`*_over_days.png`, `confusion_matrix.png`). Replace them with the newest charts whenever you re-run simulations.
- **Reports**: the repository root `acceptance_metrics_report.md` and `telemetry_schema.md` files are referenced by multiple teams; keep them updated after every major simulation or schema change.

## Conventions & Next Steps

- Each API subsystem README documents its runtime contract and directory structure. When adding new services, mirror that layout and link them from `API/README.md`.
- Generated artifacts should live under clearly named folders (`model/`, `data/`, `reports/`) so automation scripts can rely on stable paths.
- For the next iteration consider:
  1. Converting `Dashboard/` assets into live notebooks that regenerate plots from the CSV logs.
  2. Publishing an OpenAPI spec for all RRM+ endpoints (start from `SensingOrchestra/utils/api_definitions.yaml`).
  3. Adding lightweight CI smoke tests (one per subsystem) to ensure scripts keep running as dependencies evolve.
