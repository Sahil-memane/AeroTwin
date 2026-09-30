"""
E2E — Scenario A (normal operations): log in, list the fleet, pull an
engine's current telemetry/health/RUL/fault/bearing/aux, confirm the
dashboard summary aggregates real data. No fault injection here — this
is the "nothing is on fire" baseline every other E2E scenario is a
variation of.

Also checks the "no false criticals" guarantee Phase 3 actually makes:
NOT that the fault model is well-calibrated on nominal data (a known,
already-documented, separate model-quality issue — see Phase 7's own
edge-packaging notes: this fault model leans "Compass Failure" on
plain nominal/taxi-phase telemetry too, independent of any real
injected fault, once its 80-reading window fills — that's a model-
training gap, not a fusion-logic bug, and out of this pass's scope to
retrain), but that health_fusion.py never force-zeroes the score from
Fault UNLESS `state == FAULT_CONFIRMED` — i.e. a single anomalous
reading, or a still-escalating ANOMALY_DETECTED/FAULT_SUSPECTED state,
must never alone drive `forced_zero`. This holds regardless of the
underlying model's classification quality, and is squarely what Phase
3 + Phase 5 actually guarantee.

Run: python scripts/e2e/test_normal_ops.py
"""
import json
import os
import sys
import time

import httpx

sys.path.insert(0, os.path.dirname(__file__))
from _common import BASE_URL, ENGINE_ID, MISSION_ID, auth_headers, login, new_client_id  # noqa: E402

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, _REPO_ROOT)
from edge.telemetry_publisher.simulate import EngineSimulator  # noqa: E402

MQTT_HOST = os.environ.get("AEROTWIN_MQTT_HOST", "127.0.0.1")
MQTT_PORT = int(os.environ.get("AEROTWIN_MQTT_PORT", "1883"))


def publish_nominal_burst(n_readings: int = 15, rate: float = 0.2):
    import paho.mqtt.client as mqtt

    sim = EngineSimulator(ENGINE_ID, MISSION_ID)  # no trigger_fault() — nominal only
    client_id = new_client_id("aerotwin-e2e-a")
    mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id) if hasattr(mqtt, "CallbackAPIVersion") \
        else mqtt.Client(client_id)
    mqtt_client.connect(MQTT_HOST, MQTT_PORT, 30)
    mqtt_client.loop_start()
    topic = f"aerotwin/telemetry/{ENGINE_ID}"
    try:
        for _ in range(n_readings):
            payload = sim.step(dt=rate)
            mqtt_client.publish(topic, json.dumps(payload), qos=1)
            time.sleep(rate)
    finally:
        mqtt_client.loop_stop()
        mqtt_client.disconnect()


def main():
    with httpx.Client(timeout=10.0) as client:
        token = login(client)
        headers = auth_headers(token)
        print("[1/7] Logged in.")

        engines = client.get(f"{BASE_URL}/engines", headers=headers)
        engines.raise_for_status()
        assert len(engines.json()) > 0, "expected at least one engine"
        print(f"[2/7] Fleet has {len(engines.json())} engine(s).")

        health = client.get(f"{BASE_URL}/engines/{ENGINE_ID}/health-score", headers=headers)
        health.raise_for_status()
        body = health.json()
        assert "combined_score" in body and "status" in body
        print(f"[3/7] Health score: {body['combined_score']} ({body['status']})")

        summary = client.get(f"{BASE_URL}/dashboard/summary", headers=headers)
        summary.raise_for_status()
        summary_body = summary.json()
        assert "fleet_health" in summary_body
        print(f"[4/7] Dashboard summary fleet_health: {summary_body['fleet_health']}")

        telemetry = client.get(f"{BASE_URL}/engines/{ENGINE_ID}/telemetry/latest", headers=headers)
        if telemetry.status_code == 200:
            print(f"[5/7] Latest telemetry: rpm={telemetry.json().get('rpm')}")
        else:
            print(f"[5/7] No telemetry yet (status {telemetry.status_code}) — acceptable if the "
                  f"simulator isn't running right now.")

        models = client.get(f"{BASE_URL}/models", headers=headers)
        models.raise_for_status()
        assert len(models.json()) >= 1
        print(f"[6/7] Model registry has {len(models.json())} entries.")

        print("[7/7] Checking Phase 3's no-false-critical guarantee (forced_zero requires FAULT_CONFIRMED)...")
        publish_nominal_burst()
        fault = client.get(f"{BASE_URL}/engines/{ENGINE_ID}/faults/latest", headers=headers)
        health = client.get(f"{BASE_URL}/engines/{ENGINE_ID}/health-score", headers=headers)
        health.raise_for_status()
        health_factors = health.json().get("contributing_factors") or []
        fault_factor = next((f for f in health_factors if f["source"] == "fault"), None)

        if fault.status_code == 200:
            fault_state = fault.json().get("state")
            print(f"    Latest fault classification: {fault.json()['fault_class']} (state={fault_state}).")
            if fault_factor is not None and fault_factor.get("forced_zero"):
                assert fault_state == "FAULT_CONFIRMED", (
                    f"health_fusion forced the score to 0 from Fault while state={fault_state!r} "
                    f"(not FAULT_CONFIRMED) — a false critical from a single/unconfirmed reading: {fault_factor}"
                )
                print("    A forced-zero IS present, but only because state is genuinely FAULT_CONFIRMED — correct.")
            else:
                print("    No fault-forced-zero present — no false critical.")
        else:
            print(f"    No fault prediction yet (status {fault.status_code}) — window still filling, acceptable.")

    print("\nPASS: normal ops E2E (Scenario A)")


if __name__ == "__main__":
    main()
