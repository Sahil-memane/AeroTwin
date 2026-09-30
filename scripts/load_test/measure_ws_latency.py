"""
Phase 8 — WS broadcast latency under load.

`POST /telemetry/ingest` (what locustfile.py load-tests) never touches
ML inference or the WebSocket broadcast — it's a bare storage write (see
telemetry.py). Only the MQTT ingestion path runs inference + health
fusion + `ws_manager` broadcast, so THAT'S the path this measures:
publish a telemetry reading over MQTT for the real demo engine, time how
long it takes to arrive on that engine's `/live` WebSocket as a `type:
telemetry` message, and report p50/p95/max. Run this WHILE
`locust -f locustfile.py` is hammering /telemetry/ingest concurrently —
same Postgres instance, same event loop — to see whether that unrelated
write load drags down live-broadcast latency for anyone watching the
dashboard.

Run: python scripts/load_test/measure_ws_latency.py [n_samples]
"""
import asyncio
import json
import os
import sys
import time

import httpx
import websockets

_SCRIPTS_E2E = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "e2e"))
sys.path.insert(0, _SCRIPTS_E2E)
from _common import BASE_URL, ENGINE_ID, MISSION_ID, login  # noqa: E402

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, _REPO_ROOT)
from edge.telemetry_publisher.simulate import EngineSimulator  # noqa: E402

import paho.mqtt.client as mqtt  # noqa: E402

MQTT_HOST = os.environ.get("AEROTWIN_MQTT_HOST", "127.0.0.1")
MQTT_PORT = int(os.environ.get("AEROTWIN_MQTT_PORT", "1883"))
WS_URL = os.environ.get("AEROTWIN_WS_URL", "ws://127.0.0.1:8000/api/v1")
N_SAMPLES = int(sys.argv[1]) if len(sys.argv) > 1 else 30


async def main():
    with httpx.Client(timeout=10.0) as client:
        token = login(client)

    mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, "aerotwin-ws-latency") \
        if hasattr(mqtt, "CallbackAPIVersion") else mqtt.Client("aerotwin-ws-latency")
    mqtt_client.connect(MQTT_HOST, MQTT_PORT, 30)
    mqtt_client.loop_start()
    sim = EngineSimulator(ENGINE_ID, MISSION_ID)
    topic = f"aerotwin/telemetry/{ENGINE_ID}"

    latencies = []
    uri = f"{WS_URL}/engines/{ENGINE_ID}/live?token={token}"
    async with websockets.connect(uri) as ws:
        for i in range(N_SAMPLES):
            reading = sim.step(dt=1.0)
            sent_at = time.monotonic()
            mqtt_client.publish(topic, json.dumps(reading), qos=1)

            # Drain messages until we see the telemetry update for this tick
            # (other message types — health_score, fault, etc. — may also
            # arrive; skip those) or give up after 5s.
            deadline = sent_at + 5.0
            while time.monotonic() < deadline:
                try:
                    remaining = deadline - time.monotonic()
                    msg = await asyncio.wait_for(ws.recv(), timeout=max(0.1, remaining))
                except asyncio.TimeoutError:
                    break
                data = json.loads(msg)
                if data.get("type") == "telemetry":
                    latencies.append(time.monotonic() - sent_at)
                    break
            await asyncio.sleep(1.0)

    mqtt_client.loop_stop()
    mqtt_client.disconnect()

    if not latencies:
        print("FAIL: received zero matching WS telemetry updates — is the backend's MQTT subscriber running?")
        sys.exit(1)

    latencies.sort()
    p50 = latencies[len(latencies) // 2]
    p95 = latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))]
    print(f"Samples: {len(latencies)}/{N_SAMPLES} matched | p50={p50:.3f}s p95={p95:.3f}s max={max(latencies):.3f}s")
    if p95 < 2.0:
        print("PASS: p95 WS latency under the 2s target")
    else:
        print("FAIL: p95 WS latency exceeds the 2s target")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
