"""
Engine specification constants for the AeroTwin physics model.

Calibrated against a Rotax 912/914-class 4-cylinder, 4-stroke,
horizontally-opposed, air/oil-cooled spark-ignition aero-piston engine
used in MALE-class UAVs.

Sources:
  - Rotax 912 ULS Installation Manual (ref. MWB-912)
  - FAA Type Certificate Data Sheet E00051EN
  - Standard Otto-cycle thermodynamic references
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class AtmosphericConstants:
    """International Standard Atmosphere (ISA) constants."""
    T0: float = 288.15          # Sea-level temperature [K]
    P0: float = 101325.0        # Sea-level pressure [Pa]
    L: float = 0.0065           # Temperature lapse rate [K/m]
    g: float = 9.80665          # Gravitational acceleration [m/s²]
    M: float = 0.0289644        # Molar mass of dry air [kg/mol]
    R: float = 8.31447          # Universal gas constant [J/(mol·K)]
    R_specific: float = 287.058 # Specific gas constant for dry air [J/(kg·K)]


@dataclass(frozen=True)
class EngineSpecs:
    """
    Physical and performance parameters for the target aero-piston engine.

    Default values are calibrated to a Rotax 912 ULS / 914 UL class engine:
      - 4-cylinder horizontally-opposed boxer
      - 1211 cc (912 ULS) / 1211 cc turbocharged (914 UL)
      - Compression ratio 9.0:1 (912) / 9.0:1 (914, effective with turbo)
      - Rated 73.5 kW (100 HP) @ 5800 RPM (912 ULS)
      - Rated 84.5 kW (115 HP) @ 5800 RPM (914 UL)
    """

    # ── Geometric parameters ──────────────────────────────────────────
    num_cylinders: int = 4
    displacement_cc: float = 1211.0     # Total displacement [cm³]
    compression_ratio: float = 9.0      # Geometric compression ratio r

    # ── Thermodynamic parameters ──────────────────────────────────────
    gamma: float = 1.30                 # Ratio of specific heats (effective for combustion)
    cv: float = 1100.0                  # Effective specific heat at constant volume [J/(kg·K)]
    cp: float = 1430.0                  # Effective specific heat at constant pressure [J/(kg·K)]

    # ── Fuel parameters ───────────────────────────────────────────────
    LHV: float = 43.5e6                 # Lower heating value of AvGas 100LL [J/kg]
    stoich_afr: float = 14.7            # Stoichiometric air-fuel ratio
    bsfc_nominal: float = 260.0         # Brake specific fuel consumption [g/kWh]

    # ── Efficiency factors ────────────────────────────────────────────
    eta_volumetric: float = 0.85        # Volumetric efficiency at WOT
    eta_combustion: float = 0.90        # Effective combustion heat release fraction
    eta_mechanical: float = 0.88        # Mechanical efficiency (friction losses)

    # ── Thermal model calibration constants ───────────────────────────
    CHT_baseline: float = 60.0          # Block warmup base temp
    K_cht: float = 45.0                 # Heat transfer gain for CHT [°C·RPM^exp/kW]
    cht_rpm_exp: float = 0.30           # RPM exponent for cooling airflow effect
    cht_airspeed_gain: float = 0.05     # Per-m/s cooling improvement from ram air

    # EGT model: EGT = T4_celsius - delta_T_exhaust_cooling
    egt_cooling_offset: float = 450.0   # Exhaust port / manifold cooling [°C]
    egt_richness_factor: float = 25.0   # EGT offset per 0.1 lambda deviation [°C]

    # Oil model
    oil_pressure_base: float = 65.0     # Nominal oil pressure at cruise [psi]
    oil_pressure_rpm_gain: float = 0.008  # psi per RPM above idle
    oil_temp_base: float = 85.0         # Nominal oil temp at cruise [°C]
    oil_temp_power_gain: float = 0.35   # °C per kW of brake power

    # ── Operating envelope (for sanity checks / clamping) ─────────────
    rpm_idle: float = 1400.0
    rpm_cruise: float = 4800.0
    rpm_max: float = 5800.0
    rated_power_kw: float = 73.5        # Max rated brake power [kW]

    # ── Manifold heating ──────────────────────────────────────────────
    manifold_heat_rise: float = 15.0    # Intake air heating in manifold [K]

    @property
    def displacement_m3(self) -> float:
        """Total displacement in m³."""
        return self.displacement_cc * 1e-6


# Module-level default instance
ISA = AtmosphericConstants()
DEFAULT_SPECS = EngineSpecs()
