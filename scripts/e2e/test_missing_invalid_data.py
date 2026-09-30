"""
E2E — Scenario F (missing/invalid data): exercises Phase 1's data-
quality layer end to end via the REST `/telemetry/ingest` path (the
edge-device route, `verify_edge_api_key`-guarded) — confirms invalid
telemetry is rejected with a clear 400 and never silently produces a
fabricated prediction, and that a genuinely valid reading still gets
accepted normally (this is a rejection test AND a regression test, not
rejection-only).

Requires AEROTWIN_EDGE_API_KEY to be set to the real backend
EDGE_API_KEY (see backend/.env) — this hits an edge-auth-gated endpoint,
not a JWT one.

Run: AEROTWIN_EDGE_API_KEY=... python scripts/e2e/test_missing_invalid_data.py
"""
import json
import os
import sys
import time
import uuid

import httpx

sys.path.insert(0, os.path.dirname(__file__))
from _common import BASE_URL, EDGE_API_KEY, ENGINE_ID  # noqa: E402

HEADERS = {"X-Edge-Api-Key": EDGE_API_KEY}


def _base_reading(**overrides) -> dict:
    reading = {
        "engine_id": ENGINE_ID,
        "ts": time.time(),
        "rpm": 2500.0, "cht": 90.0, "egt": 700.0,
        "oil_pressure": 55.0, "oil_temp": 95.0, "fuel_flow": 12.0,
    }
    reading.update(overrides)
    return reading


def expect_rejected(client: httpx.Client, label: str, reading: dict):
    # httpx's `json=` kwarg serializes with allow_nan=False (strict JSON),
    # which would raise client-side before the request is even sent — but
    # NaN/Infinity are exactly two of the corrupted-payload shapes this
    # scenario needs to send. Serialize manually with allow_nan=True (as
    # Python's json module itself defaults to) instead.
    body = json.dumps(reading, allow_nan=True)
    resp = client.post(
        f"{BASE_URL}/telemetry/ingest", content=body,
        headers={**HEADERS, "Content-Type": "application/json"},
    )
    assert resp.status_code == 400, f"{label}: expected 400, got {resp.status_code} — {resp.text}"
    print(f"    {label}: correctly rejected (400) — {resp.json().get('detail')}")


def main():
    if not EDGE_API_KEY:
        print("SKIPPED: set AEROTWIN_EDGE_API_KEY to the real backend EDGE_API_KEY to run this scenario.")
        return

    with httpx.Client(timeout=10.0) as client:
        print("[1/6] Missing required field (no `cht`)...")
        missing = _base_reading()
        del missing["cht"]
        expect_rejected(client, "missing cht", missing)

        print("[2/6] Out-of-range value (rpm impossibly high)...")
        expect_rejected(client, "rpm=99999", _base_reading(rpm=99999.0))

        print("[3/6] NaN value...")
        expect_rejected(client, "cht=NaN", _base_reading(cht=float("nan")))

        print("[4/6] Infinite value...")
        expect_rejected(client, "egt=inf", _base_reading(egt=float("inf")))

        print("[5/6] Unparseable timestamp...")
        expect_rejected(client, "ts=garbage", _base_reading(ts="not-a-timestamp"))

        print("[6/6] A genuinely valid reading is still accepted normally (regression check)...")
        valid = _base_reading(ts=time.time(), engine_id=ENGINE_ID)
        # Use a fresh mission-less reading; engine_id stays the real one so
        # it round-trips through the same FK check invalid payloads above
        # never even reached.
        resp = client.post(f"{BASE_URL}/telemetry/ingest", json=valid, headers=HEADERS)
        assert resp.status_code == 201, f"expected 201 for a valid reading, got {resp.status_code} — {resp.text}"
        assert resp.json()["status"] == "accepted"
        print(f"    Valid reading accepted: {resp.json()}")

        print("[bonus] Unknown engine_id is rejected distinctly (404, not fabricated data for a nonexistent engine)...")
        unknown = _base_reading(engine_id=str(uuid.uuid4()))
        resp = client.post(f"{BASE_URL}/telemetry/ingest", json=unknown, headers=HEADERS)
        assert resp.status_code == 404, f"expected 404 for unknown engine_id, got {resp.status_code}"
        print(f"    Correctly rejected with 404: {resp.json().get('detail')}")

    print("\nPASS: missing/invalid data E2E (Scenario F)")


if __name__ == "__main__":
    main()
