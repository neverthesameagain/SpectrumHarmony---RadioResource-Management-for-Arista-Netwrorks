# Non-WiFi Classifier Service

This component provides the spectrum-intelligence microservice that Sensing Orchestra queries to understand whether an observed FFT capture contains Wi-Fi or one of six common non-Wi-Fi interferers (BLE, ZigBee, Microwave, FHSS, Radar). It contains the trained TensorFlow model plus two reference entry points:

- `NonWiFiClassifier.ipynb` – notebook that shows the original training and evaluation workflow (for retraining or experimentation).
- `nonwifiinference.py` – production-style Python module that loads the exported model and performs continuous inference over streaming FFT tensors.

## Repository Layout

```
NonWiFi Classifier/
├── README.md
├── NonWiFiClassifier.ipynb         # Training and evaluation walkthrough
├── nonwifiinference.py             # Real-time inference loop + demo source
└── model/
    └── best_model.h5               # Saved TensorFlow/Keras model weights
```

The inference script expects the model artifact to live under `model/best_model.h5`, so keep new exports in that directory (or update the `MODEL_PATH` constant if you change the layout).

## Prerequisites

- Python 3.9+
- `tensorflow>=2.12`
- `numpy`

Optional (for notebook use): `matplotlib`, `scikit-learn`, `pandas`, and `jupyter`.

Create a virtual environment before installing TensorFlow to avoid polluting the system Python:

```bash
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install tensorflow numpy
```

## Running Real-Time Inference

1. **Activate your environment** and `cd` into `API/NonWiFi Classifier`.
2. **Point the FFT source**:
   - The default `demo_fft_source()` emits random FFT frames once per second and is only meant for smoke testing the loop.
   - Replace `demo_fft_source` with a generator that pulls from your radio/AP/Kafka feed or inject FFTs into the provided `queue.Queue`.
3. **Run the service**:
   ```bash
   python nonwifiinference.py
   ```
   Each FFT is normalized, classified, and appended to `live_inference_output.jsonl`. Live results are echoed to stdout.

## Integrating with Other API Components

- The script exposes `infer_fft` and `continuous_loop` so other subsystems (for example Sensing Orchestra) can import the module and supply their own `get_next_fft_fn`.
- Metadata keys required from the FFT source are documented inside `continuous_loop`. Retain the schema so downstream consumers can correlate predictions with AP/channel telemetry.

## Updating the Model

1. Open `NonWiFiClassifier.ipynb`, retrain or fine-tune the network, and export the new weights to `model/best_model.h5`.
2. Capture the training configuration or new preprocessing requirements in this README (or a CHANGELOG) so inference remains consistent.
3. Re-run `nonwifiinference.py` to confirm the new artifact loads and produces expected predictions.

