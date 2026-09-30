"""
Telemetry source abstraction for the edge agent.

`edge/telemetry_publisher/simulate.py`'s `EngineSimulator` is the only
telemetry source that exists today — there is no real UAV/engine hardware
in this hackathon's scope. This module wraps it behind the same small
`read()` interface a real CAN-bus reader would implement, so
`edge/inference/edge_agent.py` never has to know which one it's talking
to — swapping to real hardware later means writing one new class here,
not touching the agent, the ONNX runners, or the buffering logic.
"""
from __future__ import annotations

import os
import sys
from abc import ABC, abstractmethod

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from edge.telemetry_publisher.simulate import EngineSimulator  # noqa: E402


class TelemetryReader(ABC):
    """Common interface every telemetry source implements."""

    @abstractmethod
    def read(self) -> dict:
        """Return one telemetry reading as a flat dict (see EngineSimulator.step)."""
        raise NotImplementedError


class SimulatedReader(TelemetryReader):
    """Wraps the physics-based `EngineSimulator` — today's only data source."""

    def __init__(self, engine_id: str, mission_id: str, ambient_temp_c: float = 15.0, dt: float = 1.0):
        self._sim = EngineSimulator(engine_id, mission_id, ambient_temp_c)
        self._dt = dt

    def read(self) -> dict:
        return self._sim.step(dt=self._dt)

    def trigger_fault(self, fault_type: str = "cht_overheat") -> None:
        self._sim.trigger_fault(fault_type)

    def clear_fault(self) -> None:
        self._sim.clear_fault()


class CANBusReader(TelemetryReader):
    """
    Placeholder for the real hardware path — a CAN transceiver wired to
    the engine ECU (e.g. via `python-can` against a SocketCAN/PCAN
    interface), decoding the same fields `EngineSimulator.step()`
    returns (rpm/cht/egt/oil_pressure/oil_temp/fuel_flow/vibration_x/y/z)
    from real CAN frames using the ECU's DBC definitions.

    Not implemented: no CAN hardware exists in this project yet. This
    class exists so the swap-in point is explicit and typed, rather than
    an implicit assumption buried in `edge_agent.py`.
    """

    def __init__(self, channel: str, dbc_path: str):
        self._channel = channel
        self._dbc_path = dbc_path

    def read(self) -> dict:
        raise NotImplementedError(
            "No CAN hardware is connected in this project — use SimulatedReader. "
            "Implementing this requires a python-can Bus on the given channel, "
            "a DBC file for the ECU's frame layout, and a decode step producing "
            "the same field names EngineSimulator.step() returns."
        )
