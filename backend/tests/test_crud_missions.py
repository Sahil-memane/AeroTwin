from datetime import datetime, timedelta, timezone
from tests.conftest import auth_headers


async def test_list_missions_empty_ok(client, operator_user):
    resp = await client.get("/api/v1/missions", headers=auth_headers(operator_user))
    assert resp.status_code == 200


async def test_create_mission_requires_operator_or_above(client, make_user, make_uav_asset):
    # maintenance_engineer is below operator in the allowed-roles list for this endpoint
    maint_user = await make_user("maintenance_engineer")
    asset = await make_uav_asset()
    resp = await client.post(
        "/api/v1/missions",
        json={
            "uav_asset_id": str(asset.id),
            "mission_type": "endurance",
            "start_time": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        },
        headers=auth_headers(maint_user),
    )
    assert resp.status_code == 403


async def test_create_and_get_mission(client, operator_user, make_uav_asset):
    asset = await make_uav_asset()
    create_resp = await client.post(
        "/api/v1/missions",
        json={
            "uav_asset_id": str(asset.id),
            "mission_type": "endurance",
            "start_time": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        },
        headers=auth_headers(operator_user),
    )
    assert create_resp.status_code == 201
    mission_id = create_resp.json()["id"]

    get_resp = await client.get(f"/api/v1/missions/{mission_id}", headers=auth_headers(operator_user))
    assert get_resp.status_code == 200
    assert get_resp.json()["mission_type"] == "endurance"


async def test_update_mission_status(client, operator_user, make_mission):
    mission = await make_mission()
    resp = await client.put(
        f"/api/v1/missions/{mission.id}",
        json={"status": "in_progress"},
        headers=auth_headers(operator_user),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "in_progress"


async def test_delete_mission_requires_admin(client, operator_user, make_mission):
    mission = await make_mission()
    resp = await client.delete(f"/api/v1/missions/{mission.id}", headers=auth_headers(operator_user))
    assert resp.status_code == 403


async def test_get_mission_not_found(client, operator_user):
    resp = await client.get(
        "/api/v1/missions/00000000-0000-0000-0000-0000000000ff", headers=auth_headers(operator_user)
    )
    assert resp.status_code == 404


# ── GET /missions?include_stats=true ─────────────────────────────────

async def test_list_missions_stats_are_opt_in_and_correct(client, admin_user, make_uav_asset, make_mission, make_engine):
    """Fixture order matters for teardown: the engine (which owns the telemetry
    rows) must be torn down before the mission those rows reference."""
    import datetime as dt
    from app.db.session import AsyncSessionLocal
    from app.models.telemetry_reading import TelemetryReading
    from tests.conftest import auth_headers

    asset = await make_uav_asset()
    with_data = await make_mission(asset.id)
    empty = await make_mission(asset.id)
    engine = await make_engine(asset.id)

    base = dt.datetime(2020, 1, 1, 12, 0, 0)
    async with AsyncSessionLocal() as db:
        db.add_all([
            TelemetryReading(engine_id=engine.id, mission_id=with_data.id, ts=base + dt.timedelta(seconds=i),
                             rpm=3000, cht=140, egt=700, oil_pressure=70, oil_temp=92, fuel_flow=9)
            for i in range(7)
        ])
        await db.commit()

    headers = auth_headers(admin_user)

    plain = {m["id"]: m for m in (await client.get("/api/v1/missions", headers=headers)).json()}
    assert plain[str(with_data.id)]["reading_count"] is None  # not computed unless asked

    rich = {m["id"]: m for m in (await client.get("/api/v1/missions?include_stats=true", headers=headers)).json()}
    a, b = rich[str(with_data.id)], rich[str(empty.id)]
    assert a["reading_count"] == 7
    assert a["first_ts"].startswith("2020-01-01T12:00:00") and a["last_ts"].startswith("2020-01-01T12:00:06")
    assert b["reading_count"] == 0 and b["first_ts"] is None and b["last_ts"] is None  # empty is 0, not None
    assert a["mission_type"] == with_data.mission_type  # regular fields unchanged
