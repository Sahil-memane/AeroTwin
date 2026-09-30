"""
Phase 8 load test — ~50 concurrent simulated engines POSTing telemetry
to /telemetry/ingest (the REST edge-ingestion path; MQTT ingestion is a
separate subscriber process this HTTP-focused tool can't drive directly,
but both paths share the same validation + DB write code, so this still
load-tests the part that's actually expensive: `validate_payload` +
the TimescaleDB insert).

Setup:
  python scripts/load_test/seed_engines.py 50
  locust -f scripts/load_test/locustfile.py --host http://127.0.0.1:8000

Teardown:
  python scripts/load_test/cleanup_engines.py
"""
import json
import os
import random
from datetime import datetime, timezone

from locust import HttpUser, task, between

_ENGINE_IDS_PATH = os.path.join(os.path.dirname(__file__), "engine_ids.json")
with open(_ENGINE_IDS_PATH) as f:
    ENGINE_IDS = json.load(f)

EDGE_API_KEY = os.environ.get("AEROTWIN_EDGE_API_KEY", "")


class EdgeDeviceUser(HttpUser):
    """One instance == one simulated engine's edge device."""

    wait_time = between(0.8, 1.2)  # ~1 reading/second, matching the real simulator's default rate

    def on_start(self):
        self.engine_id = random.choice(ENGINE_IDS)

    @task
    def post_telemetry(self):
        payload = {
            "engine_id": self.engine_id,
            # Microsecond resolution matters: at 50 concurrent users
            # posting ~1/s, several requests for the same engine_id can
            # legitimately land in the same wall-clock second, and
            # (engine_id, ts) is the table's primary key.
            "ts": datetime.now(timezone.utc).isoformat(),
            "rpm": random.uniform(1600, 5500),
            "cht": random.uniform(80, 160),
            "egt": random.uniform(350, 750),
            "oil_pressure": random.uniform(45, 75),
            "oil_temp": random.uniform(80, 105),
            "fuel_flow": random.uniform(3, 15),
            "vibration_x": random.uniform(0.2, 0.9),
            "vibration_y": random.uniform(0.2, 0.9),
            "vibration_z": random.uniform(0.1, 0.5),
        }
        self.client.post(
            "/api/v1/telemetry/ingest",
            json=payload,
            headers={"X-Edge-Api-Key": EDGE_API_KEY},
            name="/telemetry/ingest",
        )
