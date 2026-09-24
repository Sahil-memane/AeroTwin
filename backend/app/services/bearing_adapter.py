"""
bearing_adapter.py

Converts a single scalar vibration_magnitude (from piston engine telemetry)
into the 32x32 matrix representation that Model 3 CNN was trained on.

Training preprocessing contract (from normalization.json):
  - mean : 0.01568922728195663
  - std  : 0.4564410815002781
  - normalization: x_norm = (x - mean) / (std + 1e-8)
  - reshape: (1024,) -> (32, 32) -> add channel -> (1, 32, 32, 1)
"""

import math
import numpy as np
from typing import Dict, Any

# ── Training normalization constants (from normalization.json) ────────
NORM_MEAN: float = 0.01568922728195663
NORM_STD:  float = 0.4564410815002781
NORM_EPS:  float = 1e-8

# ── Simulated CWRU-like sampling parameters ───────────────────────────
# The CWRU dataset was captured at 48 kHz; each 32x32 sample = 1024 pts.
# Our simulator runs at ~1 Hz so we synthesize the 1024-pt window per tick.
SAMPLE_LEN: int = 1024         # = 32 × 32
SAMPLE_RATE: float = 48_000.0  # Hz (nominal, used for frequency scaling)

# Defect frequency multipliers (approximate BPFI/BPFO/BSF for a 6205 bearing)
_INNER_RACE_HARM:  float = 5.415   # Ball Pass Frequency Inner Race (BPFI)
_OUTER_RACE_HARM:  float = 3.585   # Ball Pass Frequency Outer Race (BPFO)
_BALL_HARM:        float = 2.357   # Ball Spin Frequency (BSF)


def _generate_vibration_window(
    vibration_magnitude: float,
    rpm: float = 1772.0,
    fault_hint: str = "none",
) -> np.ndarray:
    """
    Synthesize a 1024-sample vibration window from a scalar magnitude.

    The waveform is composed of:
      - White noise at the given amplitude (always present).
      - Harmonic fault signatures injected when magnitude is elevated,
        shaped to loosely mimic CWRU defect patterns.

    This keeps the CNN inference flowing in real-time during the demo
    while the real accelerometer data source is not yet connected.

    Args:
        vibration_magnitude: scalar vibration level from telemetry (g or m/s²).
        rpm: current engine RPM (used to scale defect harmonic base frequency).
        fault_hint: optional hint from simulator fault injection state.

    Returns:
        np.ndarray of shape (1024,) with float32 values.
    """
    rng = np.random.default_rng()  # fresh RNG per call — no reproducibility needed

    # Base white noise scaled to the vibration magnitude
    noise_amp = vibration_magnitude * 0.6
    signal = rng.normal(0.0, noise_amp, size=SAMPLE_LEN).astype(np.float32)

    # Time axis
    rpm_hz = rpm / 60.0
    t = np.linspace(0.0, SAMPLE_LEN / SAMPLE_RATE, num=SAMPLE_LEN, endpoint=False, dtype=np.float32)

    # Inject harmonic content proportional to vibration above baseline
    fault_amp = max(0.0, vibration_magnitude - 0.25)  # only inject above quiet baseline

    if fault_amp > 0.05:
        if fault_hint == "high_vibration":
            # Strong outer-race harmonic when fault is active in simulator
            freq = _OUTER_RACE_HARM * rpm_hz
            signal += fault_amp * np.sin(2 * math.pi * freq * t, dtype=np.float32)
            signal += (fault_amp * 0.4) * np.sin(4 * math.pi * freq * t, dtype=np.float32)
        else:
            # Low-level bearing rumble — mostly white noise + mild shaft harmonic
            signal += (fault_amp * 0.3) * np.sin(2 * math.pi * rpm_hz * t, dtype=np.float32)

    return signal


def preprocess_to_matrix(
    vibration_magnitude: float,
    rpm: float = 1772.0,
    fault_hint: str = "none",
) -> np.ndarray:
    """
    Full preprocessing pipeline matching Model 3 training:
      1. Synthesise 1024-sample vibration window
      2. Z-score normalise with training mean/std
      3. Reshape to (32, 32)
      4. Add batch + channel dims → (1, 32, 32, 1)

    Returns:
        np.ndarray of shape (1, 32, 32, 1) ready for model.predict().
    """
    # Step 1 — synthesise
    signal = _generate_vibration_window(vibration_magnitude, rpm, fault_hint)

    # Step 2 — normalise with training constants (must NOT re-compute from sample)
    signal_norm = (signal - NORM_MEAN) / (NORM_STD + NORM_EPS)

    # Step 3 — reshape
    matrix = signal_norm.reshape(32, 32).astype(np.float32)

    # Step 4 — add batch + channel dims: (32,32) → (1,32,32,1)
    return matrix[np.newaxis, ..., np.newaxis]
