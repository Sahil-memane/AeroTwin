"""
E2E — Scenario D (sensor failure), PARTIAL per the plan's own scope
note: full sensor-vs-engine fault isolation (a model-level distinction
between "this sensor is glitching" and "this engine has a real fault")
is Tier 2 work and isn't implemented yet — `fault_state.FaultState`
reserves a `SENSOR_ANOMALY` value for it, but nothing in this codebase
ever assigns it today. This script exercises the boundary that DOES
exist: Phase 1's data-quality layer catching an implausible single-
sensor jump (one channel spikes while the others stay nominal — a
classic sensor-glitch shape, not a real engine-wide fault pattern) and
flagging it SUSPICIOUS rather than either silently accepting it as
real or misclassifying it as a confirmed engine fault.

Run: python scripts/e2e/test_sensor_failure.py
"""
import json
import os
import sys
import time

import httpx
import paho.mqtt.client as mqtt

sys.path.insert(0, os.path.dirname(__file__))
from _common import BASE_URL, ENGINE_ID, MISSION_ID, auth_headers, login, new_client_id, wait_until  # noqa: E402

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, _REPO_ROOT)
from edge.telemetry_publisher.simulate import EngineSimulator  # noqa: E402

MQTT_HOST = os.environ.get("AEROTWIN_MQTT_HOST", "127.0.0.1")
MQTT_PORT = int(os.environ.get("AEROTWIN_MQTT_PORT", "1883"))

# telemetry_limits.yaml: data_quality.max_jump_per_reading.rpm = 1500 —
# a spike safely past that on ONE channel, nothing else touched.
RPM_GLITCH_DELTA = 2200.0


def publish(mqtt_client, topic, payload):
    mqtt_client.publish(topic, json.dumps(payload), qos=1)


def main():
    with httpx.Client(timeout=10.0) as client:
        token = login(client)
        headers = auth_headers(token)
        print("[1/4] Logged in.")

        sim = EngineSimulator(ENGINE_ID, MISSION_ID)  # nominal, no trigger_fault()
        client_id = new_client_id("aerotwin-e2e-d")
        mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id) if hasattr(mqtt, "CallbackAPIVersion") \
            else mqtt.Client(client_id)
        mqtt_client.connect(MQTT_HOST, MQTT_PORT, 30)
        mqtt_client.loop_start()
        topic = f"aerotwin/telemetry/{ENGINE_ID}"

        try:
            # Baseline reading so the MQTT path's per-engine `_last_reading`
            # state has something to compare the glitched one against.
            baseline = sim.step(dt=0.2)
            publish(mqtt_client, topic, baseline)
            time.sleep(0.5)
            baseline_ts = baseline["ts"]
            print(f"[2/4] Published a nominal baseline reading (rpm={baseline['rpm']:.1f}).")

            # A single-channel glitch: rpm spikes far past the plausible
            # per-reading jump, CHT/EGT/oil/fuel all stay exactly where
            # the simulator's own nominal physics put them — the shape of
            # a sensor fault, not an engine-wide one.
            glitched = sim.step(dt=0.2)
            glitched["rpm"] = glitched["rpm"] + RPM_GLITCH_DELTA
            publish(mqtt_client, topic, glitched)
            glitched_ts = glitched["ts"]
            print(f"[3/4] Published a single-channel RPM glitch (rpm={glitched['rpm']:.1f}, "
                  f"+{RPM_GLITCH_DELTA:.0f} in one reading).")
            time.sleep(1.0)
        finally:
            mqtt_client.loop_stop()
            mqtt_client.disconnect()

        def find_glitched_row():
            resp = client.get(
                f"{BASE_URL}/engines/{ENGINE_ID}/telemetry", headers=headers,
                params={"limit": 20},
            )
            resp.raise_for_status()
            for row in resp.json():
                if abs(row["rpm"] - glitched["rpm"]) < 0.5:
                    return row
            return None

        row = wait_until(find_glitched_row, timeout_s=15.0, description="the glitched reading to persist")
        assert row["quality_status"] == "SUSPICIOUS", \
            f"expected the single-channel RPM glitch to be flagged SUSPICIOUS, got {row['quality_status']!r}"
        print(f"[4/4] Glitched reading correctly flagged quality_status=SUSPICIOUS "
              f"(accepted, not silently trusted, not silently dropped).")

    print("\nNOTE: this only covers today's boundary (Phase 1 data-quality flagging). Full")
    print("sensor-vs-engine fault isolation (fault_state.FaultState.SENSOR_ANOMALY) is")
    print("reserved but not yet assigned by any model — Tier 2, not implemented in this pass.")
    print("\nPASS (partial): sensor failure E2E (Scenario D)")


if __name__ == "__main__":
    main()
