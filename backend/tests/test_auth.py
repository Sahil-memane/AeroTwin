"""
Auth flow tests — login, refresh, and the access/refresh token-type fix.

Regression coverage for the bug where /auth/refresh issued a token
byte-for-byte identical to an access token (no `type` claim), making a
refresh token usable anywhere an access token was and vice versa.
"""
from tests.conftest import TEST_PASSWORD


async def test_login_success_returns_distinct_access_and_refresh_tokens(client, operator_user):
    resp = await client.post("/api/v1/auth/login", json={
        "email": operator_user.email, "password": TEST_PASSWORD,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"] != body["refresh_token"]
    assert body["role"] == "operator"


async def test_login_wrong_password_rejected(client, operator_user):
    resp = await client.post("/api/v1/auth/login", json={
        "email": operator_user.email, "password": "wrong-password",
    })
    assert resp.status_code == 401


async def test_login_inactive_account_locked(client, make_user):
    user = await make_user("operator", is_active=False)
    resp = await client.post("/api/v1/auth/login", json={
        "email": user.email, "password": TEST_PASSWORD,
    })
    assert resp.status_code == 423


async def test_refresh_with_real_refresh_token_issues_new_access_token(client, operator_user):
    login = await client.post("/api/v1/auth/login", json={
        "email": operator_user.email, "password": TEST_PASSWORD,
    })
    refresh_token = login.json()["refresh_token"]

    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 200
    assert "access_token" in resp.json()


async def test_refresh_rejects_an_access_token(client, operator_user):
    """Regression: an access token must not work as a refresh token."""
    login = await client.post("/api/v1/auth/login", json={
        "email": operator_user.email, "password": TEST_PASSWORD,
    })
    access_token = login.json()["access_token"]

    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": access_token})
    assert resp.status_code == 401


async def test_protected_endpoint_rejects_a_refresh_token(client, operator_user):
    """Regression: a refresh token must not work as a bearer access token."""
    login = await client.post("/api/v1/auth/login", json={
        "email": operator_user.email, "password": TEST_PASSWORD,
    })
    refresh_token = login.json()["refresh_token"]

    resp = await client.get(
        "/api/v1/engines", headers={"Authorization": f"Bearer {refresh_token}"}
    )
    assert resp.status_code == 401


async def test_login_rate_limited_after_five_attempts(client, operator_user):
    for _ in range(5):
        r = await client.post("/api/v1/auth/login", json={
            "email": operator_user.email, "password": "wrong-password",
        })
        assert r.status_code == 401

    sixth = await client.post("/api/v1/auth/login", json={
        "email": operator_user.email, "password": "wrong-password",
    })
    assert sixth.status_code == 429
