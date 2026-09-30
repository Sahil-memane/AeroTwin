import uuid
from tests.conftest import auth_headers


# ── Alerts ────────────────────────────────────────────────────────────

async def test_list_alerts_filters_and_defaults_to_all(client, operator_user, make_engine):
    from app.db.session import AsyncSessionLocal
    from app.models.alert import Alert

    engine = await make_engine()
    async with AsyncSessionLocal() as db:
        db.add(Alert(id=uuid.uuid4(), engine_id=engine.id, source="test", severity="warning", message="m1"))
        db.add(Alert(id=uuid.uuid4(), engine_id=engine.id, source="test", severity="critical", message="m2"))
        await db.commit()

    # Scope by engine_id — this is a shared dev DB, not a per-test-isolated
    # one, so other engines' alerts may legitimately also exist.
    default_list = await client.get(
        "/api/v1/alerts", params={"engine_id": str(engine.id)}, headers=auth_headers(operator_user)
    )
    assert default_list.status_code == 200
    assert len(default_list.json()) == 2

    filtered = await client.get(
        "/api/v1/alerts",
        params={"engine_id": str(engine.id), "severity": "critical"},
        headers=auth_headers(operator_user),
    )
    assert filtered.status_code == 200
    assert len(filtered.json()) == 1
    assert all(a["severity"] == "critical" for a in filtered.json())

    bad_severity = await client.get(
        "/api/v1/alerts", params={"severity": "nonsense"}, headers=auth_headers(operator_user)
    )
    assert bad_severity.status_code == 400


async def test_list_alerts_is_acknowledged_filter_true_false_and_omitted(client, admin_user, make_engine):
    from app.db.session import AsyncSessionLocal
    from app.models.alert import Alert

    engine = await make_engine()
    async with AsyncSessionLocal() as db:
        db.add(Alert(id=uuid.uuid4(), engine_id=engine.id, source="test", severity="warning", message="open"))
        db.add(Alert(
            id=uuid.uuid4(), engine_id=engine.id, source="test", severity="warning", message="closed",
            is_acknowledged=True,
        ))
        await db.commit()

    all_alerts = await client.get(
        "/api/v1/alerts", params={"engine_id": str(engine.id)}, headers=auth_headers(admin_user)
    )
    assert len(all_alerts.json()) == 2

    unacked = await client.get(
        "/api/v1/alerts",
        params={"engine_id": str(engine.id), "is_acknowledged": False},
        headers=auth_headers(admin_user),
    )
    assert [a["message"] for a in unacked.json()] == ["open"]

    acked = await client.get(
        "/api/v1/alerts",
        params={"engine_id": str(engine.id), "is_acknowledged": True},
        headers=auth_headers(admin_user),
    )
    assert [a["message"] for a in acked.json()] == ["closed"]


async def test_acknowledge_alert_requires_privileged_role(client, operator_user, make_engine):
    from app.db.session import AsyncSessionLocal
    from app.models.alert import Alert

    engine = await make_engine()
    alert_id = uuid.uuid4()
    async with AsyncSessionLocal() as db:
        db.add(Alert(id=alert_id, engine_id=engine.id, source="test", severity="warning", message="m"))
        await db.commit()

    resp = await client.patch(f"/api/v1/alerts/{alert_id}/acknowledge", headers=auth_headers(operator_user))
    assert resp.status_code == 403


async def test_acknowledge_alert_not_found(client, admin_user):
    resp = await client.patch(
        f"/api/v1/alerts/{uuid.uuid4()}/acknowledge", headers=auth_headers(admin_user)
    )
    assert resp.status_code == 404


# ── Model registry ────────────────────────────────────────────────────

async def test_list_models_requires_privileged_role(client, operator_user):
    resp = await client.get("/api/v1/models", headers=auth_headers(operator_user))
    assert resp.status_code == 403


async def test_list_models_returns_seeded_registry(client, admin_user):
    resp = await client.get("/api/v1/models", headers=auth_headers(admin_user))
    assert resp.status_code == 200
    names = {m["model_name"] for m in resp.json()}
    assert {"fault_lgb_2stage", "rul_xgb_base", "aux_predictive_maintenance", "bearing_vibration_cnn"} <= names


async def test_list_models_rejects_unknown_model_name_filter(client, admin_user):
    resp = await client.get(
        "/api/v1/models", params={"model_name": "not_a_real_model"}, headers=auth_headers(admin_user)
    )
    assert resp.status_code == 400


# ── Maintenance logs ──────────────────────────────────────────────────

async def test_create_maintenance_log_requires_privileged_role(client, operator_user, make_engine):
    engine = await make_engine()
    resp = await client.post(
        f"/api/v1/engines/{engine.id}/maintenance-logs",
        json={"action_taken": "Inspected oil filter"},
        headers=auth_headers(operator_user),
    )
    assert resp.status_code == 403


async def test_create_maintenance_log_success(client, admin_user, make_engine):
    engine = await make_engine()
    resp = await client.post(
        f"/api/v1/engines/{engine.id}/maintenance-logs",
        json={"action_taken": "Replaced spark plugs", "notes": "routine 100hr service"},
        headers=auth_headers(admin_user),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["action_taken"] == "Replaced spark plugs"
    assert body["engine_id"] == str(engine.id)


async def test_create_maintenance_log_unknown_engine_404(client, admin_user):
    resp = await client.post(
        f"/api/v1/engines/{uuid.uuid4()}/maintenance-logs",
        json={"action_taken": "x"},
        headers=auth_headers(admin_user),
    )
    assert resp.status_code == 404


# ── Dashboard ─────────────────────────────────────────────────────────

async def test_dashboard_summary_shape(client, operator_user):
    resp = await client.get("/api/v1/dashboard/summary", headers=auth_headers(operator_user))
    assert resp.status_code == 200
    body = resp.json()
    assert "total_engines" in body
    assert "fleet_health" in body
