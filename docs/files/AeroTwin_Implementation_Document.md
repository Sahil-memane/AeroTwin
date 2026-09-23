# AeroTwin — Complete Implementation Document

**AI-Enabled Real-Time Digital Twin for Aero-Piston Engines in MALE UAVs**
Smart India Hackathon 2026 · Problem Statement ID **26054** · Organization: DRDO — Department of Defence R&D · Theme: Robotics and Drones
Team: **Antigravity** · Team Size: **Solo Developer**
Companion documents: *AeroTwin — Complete Project Implementation Document*, *AeroTwin — ML Model Specification & Frontend Integration Guide*, *Dataset & Model Collection Guide*

> This document is the single execution plan: it takes everything already specified in the three companion documents (system architecture, database schema, API design, the 4 trained models, repository structure) and turns it into an ordered, checklist-driven build sequence a solo developer can run without further planning. Nothing here should require re-deciding something the companion documents already decided — where a companion doc left something open, this document resolves it explicitly (see Section 5).

---

## Table of Contents

1. [Team Responsibilities](#1-team-responsibilities)
2. [Repository Setup and Structure](#2-repository-setup-and-structure)
3. [Environment & Tooling Setup](#3-environment--tooling-setup)
4. [Data & Model Pipeline Prerequisites](#4-data--model-pipeline-prerequisites)
5. [System Design Lock (Decisions Log)](#5-system-design-lock-decisions-log)
6. [Detailed Development Roadmap](#6-detailed-development-roadmap)
7. [Testing Strategy](#7-testing-strategy)
8. [CI/CD & Deployment Runbook](#8-cicd--deployment-runbook)
9. [Timeline & Milestones](#9-timeline--milestones)
10. [Risk Register](#10-risk-register)
11. [Definition of Done & Submission Checklist](#11-definition-of-done--submission-checklist)
12. [Appendix](#12-appendix)
    - [12.1 Environment Variable Reference](#121-environment-variable-reference)
    - [12.2 Useful Commands](#122-useful-commands)
    - [12.3 Related Documents](#123-related-documents)
    - [12.4 Full API Endpoint Reference](#124-full-api-endpoint-reference)
    - [12.5 Database Schema Quick Reference](#125-database-schema-quick-reference)

---

## 1. Team Responsibilities

AeroTwin is built by a single developer wearing multiple functional hats. Splitting the work into explicit "roles" — even for one person — matters because it sets a fixed order of concerns (you cannot debug the frontend with a role hat that hasn't finished the API it calls) and gives every roadmap phase in Section 6 an unambiguous owner.

| Developer | Role (hat) | Responsibilities |
|---|---|---|
| Sahil | **Project Lead / Architect** | Owns Sections 2–5 of this document; locks the API contract and DB schema before coding starts; makes and records every architecture decision in the Decisions Log (Section 5); owns scope control against the hackathon deadline. |
| Sahil | **Backend Engineer** | FastAPI application: auth, CRUD endpoints, telemetry ingestion service, health fusion service, alert engine, WebSocket broadcaster; owns `backend/` end to end. |
| Sahil | **ML / Data Engineer** | Dataset acquisition and preprocessing for all 4 models (ALFA, C-MAPSS, CWRU, AI4I 2020), model training, evaluation, ONNX export, model registry entries; owns `ml/`. |
| Sahil | **Frontend Engineer** | React + TypeScript dashboard: auth flow, engine/fleet views, model-specific components (fault banner, RUL trend, bearing gauge, health gauge), live WebSocket updates; owns `frontend/`. |
| Sahil | **DevOps / Infra Engineer** | Docker Compose for local dev, GitHub Actions CI/CD, free-tier cloud deployment (Section 8), edge packaging (`edge/`), secrets management. |
| Sahil | **QA / Release Engineer** | Test strategy execution (Section 7), load testing, security pass, go/no-go call before each deployment. |

### 1.1 Solo-Developer Operating Model

- [ ] Work in **one hat per work block** (half-day minimum) — context-switching between backend, ML, and frontend inside the same block is the single biggest cause of slipped hackathon timelines.
- [ ] Every roadmap block in Section 6 states its owning hat — use that as the day's hat, not whatever feels urgent.
- [ ] End each work block with a commit and a one-line entry in `docs/devlog.md` (what shipped, what's blocked) — this doubles as demo-day and submission-doc material later (Section 11).
- [ ] If a task needs two hats at once (e.g. "wire the frontend to the new endpoint"), do the backend half, commit, switch hats explicitly, then do the frontend half — don't blend them in one commit.

---

## 2. Repository Setup and Structure

### 2.1 Repository Creation

- [ ] Create the repository on GitHub: name `aerotwin`, **public** visibility (SIH judging requires visible source), description: *"AI-enabled real-time digital twin for aero-piston engines in MALE UAVs — SIH26054"*.
- [ ] Initialize with: `README.md`, `.gitignore` (combine the **Node** and **Python** GitHub templates — the repo has both a `frontend/` and a `backend/`/`ml/`), and an **MIT** or **Apache-2.0** `LICENSE` (MIT is the simpler default for a hackathon submission unless DRDO guidance says otherwise — flag this as an open item if unclear).
- [ ] Set the default branch to `main`.
- [ ] Add repository **topics**: `digital-twin`, `predictive-maintenance`, `uav`, `fastapi`, `react`, `machine-learning`, `sih2026` (improves discoverability for judges browsing GitHub).
- [ ] Clone locally and scaffold the full directory tree in one commit before any feature code (this matches the Repository Structure section of the main Project Implementation Document exactly):

```text
aerotwin/
├── frontend/                          # React + TypeScript operator/maintenance dashboard
│   ├── src/
│   │   ├── components/                # FaultAlertBanner.tsx, RulTrendChart.tsx, BearingHealthGauge.tsx, HealthScoreGauge.tsx, ...
│   │   ├── pages/                     # Dashboard, Missions, Alerts, Fleet, Login route-level views
│   │   ├── hooks/                     # useTelemetryStream (WebSocket), useAuth, useApi
│   │   ├── services/                  # apiClient.ts — typed REST client for the backend
│   │   ├── store/                     # Zustand store: live engine state, auth session
│   │   ├── types/                     # Shared TypeScript interfaces (mirrors backend schemas)
│   │   └── App.tsx                    # Route definitions and top-level layout
│   ├── public/                        # Static assets, favicon, manifest
│   ├── tests/                         # Jest + React Testing Library specs
│   ├── .env.example                   # VITE_API_URL, VITE_WS_URL placeholders
│   └── package.json
│
├── backend/                           # FastAPI application (REST + WebSocket)
│   ├── app/
│   │   ├── api/                       # Versioned routers: auth, telemetry, faults, rul, missions...
│   │   │   └── v1/
│   │   │       ├── auth.py            # /auth/login, /auth/refresh
│   │   │       ├── telemetry.py       # /telemetry/ingest, /engines/{id}/telemetry(/latest)
│   │   │       ├── engines.py         # engines CRUD, /engines/{id}/health-score
│   │   │       ├── uav_assets.py      # uav_assets CRUD
│   │   │       ├── users.py           # users CRUD
│   │   │       ├── faults.py          # /engines/{id}/faults/latest
│   │   │       ├── rul.py             # /engines/{id}/rul
│   │   │       ├── bearing.py         # /engines/{id}/bearing-health
│   │   │       ├── dashboard.py       # /dashboard/summary
│   │   │       ├── missions.py        # /missions, /missions/{id}
│   │   │       ├── simulation.py      # /simulation/run, /simulation/{id}
│   │   │       ├── alerts.py          # /alerts, /alerts/{id}/acknowledge
│   │   │       ├── maintenance.py     # /engines/{id}/maintenance-logs
│   │   │       └── models.py          # /models (model_registry read)
│   │   ├── core/                      # config.py (env settings), security.py (JWT), logging.py
│   │   ├── models/                    # SQLAlchemy ORM models — one file per entity (Section 7): user.py, uav_asset.py, engine.py, mission.py, telemetry_reading.py, fault_prediction.py, rul_prediction.py, bearing_health_reading.py, aux_prediction.py, maintenance_log.py, alert.py, model_registry.py
│   │   ├── schemas/                   # Pydantic request/response schemas (mirrors models/, one file per entity)
│   │   ├── services/                  # Business logic: ingestion.py, health_fusion.py, alert_engine.py
│   │   ├── ws/                        # connection_manager.py, telemetry_broadcaster.py — WebSocket connection manager, live telemetry broadcaster
│   │   ├── db/                        # session.py, base.py, Alembic migration environment
│   │   └── main.py                    # FastAPI app instance, router + middleware registration
│   ├── tests/                         # pytest suite (unit + integration, uses a test DB container)
│   │   ├── unit/
│   │   └── integration/
│   ├── alembic/                       # Auto-generated migration scripts
│   │   └── versions/
│   ├── .env.example                   # DATABASE_URL, MQTT_BROKER_URL, JWT_SECRET placeholders
│   └── requirements.txt
│
├── ml/                                # Model training, evaluation, and export
│   ├── data/                          # raw/ and processed/ — gitignored, tracked via DVC pointers
│   ├── notebooks/                     # EDA and experiment notebooks (one per model)
│   ├── training/
│   │   ├── fault_model/               # ALFA-based 7-class fault classifier: preprocess.py, train.py, export_onnx.py
│   │   ├── rul_model/                 # C-MAPSS-based LSTM/XGBoost RUL regressor: preprocess.py, train.py, export_onnx.py
│   │   ├── bearing_model/             # CWRU-based FFT + classifier: fft_features.py, train.py, export_onnx.py
│   │   ├── aux_model/                 # AI4I 2020 + engine-failure transfer-learning: pretrain.py, finetune.py, export_onnx.py
│   │   └── physics_model/             # Thermodynamic solver + calibration against spec sheets: otto_cycle_solver.py
│   ├── models/                        # Exported .onnx artifacts + model_card.md per model
│   │   ├── fault_model/
│   │   ├── rul_model/
│   │   ├── bearing_model/
│   │   └── aux_model/
│   ├── evaluation/                    # Held-out test metrics, confusion matrices, RUL error plots
│   └── requirements.txt
│
├── simulation/                        # Mission simulation & replay engine
│   ├── mission_profiles/              # Sample/reference profiles (altitude, temp, throttle)
│   ├── replay_engine/                 # Reconstructs a historical mission from stored telemetry
│   └── scenario_generator/            # Builds synthetic what-if profiles for pre-mission testing
│
├── edge/                              # Onboard / GCS edge-deployment code
│   ├── can_interface/                 # python-can / SocketCAN listener → MQTT publisher
│   ├── inference/                     # ONNX Runtime inference for Fault + RUL at the edge
│   └── telemetry_publisher/           # simulate.py (Phase 2 telemetry simulator) + buffering/republish-on-reconnect logic
│
├── infra/                             # Infrastructure as configuration
│   ├── docker/                        # Dockerfiles for frontend, backend, ml-inference
│   │   ├── Dockerfile.backend
│   │   ├── Dockerfile.frontend
│   │   ├── Dockerfile.ml-inference
│   │   └── docker-compose.yml         # Local dev stack: backend, db, mqtt, redis, frontend
│   └── nginx/                         # Reverse proxy config for production
│
├── docs/
│   ├── architecture/                  # Architecture diagram source + exported images
│   ├── api/                           # openapi.yaml export / Postman collection
│   ├── dataset-guide/                 # Dataset & Model Collection Guide (dataset provenance, licensing, open items)
│   ├── decisions-log.md               # D1–D3 resolutions (Section 5)
│   └── devlog.md                      # One-line-per-work-block dev log (Section 1.1)
│
├── .github/
│   ├── workflows/                     # ci.yml (lint+test), deploy.yml (build+deploy on push to main)
│   ├── ISSUE_TEMPLATE/                # bug_report.md, feature_request.md
│   └── pull_request_template.md
│
├── .env.example                       # Root-level shared environment variable reference
├── README.md                          # Setup, run, and contribution instructions
└── LICENSE
```

> Note: `ml/data/` is intentionally gitignored — raw and processed datasets are tracked by pointer (DVC or a documented download script in `docs/dataset-guide/`) rather than committed, to keep the repository small and reproducible.

- [ ] Commit message for the scaffold: `chore: initial repository structure`.

### 2.2 GitHub Settings

- [ ] **Branch protection on `main`:**
  - [ ] Require a pull request before merging (even solo — this forces the CI gate below to run before code lands on `main`).
  - [ ] Require status checks to pass: `ci / lint`, `ci / test-backend`, `ci / test-frontend` (defined in Section 8).
  - [ ] Require branches to be up to date before merging.
  - [ ] Do **not** require a second reviewer (solo team) — but do require the check above.
- [ ] **Branching model:** trunk-based for a solo dev — short-lived feature branches (`feat/telemetry-ingestion`, `fix/jwt-refresh`) merged to `main` via PR, deleted after merge. No long-lived `develop` branch; it adds merge overhead with no second developer to justify it.
- [ ] **Labels:** create `area:backend`, `area:frontend`, `area:ml`, `area:infra`, `area:docs`, `priority:p0`…`p2`, `type:bug`, `type:feature`, `blocked`.
- [ ] **GitHub Projects:** create one Project board (Kanban) with columns `Backlog → In Progress → In Review → Done`; import Section 6's roadmap blocks as issues/cards up front so the board *is* the roadmap in executable form.
- [ ] **Issue templates:** `bug_report.md`, `feature_request.md` under `.github/ISSUE_TEMPLATE/`.
- [ ] **PR template:** `.github/pull_request_template.md` with a checklist: tests added, docs updated, migration included if schema changed, linked issue.
- [ ] **Secrets** (Settings → Secrets and variables → Actions) — create placeholders now, populate values in Phase 9 (Section 6):
  - [ ] `DATABASE_URL`, `JWT_SECRET`, `MQTT_BROKER_URL`, `REDIS_URL`
  - [ ] `RENDER_DEPLOY_HOOK` (or `RAILWAY_TOKEN`), `VERCEL_TOKEN` (or `NETLIFY_AUTH_TOKEN`)
  - [ ] `CLOUDFLARE_R2_ACCESS_KEY`, `CLOUDFLARE_R2_SECRET_KEY`
- [ ] **Dependabot:** enable version updates for `npm` (frontend) and `pip` (backend/ml) — weekly cadence, low overhead for a solo repo.
- [ ] **Security:** enable secret scanning and push protection (Settings → Code security).
- [ ] Leave **Discussions** and **Wiki** off — `docs/` in-repo is the single source of truth; two places to document is a solo-team anti-pattern.

---

## 3. Environment & Tooling Setup

### 3.1 Prerequisites Checklist

- [ ] Node.js 20 LTS + npm 10+ (`node -v`, `npm -v`)
- [ ] Python 3.11 + `venv`
- [ ] Docker Desktop (or Docker Engine + Compose v2 on Linux) — `docker compose version`
- [ ] Git, configured with the GitHub account used in Section 2
- [ ] VS Code (recommended extensions: ESLint, Prettier, Python, Ruff, Docker, Mermaid Preview)
- [ ] A CWRU Bearing Data Center account — **registration takes time to approve; start this today**, not when Phase 3 (Section 6) reaches the Bearing model.
- [ ] Kaggle account + API token (`kaggle.json`) for the C-MAPSS mirror, AI4I 2020, and the Aux model's still-unconfirmed second dataset.

### 3.2 Local Dev Bootstrap

- [ ] `backend/`: `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
- [ ] `frontend/`: `npm install`
- [ ] `ml/`: separate venv, `pip install -r ml/requirements.txt` (keep ML deps out of the API's `requirements.txt` — the backend container should not ship PyTorch/training-only packages).
- [ ] Copy every `.env.example` to `.env` at the root, `backend/`, and `frontend/`; fill local values (a throwaway `JWT_SECRET` is fine locally).
- [ ] `infra/docker/docker-compose.yml` — bring up backend, Postgres+TimescaleDB, Mosquitto, Redis, frontend together:
  ```bash
  docker compose -f infra/docker/docker-compose.yml up -d
  ```
- [ ] Verify: `curl localhost:8000/healthz` returns `200`, frontend loads at `localhost:5173`, `docker compose ps` shows all 5 services `healthy`.

### 3.3 Linting, Formatting, Pre-commit

- [ ] Backend: `ruff` for lint + format (`ruff check .`, `ruff format .`).
- [ ] Frontend: ESLint + Prettier (already implied by the tech stack's `eslint`/`prettier` in CI — Section 8).
- [ ] Install `pre-commit` and add hooks: `ruff`, `ruff-format`, `eslint --fix`, `prettier --write`, and a check that blocks committing `.env` files.
- [ ] `git commit` should fail locally on a lint error — catching it before CI saves a round trip on a solo repo where every CI run is also read by nobody but you.

---

## 4. Data & Model Pipeline Prerequisites

This section exists so Phase 3 of the roadmap (Section 6) can start immediately on data that's already in hand rather than losing days to dataset sourcing mid-sprint. Do these **before** Phase 3, ideally in parallel with Phases 0–2.

| Dataset | For model | Action needed now | Blocking? |
|---|---|---|---|
| ALFA (CMU AirLab) | Fault | Download via `theairlab.org/alfa-dataset`; write the ROS bag → CSV conversion script into `ml/training/fault_model/` | No — open mirror |
| NASA C-MAPSS | RUL | Pull via Kaggle mirror `behrad3d/nasa-cmaps` using the Kaggle API token from Section 3.1 | No — open mirror |
| CWRU bearing data | Bearing | **Register on the CWRU portal today** (Section 3.1) — this is the one dataset without an open mirror | **Yes** — start immediately |
| AI4I 2020 (milling) | Aux | Pull via Kaggle `shivamb/machine-predictive-maintenance-classification` | No — open mirror |
| "Engine failure dataset" | Aux | **Unconfirmed source** — per the Dataset & Model Collection Guide, re-verify and find the exact Kaggle/UCI link before Phase 3 Block 3.5 | **Yes** — resolve before training the Aux model's second stage |
| Engine performance maps / thermodynamic constants | Physics model | Source manufacturer spec sheets or FAA Type Certificate Data Sheets for a comparable piston engine as a proxy | Yes — needed before Phase 3 Block 3.1 |
| Mission/environmental profiles | Simulation engine | Confirm scenario diversity (hot weather, high altitude, rapid throttle) against NASA DASHlink flight-profile data | No — needed by Phase 6, not blocking earlier phases |

- [ ] `ml/data/` stays gitignored; track dataset provenance by pointer in `docs/dataset-guide/` (a documented download script per dataset), not by committing raw data.
- [ ] Set up **MLflow** (self-hosted, via `docker-compose`) before the first training run in Phase 3 — retrofitting experiment tracking after a few models are already trained means losing early-run history.

---

## 5. System Design Lock (Decisions Log)

The companion documents left two items explicitly open. Both must be resolved **before** the roadmap phases that depend on them (flagged below) — resolving them mid-phase means rework in the DB schema, the API contract, and the frontend types simultaneously.

| # | Decision | Options | Resolution deadline |
|---|---|---|---|
| D1 | **Fault model taxonomy.** ALFA's real labels are UAV flight-control faults (No failure / RC / GPS / Aileron / Elevator / Rudder / Engine failure), not the piston-engine-specific classes named in the main Project Implementation Document. | **(A)** Source/relabel data for the engine-specific taxonomy. **(B)** Keep ALFA's actual 7 classes and reframe the Fault model's scope as UAV-system fault detection. | Before Phase 1 Block 1.1 (DB `CHECK` constraint on `fault_predictions.fault_class`) and Phase 3 Block 3.2 |
| D2 | **Schema gaps.** No `aux_predictions` table exists yet; `bearing_health_readings` has no `model_version_id`. | Add `aux_predictions (engine_id, model_version_id, ts, aux_score)`; add `model_version_id` FK to `bearing_health_readings`. | Before Phase 1 Block 1.1 (first migration) |
| D3 | **License for public repo.** | MIT vs. Apache-2.0 vs. a DRDO-specified license. | Before Section 2.1 commit |

- [ ] Record the chosen option for D1–D3 directly in `docs/decisions-log.md` with a one-line rationale — this file is what Section 6 phases reference as "the decision," so it must exist before Phase 1 starts.
- [ ] Once D1 is chosen, update the Fault model's `faultClass` TypeScript union (frontend), the `fault_predictions.fault_class` CHECK constraint (backend), and the model's training label set (ML) **in the same PR** — these three must never drift apart again.

---

## 6. Detailed Development Roadmap

### 6.1 Roadmap at a Glance

```mermaid
flowchart LR
    P0[Phase 0\nKickoff & Design Lock] --> P1[Phase 1\nBackend & DB Foundation]
    P1 --> P2[Phase 2\nIngestion & Twin Core]
    P1 --> P5[Phase 5\nFrontend Dashboard]
    P2 --> P3[Phase 3\nML Model Development]
    P3 --> P4[Phase 4\nHealth Fusion & Alerts]
    P3 --> P7[Phase 7\nEdge Packaging]
    P4 --> P6[Phase 6\nSimulation Engine]
    P5 --> P8
    P6 --> P8[Phase 8\nIntegration Testing]
    P7 --> P8
    P8 --> P9[Phase 9\nDeployment]
    P9 --> P10[Phase 10\nDemo Prep & Submission]
```

### 6.2 System Data Flow (for reference while building Phases 2–4)

```mermaid
sequenceDiagram
    participant Sensor as Engine / Telemetry Simulator
    participant Edge as Edge Gateway
    participant MQTT as MQTT Broker
    participant Ingest as Ingestion Service
    participant DB as TimescaleDB
    participant Infer as Inference Service
    participant Fusion as Health Fusion
    participant WS as WebSocket Broadcaster
    participant FE as Dashboard (React)

    Sensor->>Edge: CAN frame (RPM, CHT, EGT, ...)
    Edge->>MQTT: publish telemetry
    MQTT->>Ingest: telemetry message
    Ingest->>DB: INSERT telemetry_readings
    Ingest->>Infer: preprocessed feature window
    Infer->>DB: INSERT fault / rul / bearing / aux prediction
    Infer->>Fusion: model outputs
    Fusion->>DB: INSERT / UPDATE health score
    Fusion->>WS: push health_score + alert (if any)
    WS-->>FE: telemetry / fault_prediction / health_score events
    FE-->>FE: update store, re-render charts
```

### 6.3 Entity Model (for reference while building Phase 1)

```mermaid
erDiagram
    USERS ||--o{ ALERTS : acknowledges
    USERS ||--o{ MAINTENANCE_LOGS : logs
    UAV_ASSETS ||--o{ ENGINES : fitted_with
    UAV_ASSETS ||--o{ MISSIONS : flies
    ENGINES ||--o{ TELEMETRY_READINGS : generates
    ENGINES ||--o{ FAULT_PREDICTIONS : has
    ENGINES ||--o{ RUL_PREDICTIONS : has
    ENGINES ||--o{ BEARING_HEALTH_READINGS : has
    ENGINES ||--o{ AUX_PREDICTIONS : has
    ENGINES ||--o{ MAINTENANCE_LOGS : has
    ENGINES ||--o{ ALERTS : raises
    MISSIONS ||--o{ TELEMETRY_READINGS : recorded_during
    MODEL_REGISTRY ||--o{ FAULT_PREDICTIONS : produced
    MODEL_REGISTRY ||--o{ RUL_PREDICTIONS : produced
    MODEL_REGISTRY ||--o{ BEARING_HEALTH_READINGS : produced
    MODEL_REGISTRY ||--o{ AUX_PREDICTIONS : produced
```

---

### Phase 0 — Kickoff & Design Lock

**Owner:** Sahil (Project Lead / Architect hat) · **Duration:** 3 days

**Work to do:**
- [ ] Complete Sections 2–5 of this document (repo live, environment boots, decisions log D1–D3 recorded).
- [ ] Freeze the API contract: export the OpenAPI spec from the endpoint table in Section 12.4 (Full API Endpoint Reference) into `docs/api/openapi.yaml` — this is what Phase 5 (frontend) codes against even before Phase 1's endpoints exist, using a mock server.
- [ ] Stand up a mock API server (`prism mock docs/api/openapi.yaml` or similar) so frontend work in Phase 5 can start without waiting on the real backend.
- [ ] Create all Phase 1–10 blocks below as GitHub issues on the Project board (Section 2.2).

**Exit Criteria:**
- [ ] `docker compose up` boots an empty stack with all services healthy.
- [ ] CI pipeline (`ci.yml`) runs on a trivial PR and all three checks pass.
- [ ] `docs/decisions-log.md` has signed-off entries for D1, D2, D3.
- [ ] OpenAPI spec committed and mock server runs locally.

---

### Phase 1 — Backend & Database Foundation

**Owner:** Sahil (Backend Engineer hat) · **Duration:** 1 week

**Blocks:**

**1.1 Database schema & migrations**
- [ ] Write SQLAlchemy models for all tables from the main document's Section 7, **plus** the D2 additions (`aux_predictions`, `bearing_health_readings.model_version_id`).
- [ ] Apply the D1 decision to the `fault_predictions.fault_class` CHECK constraint.
- [ ] Enable the TimescaleDB extension; convert `telemetry_readings` to a hypertable partitioned on `ts`.
- [ ] Generate and apply the first Alembic migration; add the CI step that fails the build on a model/migration mismatch.

**1.2 Auth & RBAC**
- [ ] `POST /api/v1/auth/login`, `POST /api/v1/auth/refresh` — JWT access + refresh tokens, `passlib`/bcrypt password hashing.
- [ ] Role-based dependency (`operator`, `maintenance_engineer`, `program_manager`, `admin`) enforced per-endpoint via a FastAPI dependency.
- [ ] Rate-limit login to 5 attempts/min/IP.

**1.3 Core CRUD endpoints**
- [ ] `users`, `uav_assets`, `engines`, `missions` — full CRUD respecting the RBAC roles above.
- [ ] `GET /api/v1/dashboard/summary` returning an empty-but-correctly-shaped payload (no predictions exist yet — that's fine, this just proves the join logic).

**Exit Criteria:**
- [ ] `alembic upgrade head` runs clean from an empty database.
- [ ] `POST /auth/login` → `POST /auth/refresh` → authenticated `GET /engines` round-trips correctly in a Postman/httpx smoke test.
- [ ] `pytest` coverage on `backend/app/api/v1/` ≥ 70%.
- [ ] CI's `test-backend` check is green on `main`.

---

### Phase 2 — Telemetry Ingestion & Digital Twin Core

**Owner:** Sahil (Backend / Infra hat) · **Duration:** 1 week

> A real UAV isn't available during development, so a **telemetry simulator** is a required build item, not optional — without it, nothing downstream (ingestion, ML inference, dashboard) can be exercised or demoed end to end.

**Blocks:**

**2.1 Telemetry simulator** *(new component — not in the original architecture diagram, added here because it's a hard prerequisite for every later phase's testing)*
- [ ] `edge/telemetry_publisher/simulate.py`: generates physically plausible RPM/CHT/EGT/oil pressure/oil temp/fuel flow/vibration values from a configurable mission profile (altitude, ambient temp, throttle curve), publishes to MQTT at a configurable rate.
- [ ] Support injecting a synthetic fault (e.g. ramp CHT out of range) on command, so Phase 3's Fault model has a labeled scenario to validate against beyond the training set.

**2.2 Ingestion service**
- [ ] `paho-mqtt` subscriber in `backend/app/services/ingestion.py`: validates payload ranges, writes to `telemetry_readings`.
- [ ] Reject/queue-for-review payloads outside physically plausible sensor ranges (per the API design's validation rules).

**2.3 Live broadcast**
- [ ] `GET /api/v1/engines/{engine_id}/telemetry/latest` (REST snapshot).
- [ ] `/ws/engines/{engine_id}/live` WebSocket: JWT validated at handshake (query param), pushes `{ type: "telemetry", payload }` on each new reading.

**Exit Criteria:**
- [ ] Running the simulator produces rows in `telemetry_readings` within 2 seconds of publish.
- [ ] A `wscat` client connected to `/ws/engines/{id}/live` receives live telemetry events while the simulator runs.
- [ ] Disconnecting and reconnecting MQTT doesn't lose data (buffering verified per Section 6, Phase 7 will harden this further for the edge case).

---

### Phase 3 — ML Model Development

**Owner:** Sahil (ML / Data Engineer hat) · **Duration:** 4 weeks (the largest phase — budget accordingly)

**Blocks:**

**3.1 Physics model**
- [ ] Implement the Otto-cycle-based thermodynamic solver in `ml/training/physics_model/`, calibrated against the manufacturer/FAA spec sheet sourced in Section 4.
- [ ] Expose it as a pure function: `(operating_conditions) → expected_CHT_EGT_power`.
- [ ] Compute the expected-vs-actual deviation signal and confirm it's available as a feature before the Fault/RUL models are trained (they depend on it).

**3.2 Fault model**
- [ ] Convert ALFA ROS bags → CSV per the D1-resolved taxonomy.
- [ ] Windowing + feature extraction; train PyTorch classifier (with scikit-learn baseline) against the 7 classes.
- [ ] Address class imbalance (class weighting or focal loss).
- [ ] Log every run to MLflow; register the best checkpoint in `model_registry` with `model_name='fault_model'`.
- [ ] Export to ONNX; verify ONNX Runtime output matches the PyTorch output within tolerance.

**3.3 RUL model**
- [ ] Preprocess C-MAPSS (26-column CSV); split held-out test set **by unit ID**, not by row.
- [ ] Train both LSTM (PyTorch) and XGBoost baselines; compare on `validation_score`.
- [ ] Register the winner as `is_active=true` in `model_registry`; keep the other version for reference.
- [ ] Export to ONNX.

**3.4 Bearing model**
- [ ] Confirm CWRU portal access (should already be done per Section 3.1/4).
- [ ] FFT feature extraction (NumPy/SciPy) from `.mat` vibration files; train scikit-learn classifier for `fault_location` + map fault diameter to `severity_score`.
- [ ] Register in `model_registry`; export to ONNX.

**3.5 Aux / transfer model**
- [ ] **Resolve the unconfirmed second dataset (Section 4) before starting this block.**
- [ ] Pretrain on AI4I 2020; fine-tune on the confirmed second dataset once available.
- [ ] Version the pretrained backbone separately from the fine-tuned head in `model_registry`.
- [ ] If the second dataset still isn't confirmed by the block's deadline, ship with AI4I-2020-only pretraining and flag the aux score as provisional in the health fusion weighting (Phase 4).

**3.6 Inference microservice & registry wiring**
- [ ] `ml/models/` holds exported `.onnx` artifacts + a `model_card.md` per model.
- [ ] FastAPI inference microservice loads the `is_active` model per `model_name` from the registry at startup; exposes internal endpoints the ingestion pipeline calls after each new telemetry window.
- [ ] Wire predictions into `fault_predictions`, `rul_predictions`, `bearing_health_readings`, `aux_predictions`.

**Exit Criteria (per model):**
- [ ] Dataset preprocessed and versioned (pointer in `docs/dataset-guide/`).
- [ ] Training run logged in MLflow with a `validation_score`.
- [ ] Model row exists in `model_registry` with `is_active=true` for exactly one version per `model_name`.
- [ ] ONNX export verified against the native-framework output.
- [ ] Sending a sample feature window to the inference microservice returns a correctly shaped prediction and writes a row to its table.

---

### Phase 4 — Health Fusion & Alerting

**Owner:** Sahil (Backend Engineer hat) · **Duration:** 4 days

**Work to do:**
- [ ] Implement `backend/app/services/health_fusion.py` per the fusion logic proposed in the ML Model Specification document (Section 8.2): weighted penalty from Fault/RUL/Bearing, Aux as a modifier, physics deviation as an independent check, any single critical threshold able to force `critical` severity.
- [ ] Persist `combined_score` + `contributing_factors` per engine; expose via `GET /api/v1/engines/{engine_id}/health-score`.
- [ ] Implement the alert engine: threshold breach on any model output → row in `alerts` with the correct `source` value → email (SMTP/Resend) and/or outbound webhook.
- [ ] `PATCH /api/v1/alerts/{alert_id}/acknowledge`.

**Exit Criteria:**
- [ ] Feeding the simulator's injected-fault scenario (Phase 2.1) through the full pipeline produces a `critical` alert within the expected latency budget.
- [ ] `contributing_factors` correctly attributes the score drop to the model(s) that triggered it (manually verified against 3 test scenarios).
- [ ] Acknowledging an alert is idempotent (a second acknowledge attempt returns `409`, per the API spec).

---

### Phase 5 — Frontend Dashboard

**Owner:** Sahil (Frontend Engineer hat) · **Duration:** 4 weeks (start in parallel with Phase 3 once Phase 0's mock server is live; converge onto the real backend once Phase 1 ships)

**Blocks:**

**5.1 Scaffold**
- [ ] Vite + React + TypeScript + Tailwind; routing (`Dashboard`, `Missions`, `Alerts`, `Fleet`); auth pages (login) wired to Phase 1's `/auth` endpoints (or the mock server initially).

**5.2 Core dashboard views**
- [ ] Fleet summary view (`/dashboard/summary`); engine detail view (telemetry snapshot, health score).

**5.3 Model-specific components**
*(exact contracts specified in the ML Model Specification & Frontend Integration Guide, Section 9 — implement against that spec directly)*
- [ ] `FaultAlertBanner.tsx`, `RulTrendChart.tsx`, `BearingHealthGauge.tsx`, `HealthScoreGauge.tsx`.
- [ ] `types/` TypeScript interfaces mirroring the backend schemas 1:1, including the D1-resolved `faultClass` union.

**5.4 Live updates**
- [ ] `useTelemetryStream` hook consuming the extended WebSocket event set (`telemetry`, `fault_prediction`, `rul_prediction`, `bearing_health`, `health_score`, `alert`).
- [ ] Zustand store keyed by `engine_id`, per the integration guide's Section 9.5.

**5.5 Alerts & maintenance log UI**
- [ ] Alert list with acknowledge action (RBAC-gated to `maintenance_engineer+`).
- [ ] Maintenance log entry form.

**Exit Criteria:**
- [ ] Dashboard renders live data end to end against the real backend (not the mock) once Phase 1–4 are done.
- [ ] Every component in 5.3 matches the exact TypeScript interfaces in the integration guide — no ad hoc field renaming.
- [ ] Jest + React Testing Library suite passes for all components in 5.3.
- [ ] 404 "no prediction yet" and WebSocket-disconnect states render explicit empty/error states, not blank charts.

---

### Phase 6 — Simulation & Mission Replay Engine

**Owner:** Sahil (Backend + Frontend hat) · **Duration:** 1 week

**Work to do:**
- [ ] `simulation/replay_engine/`: reconstructs a historical mission's engine-state trace from stored `telemetry_readings` + predictions.
- [ ] `simulation/scenario_generator/`: builds a synthetic what-if profile (altitude, temp, throttle, duration) and runs it through the physics model + all 4 ONNX models.
- [ ] `POST /api/v1/simulation/run` (mode: `replay` | `what_if`); result retrieval via `GET /simulation/{id}`.
- [ ] Frontend: a timeline view rendering the simulated/replayed trace, flagging any point where a fault/RUL threshold would be crossed.

**Exit Criteria:**
- [ ] A stored mission can be replayed end to end and rendered on the dashboard's timeline.
- [ ] A hypothetical (hot-weather, high-altitude, rapid-throttle) profile produces a plausible simulated trace, validated against the scenario-diversity check from Section 4.

---

### Phase 7 — Edge Packaging

**Owner:** Sahil (Infra / ML hat) · **Duration:** 4 days

**Work to do:**
- [ ] `edge/inference/`: ONNX Runtime container running **only** the Fault and RUL models (per the architecture's edge/cloud split — Bearing and Aux stay cloud-side).
- [ ] `edge/can_interface/`: `python-can`/SocketCAN listener → MQTT publisher (swap in for the Phase 2 simulator when real hardware is available).
- [ ] `edge/telemetry_publisher/`: local buffering and republish-on-reconnect logic.
- [ ] Deployment script/Dockerfile targeting a Raspberry Pi / Jetson Nano-class device.

**Exit Criteria:**
- [ ] Edge container produces a Fault + RUL prediction locally with the cloud MQTT link disabled (simulated via `docker network disconnect`).
- [ ] Reconnecting the network republishes all buffered readings with no data loss (verified by row count).

---

### Phase 8 — Integration Testing & Hardening

**Owner:** Sahil (QA / Release hat) · **Duration:** 1 week

**Work to do:**
- [ ] Write end-to-end scenarios covering: normal operation, injected fault → alert → acknowledge, degraded connectivity → edge buffering → recovery, mission replay, what-if simulation.
- [ ] Locust load test on `/telemetry/ingest` and the WebSocket broadcast path — establish and hit a target throughput (e.g. 50 simulated engines streaming concurrently).
- [ ] Security pass: confirm every endpoint's RBAC role matches the API design table exactly; confirm rate limiting on `/auth/login`; run `git-secrets`/secret-scan over the full history; confirm `.env` files are never committed.

**Exit Criteria:**
- [ ] All E2E scenarios pass in CI.
- [ ] Load test meets the target throughput with p95 WebSocket broadcast latency under 2 seconds.
- [ ] Zero critical/high findings on the security checklist.

---

### Phase 9 — Deployment (Free-Tier Cloud)

**Owner:** Sahil (DevOps hat) · **Duration:** 3 days — full runbook in Section 8

**Work to do:**
- [ ] Backend + inference microservice → Render or Railway (free tier).
- [ ] Frontend → Vercel or Netlify (free tier).
- [ ] Database → self-hosted TimescaleDB on a free-tier VM (Oracle Cloud Free Tier) or Supabase for non-hypertable tables.
- [ ] MQTT broker → self-hosted Mosquitto on the same free VM, or HiveMQ Cloud free tier.
- [ ] Redis + Cloudflare R2, both free tier.
- [ ] Populate the Section 2.2 GitHub secrets with real values; wire `deploy.yml` to trigger on merge to `main`.

**Exit Criteria:**
- [ ] Production URL is live and publicly reachable; `/healthz` returns `200`.
- [ ] A merge to `main` triggers an automatic deploy with no manual steps.
- [ ] The deployed frontend shows live data from the deployed backend (simulator running against production for the demo).

---

### Phase 10 — Demo Prep & Submission

**Owner:** Sahil (Project Lead hat) · **Duration:** 3 days

**Work to do:**
- [ ] Script a 4–5 minute demo: seed a mission via the simulator, inject a fault live, show the alert → dashboard → acknowledge flow, then a replay/what-if simulation.
- [ ] Finalize `README.md` with setup instructions and links to all three companion documents.
- [ ] Update `docs/decisions-log.md` and `docs/dataset-guide/` with final, confirmed dataset links (Section 4's D-blockers must be closed by now).
- [ ] Build the pitch deck and demo video per the SIH submission portal's requirements.
- [ ] Run the full Definition of Done checklist (Section 11).

**Exit Criteria:**
- [ ] Demo script rehearsed end to end, under time, at least twice.
- [ ] Every item in Section 11 is checked.
- [ ] Submission uploaded before the portal deadline.

---

## 7. Testing Strategy

| Layer | Tooling | What's covered | When it runs |
|---|---|---|---|
| Backend unit | `pytest` + `pytest-asyncio` | Services, validators, health fusion logic | Every commit (pre-commit) + CI |
| Backend integration | `httpx.AsyncClient` against a test DB container | Full endpoint round-trips incl. RBAC | CI on every PR |
| Frontend unit | Jest + React Testing Library | Components from Phase 5.3, hooks | CI on every PR |
| ML evaluation | MLflow-logged metrics + held-out test sets | Per-model validation_score vs. baseline | Every training run (Phase 3) |
| Load | Locust | Ingestion + WebSocket broadcast throughput | Phase 8, and before each deploy to production |
| E2E | Scripted scenarios (Section 6, Phase 8) | Full pipeline, sensor → dashboard | Phase 8, and before Phase 10 demo |
| Security | Manual checklist + secret scanning | RBAC correctness, rate limits, no leaked secrets | Phase 8, and before every deploy |

- [ ] No PR merges to `main` without CI green (enforced by the branch protection rule in Section 2.2).
- [ ] Every new model version (Phase 3) requires a logged `validation_score` before it can be set `is_active=true` — no manual registry edits.

---

## 8. CI/CD & Deployment Runbook

### 8.1 `ci.yml` (on every PR)

- [ ] Lint: `ruff check` (backend/ml), `eslint` (frontend).
- [ ] Type-check: `mypy` or `pyright` (backend), `tsc --noEmit` (frontend).
- [ ] Test: `pytest` (backend), `jest` (frontend).
- [ ] Alembic migration check: fail the build if a model change has no matching migration.

### 8.2 `deploy.yml` (on merge to `main`)

- [ ] Build Docker images for `backend` and `ml-inference`; push to a registry (GitHub Container Registry is the zero-extra-account option).
- [ ] Trigger the Render/Railway deploy hook for the backend.
- [ ] Trigger the Vercel/Netlify deploy hook for the frontend (or let their native GitHub integration handle it directly).
- [ ] Run a post-deploy smoke test against the production `/healthz` endpoint; fail the workflow (and alert) if it doesn't return `200` within 60 seconds.

### 8.3 Rollback

- [ ] Render/Railway and Vercel/Netlify both keep prior deploys — a rollback is "redeploy the previous build," documented as a one-command runbook entry in `docs/`.
- [ ] Database migrations are the one non-trivial rollback case: never ship a migration that isn't backward-compatible with the previous backend version for at least one deploy cycle.

---

## 9. Timeline & Milestones

```mermaid
gantt
    title AeroTwin — Solo Developer Delivery Timeline (12 weeks)
    dateFormat  YYYY-MM-DD
    axisFormat  %d %b
    section Phase 0 - Kickoff
    Repo & design lock            :p0, 2026-09-29, 3d
    section Phase 1 - Backend Foundation
    DB schema & migrations        :p1a, after p0, 3d
    Auth & RBAC                   :p1b, after p1a, 2d
    Core CRUD endpoints           :p1c, after p1b, 2d
    section Phase 2 - Ingestion & Twin Core
    Telemetry simulator           :p2a, after p1c, 2d
    Ingestion + WS broadcast      :p2b, after p2a, 3d
    section Phase 3 - ML Models
    Physics model                 :p3a, after p2b, 3d
    Fault model                   :p3b, after p3a, 5d
    RUL model                     :p3c, after p3b, 5d
    Bearing model                 :p3d, after p3c, 4d
    Aux model                     :p3e, after p3d, 4d
    ONNX export + registry        :p3f, after p3e, 2d
    section Phase 4 - Fusion & Alerts
    Health fusion + alerting      :p4, after p3f, 4d
    section Phase 5 - Frontend
    Scaffold + auth pages         :p5a, after p1c, 3d
    Core dashboard views          :p5b, after p5a, 4d
    Model components              :p5c, after p3f, 4d
    Live updates                  :p5d, after p5c, 3d
    section Phase 6 - Simulation Engine
    Replay + what-if              :p6, after p4, 5d
    section Phase 7 - Edge Packaging
    Edge inference service        :p7, after p3f, 4d
    section Phase 8 - Testing & Hardening
    E2E + load + security         :p8, after p6, 5d
    section Phase 9 - Deployment
    Cloud deployment               :p9, after p8, 3d
    section Phase 10 - Demo Prep
    Docs, deck, rehearsal           :p10, after p9, 3d
```

### 9.1 Milestone Checklist

| Milestone | Target end of | Signals |
|---|---|---|
| M1 — Foundation live | Week 2 | Phase 1 + 2 exit criteria all checked; simulator streaming into a real DB |
| M2 — All 4 models registered | Week 6 | Phase 3 exit criteria all checked for Fault, RUL, Bearing, Aux |
| M3 — Full pipeline demoable | Week 7 | Phase 4 exit criteria checked; a fault-to-alert scenario works end to end |
| M4 — Dashboard feature-complete | Week 8 | Phase 5 exit criteria checked against real backend |
| M5 — Simulation + edge complete | Week 9 | Phase 6 + 7 exit criteria checked |
| M6 — Production-ready | Week 11 | Phase 8 + 9 exit criteria checked; live production URL |
| M7 — Submission-ready | Week 12 | Phase 10 exit criteria + Section 11 fully checked |

---

## 10. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| CWRU portal registration delayed | Medium | Blocks Phase 3.4 | Start registration in Phase 0/Section 4, not when Phase 3 arrives |
| Aux model's second dataset stays unconfirmed | Medium | Aux model ships as provisional | Ship AI4I-2020-only pretraining as a fallback (Phase 3.5); flag score as advisory in fusion weighting |
| Solo-developer time overrun on Phase 3 (largest phase) | High | Cascades into Phases 4–9 | Phase 3 has the longest duration budget (4 weeks) in the timeline for exactly this reason; if still overrunning, cut Aux model scope first (it's already the most advisory of the four) |
| Free-tier cloud service limits hit during load testing or demo | Medium | Downtime during Phase 8 or the live demo | Load-test against free-tier limits explicitly in Phase 8; keep the upgrade path (main document Section 11.4) as a documented fallback, not an emergency scramble |
| D1 (fault taxonomy) decided late | Low if Section 5 is followed | Rework across DB, backend, frontend, ML | Section 5 makes this a Phase-0 blocking decision, not a Phase-3 surprise |
| No real UAV/engine hardware for validation | High (known, accepted) | Models validated only on proxy datasets | Explicitly documented in every model's related-considerations section of the ML spec doc; state clearly in the demo (Phase 10) rather than overclaiming readiness |

---

## 11. Definition of Done & Submission Checklist

- [ ] All Phase 0–10 exit criteria in Section 6 are checked.
- [ ] `docs/decisions-log.md` has no open items (D1, D2, D3 all resolved and implemented).
- [ ] Dataset & Model Collection Guide's open items (Section 4 of that document) are closed: Aux model's second dataset linked, licensing double-checked, domain-gap mitigation note carried into the submission sheet.
- [ ] All 4 models are `is_active=true` in `model_registry` with a logged `validation_score`.
- [ ] CI is green on `main`; production deploy is live and passing its smoke test.
- [ ] README links the main Project Implementation Document, the ML Model Specification & Frontend Integration Guide, and the Dataset & Model Collection Guide.
- [ ] Demo script rehearsed at least twice, under time.
- [ ] Pitch deck and demo video finalized per the SIH submission portal's format requirements.
- [ ] Submission uploaded before the deadline, with a buffer for upload/processing delays.

---

## 12. Appendix

### 12.1 Environment Variable Reference

| Variable | Used by | Example / notes |
|---|---|---|
| `DATABASE_URL` | backend | `postgresql+asyncpg://user:pass@host:5432/aerotwin` |
| `JWT_SECRET` | backend | 256-bit random string; rotate for production |
| `MQTT_BROKER_URL` | backend, edge | `mqtt://host:1883` |
| `REDIS_URL` | backend | `redis://host:6379/0` |
| `VITE_API_URL` | frontend | `https://api.aerotwin.example.com` |
| `VITE_WS_URL` | frontend | `wss://api.aerotwin.example.com` |
| `CLOUDFLARE_R2_ACCESS_KEY` / `_SECRET_KEY` | backend | Object storage for CAN logs, model artifacts |

### 12.2 Useful Commands

```bash
# Local stack
docker compose -f infra/docker/docker-compose.yml up -d
docker compose -f infra/docker/docker-compose.yml logs -f backend

# Backend
cd backend && source .venv/bin/activate
alembic upgrade head
pytest --cov=app

# Frontend
cd frontend && npm run dev
npm test

# ML
cd ml && python training/fault_model/train.py
mlflow ui   # http://localhost:5000

# Telemetry simulator (Phase 2)
python edge/telemetry_publisher/simulate.py --mission hot_weather_endurance
```

### 12.3 Related Documents

- *AeroTwin — Complete Project Implementation Document* (system architecture, database design, API design, deployment architecture, scalability strategy)
- *AeroTwin — ML Model Specification & Frontend Integration Guide* (per-model dataset/input/output detail, TypeScript interfaces, example components)
- *Dataset & Model Collection Guide* (dataset provenance, licensing, open items)

### 12.4 Full API Endpoint Reference

All endpoints are versioned under `/api/v1`. Authentication is via short-lived JWT access tokens (Section 6.8 of the main Project Implementation Document); the **Auth** column below names the minimum role required in addition to a valid token, where a role is enforced. This is the exact contract Phase 0 exports to `docs/api/openapi.yaml` for the mock server, and that Phase 1–6 implement against — keep this table and the OpenAPI spec in sync; if they drift, the spec wins and this table gets corrected in the same PR.

**Authentication**

| Endpoint | Auth | Request | Response | Errors |
|---|---|---|---|---|
| `POST /api/v1/auth/login` | None (issues token) | `{ email, password }` | `{ access_token, refresh_token, expires_in, role }` | `401` invalid credentials · `423` account locked · `422` malformed body |
| `POST /api/v1/auth/refresh` | Refresh token (body) | `{ refresh_token }` | `{ access_token, expires_in }` | `401` invalid/expired token · `422` malformed body |

**Telemetry**

| Endpoint | Auth | Request | Response | Errors |
|---|---|---|---|---|
| `POST /api/v1/telemetry/ingest` | Edge device API key (header) | `{ engine_id, mission_id?, ts, rpm, cht, egt, oil_pressure, oil_temp, fuel_flow, vibration_x?, vibration_y?, vibration_z? }` | `{ status: "accepted", id }` | `400` out-of-range value · `401` invalid API key · `404` unknown `engine_id` · `429` rate limit exceeded |
| `GET /api/v1/engines/{engine_id}/telemetry/latest` | Bearer JWT | Path: `engine_id` | `{ ts, rpm, cht, egt, oil_pressure, oil_temp, fuel_flow, vibration_x, vibration_y, vibration_z }` | `401` unauthenticated · `403` forbidden (wrong role/asset) · `404` no readings yet |
| `GET /api/v1/engines/{engine_id}/telemetry` | Bearer JWT | Query: `from`, `to`, `limit` (default 500, max 5000) | `[{ ts, rpm, cht, egt, ... }, ...]` | `400` invalid range · `401`/`403` as above |

*Validation:* `engine_id` must be a valid UUID the caller has role-based access to; on the range query, `from < to` and the range is capped at 30 days per request to protect the hypertable.

**Fault / RUL / Bearing**

| Endpoint | Auth | Request | Response | Errors |
|---|---|---|---|---|
| `GET /api/v1/engines/{engine_id}/faults/latest` | Bearer JWT | Path: `engine_id` | `{ ts, fault_class, confidence, model_version }` | `401`/`403` · `404` no prediction yet |
| `GET /api/v1/engines/{engine_id}/rul` | Bearer JWT | Query: `from?`, `to?` (defaults to last 90 days) | `[{ ts, rul_cycles, degradation_index }, ...]` | `400` invalid range · `401`/`403` · `404` no data |
| `GET /api/v1/engines/{engine_id}/bearing-health` | Bearer JWT | Path: `engine_id` | `{ ts, fault_location, severity_score }` | `401`/`403` · `404` no data |

**Health & Dashboard**

| Endpoint | Auth | Request | Response | Errors |
|---|---|---|---|---|
| `GET /api/v1/engines/{engine_id}/health-score` | Bearer JWT | Path: `engine_id` | `{ combined_score, contributing_factors: [...], last_updated }` | `401`/`403` · `404` not yet computed |
| `GET /api/v1/dashboard/summary` | Bearer JWT | Query: `fleet?` (admin/program_manager only) | `{ engines: [{ engine_id, tail_number, health_score, open_alerts }] }` | `401` unauthenticated · `403` role not permitted (fleet-wide view restricted to `program_manager`/`admin`) |

**Missions & Simulation**

| Endpoint | Auth | Request | Response | Errors |
|---|---|---|---|---|
| `POST /api/v1/missions` | Bearer JWT (`operator+`) | `{ uav_asset_id, mission_type, start_time, environmental_profile }` | `{ id, status: "scheduled" }` | `400` invalid profile · `401`/`403` · `409` asset already on an active mission |
| `GET /api/v1/missions/{mission_id}` | Bearer JWT | Path: `mission_id` | `{ id, uav_asset_id, mission_type, start_time, end_time, environmental_profile, telemetry_summary }` | `401`/`403` · `404` not found |
| `POST /api/v1/simulation/run` | Bearer JWT (`engineer+`) | `{ engine_id, mode: "replay"\|"what_if", mission_id? \| environmental_profile? }` | `{ simulation_id, status: "queued" }` — result via `GET /simulation/{id}` | `400` conflicting mode/payload · `401`/`403` · `404` mission not found |

*Validation:* mission `start_time` cannot be in the past and `uav_asset_id` must exist and be `status='active'`; for simulation, exactly one of `mission_id` / `environmental_profile` must be supplied depending on `mode`.

**Alerts**

| Endpoint | Auth | Request | Response | Errors |
|---|---|---|---|---|
| `GET /api/v1/alerts` | Bearer JWT | Query: `engine_id?`, `severity?`, `is_acknowledged?` (default: `false`) | `[{ id, engine_id, source, severity, is_acknowledged, created_at }, ...]` | `400` invalid filter value · `401`/`403` |
| `PATCH /api/v1/alerts/{alert_id}/acknowledge` | Bearer JWT (`maintenance_engineer+`) | Path: `alert_id` (empty body) | `{ id, is_acknowledged: true, acknowledged_by, acknowledged_at }` | `401`/`403` · `404` not found · `409` already acknowledged (idempotency check — Phase 4 exit criteria) |

**Maintenance**

| Endpoint | Auth | Request | Response | Errors |
|---|---|---|---|---|
| `POST /api/v1/engines/{engine_id}/maintenance-logs` | Bearer JWT (`maintenance_engineer+`) | `{ action_taken, notes? }` | `{ id, ts, logged_by }` | `400` validation error (`action_taken` required, max 120 chars) · `401`/`403` · `404` engine not found |

**Model Registry**

| Endpoint | Auth | Request | Response | Errors |
|---|---|---|---|---|
| `GET /api/v1/models` | Bearer JWT (`engineer+`) | Query: `model_name?` | `[{ id, model_name, version, framework, trained_at, validation_score, is_active }, ...]` | `400` invalid filter (`model_name`, if given, must be one of the four known model types) · `401`/`403` |

**Live streaming**

| Endpoint | Auth | Request | Response | Errors |
|---|---|---|---|---|
| `WebSocket /ws/engines/{engine_id}/live` | Bearer JWT (as query param at handshake) | WebSocket upgrade; no body | Server pushes `{ type: "telemetry"\|"fault_prediction"\|"rul_prediction"\|"bearing_health"\|"health_score"\|"alert", payload }` messages as they occur | `4401` unauthenticated · `4403` forbidden · `1011` server error |

> RBAC roles referenced above, from lowest to highest privilege: `operator` → `maintenance_engineer` → `program_manager` → `admin`. Phase 8's security pass (Section 7) re-verifies every row of this table against the live implementation before deployment.

### 12.5 Database Schema Quick Reference

PostgreSQL 15 with the TimescaleDB extension. `telemetry_readings` is a TimescaleDB hypertable (partitioned on `ts`) because of its high write volume; every other table is a standard relational table. All primary keys use UUIDs (`gen_random_uuid()`) except `telemetry_readings`, which uses a `BIGINT` identity column for hypertable-compatible ordering. Full column-level DDL lives in `backend/app/models/` (Phase 1.1) — this table is the at-a-glance map for wiring foreign keys and indexes correctly the first time.

| Table | Primary Key | Foreign Keys | Key Indexes | Notes |
|---|---|---|---|---|
| `users` | `id` | — | UNIQUE on `email`; index on `role` | Operators, maintenance engineers, program managers, admins |
| `uav_assets` | `id` | — | UNIQUE on `tail_number` | One asset fitted with one engine (current); flies many missions |
| `engines` | `id` | `uav_asset_id → uav_assets.id` | UNIQUE on `engine_serial_no`; index on `uav_asset_id` | Core entity everything else attaches to |
| `missions` | `id` | `uav_asset_id → uav_assets.id` | Index on `uav_asset_id`; index on `start_time` | Environmental/operating profile per flight |
| `telemetry_readings` | `id` (composite with `ts`) | `engine_id → engines.id`; `mission_id → missions.id` | Hypertable chunk index on `ts`; composite `(engine_id, ts DESC)` | High-frequency raw + preprocessed sensor data |
| `fault_predictions` | `id` | `engine_id → engines.id`; `model_version_id → model_registry.id` | Composite `(engine_id, ts DESC)` | One row per Fault-model inference run; may trigger an alert |
| `rul_predictions` | `id` | `engine_id → engines.id`; `model_version_id → model_registry.id` | Composite `(engine_id, ts DESC)` | One row per RUL-model inference run; may trigger an alert |
| `bearing_health_readings` | `id` | `engine_id → engines.id`; `model_version_id → model_registry.id` **(D2)** | Composite `(engine_id, ts DESC)` | `model_version_id` FK added per Decision D2 (Section 5) — not in the original schema |
| `aux_predictions` | `id` | `engine_id → engines.id`; `model_version_id → model_registry.id` **(D2, new table)** | Composite `(engine_id, ts DESC)` | Table added per Decision D2 (Section 5): `(engine_id, model_version_id, ts, aux_score)` |
| `maintenance_logs` | `id` | `engine_id → engines.id`; `logged_by → users.id` | Index on `engine_id` | Service/maintenance actions recorded against an engine |
| `alerts` | `id` | `engine_id → engines.id`; `acknowledged_by → users.id` | Index on `(engine_id, is_acknowledged)`; index on `severity` | Raised by Fault/RUL/Bearing models or the health-fusion rule engine |
| `model_registry` | `id` | — | UNIQUE on `(model_name, version)`; index on `is_active` | Version-tracked record of every trained model deployed to inference |

> `aux_predictions` and the `model_version_id` FK on `bearing_health_readings` are **not** in the original architecture diagram — they are Decision D2 from Section 5 and must land in the very first Alembic migration (Phase 1, Block 1.1).
