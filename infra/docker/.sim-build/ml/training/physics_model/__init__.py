"""
AeroTwin Physics Model — Otto-cycle thermodynamic solver.

Public API
----------
- ``compute_expected_telemetry(operating_conditions, specs=DEFAULT_SPECS)``
- ``compute_physics_deviation(actual_telemetry, operating_conditions=None, specs=DEFAULT_SPECS)``
- ``OttoCycleSolver``  — stateless class if you need explicit specs control
- ``DEFAULT_SPECS``    — Rotax 912/914 proxy constants
- ``EngineSpecs``      — dataclass you can customise
"""

from .specs import AtmosphericConstants, EngineSpecs, ISA, DEFAULT_SPECS
from .otto_cycle_solver import (
    OttoCycleSolver,
    ExpectedTelemetry,
    PhysicsDeviation,
    PARAMETER_TOLERANCES,
    compute_expected_telemetry,
    compute_physics_deviation,
    isa_temperature,
    isa_pressure,
    isa_density,
)

__all__ = [
    "OttoCycleSolver",
    "ExpectedTelemetry",
    "PhysicsDeviation",
    "PARAMETER_TOLERANCES",
    "compute_expected_telemetry",
    "compute_physics_deviation",
    "isa_temperature",
    "isa_pressure",
    "isa_density",
    "EngineSpecs",
    "AtmosphericConstants",
    "ISA",
    "DEFAULT_SPECS",
]
