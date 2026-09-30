# Phase 8 load test

```
python scripts/load_test/seed_engines.py 50
AEROTWIN_EDGE_API_KEY=<value from backend/.env> \
  locust -f scripts/load_test/locustfile.py --host http://127.0.0.1:8000 \
  --users 50 --spawn-rate 5 --run-time 2m --headless
python scripts/load_test/measure_ws_latency.py 30   # run concurrently with the above, in another shell
python scripts/load_test/cleanup_engines.py
```

`locustfile.py` load-tests `/telemetry/ingest` (REST edge ingestion —
validation + the TimescaleDB write). It intentionally does NOT touch the
WebSocket broadcast: that endpoint is a bare storage write with no ML
inference or `ws_manager` broadcast (see `telemetry.py` — only the MQTT
ingestion path does that). `measure_ws_latency.py` is the counterpart
that actually exercises the broadcast path, publishing real telemetry
over MQTT for the demo engine and timing WS delivery — meant to be run
*while* the Locust load is active, to see whether unrelated write load
drags down live-dashboard latency for anyone watching it.
