# AeroTwin Edge Agent (Phase 7)

Runs on the aircraft-side device (simulated today — see `can_interface/`).
Predicts Fault + RUL locally via ONNX Runtime, publishes telemetry (plus
the local predictions) to the cloud over MQTT, and survives a lost
connection to the broker without dropping data.

Bearing and Aux stay cloud-only — they're not exported or run here.

## Layout

- `can_interface/reader.py` — telemetry source abstraction. `SimulatedReader`
  wraps the existing physics-based `EngineSimulator`; `CANBusReader` is the
  documented, not-yet-implemented seam for real hardware.
- `inference/fault_runner.py`, `inference/rul_runner.py` — ONNX Runtime
  ports of `backend/app/services/{fault,rul}_service.py`. Verified
  bit-parity against the original models (same feature engineering,
  imported directly from the backend rather than duplicated).
- `inference/buffer.py` — SQLite-backed durable outbox for readings that
  couldn't reach the broker.
- `inference/edge_agent.py` — the runnable agent tying it together.
- `requirements.txt` — the edge device's own dependency set: `onnxruntime`
  + `numpy`/`scipy`/`paho-mqtt`, not the cloud backend's `tensorflow`/
  `xgboost`/`lightgbm`/`scikit-learn`/`joblib`.

## Regenerating the ONNX models

```
python ml/export_onnx.py
```

Writes `ml/models/{fault_stage1,fault_stage2,rul_xgb}.onnx` plus two JSON
sidecars (`fault_feature_names.json`, `rul_preprocessing.json`) the edge
runners load alongside them. Re-run this after retraining any of the two
source models.

## Running

```
python edge/inference/edge_agent.py --rate 1.0
```

Same `f`/`o`/`v`/`c` fault-injection keys as the original simulator.

## Verifying the offline/reconnect behavior

```
docker stop aerotwin-mqtt      # simulate a lost cloud connection
# ... watch the agent print "BUFFERED (N pending)" ...
docker start aerotwin-mqtt     # restore it
# ... watch it print "Reconnected — flushing N buffered reading(s) in order..."
#     followed by "Flushed N/N buffered reading(s); 0 remain."
```
