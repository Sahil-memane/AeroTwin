"""
Synthetic what-if telemetry generator. Given a mission envelope
(altitude, ambient temperature, airspeed, throttle pattern), computes a
plausible sensor timeline using the same first-principles physics model
the backend already uses for anomaly detection (`ml.training.physics_model`),
rather than inventing a second, disconnected curve-generation approach.
"""
import math
import os
import sys
from datetime import datetime, timedelta, timezone

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from ml.training.physics_model.otto_cycle_solver import compute_expected_telemetry  # noqa: E402
from ml.training.physics_model.specs import DEFAULT_SPECS  # noqa: E402

_THROTTLE_PATTERNS = {
    # Fraction of `peak_throttle` at each of 7 mission phases, matching
    # the taxi/takeoff/climb/cruise/descent/approach/touchdown shape the
    # (Phase 2) telemetry simulator already uses, so replay and what-if
    # curves read consistently.
    "climb_cruise_descent": [0.10, 0.55, 0.90, 1.0, 0.85, 0.45, 0.15],
    "aggressive": [0.10, 0.95, 1.0, 0.60, 1.0, 0.50, 0.15],
}


def generate_what_if_telemetry(profile: dict, num_points: int = 42) -> list[dict]:
    """
    Returns a list of synthetic telemetry dicts (same shape as a real
    `TelemetryReading`), `num_points` long, spanning a synthetic mission
    under the given environmental envelope.
    """
    altitude_m = float(profile.get("altitude_m", 0.0))
    ambient_temp_c = profile.get("ambient_temp_c")
    airspeed_mps = float(profile.get("airspeed_mps", 45.0))
    peak_throttle = float(profile.get("peak_throttle", 0.85))
    pattern = _THROTTLE_PATTERNS.get(profile.get("throttle_pattern", "climb_cruise_descent"), _THROTTLE_PATTERNS["climb_cruise_descent"])

    rpm_idle = DEFAULT_SPECS.rpm_idle
    rpm_max = DEFAULT_SPECS.rpm_max

    readings = []
    start = datetime.now(timezone.utc).replace(tzinfo=None)
    phase_len = max(1, num_points // len(pattern))

    for i in range(num_points):
        phase_idx = min(i // phase_len, len(pattern) - 1)
        # Smooth within a phase with a half-sine ramp rather than a hard step.
        within = (i % phase_len) / max(phase_len - 1, 1)
        throttle = max(0.08, pattern[phase_idx] * peak_throttle * (0.85 + 0.15 * math.sin(within * math.pi)))
        rpm = rpm_idle + (rpm_max - rpm_idle) * throttle

        expected = compute_expected_telemetry({
            "rpm": rpm,
            "throttle": throttle,
            "altitude_m": altitude_m,
            "ambient_temp_c": ambient_temp_c,
            "airspeed_mps": airspeed_mps,
        })

        # Small deterministic vibration signal — not physics-modeled, just
        # a plausible low-amplitude baseline so downstream bearing/aux
        # feature extraction has non-degenerate input.
        vib = 0.3 + 0.15 * math.sin(i * 0.7)

        readings.append({
            "ts": (start + timedelta(seconds=i * 2)).isoformat(),
            "rpm": round(rpm, 1),
            "cht": expected.cht,
            "egt": expected.egt,
            "oil_pressure": expected.oil_pressure,
            "oil_temp": expected.oil_temp,
            "fuel_flow": expected.fuel_flow_gph,
            "vibration_x": round(vib, 2),
            "vibration_y": round(vib * 0.8, 2),
            "vibration_z": round(vib * 0.6, 2),
            "throttle": round(throttle, 3),
            "altitude_m": altitude_m,
        })

    return readings
