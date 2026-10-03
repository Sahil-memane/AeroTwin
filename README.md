# AeroTwin — Digital Twin Operations Platform

> **Live deployment:** https://aerotwin-clutchx.duckdns.org

AeroTwin is a full-stack digital twin operations platform for UAV engine fleets. It ingests real-time (or simulated) engine telemetry over MQTT, runs ML-based predictive maintenance models (RUL, fault detection, auxiliary), renders an interactive 3D digital twin, and surfaces an AI-powered maintenance copilot backed by a RAG knowledge base.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Repository Structure](#2-repository-structure)
3. [Technology Stack](#3-technology-stack)
4. [Container Stack](#4-container-stack)
5. [API Reference](#5-api-reference)
6. [Frontend Pages and Components](#6-frontend-pages-and-components)
7. [Data Model](#7-data-model)
8. [Execution and Startup Sequence](#8-execution-and-startup-sequence)
9. [Simulator On-Demand Telemetry](#9-simulator-on-demand-telemetry)
10. [ML Pipeline](#10-ml-pipeline)
11. [Documentation and Research](#11-documentation-and-research)
12. [CI/CD Pipeline](#12-cicd-pipeline)
13. [Infrastructure and Deployment](#13-infrastructure-and-deployment)
14. [Environment Variables](#14-environment-variables)
15. [Local Development](#15-local-development)
16. [Production Operations](#16-production-operations)
17. [User Roles and Permissions](#17-user-roles-and-permissions)
18. [Security](#18-security)
19. [Known Limitations and Roadmap](#19-known-limitations-and-roadmap)

---

## 1. Architecture Overview

```
                     GCP Compute Engine VM (e2-micro, 2 GB swap)
                  +------------------------------------------------+
                  |                                                |
Browser --HTTPS-->|  Caddy :443/:80                               |
                  |   /api/*  --> backend:8000 (FastAPI)          |
                  |   /healthz-> backend:8000                     |
                  |   *       --> frontend:80 (Nginx/React)       |
                  |                   |                           |
                  |         +---------+----------+                |
                  |         |         |          |                |
                  |       DB:5432  Redis:6379  MQTT:1883          |
                  |    TimescaleDB             Mosquitto           |
                  |                               ^               |
                  |                        Simulator (on-demand)  |
                  +------------------------------------------------+
```

**Traffic flow:**
- All HTTPS traffic enters through **Caddy** (auto-TLS via Lets Encrypt)
- `/api/*` and `/healthz` are reverse-proxied to **FastAPI backend** on port 8000
- All other paths serve the **React SPA** via Nginx on port 80
- Backend subscribes to **MQTT** for telemetry ingestion
- Simulator container launched **on-demand** by backend via Docker SDK when user clicks START

---

## 2. Repository Structure

```
AeroTwin/
|-- backend/                          FastAPI backend service
|   |-- app/
|   |   |-- api/v1/                   API route handlers (one file per domain)
|   |   |   |-- auth.py               JWT login / register / refresh
|   |   |   |-- engines.py            Engine CRUD + WebSocket telemetry stream
|   |   |   |-- telemetry.py          Telemetry HTTP ingest + latest readings
|   |   |   |-- simulator_control.py  Start / stop / status / heartbeat
|   |   |   |-- simulation.py         Simulation runs and what-if scenarios
|   |   |   |-- dashboard.py          Fleet summary KPIs
|   |   |   |-- alerts.py             Alert CRUD + acknowledge
|   |   |   |-- copilot.py            RAG-powered AI copilot endpoint
|   |   |   |-- missions.py           Mission CRUD + telemetry summary
|   |   |   |-- uav_assets.py         UAV asset registry
|   |   |   |-- users.py              User management
|   |   |   |-- maintenance.py        Maintenance log CRUD
|   |   |   |-- faults.py             Fault prediction read endpoints
|   |   |   |-- bearing.py            Bearing health readings
|   |   |   |-- auxiliary.py          Auxiliary system predictions
|   |   |   |-- models.py             ML model registry
|   |   |   +-- rul.py                Remaining Useful Life endpoints
|   |   |-- core/
|   |   |   |-- config.py             Settings (Pydantic BaseSettings)
|   |   |   +-- security.py           JWT auth, role decorators
|   |   |-- db/
|   |   |   +-- session.py            Async SQLAlchemy session factory
|   |   |-- models/                   SQLAlchemy ORM models
|   |   |-- schemas/                  Pydantic request/response schemas
|   |   |-- services/
|   |   |   |-- ingestion.py          MQTT subscriber + DB writer
|   |   |   |-- simulator_manager.py  Docker SDK wrapper for sim lifecycle
|   |   |   |-- rul_service.py        RUL ML inference
|   |   |   |-- fault_service.py      Fault detection ML inference
|   |   |   |-- aux_service.py        Auxiliary prediction ML inference
|   |   |   |-- bearing_service.py    Bearing health ML inference
|   |   |   +-- physics_model.py      Physics-based deviation checks
|   |   |-- ws/
|   |   |   +-- connection_manager.py WebSocket connection pool
|   |   +-- main.py                   FastAPI app factory + router mounts
|   |-- alembic/                      Database migrations
|   |-- AeroTwin_Rag/                 RAG knowledge base + copilot engine
|   |-- create_user.py                Admin CLI: create/update users
|   |-- entrypoint.sh                 Docker entrypoint (alembic + uvicorn)
|   +-- requirements.txt
|
|-- frontend/                         React + TypeScript SPA
|   |-- src/
|   |   |-- pages/
|   |   |   |-- Dashboard.tsx         Fleet overview + simulator controls
|   |   |   |-- EngineDetail.tsx      Per-engine telemetry detail
|   |   |   |-- EngineTwin.tsx        Interactive 3D digital twin
|   |   |   |-- TwinIndex.tsx         Twin engine picker
|   |   |   |-- SimulationReplay.tsx  Historical simulation playback
|   |   |   |-- Missions.tsx          Mission list
|   |   |   |-- MissionDetail.tsx     Mission telemetry deep-dive
|   |   |   |-- Assets.tsx            UAV asset registry
|   |   |   |-- Alerts.tsx            Alert centre
|   |   |   |-- Login.tsx             Authentication
|   |   |   +-- Register.tsx          User registration
|   |   |-- components/               Shared UI components
|   |   |-- services/
|   |   |   |-- apiClient.ts          Fetch wrapper with JWT + auto-refresh
|   |   |   +-- resources.ts          Typed API resource functions
|   |   |-- store/
|   |   |   |-- authStore.ts          Zustand auth state
|   |   |   +-- simulatorStore.ts     Zustand global simulator state
|   |   +-- types/                    TypeScript type definitions
|   |-- .env.production               VITE_API_URL=/api/v1 (baked at build)
|   +-- nginx.conf                    Nginx: SPA fallback + cache headers
|
|-- edge/                             Edge agent (real hardware / simulator)
|   |-- telemetry_publisher/
|   |   +-- simulate.py               Physics-based engine simulator -> MQTT
|   |-- inference/
|   |   +-- edge_agent.py             On-device inference agent
|   +-- can_interface/
|       +-- reader.py                 CAN bus / simulated reader
|
|-- ml/                               ML training pipeline
|   |-- training/
|   |   |-- rul_model/                RUL LSTM/XGBoost training
|   |   |-- fault_model/              Binary fault detection (LightGBM)
|   |   +-- aux_model/                Auxiliary failure prediction
|   +-- data/                         Training datasets (NASA C-MAPSS etc.)
|
|-- simulation/                       Simulation scenario configs
|
|-- infra/
|   +-- docker/
|       |-- docker-compose.yml        Local development stack
|       |-- docker-compose.prod.yml   Production (build-from-source)
|       |-- docker-compose.vm.yml     Production VM (pull from registry)
|       |-- Dockerfile.backend        Multi-stage backend image
|       |-- Dockerfile.frontend       Multi-stage frontend (Vite -> Nginx)
|       |-- Dockerfile.simulator      Simulator container image
|       |-- Caddyfile                 Caddy reverse proxy + auto-TLS
|       |-- mosquitto.conf            MQTT broker config (dev)
|       |-- mosquitto.prod.conf       MQTT broker config (prod)
|       |-- .env.prod                 Production secrets (gitignored)
|       +-- .env.prod.example         Template for .env.prod
|
|-- scripts/                          Utility scripts
|-- cloudbuild.yaml                   GCP Cloud Build CI/CD pipeline
|-- build-and-push.sh                 Manual image build + push script
+-- deploy-from-registry.sh           VM pull-and-restart script
```

---

## 3. Technology Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11, FastAPI, SQLAlchemy (async), Alembic, asyncpg |
| Database | TimescaleDB 2.17 (PostgreSQL 16) with time-series hypertables |
| Cache / PubSub | Redis 7 |
| Message Broker | Eclipse Mosquitto 2.0 (MQTT) |
| ML Inference | scikit-learn, LightGBM, joblib, ONNX Runtime |
| AI Copilot | Groq (llama3) / Google Gemini with RAG knowledge base |
| Frontend | React 18, TypeScript, Vite 5, Zustand, React Router v6 |
| 3D Rendering | Three.js / React Three Fiber |
| Reverse Proxy | Caddy 2 (automatic Lets Encrypt TLS) |
| Containers | Docker, Docker Compose |
| CI/CD | GCP Cloud Build + Artifact Registry |
| Infrastructure | GCP Compute Engine (e2-micro, us-central1-a) |
| DNS | DuckDNS (aerotwin-clutchx.duckdns.org) |

---

## 4. Container Stack

Six containers run permanently in the `aerotwin-prod` network, plus one launched on-demand:

| Container | Image | Port | Role |
|-----------|-------|------|------|
| aerotwin-prod-caddy-1 | caddy:2-alpine | 80, 443 (host) | Reverse proxy + TLS termination |
| aerotwin-prod-frontend-1 | aerotwin-frontend:latest | 80 (internal) | React SPA via Nginx |
| aerotwin-prod-backend-1 | aerotwin-backend:latest | 8000 (internal) | FastAPI application server |
| aerotwin-prod-db-1 | timescale/timescaledb:2.17.2-pg16 | 5432 (internal) | Primary database |
| aerotwin-prod-redis-1 | redis:7-alpine | 6379 (internal) | Session cache + rate limiting |
| aerotwin-prod-mqtt-1 | eclipse-mosquitto:2.0.20 | 1883 (internal) | MQTT message broker |
| aerotwin-simulator (on-demand) | aerotwin-simulator:latest | none | Physics-based telemetry publisher |

**Startup dependency order:**

```
db (healthy) ---+
redis (healthy) +---> backend ---> caddy
mqtt (started) -+

frontend (independent) ---> caddy
```

The simulator is NOT started at boot. It is launched on-demand via Docker SDK.

---

## 5. API Reference

**Base URL:** `https://aerotwin-clutchx.duckdns.org/api/v1`

**Swagger UI:** `https://aerotwin-clutchx.duckdns.org/api/v1/docs`

All endpoints except `/auth/*` require: `Authorization: Bearer <access_token>`

### Authentication `/auth`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | /auth/register | No | Register new user, returns JWT |
| POST | /auth/login | No | Login with email + password, returns JWT |
| POST | /auth/refresh | No | Refresh access token using refresh token |

### Engines `/engines`

| Method | Path | Roles | Description |
|--------|------|-------|-------------|
| GET | /engines | All | List all engines |
| GET | /engines/{id} | All | Get single engine |
| POST | /engines | admin, program_manager | Create engine |
| PUT | /engines/{id} | admin, program_manager | Update engine |
| DELETE | /engines/{id} | admin | Delete engine |
| GET | /engines/{id}/telemetry | All | Telemetry history (paginated) |
| GET | /engines/{id}/telemetry/latest | All | Latest telemetry reading |
| GET | /engines/{id}/health-score | All | Health score + history |
| GET | /engines/{id}/rul | All | RUL predictions |
| GET | /engines/{id}/rul/status | All | Latest RUL status |
| GET | /engines/{id}/faults | All | Fault predictions |
| GET | /engines/{id}/bearing | All | Bearing health readings |
| GET | /engines/{id}/aux | All | Auxiliary system predictions |
| GET | /engines/{id}/maintenance | All | Maintenance log entries |
| POST | /engines/{id}/maintenance | maintenance_engineer, admin | Add maintenance log |
| GET | /engines/{id}/twin | All | 3D twin spec (sensor ranges, geometry) |
| GET | /engines/{id}/physics-consistency | All | Physics deviation check |
| WS | /engines/{id}/ws | All | Live telemetry WebSocket stream |

### Simulator Control `/simulator`

| Method | Path | Description |
|--------|------|-------------|
| POST | /simulator/{engine_id}/start | Start simulator container (idempotent) |
| POST | /simulator/{engine_id}/stop | Stop simulator container |
| GET | /simulator/{engine_id}/status | Get current simulator state |
| POST | /simulator/{engine_id}/heartbeat | Frontend liveness ping |

### Dashboard `/dashboard`

| Method | Path | Description |
|--------|------|-------------|
| GET | /dashboard/summary | Fleet KPIs: total engines, avg health, active alerts, active missions |

### Alerts `/alerts`

| Method | Path | Description |
|--------|------|-------------|
| GET | /alerts | List all alerts (filterable by engine, severity, acknowledged) |
| GET | /alerts/{id} | Get single alert |
| POST | /alerts/{id}/acknowledge | Acknowledge alert |

### Missions `/missions`

| Method | Path | Description |
|--------|------|-------------|
| GET | /missions | List all missions |
| GET | /missions/{id} | Mission detail + telemetry summary |
| POST | /missions | Create mission |
| PUT | /missions/{id} | Update mission |
| DELETE | /missions/{id} | Delete mission |

### UAV Assets `/uav-assets`

| Method | Path | Description |
|--------|------|-------------|
| GET | /uav-assets | List all UAV assets |
| GET | /uav-assets/{id} | Get single asset |
| POST | /uav-assets | Create asset |
| PUT | /uav-assets/{id} | Update asset |

### Simulation `/simulation`

| Method | Path | Description |
|--------|------|-------------|
| POST | /simulation/run | Start a simulation run (replay or what-if mode) |
| GET | /simulation/runs | List simulation runs |
| GET | /simulation/runs/{id} | Get simulation run results |

### Copilot `/copilot`

| Method | Path | Rate Limit | Description |
|--------|------|------------|-------------|
| POST | /copilot/query | 10 req/min | Ask AI copilot (RAG + live engine data) |

Request body:
```json
{
  "message": "What is the RUL status of the engine?",
  "engine_id": "11244686-4ac4-415a-bf0a-01dae03e339c"
}
```

### Other

| Method | Path | Description |
|--------|------|-------------|
| POST | /telemetry/ingest | HTTP telemetry ingest for edge devices |
| GET | /healthz | Health check, no auth required |

---

## 6. Frontend Pages and Components

| Route | Page | Description |
|-------|------|-------------|
| /login | Login | JWT authentication |
| /register | Register | Self-registration (default role: maintenance_engineer) |
| /dashboard | Dashboard | Fleet overview, KPIs, live tickers, simulator START/STOP buttons |
| /engines/:id | EngineDetail | Per-engine telemetry charts, RUL, fault history |
| /twin | TwinIndex | Engine selection for 3D twin |
| /twin/:id | EngineTwin | Interactive 3D digital twin with live sensor overlays |
| /missions | Missions | Mission list with telemetry summaries |
| /missions/:id | MissionDetail | Mission telemetry deep-dive |
| /assets | Assets | UAV asset registry |
| /alerts | Alerts | Alert centre with severity filtering and acknowledge |
| /simulation/:runId | SimulationReplay | Historical simulation playback |

### Key Frontend Architecture

**apiClient.ts** - Fetch wrapper that:
- Constructs URLs via `new URL(path, window.location.href)` supporting both absolute (dev) and relative (prod) base URLs
- Injects Authorization header automatically
- Handles 401 with silent token refresh and retry
- Supports request timeouts via AbortController

**simulatorStore.ts** (Zustand) - Global simulator state: `stopped -> loading -> connecting -> running -> error`

**authStore.ts** (Zustand) - JWT access/refresh token with localStorage persistence

---

## 7. Data Model

| Table | Description |
|-------|-------------|
| engines | Engine registry: serial_number, status, uav_asset_id |
| uav_assets | UAV platform registry: tail_number, status |
| missions | Flight missions: uav_asset_id, mission_type, start_time, status |
| users | Accounts: email, hashed_password, role, is_active |
| telemetry_readings | TimescaleDB hypertable: ts, engine_id, mission_id, all sensor fields |
| rul_predictions | RUL outputs: ts, engine_id, predicted_rul, confidence |
| health_scores | Composite health: ts, engine_id, score |
| fault_predictions | Fault detection: ts, engine_id, fault_type, probability |
| bearing_health_readings | Bearing vibration: ts, engine_id, health_index |
| alerts | System alerts: engine_id, source, severity, message, is_acknowledged |
| maintenance_logs | Maintenance actions: engine_id, user_id, action, notes |
| simulation_runs | Simulation records: mission_id, engine_id, mode, status |
| model_registry | ML model versions: model_name, version, is_active, validation_score |

### Seeded Production Reference Data

| Table | Records |
|-------|---------|
| engines | ENG-ALPHA-001 (operational, linked to UAV-HAWK-01) |
| uav_assets | UAV-HAWK-01 (active), UAV-HAWK-02 (maintenance), UAV-RAVEN-01 (active) |
| missions | 00000000-0000-0000-0000-000000000002 surveillance, active |
| alerts | 7 alerts: 2 critical, 3 warning, 2 info |

> IMPORTANT: Mission UUID 00000000-0000-0000-0000-000000000002 matches DEFAULT_MISSION_ID hardcoded in edge/telemetry_publisher/simulate.py. This is intentional so simulator telemetry satisfies the FK constraint.

---

## 8. Execution and Startup Sequence

### Production cold-start

```
docker compose up -d
|
|-> db starts -> healthcheck: pg_isready
|-> redis starts -> healthcheck: redis-cli ping
|-> mqtt starts
|
|-> backend starts (after db + redis healthy)
|     |-> entrypoint.sh:
|           1. alembic upgrade head  (apply DB migrations)
|           2. uvicorn app.main:app  (start FastAPI)
|                |-> lifespan startup:
|                      ingestion_service.start()
|                        (connect to MQTT, subscribe to telemetry/#)
|
|-> frontend starts
|     |-> nginx serves pre-built Vite SPA
|
|-> caddy starts
      |-> obtain Lets Encrypt cert for $DOMAIN
            /api/*   -> backend:8000
            /healthz -> backend:8000
            *        -> frontend:80
```

### Simulator on-demand lifecycle

```
1. User clicks START on Dashboard
2. POST /api/v1/simulator/{engine_id}/start
3. SimulatorManager._docker_start():
   - Check if container "aerotwin-simulator" exists
   - If exited: docker container start
   - If not found: docker run aerotwin-simulator:latest
     ENV: ENGINE_ID={engine_id}, MQTT_HOST=mqtt
     NETWORK: aerotwin-prod_default
   - Returns: {"engine_id": "...", "status": "running"}
4. Simulator publishes JSON to MQTT topic: telemetry/{engine_id} (1 Hz)
5. Backend ingestion_service:
   - Receives MQTT message
   - Writes TelemetryReading to TimescaleDB
   - Triggers ML inference (RUL, fault, bearing, aux)
   - Broadcasts via WebSocket to connected frontend clients
6. Frontend updates live charts and KPIs in real-time
```

### MQTT Telemetry Payload Schema

```json
{
  "engine_id": "11244686-4ac4-415a-bf0a-01dae03e339c",
  "mission_id": "00000000-0000-0000-0000-000000000002",
  "ts": "2026-10-03T12:30:00Z",
  "n1_rpm": 12450.0,
  "n2_rpm": 15200.0,
  "egt_c": 645.2,
  "fuel_flow_kgh": 142.8,
  "oil_pressure_bar": 4.1,
  "oil_temp_c": 88.5,
  "vibration_g": 0.12,
  "altitude_ft": 8500.0,
  "mach": 0.45,
  "ambient_temp_c": 12.0
}
```

---

## 9. Simulator On-Demand Telemetry

The simulator (edge/telemetry_publisher/simulate.py) implements a physics-based turbofan engine model:

| Feature | Detail |
|---------|--------|
| Degradation model | Linear wear accumulation with configurable rate |
| Sensor noise | Per-sensor Gaussian noise (realistic SNR) |
| Fault injection | Bearing wear, oil pressure drops, EGT spikes |
| Publication rate | 1 Hz (1 reading per second) |
| Default mission | 00000000-0000-0000-0000-000000000002 |
| MQTT topic | telemetry/{engine_id} |

Backend uses Docker Python SDK v7.2. Docker socket /var/run/docker.sock is bind-mounted read-only into the backend container.

**Simulator environment variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| MQTT_HOST | mqtt | MQTT broker hostname |
| ENGINE_ID | required | Engine UUID to publish telemetry for |
| MISSION_ID | 00000000-0000-0000-0000-000000000002 | Mission UUID |
| AMBIENT_TEMP | 15.0 | Ambient temperature Celsius |

---

## 10. ML Pipeline

### Models

| Model | Algorithm | Input | Output |
|-------|-----------|-------|--------|
| RUL | LSTM / XGBoost | Sequential telemetry (N1, N2, EGT, fuel flow) | Remaining cycles |
| Fault Detection | LightGBM binary | Windowed sensor statistics | Fault probability 0-1 |
| Auxiliary | LightGBM | Oil, vibration, altitude features | Failure risk 0-1 |
| Bearing Health | CNN on vibration FFT | Vibration signature | Health index 0-1 |

### Inference pipeline

```
MQTT telemetry received
|-> TelemetryReading written to TimescaleDB
|-> rul_service.py      -> rul_predictions row
|-> fault_service.py    -> fault_predictions row
|-> aux_service.py      -> aux_predictions row
+-> bearing_service.py  -> bearing_health_readings row
```

> Note: ML model binary files are excluded from the Docker image. Telemetry flows correctly but ML predictions return errors until model files are uploaded and volume-mounted on the VM.

### Model Export for Edge Inference

The models trained in scikit-learn/XGBoost are exported to ONNX (or JSON/joblib formats) to be run at the edge (e.g., in the simulator or UAV gateway) without heavy dependencies.
Run the export script from the repo root to convert and place the exported models in `ml/models`:
```bash
python ml/export_onnx.py
```
This script exports the RUL models and Scalers to JSON/joblib, which are re-applied with numpy in `edge/inference/rul_runner.py`.

---

## 11. Documentation and Research

Detailed architecture decisions, model pipelines, and project reports are available in `docs/files/`. Key documents include:
- **Project Documentation**: `AeroTwin_Project_Document.md`, `AeroTwin_Implementation_Document.md`
- **ML Model Integrations**: `AeroTwin_ML_Model_Spec_and_Frontend_Integration.md`, `RUL_Model_Integration_Documentation.md`
- **Pipelines**: `RUL_Pipeline_Flow.md`, `Fault_Model_Pipeline_Flow.md`, `Bearing_Model_Pipeline_Flow.md`, `Aux_Model_Pipeline_Flow.md`
- **Dataset Collection**: `Dataset_Model_Collection_Guide.md`

Please refer to these documents for deep technical dives into the RUL, bearing, and auxiliary model architectures.

---

## 12. CI/CD Pipeline

Trigger: `gcloud builds submit . --config=cloudbuild.yaml --project=aerotwin-510405`

```
Step 1: Build backend
        docker build -f infra/docker/Dockerfile.backend
        -> us-central1-docker.pkg.dev/aerotwin-510405/aerotwin/aerotwin-backend:latest
        Timeout: 30 minutes

Step 2: Build frontend
        docker build -f infra/docker/Dockerfile.frontend
        --build-arg VITE_API_URL=/api/v1
        --build-arg VITE_WS_URL=/api/v1
        -> us-central1-docker.pkg.dev/aerotwin-510405/aerotwin/aerotwin-frontend:latest
        Timeout: 10 minutes

Step 3: Build simulator
        docker build -f infra/docker/Dockerfile.simulator
        -> us-central1-docker.pkg.dev/aerotwin-510405/aerotwin/aerotwin-simulator:latest
        Timeout: 10 minutes
```

Build machine: E2_HIGHCPU_8 (8 vCPU, 8 GB RAM), ~6-7 minutes total

Note: VITE_API_URL is baked into the frontend bundle at build time via .env.production. This file takes precedence over Docker build-arg per Vites env loading order.

---

## 13. Infrastructure and Deployment

### GCP Resources

| Resource | Details |
|----------|---------|
| Compute Engine | aerotwin-prod, e2-micro, us-central1-a |
| OS | Ubuntu 22.04 LTS |
| Memory | 1 GB RAM + 2 GB /swapfile (OOM mitigation) |
| Artifact Registry | us-central1-docker.pkg.dev/aerotwin-510405/aerotwin/ |
| SSH access | Identity-Aware Proxy (IAP) tunnel, port 22 not public |
| Firewall | HTTP :80 and HTTPS :443 open; all other ports closed |

### DNS

| Domain | Provider | Target |
|--------|----------|--------|
| aerotwin-clutchx.duckdns.org | DuckDNS | 35.224.45.138 (VM external IP) |

### Production file layout on VM

```
/opt/aerotwin/
+-- infra/
    +-- docker/
        |-- docker-compose.vm.yml
        |-- .env.prod                (secrets, never in git)
        |-- Caddyfile
        |-- mosquitto.prod.conf
        +-- mosquitto.passwd
```

### Caddy routing

```
{$DOMAIN} {
    encode gzip
    handle /api/*   { reverse_proxy backend:8000 }
    handle /healthz { reverse_proxy backend:8000 }
    handle          { reverse_proxy frontend:80  }
    header {
        Strict-Transport-Security "max-age=31536000"
        X-Content-Type-Options "nosniff"
        Referrer-Policy "strict-origin-when-cross-origin"
    }
}
```

---

## 14. Environment Variables

### .env.prod (Production secrets)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| DOMAIN | Yes | - | Public domain |
| ACME_EMAIL | Yes | - | Lets Encrypt contact email |
| JWT_SECRET | Yes | - | JWT signing key (min 32 chars) |
| EDGE_API_KEY | Yes | - | API key for edge telemetry ingest (min 16 chars) |
| POSTGRES_PASSWORD | Yes | - | Database password |
| POSTGRES_USER | No | aerotwin | Database username |
| POSTGRES_DB | No | aerotwin | Database name |
| REGISTRY | Yes | - | Artifact Registry base path |
| IMAGE_TAG | No | latest | Docker image tag |
| LLM_PROVIDER | No | gemini | AI provider: gemini or groq |
| GEMINI_API_KEY | No | - | Google Gemini API key |
| GROQ_API_KEY | No | - | Groq API key |
| BACKEND_MEM_LIMIT | No | 750m | Docker memory limit for backend |

### Backend runtime (set by docker-compose.vm.yml)

| Variable | Value | Description |
|----------|-------|-------------|
| SIMULATOR_USE_DOCKER | true | Use Docker SDK for simulator control |
| SIMULATOR_CONTAINER_NAME | aerotwin-simulator | Simulator container name |
| SIMULATOR_IMAGE | ${REGISTRY}/aerotwin-simulator:latest | Simulator image |
| DOCKER_NETWORK | aerotwin-prod_default | Docker network for simulator |
| MQTT_BROKER_URL | mqtt://mqtt:1883 | MQTT broker address |

### Frontend build-time (.env.production)

| Variable | Value | Description |
|----------|-------|-------------|
| VITE_API_URL | /api/v1 | Relative API base, proxied by Caddy |
| VITE_WS_URL | /api/v1 | WebSocket base path |

---

## 15. Local Development

### Prerequisites

- Docker Desktop
- Node.js 20+
- Python 3.11+
- gcloud CLI (for production deployment)

### Quick start

```bash
# 1. Clone
git clone https://github.com/your-org/AeroTwin.git
cd AeroTwin

# 2. Configure environment
cp infra/docker/.env.prod.example infra/docker/.env.prod
# Edit .env.prod: set JWT_SECRET, EDGE_API_KEY, POSTGRES_PASSWORD

# 3. Start full local stack
docker compose -f infra/docker/docker-compose.yml up -d

# 4. Run DB migrations
docker compose exec backend alembic upgrade head

# 5. Create admin user
docker compose exec -e AEROTWIN_USER_PASSWORD="Admin123456!!" backend \
  python create_user.py admin@local.dev admin

# 6. Frontend dev server (hot reload)
cd frontend && npm install && npm run dev
```

**Local URLs:**
- Frontend (hot reload): http://localhost:5173
- Backend API + Swagger: http://localhost:8000/api/v1/docs
- Database: localhost:5432

### Seed test data (required for simulator)

```bash
docker compose exec db psql -U aerotwin -d aerotwin -c "
INSERT INTO uav_assets (id, tail_number, status) VALUES
  ('a1000000-0000-0000-0000-000000000001', 'UAV-HAWK-01', 'active');

INSERT INTO engines (id, serial_number, status, uav_asset_id) VALUES
  (gen_random_uuid(), 'ENG-ALPHA-001', 'operational',
   'a1000000-0000-0000-0000-000000000001');

INSERT INTO missions (id, uav_asset_id, mission_type, start_time, status) VALUES
  ('00000000-0000-0000-0000-000000000002',
   'a1000000-0000-0000-0000-000000000001',
   'surveillance', NOW(), 'active');
"
```

---

## 16. Production Operations

### Create or update a user

```bash
gcloud compute ssh aerotwin-prod --zone=us-central1-a --tunnel-through-iap --command="
  sudo docker exec \
    -e AEROTWIN_USER_PASSWORD='SecurePassword123!!' \
    aerotwin-prod-backend-1 \
    python create_user.py user@company.com maintenance_engineer
"
```

Roles: `operator | maintenance_engineer | program_manager | admin`

### View live logs

```bash
gcloud compute ssh aerotwin-prod --tunnel-through-iap --command="
  sudo docker logs -f aerotwin-prod-backend-1"
```

### Database access

```bash
gcloud compute ssh aerotwin-prod --tunnel-through-iap --command="
  sudo docker exec -it aerotwin-prod-db-1 psql -U aerotwin -d aerotwin"
```

### Restart a single service

```bash
gcloud compute ssh aerotwin-prod --tunnel-through-iap --command="
  cd /opt/aerotwin/infra/docker
  sudo docker compose --env-file .env.prod -f docker-compose.vm.yml \
    up -d --no-deps --force-recreate backend"
```

### Full redeploy

```bash
# 1. Build + push all images (about 7 minutes)
gcloud builds submit . --config=cloudbuild.yaml --project=aerotwin-510405

# 2. SCP updated config if changed
gcloud compute scp infra/docker/docker-compose.vm.yml \
  aerotwin-prod:/tmp/docker-compose.vm.yml \
  --zone=us-central1-a --tunnel-through-iap

# 3. Pull and restart on VM
gcloud compute ssh aerotwin-prod --zone=us-central1-a --tunnel-through-iap --command="
  REGISTRY=us-central1-docker.pkg.dev/aerotwin-510405/aerotwin
  cd /opt/aerotwin/infra/docker
  sudo cp /tmp/docker-compose.vm.yml .
  sudo docker pull \$REGISTRY/aerotwin-backend:latest
  sudo docker pull \$REGISTRY/aerotwin-frontend:latest
  sudo docker pull \$REGISTRY/aerotwin-simulator:latest
  sudo REGISTRY=\$REGISTRY docker compose --env-file .env.prod \
    -f docker-compose.vm.yml up -d --force-recreate"
```

---

## 17. User Roles and Permissions

| Role | Self-Register | Read Data | Start Simulator | Manage Engines | Admin |
|------|:---:|:---:|:---:|:---:|:---:|
| maintenance_engineer | Yes (default) | Yes | Yes | No | No |
| operator | Yes | Yes | Yes | No | No |
| program_manager | Yes | Yes | Yes | Yes | No |
| admin | CLI only | Yes | Yes | Yes | Yes |

**Production admin:**
- Email: admin@aerotwin.local
- Created via create_user.py (cannot self-register)

---

## 18. Security

| Concern | Implementation |
|---------|---------------|
| Authentication | JWT HS256: access token 8 days + refresh token 22 days |
| Password hashing | bcrypt |
| Transport security | HTTPS enforced by Caddy; HSTS max-age=31536000 |
| CORS | Production: exact frontend origin only, no wildcard |
| Rate limiting | slowapi: copilot 10 req/min; auth endpoints limited |
| Role enforcement | Depends(require_role([...])) on all protected routes |
| Secret management | .env.prod gitignored, passed via Docker env, never in image layers |
| Docker socket | Mounted read-only (:ro) into backend container |
| SSH access | IAP tunnel only, TCP port 22 not open to internet |
| Security headers | X-Content-Type-Options nosniff, Referrer-Policy strict-origin-when-cross-origin |

---

## 19. Known Limitations and Roadmap

### Current Limitations

- ML model binaries excluded from Docker image: RUL/Fault/Aux predictions fail gracefully while telemetry still flows. Fix: upload ml/training/*/saved_models/ to VM and mount as Docker volume.
- e2-micro VM is memory-constrained: running all containers plus active simulator uses about 1.8 GB of the 3 GB available (RAM + swap).
- Single engine in production seed: multi-engine requires one simulator container per engine (SimulatorManager shares one container name).
- MQTT has no authentication in current production setup.
- No auto-deploy: after Cloud Build succeeds, VM pull/restart must be triggered manually.

### Roadmap

- [ ] Mount trained ML model files on VM for full RUL/Fault/Aux inference
- [ ] WebSocket auto-reconnect with exponential back-off
- [ ] Cloud Build to Pub/Sub to VM auto-deploy trigger on build success
- [ ] Multi-engine simulator: parameterized container names per engine UUID
- [ ] MQTT TLS + username/password authentication in production
- [ ] Prometheus metrics endpoint + Grafana dashboard
- [ ] Automated daily PostgreSQL backups to GCS bucket
- [ ] Staging environment with separate GCP project

---

## License

MIT - see LICENSE

---

Built with love by the AeroTwin team.
