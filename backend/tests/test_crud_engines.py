from tests.conftest import auth_headers


async def test_list_engines_empty_ok(client, operator_user):
    resp = await client.get("/api/v1/engines", headers=auth_headers(operator_user))
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_create_engine_requires_privileged_role(client, operator_user, make_uav_asset):
    asset = await make_uav_asset()
    resp = await client.post(
        "/api/v1/engines",
        json={"serial_number": "SN-1", "uav_asset_id": str(asset.id)},
        headers=auth_headers(operator_user),
    )
    assert resp.status_code == 403


async def test_create_engine_success_and_duplicate_serial_conflict(client, admin_user, make_uav_asset):
    asset = await make_uav_asset()
    body = {"serial_number": f"SN-{asset.id}", "uav_asset_id": str(asset.id)}

    first = await client.post("/api/v1/engines", json=body, headers=auth_headers(admin_user))
    assert first.status_code == 201

    dup = await client.post("/api/v1/engines", json=body, headers=auth_headers(admin_user))
    assert dup.status_code == 409

    engine_id = first.json()["id"]
    await client.delete(f"/api/v1/engines/{engine_id}", headers=auth_headers(admin_user))


async def test_get_engine_not_found(client, operator_user):
    resp = await client.get(
        "/api/v1/engines/00000000-0000-0000-0000-0000000000ff",
        headers=auth_headers(operator_user),
    )
    assert resp.status_code == 404


async def test_delete_engine_requires_admin(client, operator_user, make_engine):
    engine = await make_engine()
    resp = await client.delete(f"/api/v1/engines/{engine.id}", headers=auth_headers(operator_user))
    assert resp.status_code == 403


async def test_engine_telemetry_latest_404_when_no_data(client, operator_user, make_engine):
    engine = await make_engine()
    resp = await client.get(
        f"/api/v1/engines/{engine.id}/telemetry/latest", headers=auth_headers(operator_user)
    )
    assert resp.status_code == 404


async def test_engine_health_score_stub_for_unknown_engine_404(client, operator_user):
    resp = await client.get(
        "/api/v1/engines/00000000-0000-0000-0000-0000000000ff/health-score",
        headers=auth_headers(operator_user),
    )
    assert resp.status_code == 404


async def test_engine_rul_empty_list_when_no_predictions(client, operator_user, make_engine):
    engine = await make_engine()
    resp = await client.get(f"/api/v1/engines/{engine.id}/rul", headers=auth_headers(operator_user))
    assert resp.status_code == 200
    assert resp.json() == []


async def test_engine_faults_latest_404_when_no_predictions(client, operator_user, make_engine):
    engine = await make_engine()
    resp = await client.get(
        f"/api/v1/engines/{engine.id}/faults/latest", headers=auth_headers(operator_user)
    )
    assert resp.status_code == 404


async def test_engine_bearing_health_404_when_no_readings(client, operator_user, make_engine):
    engine = await make_engine()
    resp = await client.get(
        f"/api/v1/engines/{engine.id}/bearing-health", headers=auth_headers(operator_user)
    )
    assert resp.status_code == 404


async def test_engine_telemetry_range_empty_list(client, operator_user, make_engine):
    engine = await make_engine()
    resp = await client.get(
        f"/api/v1/engines/{engine.id}/telemetry", headers=auth_headers(operator_user)
    )
    assert resp.status_code == 200
    assert resp.json() == []
