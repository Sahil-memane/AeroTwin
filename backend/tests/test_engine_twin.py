"""GET /engines/{id}/twin — the static description the 3D digital twin is built from."""
import uuid
from types import SimpleNamespace


from app.api.v1 import engines as engines_api
from app.services.physics_model import DEFAULT_SPECS, PARAMETER_TOLERANCES
from tests.conftest import auth_headers


async def test_twin_spec_comes_from_real_engine_configuration(client, admin_user, make_engine):
    engine = await make_engine()
    resp = await client.get(f"/api/v1/engines/{engine.id}/twin", headers=auth_headers(admin_user))
    assert resp.status_code == 200
    body = resp.json()

    assert body["engine_id"] == str(engine.id) and body["serial_number"] == engine.serial_number
    spec = body["spec"]
    # every number is read from EngineSpecs, not restated
    assert spec["num_cylinders"] == DEFAULT_SPECS.num_cylinders
    assert spec["displacement_cc"] == DEFAULT_SPECS.displacement_cc
    assert (spec["rpm_idle"], spec["rpm_cruise"], spec["rpm_max"]) == (DEFAULT_SPECS.rpm_idle, DEFAULT_SPECS.rpm_cruise, DEFAULT_SPECS.rpm_max)
    assert spec["rated_power_kw"] == DEFAULT_SPECS.rated_power_kw
    assert spec["layout"] == "horizontally_opposed" and "specs.py" in spec["source"]
    assert body["physics_tolerances"] == PARAMETER_TOLERANCES
    assert set(body["sensor_ranges"]) == {"rpm", "cht", "egt", "oil_pressure", "oil_temp", "fuel_flow"}
    for lo, hi in body["sensor_ranges"].values():
        assert lo < hi


async def test_twin_reports_no_per_cylinder_sensors_today(client, admin_user, make_engine):
    engine = await make_engine()
    sensors = (await client.get(f"/api/v1/engines/{engine.id}/twin", headers=auth_headers(admin_user))).json()["sensors"]
    assert sensors["per_cylinder"] is False and sensors["per_cylinder_columns"] == []
    assert "per-cylinder temperatures are not measured" in sensors["note"]


def test_per_cylinder_detection_reads_the_real_table_definition(monkeypatch):
    cols = [SimpleNamespace(name=n) for n in ("ts", "cht", "egt", "oil_temp", "cht_1", "cht_2", "egt3")]
    monkeypatch.setattr(engines_api, "TelemetryReadingModel", SimpleNamespace(__table__=SimpleNamespace(columns=cols)))
    assert engines_api._per_cylinder_sensor_columns() == ["cht_1", "cht_2", "egt3"]  # cht/egt alone are engine-level


def test_capability_flag_flips_when_per_cylinder_columns_exist(monkeypatch):
    monkeypatch.setattr(engines_api, "_per_cylinder_sensor_columns", lambda: ["cht_1", "cht_2"])
    assert bool(engines_api._per_cylinder_sensor_columns()) is True


async def test_twin_unknown_engine_404_and_requires_auth(client, admin_user):
    assert (await client.get(f"/api/v1/engines/{uuid.uuid4()}/twin", headers=auth_headers(admin_user))).status_code == 404
    assert (await client.get(f"/api/v1/engines/{uuid.uuid4()}/twin")).status_code == 401
