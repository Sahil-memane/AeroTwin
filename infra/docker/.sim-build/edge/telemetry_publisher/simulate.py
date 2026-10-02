import os
import sys
import json
import time
import math
import random
import uuid
import argparse
import threading
from datetime import datetime, timezone
import paho.mqtt.client as mqtt

# ── Ensure the ml/ package is importable ──────────────────────────────
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_ml_path = os.path.join(_project_root, "ml")
if _ml_path not in sys.path:
    sys.path.insert(0, _ml_path)

from training.physics_model import compute_physics_deviation

# Default parameters
DEFAULT_MQTT_HOST = "localhost"
DEFAULT_MQTT_PORT = 1883
DEFAULT_ENGINE_ID = "00000000-0000-0000-0000-000000000001"
DEFAULT_MISSION_ID = "00000000-0000-0000-0000-000000000002"

# ── Mission profile: maps elapsed time (s) to a flight phase ─────────
MISSION_PHASES = [
    # (duration_s, phase_name, rpm_target, throttle_target, altitude_target_m)
    (30,  "taxi",      1600, 0.15,    0),
    (20,  "takeoff",   5500, 0.95, 100),
    (60,  "climb",     5200, 0.85, 1500),
    (180, "cruise",    4800, 0.75, 2400),
    (60,  "descent",   3200, 0.40, 800),
    (30,  "approach",  2200, 0.25, 100),
    (20,  "touchdown", 1600, 0.10,   0),
]


class EngineSimulator:
    """
    Physics-aware engine telemetry simulator.

    Generates plausible RPM/CHT/EGT/oil/fuel/vibration values that
    follow a configurable mission profile and computes the physics-model
    deviation_score in real time.  Supports injecting synthetic faults
    so that downstream RUL/Fault models have labeled degradation data.
    """

    def __init__(self, engine_id: str, mission_id: str, ambient_temp_c: float = 15.0):
        self.engine_id = engine_id
        self.mission_id = mission_id
        self.ambient_temp_c = ambient_temp_c

        # ── Current operating state ──────────────────────────────────
        self.rpm = 1600.0
        self.throttle = 0.15
        self.altitude_m = 0.0

        # Sensor baselines (will be driven by mission profile)
        self.cht = 90.0
        self.egt = 450.0
        self.oil_pressure = 60.0
        self.oil_temp = 85.0
        self.fuel_flow = 5.0
        self.vib_x = 0.3
        self.vib_y = 0.3
        self.vib_z = 0.15

        # ── Mission timeline ─────────────────────────────────────────
        self._phase_idx = 0
        self._phase_elapsed = 0.0
        self._total_elapsed = 0.0
        self._phase_list = MISSION_PHASES

        # ── Fault injection state ────────────────────────────────────
        self._fault_active = False
        self._fault_type = "none"          # "cht_overheat" | "oil_pressure_loss" | "high_vibration"
        self._fault_elapsed = 0.0          # seconds since fault was injected
        self._fault_ramp_rate = 0.02       # deviation_score increase per second

    # ── Fault control ────────────────────────────────────────────────
    def trigger_fault(self, fault_type: str = "cht_overheat"):
        self._fault_active = True
        self._fault_type = fault_type
        self._fault_elapsed = 0.0
        print(f"\n>>> SYNTHETIC FAULT INJECTED: {fault_type} <<<\n")

    def clear_fault(self):
        self._fault_active = False
        self._fault_type = "none"
        self._fault_elapsed = 0.0
        print("\n>>> FAULT CLEARED <<<\n")

    # ── Step forward by dt seconds ───────────────────────────────────
    def step(self, dt: float = 1.0) -> dict:
        # ── Advance mission phase ────────────────────────────────────
        phase_dur, phase_name, rpm_tgt, thr_tgt, alt_tgt = self._phase_list[self._phase_idx]
        self._phase_elapsed += dt
        self._total_elapsed += dt

        if self._phase_elapsed >= phase_dur:
            self._phase_elapsed = 0.0
            self._phase_idx = (self._phase_idx + 1) % len(self._phase_list)

        # Smooth ramp towards targets (exponential smoothing)
        alpha = 1.0 - math.exp(-dt / 8.0)   # ~8 s time constant
        self.rpm       += alpha * (rpm_tgt - self.rpm)
        self.throttle  += alpha * (thr_tgt - self.throttle)
        self.altitude_m += alpha * (alt_tgt - self.altitude_m)

        # ── Derive sensor values from operating state ────────────────
        rpm_frac = self.rpm / 5800.0

        self.cht = 80 + 70 * rpm_frac * self.throttle + random.gauss(0, 1.5)
        self.egt = 350 + 400 * rpm_frac * self.throttle + random.gauss(0, 5.0)
        self.oil_pressure = 55 + 15 * rpm_frac + random.gauss(0, 0.8)
        self.oil_temp = 80 + 25 * rpm_frac + random.gauss(0, 0.5)
        self.fuel_flow = 3 + 12 * self.throttle * rpm_frac + random.gauss(0, 0.3)

        # Vibration baseline — loosely correlated with RPM
        vib_base = 0.2 + 0.4 * rpm_frac
        self.vib_x = max(0.01, vib_base + random.gauss(0, 0.05))
        self.vib_y = max(0.01, vib_base + random.gauss(0, 0.05))
        self.vib_z = max(0.01, vib_base * 0.5 + random.gauss(0, 0.03))

        # ── Apply fault effects ──────────────────────────────────────
        if self._fault_active:
            self._fault_elapsed += dt

            if self._fault_type == "cht_overheat":
                # CHT ramps progressively higher
                fault_delta = min(self._fault_elapsed * 0.8, 120)
                self.cht += fault_delta
            elif self._fault_type == "oil_pressure_loss":
                # Oil pressure decays
                fault_delta = min(self._fault_elapsed * 0.5, 40)
                self.oil_pressure = max(10, self.oil_pressure - fault_delta)
            elif self._fault_type == "high_vibration":
                # Vibration escalates
                vib_fault = min(self._fault_elapsed * 0.1, 8.0)
                self.vib_x += vib_fault
                self.vib_y += vib_fault * 0.8
                self.vib_z += vib_fault * 0.5

        # ── Compute physics deviation_score ──────────────────────────
        actual_telemetry = {
            "rpm": self.rpm,
            "cht": self.cht,
            "egt": self.egt,
            "oil_pressure": self.oil_pressure,
            "oil_temp": self.oil_temp,
            "fuel_flow": self.fuel_flow,
            "throttle": self.throttle,
            "altitude_m": self.altitude_m,
            "ambient_temp_c": self.ambient_temp_c,
        }
        try:
            deviation = compute_physics_deviation(actual_telemetry)
            deviation_score = deviation.deviation_score
        except Exception:
            deviation_score = 0.0

        # ── Vibration magnitude (scalar) ─────────────────────────────
        vibration_magnitude = math.sqrt(
            self.vib_x ** 2 + self.vib_y ** 2 + self.vib_z ** 2
        )

        # ── Build payload ────────────────────────────────────────────
        return {
            "engine_id": self.engine_id,
            "mission_id": self.mission_id,
            "ts": datetime.now(timezone.utc).isoformat(),
            # Operating conditions (new first-class fields)
            "throttle": round(self.throttle, 4),
            "altitude_m": round(self.altitude_m, 2),
            # Core sensors
            "rpm": round(self.rpm, 2),
            "cht": round(self.cht, 2),
            "egt": round(self.egt, 2),
            "oil_pressure": round(self.oil_pressure, 2),
            "oil_temp": round(self.oil_temp, 2),
            "fuel_flow": round(self.fuel_flow, 2),
            "vibration_x": round(self.vib_x, 2),
            "vibration_y": round(self.vib_y, 2),
            "vibration_z": round(self.vib_z, 2),
            # Derived fields (new first-class fields)
            "vibration_magnitude": round(vibration_magnitude, 4),
            "deviation_score": round(deviation_score, 4),
            # Metadata
            "phase": phase_name,
            "fault_active": self._fault_active,
            "fault_type": self._fault_type,
        }


def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print("Connected to MQTT broker!")
    else:
        print(f"Failed to connect, return code {rc}")


def listen_for_fault(sim):
    """Interactive fault injection from stdin."""
    print("Commands: 'f' = CHT overheat, 'o' = oil pressure loss, 'v' = high vibration, 'c' = clear fault")
    while True:
        try:
            cmd = input().strip().lower()
            if cmd == "f":
                sim.trigger_fault("cht_overheat")
            elif cmd == "o":
                sim.trigger_fault("oil_pressure_loss")
            elif cmd == "v":
                sim.trigger_fault("high_vibration")
            elif cmd == "c":
                sim.clear_fault()
        except EOFError:
            break


def main():
    parser = argparse.ArgumentParser(description="AeroTwin Engine Telemetry Simulator")
    parser.add_argument("--host", default=os.getenv("MQTT_HOST", DEFAULT_MQTT_HOST), help="MQTT broker host")
    parser.add_argument("--port", type=int, default=int(os.getenv("MQTT_PORT", DEFAULT_MQTT_PORT)), help="MQTT broker port")
    parser.add_argument("--engine-id", default=os.getenv("ENGINE_ID", DEFAULT_ENGINE_ID), help="Engine UUID")
    parser.add_argument("--mission-id", default=os.getenv("MISSION_ID", DEFAULT_MISSION_ID), help="Mission UUID")
    parser.add_argument("--rate", type=float, default=1.0, help="Publish rate in seconds")
    parser.add_argument("--fault", choices=["cht_overheat", "oil_pressure_loss", "high_vibration"],
                        default=None, help="Start with a pre-injected fault")
    parser.add_argument("--ambient-temp", type=float, default=15.0, help="Ambient temperature in °C")

    args = parser.parse_args()

    sim = EngineSimulator(args.engine_id, args.mission_id, args.ambient_temp)
    if args.fault:
        sim.trigger_fault(args.fault)

    # Setup MQTT
    client_id = f"aerotwin-sim-{uuid.uuid4().hex[:8]}"
    if hasattr(mqtt, 'CallbackAPIVersion'):
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id)
    else:
        client = mqtt.Client(client_id)

    client.on_connect = on_connect

    print(f"Connecting to MQTT broker at {args.host}:{args.port}...")
    try:
        client.connect(args.host, args.port, 60)
    except Exception as e:
        print(f"Failed to connect to {args.host}:{args.port}: {e}")
        return

    client.loop_start()

    topic = f"aerotwin/telemetry/{args.engine_id}"
    print(f"Publishing to topic: {topic} at {args.rate}s intervals.")
    print("Commands: 'f' = CHT overheat, 'o' = oil pressure loss, 'v' = high vibration, 'c' = clear fault")
    print("Press Ctrl+C to stop.")

    # Start interactive thread
    t = threading.Thread(target=listen_for_fault, args=(sim,), daemon=True)
    t.start()

    try:
        while True:
            payload = sim.step(dt=args.rate)
            client.publish(topic, json.dumps(payload), qos=1)
            dev = payload["deviation_score"]
            phase = payload["phase"]
            print(f"[{phase:>10}] RPM={payload['rpm']:7.1f}  CHT={payload['cht']:6.1f}  "
                  f"EGT={payload['egt']:6.1f}  dev={dev:.3f}  fault={payload['fault_type']}")
            time.sleep(args.rate)
    except KeyboardInterrupt:
        print("\nStopping simulator...")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
