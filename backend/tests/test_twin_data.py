"""Backend data the 3D twin needs: live quality flag, per-step replay physics/vibration, turbo declaration."""
import datetime as dt
import json
import os
import sys


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from sqlalchemy import delete  # noqa: E402

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.physics_deviation_reading import PhysicsDeviationReading  # noqa: E402
from app.services.ingestion import ingestion_service  # noqa: E402
from app.ws.connection_manager import manager  # noqa: E402
from tests.conftest import auth_headers  # noqa: E402


async def _publish(engine_id, monkeypatch, **over):
    sent = []

    async def record(eid, message):
        sent.append(message)

    monkeypatch.setattr(manager, "broadcast_to_engine", record)
    payload = {
        "engine_id": str(engine_id), "ts": dt.datetime.now(dt.timezone.utc).isoformat(), "rpm": 3000, "cht": 140,
        "egt": 700, "oil_pressure": 70, "oil_temp": 92, "fuel_flow": 9, "vibration_x": 0.3, "vibration_y": 0.2, "vibration_z": 0.1,
    }
    payload.update(over)
    try:
        await ingestion_service._handle_message("aerotwin/telemetry/x", json.dumps(payload).encode())
    finally:
        # ingestion writes physics-deviation rows, which the shared engine fixture's cleanup doesn't know about
        async with AsyncSessionLocal() as db:
            await db.execute(delete(PhysicsDeviationReading).where(PhysicsDeviationReading.engine_id == engine_id))
            await db.commit()
    return [m for m in sent if m["type"] == "telemetry"]


async def test_live_telemetry_broadcast_carries_quality_status(make_engine, monkeypatch):
    engine = await make_engine()
    msgs = await _publish(engine.id, monkeypatch)
    assert len(msgs) == 1
    assert msgs[0]["payload"]["quality_status"] == "VALID"
    assert msgs[0]["payload"]["rpm"] == 3000  # the rest of the payload is unchanged


async def test_a_stale_reading_is_broadcast_as_stale_not_valid(make_engine, monkeypatch):
    engine = await make_engine()
    old = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=10)).isoformat()
    msgs = await _publish(engine.id, monkeypatch, ts=old)
    assert msgs and msgs[0]["payload"]["quality_status"] == "STALE"


def test_replay_frames_carry_physics_consistency_and_vibration():
    from simulation import replay_engine

    rows = [
        {"rpm": 3000 + 10 * i, "cht": 140, "egt": 700, "oil_pressure": 70, "oil_temp": 92, "fuel_flow": 9,
         "vibration_x": 0.3, "vibration_y": 0.4, "vibration_z": 0.0}
        for i in range(3)
    ]
    frames = replay_engine.run_sequence(rows, "twin-data-test")
    assert len(frames) == 3
    f = frames[0]
    assert (f["telemetry"]["vibration_x"], f["telemetry"]["vibration_y"], f["telemetry"]["vibration_z"]) == (0.3, 0.4, 0.0)
    assert {p["parameter"] for p in f["physics"]} == {"cht", "egt", "oil_pressure", "oil_temp", "fuel_flow"}
    for p in f["physics"]:
        assert set(p) == {"parameter", "expected", "measured", "residual", "status"}
        assert p["status"] in ("CONSISTENT", "ELEVATED", "REVIEW", "ANOMALY")
    cht = next(p for p in f["physics"] if p["parameter"] == "cht")
    assert cht["measured"] == 140  # the step's own measurement, not a neighbour's


async def test_twin_spec_does_not_assume_a_turbo(client, admin_user, make_engine):
    engine = await make_engine()
    spec = (await client.get(f"/api/v1/engines/{engine.id}/twin", headers=auth_headers(admin_user))).json()["spec"]
    assert spec["turbocharged"] is None  # unknown, not False and not True
    assert "num_cylinders" in spec
