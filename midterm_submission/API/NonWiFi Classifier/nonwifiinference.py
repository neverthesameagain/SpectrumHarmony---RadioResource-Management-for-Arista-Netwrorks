#!/usr/bin/env python3
"""
continuous_inference.py

Real-time inference script for the trained non-WiFi classifier.
Continuously reads FFT tensors (24 x 512), normalizes, runs inference,
and exports classification + confidence + spectral metadata.

This script can be deployed on-device or on server.
"""

import numpy as np
import tensorflow as tf
import time
import json
from pathlib import Path
import logging
import queue

# ============================
# CONFIG
# ============================
MODEL_PATH = "model/best_model.h5"
FRAMES = 24
BINS = 512

# optional output logging
OUTPUT_PATH = Path("live_inference_output.jsonl")
OUTPUT_PATH.unlink(missing_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("LiveInference")

# ============================
# LOAD MODEL
# ============================
log.info("Loading model...")
model = tf.keras.models.load_model(MODEL_PATH)

# assume classes (ordered)
CLASS_NAMES = ["wifi","BLE","ZigBee","Microwave","FHSS","Radar"]


# ============================
# NORMALIZE + INFER FUNCTION
# ============================
def infer_fft(tensor_24x512):
    """
    tensor_24x512 : np.ndarray shape (24, 512)
    Returns: (class_name, confidence)
    """

    # safety
    assert tensor_24x512.shape == (FRAMES, BINS)

    # normalize
    x = tensor_24x512
    x = (x - x.mean()) / (x.std() + 1e-6)
    x = np.expand_dims(x.astype(np.float32), axis=(0, -1))  # (1, 24, 512, 1)

    preds = model.predict(x, verbose=0)[0]
    idx = int(np.argmax(preds))
    return CLASS_NAMES[idx], float(preds[idx])


# ============================
# CONTINUOUS INFERENCE LOOP
# ============================
def continuous_loop(get_next_fft_fn):
    """
    get_next_fft_fn: a function that returns:
      (fft_tensor_24x512, metadata_dict)
    
    metadata_dict must include:
       - "timestamp"
       - "duty"
       - "center_mhz"
       - "bw_mhz"
       - "ap_id"
       - "band"
       - "channel"

    This function runs inference FOREVER.
    """

    log.info("Starting continuous inference... (Ctrl+C to stop)")

    while True:
        try:
            fft_tensor, meta = get_next_fft_fn()

            if fft_tensor is None:
                time.sleep(0.1)   # nothing new yet
                continue

            cls, conf = infer_fft(fft_tensor)

            result = {
                "timestamp": meta["timestamp"],
                "ap_id": meta["ap_id"],
                "band": meta["band"],
                "channel": meta["channel"],
                "duty": meta["duty"],
                "center_mhz": meta["center_mhz"],
                "bw_mhz": meta["bw_mhz"],

                "predicted_class": cls,
                "confidence": conf
            }

            # print live update
            print(f"[LIVE] {result['timestamp']} :: {cls} (conf={conf:.3f}) on ch={meta['channel']}")

            # append to log file
            with open(OUTPUT_PATH, "a") as f:
                f.write(json.dumps(result) + "\n")

            # small delay (tunable)
            time.sleep(0.01)

        except KeyboardInterrupt:
            log.warning("Stopping continuous inference...")
            break
        except Exception as e:
            log.error(f"Error: {e}")
            time.sleep(0.1)


# ============================
# EXAMPLE DATA SOURCE (SIMULATED)
# Replace this with real radio data source
# ============================
def demo_fft_source():
    """
    Example dummy FFT generator.
    Replace with:
      - reading from shared memory
      - reading from AP socket
      - reading from FPGA / USB radio
      - reading from incoming Kafka messages
      - reading from a FreeQueue
    """
    while True:
        # simulate waiting for next FFT
        time.sleep(1.0)

        fake_tensor = np.random.randn(FRAMES, BINS).astype(np.float32)

        meta = {
            "timestamp": time.time(),
            "ap_id": "AP24_1",
            "band": "2.4",
            "channel": 1,
            "duty": float(np.random.uniform(0.01, 0.9)),
            "center_mhz": 2412.0,
            "bw_mhz": 20.0,
        }

        yield fake_tensor, meta


# ============================
# WRAPPER TO YIELD FFTs ONE BY ONE
# ============================
fft_queue = queue.Queue()
def get_next_fft():
    try:
        return fft_queue.get_nowait()
    except queue.Empty:
        return None, None


# ============================
# MAIN
# ============================
if __name__ == "__main__":
    # feed the queue in background (simulation)
    def producer():
        for tensor, meta in demo_fft_source():
            fft_queue.put((tensor, meta))

    import threading
    threading.Thread(target=producer, daemon=True).start()

    continuous_loop(get_next_fft)
