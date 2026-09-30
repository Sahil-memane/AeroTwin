import uuid

from tests.conftest import auth_headers, TEST_PASSWORD


def _unique_email() -> str:
    return f"new-user-{uuid.uuid4().hex[:8]}@test.aerotwin"


# ── UAV assets ────────────────────────────────────────────────────────

async def test_list_and_create_uav_asset(client, operator_user, admin_user):
    tail_number = f"N-TEST-{uuid.uuid4().hex[:8]}"

    listed = await client.get("/api/v1/uav-assets", headers=auth_headers(operator_user))
    assert listed.status_code == 200

    forbidden = await client.post(
        "/api/v1/uav-assets", json={"tail_number": tail_number}, headers=auth_headers(operator_user)
    )
    assert forbidden.status_code == 403

    created = await client.post(
        "/api/v1/uav-assets", json={"tail_number": tail_number}, headers=auth_headers(admin_user)
    )
    assert created.status_code == 201
    asset_id = created.json()["id"]

    dup = await client.post(
        "/api/v1/uav-assets", json={"tail_number": tail_number}, headers=auth_headers(admin_user)
    )
    assert dup.status_code == 409

    updated = await client.put(
        f"/api/v1/uav-assets/{asset_id}", json={"status": "maintenance"}, headers=auth_headers(admin_user)
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "maintenance"

    deleted = await client.delete(f"/api/v1/uav-assets/{asset_id}", headers=auth_headers(admin_user))
    assert deleted.status_code == 204


async def test_get_uav_asset_not_found(client, operator_user):
    resp = await client.get(
        "/api/v1/uav-assets/00000000-0000-0000-0000-0000000000ff", headers=auth_headers(operator_user)
    )
    assert resp.status_code == 404


# ── Users (admin-only surface) ───────────────────────────────────────

async def test_list_users_requires_admin(client, operator_user):
    resp = await client.get("/api/v1/users", headers=auth_headers(operator_user))
    assert resp.status_code == 403


async def test_admin_can_create_list_update_delete_user(client, admin_user):
    email = _unique_email()
    create = await client.post(
        "/api/v1/users",
        json={"email": email, "role": "operator", "password": TEST_PASSWORD},
        headers=auth_headers(admin_user),
    )
    assert create.status_code == 201
    user_id = create.json()["id"]

    listed = await client.get("/api/v1/users", headers=auth_headers(admin_user))
    assert listed.status_code == 200
    assert any(u["id"] == user_id for u in listed.json())

    dup = await client.post(
        "/api/v1/users",
        json={"email": email, "role": "operator", "password": TEST_PASSWORD},
        headers=auth_headers(admin_user),
    )
    assert dup.status_code == 409

    updated = await client.put(
        f"/api/v1/users/{user_id}", json={"role": "maintenance_engineer"}, headers=auth_headers(admin_user)
    )
    assert updated.status_code == 200
    assert updated.json()["role"] == "maintenance_engineer"

    deleted = await client.delete(f"/api/v1/users/{user_id}", headers=auth_headers(admin_user))
    assert deleted.status_code == 204

    missing = await client.get(f"/api/v1/users/{user_id}", headers=auth_headers(admin_user))
    assert missing.status_code == 404
