"""
E2E — parameter What-If (POST /simulation/what-if): change engine parameters
on a real, running stack and check that

  1. the backend really runs the model pipeline and returns the full contract
     (baseline / scenario / delta / window / model_results / health_fusion /
     physics_consistency / alerts, with all four Health Fusion sources);
  2. a "no change" scenario is a no-op (all deltas 0, no model output moves);
  3. invalid input is rejected with 400 INVALID_INPUT (no simulation run);
  4. the request is strictly READ-ONLY — telemetry, alerts, health scores and
     predictions for the engine are exactly the same after as before.

Run: python scripts/e2e/test_parameter_what_if.py
"""
import httpx

from _common import BASE_URL, ENGINE_ID, auth_headers, login


def snapshot(client: httpx.Client, headers: dict) -> dict:
    """Everything the What-If must NOT change."""
    latest = client.get(f"{BASE_URL}/engines/{ENGINE_ID}/telemetry/latest", headers=headers).json()
    health = client.get(f"{BASE_URL}/engines/{ENGINE_ID}/health-score", headers=headers, params={"history_limit": 1}).json()
    alerts = client.get(f"{BASE_URL}/alerts", params={"engine_id": ENGINE_ID}, headers=headers).json()
    fault = client.get(f"{BASE_URL}/engines/{ENGINE_ID}/faults/latest", headers=headers).json()
    return {
        "telemetry_ts": latest["ts"],
        "health_ts": health["last_updated"],
        "health_score": health["combined_score"],
        "alert_ids": sorted(a["id"] for a in alerts),
        "fault_ts": fault.get("ts"),
    }


def main():
    with httpx.Client(timeout=120.0) as client:
        token = login(client)
        headers = auth_headers(token)
        print("[1/6] Logged in (ingest backlog drained).")

        config = client.get(f"{BASE_URL}/simulation/what-if/config", headers=headers)
        config.raise_for_status()
        params = config.json()["parameters"]
        assert set(params) == {"rpm", "cht", "egt", "oil_pressure", "oil_temperature", "fuel_flow"}, params
        for name, p in params.items():
            assert p["min"] < p["max"] and p["step"] > 0 and p["unit"], (name, p)
        assert "Â" not in "".join(p["unit"] for p in params.values()), "unit encoding is mojibake"
        print(f"[2/6] Config OK: {len(params)} parameters with bounds/step/unit.")

        latest = client.get(f"{BASE_URL}/engines/{ENGINE_ID}/telemetry/latest", headers=headers)
        latest.raise_for_status()
        cur = latest.json()
        baseline_ts = cur["ts"]
        before = snapshot(client, headers)

        # ── a real scenario ─────────────────────────────────────────────
        body = {
            "engine_id": ENGINE_ID,
            "baseline_timestamp": baseline_ts,
            "parameters": {"rpm": cur["rpm"] + 300, "egt": cur["egt"] + 50, "oil_pressure": cur["oil_pressure"] - 10},
        }
        resp = client.post(f"{BASE_URL}/simulation/what-if", json=body, headers=headers)
        resp.raise_for_status()
        r = resp.json()
        assert r["mode"] == "WHAT_IF" and r["scenario_type"] == "PARAMETER_PERTURBATION", r["mode"]
        assert r["simulation_status"] in ("COMPLETED", "INSUFFICIENT_DATA"), r["simulation_status"]
        assert abs(r["delta"]["rpm"] - 300) < 1e-6 and r["delta"]["cht"] == 0, r["delta"]
        w = r["window"]
        assert w["perturbed_readings"] == r["perturbation_count"] > 0
        if r["simulation_status"] == "COMPLETED":
            assert w["data_sufficiency"] == "SUFFICIENT", w
        for src in ("rul", "fault", "bearing", "aux"):
            assert src in r["health_fusion"]["scenario"]["sources"], src
        assert set(r["physics_consistency"]["parameters"]) == {"cht", "egt", "oil_pressure", "oil_temperature", "fuel_flow"}
        assert r["alerts"]["simulation"] is True
        m = r["model_results"]
        # honesty flags: bearing only sees RPM, aux only RPM/CHT
        assert m["bearing"]["input_changed"] is True and m["auxiliary"]["input_changed"] is True
        print(f"[3/6] Scenario OK: status={r['simulation_status']}, health "
              f"{r['health_fusion']['baseline']['score']} -> {r['health_fusion']['scenario']['score']}, "
              f"alerts={r['alerts']['change']}, perturbed {w['perturbed_readings']}/{w['total_readings']}.")

        # ── no-change scenario is a no-op ───────────────────────────────
        same = client.post(f"{BASE_URL}/simulation/what-if", headers=headers, json={
            "engine_id": ENGINE_ID, "baseline_timestamp": baseline_ts, "parameters": {"cht": cur["cht"]}})
        same.raise_for_status()
        s = same.json()
        assert all(v == 0 for v in s["delta"].values()), s["delta"]
        assert s["health_fusion"]["score_delta"] == 0
        assert all(not blk["changed"] for blk in s["model_results"].values()), "a no-change scenario moved a model output"
        print("[4/6] No-change scenario is an exact no-op (all deltas 0, no model changed).")

        # ── invalid input ───────────────────────────────────────────────
        for bad in ({"rpm": 999999}, {"cht": -5}, {"nope": 1}, {}):
            resp = client.post(f"{BASE_URL}/simulation/what-if", headers=headers,
                               json={"engine_id": ENGINE_ID, "parameters": bad})
            assert resp.status_code == 400, (bad, resp.status_code)
            assert resp.json()["detail"]["simulation_status"] == "INVALID_INPUT"
        print("[5/6] Invalid inputs rejected with 400 INVALID_INPUT.")

        # ── read-only ───────────────────────────────────────────────────
        after = snapshot(client, headers)
        # If a live simulator is streaming, telemetry/health legitimately advance; only
        # assert strict equality on what a What-If could wrongly create: alerts.
        assert after["alert_ids"] == before["alert_ids"], "What-If created a live alert!"
        if after["telemetry_ts"] == before["telemetry_ts"]:
            assert after == before, f"live state changed after What-If:\n before={before}\n after={after}"
            print("[6/6] Read-only confirmed: telemetry, health, fault and alerts identical before/after.")
        else:
            print("[6/6] Alerts unchanged (engine is streaming, so telemetry/health advanced on their own).")

    print("\nPASS: parameter What-If E2E")


if __name__ == "__main__":
    main()
