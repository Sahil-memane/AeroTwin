"""
Shared helpers for the Phase 8 E2E scripts. These hit a REAL running
stack (Postgres + Redis + Mosquitto + the FastAPI backend, whether run
bare-metal or via `docker-compose up`) over the network — unlike
`backend/tests/`, which uses an in-process TestClient against a test
database. Run the stack first, then run these scripts individually.
"""
import os
import time
import uuid

import httpx

BASE_URL = os.environ.get("AEROTWIN_API_URL", "http://127.0.0.1:8000/api/v1")
MQTT_HOST = os.environ.get("AEROTWIN_MQTT_HOST", "127.0.0.1")
MQTT_PORT = int(os.environ.get("AEROTWIN_MQTT_PORT", "1883"))
# Same env var name scripts/load_test/locustfile.py already uses for the
# REST telemetry-ingest path's auth — reused here rather than a second name.
EDGE_API_KEY = os.environ.get("AEROTWIN_EDGE_API_KEY", "")

ADMIN_EMAIL = "admin@aerotwin-dev.com"
ADMIN_PASSWORD = "TestPass123!"

ENGINE_ID = "00000000-0000-0000-0000-000000000001"
MISSION_ID = "00000000-0000-0000-0000-000000000002"


def login(client: httpx.Client, email: str = ADMIN_EMAIL, password: str = ADMIN_PASSWORD, drain: bool = True) -> str:
    """Log in, then (by default) wait for any earlier scenario's telemetry
    backlog to finish processing.

    All scenarios share one engine, and the backend handles that engine's
    messages strictly in order, one at a time — a burst published by the
    previous script can still be draining minutes after that script exited,
    which made the NEXT script's own readings queue behind it and time out.
    Set AEROTWIN_E2E_NO_DRAIN=1 to skip (e.g. against a live, continuously
    streaming engine where the backlog never empties)."""
    resp = client.post(f"{BASE_URL}/auth/login", json={"email": email, "password": password})
    resp.raise_for_status()
    token = resp.json()["access_token"]
    if drain and not os.environ.get("AEROTWIN_E2E_NO_DRAIN"):
        wait_for_ingest_idle(client, token)
    return token


def wait_for_ingest_idle(client: httpx.Client, token: str, engine_id: str = ENGINE_ID,
                         quiet_s: float = 4.0, timeout_s: float = 180.0) -> bool:
    """Block until the engine's newest stored reading stops advancing for `quiet_s`
    seconds. Returns False (and carries on) if it never settles within `timeout_s`."""
    last, since, deadline = None, time.time(), time.time() + timeout_s
    while time.time() < deadline:
        r = client.get(f"{BASE_URL}/engines/{engine_id}/telemetry/latest", headers=auth_headers(token))
        current = r.json().get("ts") if r.status_code == 200 else None
        if current != last:
            last, since = current, time.time()
        elif time.time() - since >= quiet_s:
            return True
        time.sleep(1.0)
    print(f"  (ingest backlog did not settle within {timeout_s:.0f}s — continuing anyway)")
    return False


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def wait_until(predicate, timeout_s: float = 30.0, interval_s: float = 1.0, description: str = "condition"):
    """Poll `predicate()` until it returns a truthy value or the timeout elapses."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(interval_s)
    raise TimeoutError(f"Timed out after {timeout_s}s waiting for: {description}")


def new_client_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"
