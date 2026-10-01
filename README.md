# AeroTwin

**AI-Enabled Real-Time Digital Twin for Aero-Piston Engines in MALE UAVs**

Smart India Hackathon 2026 · Problem Statement ID **26054** · Organization: DRDO — Department of Defence R&D · Theme: Robotics and Drones

## Overview
AeroTwin is a complete, real-time digital twin system designed to ingest, process, and analyze telemetry data from aero-piston engines in Medium Altitude Long Endurance (MALE) UAVs. The system includes machine learning models for anomaly detection (Faults), predictive maintenance (Remaining Useful Life - RUL), bearing health analysis, and auxiliary failure prediction, combined with a robust backend architecture and an interactive operator dashboard.

## Related Documents
- [AeroTwin Project Implementation Document](docs/AeroTwin_Project_Document.md)
- [ML Model Specification & Frontend Integration](docs/AeroTwin_ML_Model_Spec_and_Frontend_Integration.md)
- [Dataset & Model Collection Guide](docs/Dataset_Model_Collection_Guide.md)
- [API Documentation](docs/api/openapi.yaml)

## Quick Start

Prerequisites: Docker, Python 3.12, Node 20.

```bash
# 1. Infrastructure (TimescaleDB :5433, Redis :6379, Mosquitto :1883)
docker compose -f infra/docker/docker-compose.yml up -d db redis mqtt

# 2. Backend  (http://127.0.0.1:8000, docs at /docs)
cd backend
python -m venv .venv && .venv/Scripts/activate        # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt -r requirements-ml.txt -r AeroTwin_Rag/requirements.txt
cp .env.example .env                                   # then edit secrets / DB URL
alembic upgrade head
uvicorn app.main:app --host 127.0.0.1 --port 8000

# 3. Frontend  (http://127.0.0.1:5173)
cd ../frontend
cp .env.example .env
npm ci && npm run dev

# 4. Feed it data (telemetry simulator; f/o/v/c keys inject faults)
python edge/telemetry_publisher/simulate.py
```

Or run everything in containers: `docker compose -f infra/docker/docker-compose.yml up --build`. The compose `simulator` service (dev/demo only) keeps the demo engine streaming so the dashboard and 3D Twin show LIVE data; don't deploy it to production.

### Tests and checks

| What | Command |
|---|---|
| Backend (needs the DB from step 1) | `cd backend && pytest` |
| ML physics model | `pytest ml/tests` |
| Frontend unit/UI tests | `cd frontend && npm test` |
| Frontend typecheck + build | `cd frontend && npm run build` |
| Lint | `ruff check --config backend/ruff.toml backend/app backend/tests ml` and `cd frontend && npm run lint` |
| End-to-end (needs the running stack) | see [scripts/e2e/README.md](scripts/e2e/README.md) |

### Main features

- Live telemetry ingest (MQTT + REST) → Fault / RUL / Bearing / Auxiliary models → Health Fusion → alerts, streamed over WebSocket.
- Mission Replay, preset mission simulation, and the **parameter What-If** (change RPM/CHT/EGT/oil/fuel and see how the real models respond — read-only, never touches live state).
- **3D digital twin** (sidebar → *3D Twin*, `/engines/<id>/twin`): a WebGL engine model (selectable block, cylinders, bearing, gearbox; turbo shown as an unlit ghost) driven by live telemetry, physics-consistency status, model outputs and Health Fusion. Six view modes (Health, Thermal, Fault, Bearing, Physics↔AI, Vibration), a component inspector, and LIVE / REPLAY / WHAT-IF sources with a current-vs-scenario comparison; live state is never modified. Anything the backend doesn't provide shows "Unavailable" — per-cylinder temperatures are never shown because the engine has one CHT and one EGT sensor, and no health or physics values are computed in the browser.
- Fleet dashboard rows update live over WebSocket (LIVE/STALE chip, age, RPM/CHT/EGT).
- GARUDA Copilot (RAG) for explaining health, RUL and alerts.
- Edge agent (ONNX Fault + RUL, offline buffering) in [`edge/`](edge/README.md).

### Deploying

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) — required environment, GitHub setup, and the limits to know before going live.

## License
[MIT License](LICENSE)
