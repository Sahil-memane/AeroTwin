"""
E2E — Phase 6 simulation modes: kick off a mission replay and a what-if
run through the real API, poll until each completes, and sanity-check
the results actually vary across steps (not stuck rendering the same
frame the whole way through — the exact class of bug the bearing model
had in Phase 6/7, so this is the regression test for "does it move").

Run: python scripts/e2e/test_replay_and_what_if.py
"""
import httpx

from _common import BASE_URL, ENGINE_ID, MISSION_ID, auth_headers, login, wait_until


def poll_simulation(client: httpx.Client, headers: dict, simulation_id: str, timeout_s: float):
    def get_status():
        resp = client.get(f"{BASE_URL}/simulation/{simulation_id}", headers=headers)
        resp.raise_for_status()
        body = resp.json()
        return body if body["status"] in ("completed", "failed") else None

    return wait_until(get_status, timeout_s=timeout_s, interval_s=2.0, description="simulation to finish")


def assert_varies(results: list, field_path: list, label: str):
    values = set()
    for r in results:
        node = r
        for key in field_path:
            node = node.get(key) if node else None
        values.add(node)
    assert len(values) > 1, f"{label} never changed across {len(results)} steps (got only {values})"
    print(f"    {label}: {len(values)} distinct value(s) across {len(results)} steps — OK")


def main():
    with httpx.Client(timeout=15.0) as client:
        token = login(client)
        headers = auth_headers(token)
        print("[1/4] Logged in.")

        # ── What-if (fast) ──
        wi = client.post(
            f"{BASE_URL}/simulation/run",
            json={"engine_id": ENGINE_ID, "mode": "what_if",
                  "environmental_profile": {"preset": "hot_weather_endurance"}},
            headers=headers,
        )
        wi.raise_for_status()
        wi_id = wi.json()["simulation_id"]
        print(f"[2/4] What-if run queued ({wi_id}), polling...")
        wi_result = poll_simulation(client, headers, wi_id, timeout_s=30.0)
        assert wi_result["status"] == "completed", f"what-if failed: {wi_result.get('error')}"
        assert len(wi_result["results"]) > 1
        assert_varies(wi_result["results"], ["health_score", "combined_score"], "what-if health_score")

        # ── Replay (slower — real stored mission) ──
        replay = client.post(
            f"{BASE_URL}/simulation/run",
            json={"engine_id": ENGINE_ID, "mode": "replay", "mission_id": MISSION_ID},
            headers=headers,
        )
        replay.raise_for_status()
        replay_id = replay.json()["simulation_id"]
        print(f"[3/4] Replay run queued ({replay_id}), polling (can take ~60s)...")
        replay_result = poll_simulation(client, headers, replay_id, timeout_s=120.0)
        assert replay_result["status"] == "completed", f"replay failed: {replay_result.get('error')}"
        assert len(replay_result["results"]) > 1
        print(f"[4/4] Replay completed with {len(replay_result['results'])} steps.")
        assert_varies(replay_result["results"], ["health_score", "combined_score"], "replay health_score")
        assert_varies(replay_result["results"], ["bearing", "class_label"], "replay bearing class_label")

    print("\nPASS: replay + what-if E2E")


if __name__ == "__main__":
    main()
