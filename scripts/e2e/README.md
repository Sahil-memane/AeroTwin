# E2E scripts — Accuracy-First Phase 7 standing regression suite

Hit a REAL running stack over the network (Postgres + Redis + Mosquitto +
the FastAPI backend — whether started via `docker-compose up` or run
bare-metal) rather than an in-process test client. `backend/tests/`
covers unit/integration behavior against a test database; these cover
the same user-visible flows Phase 5B/6/7 were manually verified against
in-browser, as repeatable scripts — and, since Phase 7, the 7 named
accuracy-validation scenarios from
`docs/files/AeroTwin_Accuracy_First_Phased_Implementation_Plan.md`.
Per that document's own instruction, this is the standing regression
suite protecting every prior phase's baseline — re-run all of them
after any change to ingestion/validation/health-fusion/fault logic.

| Scenario | Script | Notes |
|---|---|---|
| A — Normal operations | `test_normal_ops.py` | Also checks a nominal burst never produces a false-critical Fault penalty (Phase 3). |
| B — Progressive degradation | `test_progressive_degradation.py` | A ramping (not step) fault; asserts the CHT trend, health-score decline, an alert firing, and RUL degradation all track the ramp. |
| C — Sudden fault → alert → ack | `test_fault_alert_ack.py` | Also queries the Copilot to explain the fired alert. |
| D — Sensor failure (partial) | `test_sensor_failure.py` | Exercises Phase 1's SUSPICIOUS jump-detection on a single glitched channel. Full sensor-vs-engine isolation (`FaultState.SENSOR_ANOMALY`) is reserved but unassigned — Tier 2, not done in this pass. |
| E — Network outage → buffer → recovery | `test_connectivity_loss_recovery.py` | Stops/starts `aerotwin-mqtt` via Docker — unchanged since Phase 7, already fully covered. |
| F — Missing/invalid data | `test_missing_invalid_data.py` | Exercises Phase 1's data-quality layer via the REST edge-ingest path. Requires `AEROTWIN_EDGE_API_KEY`. |
| G — Simulation (replay/what-if) | `test_replay_and_what_if.py` | Unchanged since Phase 6/7, still passing. |
| H — Parameter What-If | `test_parameter_what_if.py` | Real model pipeline on a modified telemetry window; asserts the contract, no-change = no-op, 400 on invalid input, and strict read-only behavior. |

Run the stack first, then each script individually (they assume the demo
admin user + seeded engine/mission already exist):

```
python scripts/e2e/test_normal_ops.py
python scripts/e2e/test_progressive_degradation.py
python scripts/e2e/test_fault_alert_ack.py
python scripts/e2e/test_sensor_failure.py
python scripts/e2e/test_connectivity_loss_recovery.py   # stops/starts aerotwin-mqtt via Docker
AEROTWIN_EDGE_API_KEY=... python scripts/e2e/test_missing_invalid_data.py
python scripts/e2e/test_replay_and_what_if.py
```

Override `AEROTWIN_API_URL` / `AEROTWIN_MQTT_HOST` / `AEROTWIN_MQTT_PORT`
env vars to point at a non-default host (e.g. a deployed environment).
`AEROTWIN_EDGE_API_KEY` must match the backend's real `EDGE_API_KEY`
(`backend/.env`) — only Scenario F needs it.

**Exit codes:** `0` pass, `1` fail, `2` *inconclusive* (currently only
`test_progressive_degradation.py`, when the engine's health is already forced
to 0 so a decline can't be observed — a model-quality limitation, not a
pipeline failure). `login()` waits for the previous scenario's telemetry
backlog to drain (set `AEROTWIN_E2E_NO_DRAIN=1` against a continuously
streaming engine).
