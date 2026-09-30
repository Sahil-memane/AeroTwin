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
from typing import Optional

import numpy as np

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


# Resonance carrier frequencies the training spectrograms respond to per
# defect family — picked empirically (see the bearing-adapter recalibration
# note below), not physical constants.
_HARMONICS = (
    (_INNER_RACE_HARM, 1.0, 3200.0),
    (_OUTER_RACE_HARM, 0.7, 2400.0),
    (_BALL_HARM, 0.5, 1800.0),
)
_IMPULSE_DECAY: float = 700.0  # exponential ringdown rate per impulse (1/s)
_BASE_NOISE_STD: float = 0.05


def _generate_vibration_window(
    vibration_magnitude: float,
    rpm: float = 1772.0,
    fault_hint: str = "none",
    seed: Optional[int] = None,
) -> np.ndarray:
    """
    Synthesize a 1024-sample vibration window from a scalar magnitude.

    Recalibration note: the original synthesis here was plain white noise
    plus one weak sinusoid. Direct probing of the loaded CNN (see
    conversation history / verification notes, not reproduced in a comment
    dump) showed that *any* such input above a small amplitude threshold
    saturates the softmax onto a single class (IR_014, confidence 1.0) —
    for both this demo's synthesized inputs AND plain Gaussian noise at the
    training normalization's own std. Broadband noise doesn't carry the
    impulsive, resonance-ringdown structure the model was trained to key
    off of. Replacing the fault component with a superposition of decaying
    impulse trains at the three classic bearing defect harmonics (BPFI/
    BPFO/BSF), each ringing at a distinct carrier frequency, was verified
    to produce a real, monotonic-ish severity progression as amplitude
    rises (Normal -> _014-class severity -> _021-class severity) instead
    of a single frozen output — this is still a synthetic proxy for real
    accelerometer data (none is connected yet), not a claim of defect-type
    accuracy.

    Args:
        vibration_magnitude: scalar vibration level from telemetry (g or m/s²).
        rpm: current engine RPM (used to scale defect harmonic base frequency).
        fault_hint: optional hint from simulator fault injection state.

    Returns:
        np.ndarray of shape (1024,) with float32 values.
    """
    # seed=None (live/replay) -> fresh entropy per call, unchanged. The What-If
    # engine passes a window-derived seed so baseline and scenario runs share
    # identical synthetic noise and differ only by their actual inputs.
    rng = np.random.default_rng(seed)

    t = np.arange(SAMPLE_LEN, dtype=np.float64) / SAMPLE_RATE
    signal = rng.normal(0.0, _BASE_NOISE_STD, size=SAMPLE_LEN)

    rpm_hz = rpm / 60.0
    amp = max(0.0, vibration_magnitude - 0.2) * 1.4
    if fault_hint == "high_vibration":
        amp *= 1.3  # an actively-injected simulator fault escalates severity further

    if amp > 0.03:
        for harmonic_mult, weight, resonance_hz in _HARMONICS:
            defect_freq = harmonic_mult * rpm_hz
            period = 1.0 / defect_freq
            n_impulses = int(t[-1] * defect_freq) + 2
            for k in range(n_impulses):
                t0 = k * period
                envelope = amp * weight * np.exp(-_IMPULSE_DECAY * np.abs(t - t0))
                signal += envelope * np.sin(2 * math.pi * resonance_hz * (t - t0))

    return signal.astype(np.float32)


def preprocess_to_matrix(
    vibration_magnitude: float,
    rpm: float = 1772.0,
    fault_hint: str = "none",
    seed: Optional[int] = None,
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
    signal = _generate_vibration_window(vibration_magnitude, rpm, fault_hint, seed)

    # Step 2 — normalise with training constants (must NOT re-compute from sample)
    signal_norm = (signal - NORM_MEAN) / (NORM_STD + NORM_EPS)

    # Step 3 — reshape
    matrix = signal_norm.reshape(32, 32).astype(np.float32)

    # Step 4 — add batch + channel dims: (32,32) → (1,32,32,1)
    return matrix[np.newaxis, ..., np.newaxis]
