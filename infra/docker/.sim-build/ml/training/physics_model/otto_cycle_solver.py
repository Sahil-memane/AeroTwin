"""
Otto-cycle thermodynamic solver for the AeroTwin physics model.

Implements a first-principles aero-piston engine model that predicts
expected CHT, EGT, brake power, fuel flow, oil pressure, and oil temperature
from operating conditions (RPM, throttle, altitude, ambient temperature).

The solver is exposed as a set of **pure functions** with no side effects,
making it safe to call from both the ML training pipeline (feature
engineering) and the real-time backend inference service.

Reference thermodynamic cycle:
  1 → 2  Isentropic compression
  2 → 3  Constant-volume heat addition (combustion)
  3 → 4  Isentropic expansion (power stroke)
  4 → 1  Constant-volume heat rejection (exhaust)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from .specs import AtmosphericConstants, EngineSpecs, ISA, DEFAULT_SPECS


# ── Result dataclasses ────────────────────────────────────────────────


@dataclass(frozen=True)
class ExpectedTelemetry:
    """Predicted engine outputs from the thermodynamic model."""
    cht: float              # Expected Cylinder Head Temperature [°C]
    egt: float              # Expected Exhaust Gas Temperature [°C]
    brake_power_kw: float   # Expected brake power [kW]
    fuel_flow_gph: float    # Expected fuel flow [US gal/h]
    oil_pressure: float     # Expected oil pressure [psi]
    oil_temp: float         # Expected oil temperature [°C]
    thermal_efficiency: float  # Otto-cycle thermal efficiency [0–1]

    # Intermediate state temperatures (for debugging / explainability)
    T1: float               # Induction temperature [K]
    T2: float               # Post-compression temperature [K]
    T3: float               # Peak combustion temperature [K]
    T4: float               # Post-expansion (exhaust) temperature [K]


@dataclass(frozen=True)
class PhysicsDeviation:
    """
    Expected-vs-actual residuals and a composite anomaly score.

    Each ``delta_*`` field is ``actual - expected``; positive means the
    actual reading exceeds the physics prediction.

    ``deviation_score`` is a normalized composite:
      0.0  → perfectly nominal
      >1.0 → one or more channels are outside the thermodynamic envelope
    """
    delta_cht: float
    delta_egt: float
    delta_oil_pressure: float
    delta_oil_temp: float
    delta_fuel_flow: float
    deviation_score: float

    # The expected values used to compute the deltas (for explainability)
    expected: ExpectedTelemetry


# ── ISA atmosphere ────────────────────────────────────────────────────


def isa_temperature(altitude_m: float, atm: AtmosphericConstants = ISA) -> float:
    """Ambient temperature [K] at *altitude_m* per the ISA troposphere model."""
    return atm.T0 - atm.L * altitude_m


def isa_pressure(altitude_m: float, atm: AtmosphericConstants = ISA) -> float:
    """Ambient pressure [Pa] at *altitude_m* per the ISA troposphere model."""
    exponent = (atm.g * atm.M) / (atm.R * atm.L)
    return atm.P0 * (1.0 - (atm.L * altitude_m) / atm.T0) ** exponent


def isa_density(altitude_m: float, atm: AtmosphericConstants = ISA) -> float:
    """Air density [kg/m³] at *altitude_m*."""
    T = isa_temperature(altitude_m, atm)
    P = isa_pressure(altitude_m, atm)
    return P / (atm.R_specific * T)


# ── Otto-cycle solver ─────────────────────────────────────────────────


class OttoCycleSolver:
    """
    Stateless thermodynamic solver for a 4-stroke SI aero-piston engine.

    All methods are deterministic and side-effect-free.  Instantiate with
    an ``EngineSpecs`` to use non-default calibration constants.
    """

    def __init__(self, specs: EngineSpecs = DEFAULT_SPECS):
        self.specs = specs

    # ── Core cycle computation ────────────────────────────────────────

    def solve(
        self,
        rpm: float,
        throttle: float = 0.75,
        altitude_m: float = 0.0,
        ambient_temp_c: Optional[float] = None,
        airspeed_mps: float = 45.0,
    ) -> ExpectedTelemetry:
        """
        Compute expected engine telemetry from operating conditions.

        Parameters
        ----------
        rpm : float
            Engine RPM (typically 1400–5800).
        throttle : float
            Throttle position, 0.0 (idle / closed) to 1.0 (WOT).
        altitude_m : float
            Pressure altitude in metres (default 0 = sea level).
        ambient_temp_c : float | None
            Override ambient temperature [°C].  ``None`` → use ISA.
        airspeed_mps : float
            True airspeed [m/s] for ram-air cooling estimation.

        Returns
        -------
        ExpectedTelemetry
        """
        s = self.specs

        # ── Atmosphere ───────────────────────────────────────────────
        if ambient_temp_c is not None:
            T_amb = ambient_temp_c + 273.15
        else:
            T_amb = isa_temperature(altitude_m)
        P_amb = isa_pressure(altitude_m)
        rho = P_amb / (ISA.R_specific * T_amb)

        # ── Effective throttle & volumetric flow ─────────────────────
        # Clamp throttle to a small minimum so idle still draws some air
        throttle_eff = max(throttle, 0.08)

        # Mass flow of air [kg/s]
        #   V_dot = displacement/2 * (RPM/60) * eta_vol * throttle_eff
        #   (divide displacement by 2 because 4-stroke fires once per 2 revs)
        V_dot = (s.displacement_m3 / 2.0) * (rpm / 60.0) * s.eta_volumetric * throttle_eff
        m_dot_air = rho * V_dot  # [kg/s]

        # Air-fuel ratio (slightly rich at high throttle for cooling)
        lambda_ratio = 1.0 - 0.08 * throttle_eff  # ~0.92 at WOT, ~1.0 at idle
        afr = s.stoich_afr * lambda_ratio
        m_dot_fuel = m_dot_air / afr  # [kg/s]

        # ── State 1: Induction ───────────────────────────────────────
        T1 = T_amb + s.manifold_heat_rise           # [K]

        # ── State 2: Isentropic compression ──────────────────────────
        r = s.compression_ratio
        g = s.gamma
        T2 = T1 * r ** (g - 1.0)

        # ── State 3: Constant-volume heat addition ───────────────────
        Q_in_per_kg = (m_dot_fuel * s.LHV * s.eta_combustion) / max(m_dot_air + m_dot_fuel, 1e-9)
        T3 = T2 + Q_in_per_kg / s.cv

        # ── State 4: Isentropic expansion ────────────────────────────
        T4 = T3 * (1.0 / r) ** (g - 1.0)

        # ── Derived quantities ───────────────────────────────────────
        # Thermal efficiency (ideal Otto)
        eta_th = 1.0 - 1.0 / r ** (g - 1.0)

        # Indicated work per cycle [J/kg_mix]
        w_net = s.cv * ((T3 - T2) - (T4 - T1))

        # Indicated power [W]
        m_dot_mix = m_dot_air + m_dot_fuel
        # Power = work_per_kg * mass_flow_rate
        P_indicated = w_net * m_dot_mix
        P_brake = max(P_indicated * s.eta_mechanical, 0.0)  # [W]
        P_brake_kw = P_brake / 1000.0

        # Cap to rated power (the real engine has physical limits)
        P_brake_kw = min(P_brake_kw, s.rated_power_kw * 1.05)

        # ── EGT ──────────────────────────────────────────────────────
        T4_celsius = T4 - 273.15
        # Richer mixtures → lower EGT (more fuel absorbs heat)
        lambda_deviation = lambda_ratio - 1.0  # negative when rich
        egt_lambda_adj = lambda_deviation * 10.0 * s.egt_richness_factor
        egt = T4_celsius - s.egt_cooling_offset + egt_lambda_adj

        # ── CHT ──────────────────────────────────────────────────────
        T_amb_c = T_amb - 273.15
        cooling_factor = 1.0 + s.cht_airspeed_gain * airspeed_mps
        rpm_safe = max(rpm, s.rpm_idle)  # avoid division issues
        cht = T_amb_c + s.CHT_baseline + s.K_cht * (P_brake_kw / (rpm_safe ** s.cht_rpm_exp * cooling_factor))

        # ── Fuel flow [gal/h] ────────────────────────────────────────
        # 1 US gallon AvGas ≈ 2.69 kg
        fuel_flow_kgh = m_dot_fuel * 3600.0  # [kg/h]
        fuel_flow_gph = fuel_flow_kgh / 2.69

        # ── Oil pressure ─────────────────────────────────────────────
        oil_pressure = s.oil_pressure_base + s.oil_pressure_rpm_gain * (rpm - s.rpm_idle)
        oil_pressure = max(oil_pressure, 15.0)  # relief valve floor

        # ── Oil temperature ──────────────────────────────────────────
        oil_temp = s.oil_temp_base + s.oil_temp_power_gain * P_brake_kw
        # Altitude cooling benefit (thinner air → less heat, but also less cooling)
        oil_temp -= 0.002 * altitude_m

        return ExpectedTelemetry(
            cht=round(cht, 2),
            egt=round(egt, 2),
            brake_power_kw=round(P_brake_kw, 2),
            fuel_flow_gph=round(fuel_flow_gph, 2),
            oil_pressure=round(oil_pressure, 2),
            oil_temp=round(oil_temp, 2),
            thermal_efficiency=round(eta_th, 4),
            T1=round(T1, 2),
            T2=round(T2, 2),
            T3=round(T3, 2),
            T4=round(T4, 2),
        )


# ── Module-level singleton ────────────────────────────────────────────

_default_solver = OttoCycleSolver()


# ── Pure function API ─────────────────────────────────────────────────


def compute_expected_telemetry(
    operating_conditions: dict,
    specs: EngineSpecs = DEFAULT_SPECS,
) -> ExpectedTelemetry:
    """
    Pure function:  (operating_conditions) → expected CHT / EGT / power / …

    Parameters
    ----------
    operating_conditions : dict
        Required key: ``rpm`` (float).
        Optional keys: ``throttle`` (0–1, default 0.75),
        ``altitude_m`` (default 0), ``ambient_temp_c`` (default ISA),
        ``airspeed_mps`` (default 45).
    specs : EngineSpecs
        Engine calibration constants (default = Rotax 912 proxy).

    Returns
    -------
    ExpectedTelemetry
    """
    solver = _default_solver if specs is DEFAULT_SPECS else OttoCycleSolver(specs)
    return solver.solve(
        rpm=operating_conditions["rpm"],
        throttle=operating_conditions.get("throttle", 0.75),
        altitude_m=operating_conditions.get("altitude_m", 0.0),
        ambient_temp_c=operating_conditions.get("ambient_temp_c"),
        airspeed_mps=operating_conditions.get("airspeed_mps", 45.0),
    )


# One-sigma tolerance band per channel — used both to normalise
# `deviation_score` below and (Accuracy-First Phase 4) by
# backend/app/services/physics_ingestion.py to classify each channel's
# own CONSISTENT/ELEVATED/REVIEW/ANOMALY status. Exposed as a module-
# level constant (rather than kept as function-local variables) purely
# so that second consumer has one real source of truth instead of a
# second, independently-maintained copy of the same numbers.
PARAMETER_TOLERANCES = {
    "cht": 15.0,            # °C
    "egt": 40.0,            # °C
    "oil_pressure": 10.0,   # psi
    "oil_temp": 12.0,       # °C
    "fuel_flow": 2.0,       # gal/h
}


def compute_physics_deviation(
    actual_telemetry: dict,
    operating_conditions: Optional[dict] = None,
    specs: EngineSpecs = DEFAULT_SPECS,
) -> PhysicsDeviation:
    """
    Compute the expected-vs-actual deviation signal.

    Parameters
    ----------
    actual_telemetry : dict
        Must contain: ``rpm``, ``cht``, ``egt``, ``oil_pressure``,
        ``oil_temp``, ``fuel_flow``.
        May optionally contain ``throttle``, ``altitude_m``,
        ``ambient_temp_c``, ``airspeed_mps`` (used to infer operating
        conditions if *operating_conditions* is ``None``).
    operating_conditions : dict | None
        If ``None``, operating conditions are inferred from the
        actual telemetry dict itself (using ``rpm`` and any optional
        keys present).
    specs : EngineSpecs
        Engine calibration constants.

    Returns
    -------
    PhysicsDeviation
        Residuals and a composite ``deviation_score``.
    """
    # Infer operating conditions from actual telemetry if not provided
    if operating_conditions is None:
        operating_conditions = {
            "rpm": actual_telemetry["rpm"],
            "throttle": actual_telemetry.get("throttle", _estimate_throttle(actual_telemetry["rpm"], specs)),
            "altitude_m": actual_telemetry.get("altitude_m", 0.0),
            "ambient_temp_c": actual_telemetry.get("ambient_temp_c"),
            "airspeed_mps": actual_telemetry.get("airspeed_mps", 45.0),
        }

    expected = compute_expected_telemetry(operating_conditions, specs)

    # Raw deltas (actual - expected)
    delta_cht = actual_telemetry["cht"] - expected.cht
    delta_egt = actual_telemetry["egt"] - expected.egt
    delta_oil_pressure = actual_telemetry["oil_pressure"] - expected.oil_pressure
    delta_oil_temp = actual_telemetry["oil_temp"] - expected.oil_temp
    delta_fuel_flow = actual_telemetry["fuel_flow"] - expected.fuel_flow_gph

    # ── Composite deviation score ─────────────────────────────────────
    # Normalise each delta by a plausible "one-sigma" tolerance band,
    # then take the RMS.  Score > 1.0 means at least one channel has
    # exceeded its expected tolerance.
    normalised = [
        (delta_cht / PARAMETER_TOLERANCES["cht"]) ** 2,
        (delta_egt / PARAMETER_TOLERANCES["egt"]) ** 2,
        (delta_oil_pressure / PARAMETER_TOLERANCES["oil_pressure"]) ** 2,
        (delta_oil_temp / PARAMETER_TOLERANCES["oil_temp"]) ** 2,
        (delta_fuel_flow / PARAMETER_TOLERANCES["fuel_flow"]) ** 2,
    ]
    deviation_score = math.sqrt(sum(normalised) / len(normalised))

    return PhysicsDeviation(
        delta_cht=round(delta_cht, 2),
        delta_egt=round(delta_egt, 2),
        delta_oil_pressure=round(delta_oil_pressure, 2),
        delta_oil_temp=round(delta_oil_temp, 2),
        delta_fuel_flow=round(delta_fuel_flow, 2),
        deviation_score=round(deviation_score, 4),
        expected=expected,
    )


def _estimate_throttle(rpm: float, specs: EngineSpecs) -> float:
    """
    Rough throttle estimate from RPM when no throttle sensor is available.

    Maps linearly from idle (throttle≈0.08) to max RPM (throttle≈1.0).
    """
    t = (rpm - specs.rpm_idle) / max(specs.rpm_max - specs.rpm_idle, 1.0)
    return max(0.08, min(1.0, 0.08 + 0.92 * t))
