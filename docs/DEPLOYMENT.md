# AeroTwin — Deployment guide

## What gets deployed

| Piece | Image / target | Notes |
|---|---|---|
| Backend (FastAPI + 4 ML models + MQTT ingestion) | `ghcr.io/<owner>/<repo>/backend` from `infra/docker/Dockerfile.backend` | **Build context is the repo root** — the image contains `backend/`, `ml/training` (model artifacts) and `simulation/`. |
| Frontend (static Vite build behind nginx) | `ghcr.io/<owner>/<repo>/frontend` from `infra/docker/Dockerfile.frontend` | `VITE_API_URL` / `VITE_WS_URL` are baked in at build time (repo variables `PROD_API_URL`, `PROD_WS_URL`). |
| PostgreSQL + TimescaleDB | managed / VM | `alembic upgrade head` runs automatically on backend start (`entrypoint.sh`). |
| MQTT broker (Mosquitto) | VM / HiveMQ Cloud | Telemetry ingest topic `aerotwin/telemetry/+`. Enable TLS + auth in production. |
| Redis | managed | Provisioned but not yet used for runtime state (see limits). |

See also [GCP_DEPLOYMENT.md](GCP_DEPLOYMENT.md) (single-VM Docker Compose production stack).

CI (`.github/workflows/ci.yml`) must be green; `deploy.yml` then builds + pushes both images and pings the deploy hooks.

## Required backend environment

| Variable | Production requirement |
|---|---|
| `ENVIRONMENT` | `production` — turns on the startup safety check below |
| `JWT_SECRET` | ≥ 32 random chars (`openssl rand -hex 32`); not a placeholder |
| `EDGE_API_KEY` | ≥ 16 random chars |
| `CORS_ORIGINS` | the real frontend origin(s), comma-separated — **not** `*` |
| `DATABASE_URL` | `postgresql+asyncpg://…` |
| `MQTT_BROKER_URL`, `REDIS_URL` | broker / redis URLs |
| `GROQ_API_KEY` / `GEMINI_API_KEY`, `LLM_PROVIDER` | Copilot (optional; degrades if unset) |
| `HEALTH_FUSION_MAX_PREDICTION_AGE_SECONDS` | default 60 |
| `HEALTH_SCORE_STALE_AFTER_SECONDS` | default 300 |

With `ENVIRONMENT=production` the app **refuses to boot** if any of the first three are unsafe — read the error, fix the variable.

Also change the seeded demo account (`admin@aerotwin-dev.com` / `TestPass123!`, hard-coded in `scripts/e2e/_common.py`) before exposing the API; the E2E scripts must only be pointed at a non-production environment.

## GitHub setup (once)

Repository **variables**: `PROD_API_URL`, `PROD_WS_URL`, optional `PROD_HEALTHZ_URL`.
Repository **secrets**: optional `BACKEND_DEPLOY_HOOK`, `FRONTEND_DEPLOY_HOOK`.
Create an `production` environment (Settings → Environments) and add required reviewers if you want a manual approval gate before `release` runs.

## Known limits — read before scaling

1. **Run exactly one backend replica.** RUL/Fault windows, the fault state machine, alert cooldowns, aux wear state and the WebSocket manager live in process memory (decision D5). After a restart the RUL window needs 30 and the Fault window 80 fresh readings before those models report again; Health Fusion shows a *partial assessment* (`missing_sources`) meanwhile instead of reusing old predictions.
2. **Memory.** The image loads TensorFlow (bearing CNN), XGBoost, LightGBM and scikit-learn. A 512 MB free-tier instance is very likely too small — **[NEEDS VERIFICATION]** on your host; budget ≥ 2 GB. Models load lazily on the first request (2–4 s cold).
3. **Model quality.** The Fault and RUL models are trained on UAV-log / turbofan data and reach piston-engine telemetry through proxy adapters (see `docs/files/RUL_Domain_Gap.md`). On some operating regimes (notably idle/low RPM) they can report a confirmed fault or RUL 0 — treat outputs as decision *support* until validated on real piston-engine data.
4. **Image not built in this repo's CI yet.** `deploy.yml` builds it; the first run will download ~1.5 GB of ML wheels.

## Shipping changes after go-live

| Change | How |
|---|---|
| UI, API endpoints, thresholds | merge to `main` → CI → deploy |
| DB schema | add an Alembic migration; it runs on the next backend start (keep changes additive/nullable, as the existing ones are) |
| Retrained model | replace the artifacts under `ml/training/...`, bump `model_registry`, redeploy |
| Config only (staleness windows, CORS) | change the env var and restart — no rebuild |

> **Dev-only service:** `infra/docker/docker-compose.yml` includes a `simulator` service (`Dockerfile.simulator`) that publishes synthetic telemetry for the demo engine. Remove it from any production deployment; real engines publish through the edge agent / MQTT.
