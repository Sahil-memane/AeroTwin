# AeroTwin Decisions Log

This document records the architectural and design decisions made during the project lifecycle.

| # | Decision | Resolution | Rationale |
|---|---|---|---|
| D1 | **Fault model taxonomy** | **Option B**: Keep ALFA's actual 7 classes and reframe the Fault model's scope as UAV-system fault detection. | Relabeling dataset to engine-specific faults requires unavailable domain expertise and data; it's safer and faster for a hackathon to keep the original labels. |
| D2 | **Schema gaps** | Add `aux_predictions (engine_id, model_version_id, ts, aux_score)` and add `model_version_id` FK to `bearing_health_readings`. | Necessary to correctly capture all prediction states and maintain relational integrity across model versions. |
| D3 | **License for public repo** | **MIT License** | Standard permissive open-source license, simplest default for a hackathon. |
| D4 | **No separate ML-inference container** | Inference stays in-process in the backend image; `Dockerfile.ml-inference` (an empty placeholder) was removed. The backend image is built from the repo root so it carries `ml/training` and `simulation/`. | The four models run inside `backend/app/services/*` and are called synchronously by ingestion/what-if; a second service would add a network hop and a second deploy for no benefit at demo scale. The edge device has its own ONNX runtime (`edge/`). Revisit only if backend memory (TensorFlow) forces the bearing CNN out. |
| D5 | **Single backend replica** | Deploy exactly one backend process (`entrypoint.sh` runs one uvicorn worker). | RUL/Fault sliding windows, the fault state machine, alert cooldowns, aux wear state and the WebSocket connection manager live in process memory. Scaling out would split that state. Moving it to Redis (already provisioned) is the prerequisite for >1 replica. |
| D6 | **Health Fusion ignores stale predictions** | A stored prediction older than `HEALTH_FUSION_MAX_PREDICTION_AGE_SECONDS` (60 s) relative to the reading being fused is treated as absent; the live `health_score` message lists `missing_sources`. | After a restart or a stopped stream the newest DB row can be hours old; without an age limit an old confirmed fault kept forcing health to 0. A missing source is reported, not silently scored as healthy. |
| D7 | **Production refuses unsafe config** | With `ENVIRONMENT=production` the app raises at startup on placeholder/short `JWT_SECRET`/`EDGE_API_KEY` or a wildcard `CORS_ORIGINS`. | Fail fast beats shipping the well-known development defaults. |

