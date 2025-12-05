# RRM+ API Portfolio

This directory aggregates the prototype services and simulations that make up the RRM+ API surface for the Arista mid-term milestone. Each subfolder is self-contained and exposes its own README with deeper usage notes, but this overview highlights how the pieces fit together and what to run first.

| Subsystem | Path | Purpose | Entry Points |
|-----------|------|---------|--------------|
| Client View Acquisition | `ClientViewAcquisition/` | High-fidelity Wi-Fi network simulator that generates synthetic telemetry, RRM events, and acceptance metrics for downstream consumers. | `persona_generator.py`, `cva_simulation.py`, `README.md` |
| Non-WiFi Classifier | `NonWiFi Classifier/` | TensorFlow-based classifier used by spectrum automation features to distinguish Wi-Fi from six classes of non-Wi-Fi interference. | `nonwifiinference.py`, `NonWiFiClassifier.ipynb`, `README.md` |
| Policy & GuardRails | `Policy and GuardRails/` | Online Bayesian Optimization (BO) engine and simulators that derive safe AP policy updates (Tx power, OBSS-PD, channel width). | `control_sim.py`, `BO/simulation_driver.py`, `ReadMe.txt` |
| Sensing Orchestra | `SensingOrchestra/` | Multi-armed bandit (MAB) scheduler that orchestrates channel scanning, adheres to DFS constraints, and consumes Non-WiFi classifications. | `SensingOrchestra.py`, `README.md` |

## Getting Started

1. **Set up Python environments** (recommended: one virtual environment per subsystem to avoid dependency collisions).
2. **Run ClientViewAcquisition** to generate telemetry schemas (`telemetry_schema.md`) plus acceptance metrics consumed by API clients.
3. **Train or validate the Non-WiFi Classifier** (`NonWiFiClassifier.ipynb`). Export the model to `NonWiFi Classifier/model/best_model.h5` for use by MAB services.
4. **Simulate spectrum policy loops** with Policy & GuardRails. Start with `control_sim.py` for quick iteration, then drive the full BO workflow via `BO/simulation_driver.py`.
5. **Launch Sensing Orchestra** so it can coordinate scanning and call into the classifier via the documented metadata contract.

## How Components Interact

- **Telemetry Flow:** ClientViewAcquisition emits device and AP telemetry that downstream API endpoints expose to dashboards and the policy engine.
- **Spectrum Intelligence:** Sensing Orchestra relies on the Non-WiFi classifier (`nonwifiinference.py`) to annotate scans; its logic ensures airtime impact remains \<2% and respects DFS rules.
- **Closed-Loop Policy:** Policy & GuardRails ingests telemetry/multi-day logs and continuously tunes RF parameters, feeding new settings back to AP simulators.

## Documentation Conventions

- Every subsystem now has a `README` (Markdown) in its root. If you add a new API component, mirror this layout and link it here.
- Store generated artifacts (models, CSVs, reports) under clearly named subdirectories (`model/`, `data/`, `reports/`) so scripts can rely on stable relative paths.
- Keep shared schemas in Markdown (`*-schema.md`) at the subsystem level; aggregate specs belong in `telemetry_schema.md` or the project root.

## Next Steps

- Flesh out REST/OpenAPI descriptions inside `SensingOrchestra/utils/api_definitions.yaml`.
- Add smoke tests (or notebooks) that exercise cross-component flows, e.g., sending ClientViewAcquisition telemetry through the policy engine and exposing summarized KPIs via a dashboard.

