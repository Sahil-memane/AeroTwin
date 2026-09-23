**AeroTwin**

**AI-Enabled Real-Time Digital Twin for Aero-Piston Engines in MALE UAVs**

*Complete Project Implementation Document*

Smart India Hackathon 2026 | Problem Statement ID: 26054

Organization: DRDO — Department of Defence R&D | Theme: Robotics and Drones

Team: Antigravity

*Document version 1.0*

**Table of Contents**

*(Right-click below and choose "Update Field" — or press F9 — after opening this document in Word to populate the contents list.)*

# **1. Project Overview**

## **1.1 Project Name**

AeroTwin — AI-Enabled Real-Time Digital Twin System for Health Monitoring, Fault Prediction and Mission Reliability Enhancement of Aero-Piston Engines used in MALE UAVs.

## **1.2 Description**

AeroTwin is a modular digital twin platform that mirrors an aero-piston engine used in a Medium Altitude Long Endurance (MALE) UAV in real time. It fuses live CAN-bus telemetry, a thermodynamic physics model, and four purpose-trained machine learning models into a single continuously synchronized virtual representation of the engine.

Instead of the threshold-based, reactive monitoring used in current UAV ground control systems, AeroTwin shifts the system to predictive, condition-based maintenance: it detects abnormal operating conditions before they become failures, estimates Remaining Useful Life (RUL), classifies incipient faults, and lets operators replay or simulate mission profiles — including high-altitude, hot-weather, and rapid-throttle-transient scenarios — before and after flight.

## **1.3 Objectives**

* Replace threshold-based reactive engine monitoring with continuous, predictive health assessment.
* Detect and classify incipient engine faults (misfire, injector abnormality, cooling degradation, lubrication issues, sensor drift, combustion instability) ahead of failure.
* Estimate Remaining Useful Life (RUL) and degradation trend per engine, per mission.
* Provide mission-wise simulation and post-flight replay under varying environmental and operating conditions.
* Deliver a real-time visualization dashboard for UAV operators, propulsion engineers, and maintenance teams.
* Build the system as an indigenous, modular, zero-licensing-cost stack that can scale from a single test rig to fleet-level health monitoring infrastructure.

## **1.4 Target Users**

| **User** | **How they use AeroTwin** |
| --- | --- |
| UAV Ground Control Station (GCS) operators | Monitor live engine health status and fault alerts during a mission; make abort/continue decisions. |
| Propulsion / maintenance engineers | Review RUL trends, fault diagnostics, and maintenance advisories; plan servicing before failure. |
| Mission planners | Use the simulation engine to evaluate engine behavior under a planned mission profile before it flies. |
| DRDO program managers / fleet health officers | Track fleet-wide reliability trends and maintenance history across all UAV tail numbers. |
| Test-rig engineers (development phase) | Validate the digital twin core and ML models against ground-test engine data before field deployment. |

## **1.5 Existing Problems**

1. Conventional UAV engine monitoring systems are primarily threshold-based and reactive — they flag an abnormality only after it has already occurred, leaving no lead time to act.
2. Piston-engine failures during flight can cause mission abort, loss of the UAV asset, or unsafe recovery conditions — with no way to anticipate them in advance.
3. Existing systems have limited or no capability to estimate Remaining Useful Life (RUL) or track long-term degradation trends.
4. There is no way to simulate or replay how the engine would behave under a specific mission profile (high altitude, endurance duration, hot weather, rapid throttle transitions) before or after the flight.
5. Health monitoring, fault detection, and maintenance planning are handled as separate, disconnected activities rather than a single synchronized system.

## **1.6 Proposed Solution**

AeroTwin implements the full Digital Twin Core → Physics Model + AI/ML Analytics + Simulation Engine → Health Fusion → Maintenance Dashboard pipeline described in Section 4 (System Architecture). Live engine sensor data (RPM, CHT, EGT, oil pressure/temperature, fuel flow, vibration) is ingested over CAN bus / SocketCAN, fused with mission history, and run through:

* A physics-based thermodynamic model that computes expected engine behavior from first principles.
* Four trained ML models — Fault classification, RUL estimation, Bearing/vibration analysis, and an auxiliary cross-domain transfer model — that compute the data-driven health picture.
* A health fusion layer that reconciles the physics-based and data-driven outputs into a single combined health score and maintenance advisory.
* A simulation/replay engine that reproduces historical missions or projects engine behavior under a proposed mission profile.

All of this surfaces on a real-time dashboard built for GCS operators and maintenance engineers, with fault alerts, RUL trends, and mission-wise health reports.

## **1.7 Expected Impact**

* Fewer in-flight engine failures and mission aborts through early, predictive fault detection.
* Lower unplanned maintenance cost via condition-based servicing instead of fixed-interval or reactive maintenance.
* Safer recovery decisions for operators, backed by a live, quantified engine health score rather than a binary threshold alarm.
* An indigenous, defense-grade digital twin capability that is not dependent on foreign proprietary engine-monitoring software.
* A modular architecture that scales from a single engine test rig to fleet-wide health monitoring without redesign.

# **2. Key Features**

## **2.1 Real-Time Digital Twin Core & Telemetry Ingestion**

|  |  |
| --- | --- |
| **Feature Name** | Real-Time Digital Twin Core & Telemetry Ingestion |
| **Problem Solved** | Operators currently see raw instrument readings with no synchronized, continuously updated model of overall engine state — so a developing problem has to be pieced together manually from separate gauges. |
| **User Flow** | Engine sensors stream over CAN bus → edge gateway timestamps and forwards over MQTT → ingestion service validates and normalizes → digital twin core updates its live state → dashboard reflects the new state within seconds. |
| **Inputs** | Live CAN-bus telemetry (RPM, CHT, EGT, oil pressure/temperature, fuel flow, vibration), mission metadata (UAV tail number, mission ID, environmental conditions). |
| **Outputs** | A continuously updated virtual engine state object, exposed via REST snapshot and WebSocket live stream to the frontend. |
| **Technologies Used** | python-can / SocketCAN, Mosquitto MQTT, FastAPI async ingestion service, TimescaleDB hypertables, WebSocket. |

## **2.2 AI Fault Detection Model (7-Class Classifier)**

|  |  |
| --- | --- |
| **Feature Name** | AI Fault Detection Model (7-Class Classifier) |
| **Problem Solved** | Threshold alarms catch only conditions the designer explicitly anticipated, and give no indication of which specific fault is occurring — misfire, injector fault, cooling degradation, and sensor drift can all look similar at the gauge level. |
| **User Flow** | Preprocessed telemetry window → feature extraction → fault classification model → predicted fault class + confidence → written to fault\_predictions → surfaced as an alert if confidence exceeds threshold. |
| **Inputs** | Windowed multivariate telemetry (RPM, CHT, EGT, vibration, fuel flow) from the digital twin core. |
| **Outputs** | Fault class (no-failure / misfire / injector abnormality / cooling degradation / lubrication issue / sensor drift / combustion instability) with a confidence score. |
| **Technologies Used** | PyTorch / scikit-learn classifier trained on ALFA UAV telemetry, ONNX export for edge inference, FastAPI inference microservice. |

## **2.3 Remaining Useful Life (RUL) Prediction Engine**

|  |  |
| --- | --- |
| **Feature Name** | Remaining Useful Life (RUL) Prediction Engine |
| **Problem Solved** | Maintenance today is scheduled on fixed intervals or triggered only after a fault has already appeared, instead of being driven by how much useful life the engine actually has left. |
| **User Flow** | Historical + live degradation-relevant telemetry → sequence model → predicted RUL in flight-hours and a degradation index → written to rul\_predictions → shown as a trend line on the maintenance dashboard. |
| **Inputs** | Time-series telemetry (operating hours, temperatures, pressures, vibration trend) per engine. |
| **Outputs** | Estimated Remaining Useful Life (hours) and a normalized degradation index (0–1). |
| **Technologies Used** | LSTM (PyTorch) and XGBoost regression baseline, trained on NASA C-MAPSS turbofan degradation data, model versioned in the model registry. |

## **2.4 Bearing & Vibration Health Model**

|  |  |
| --- | --- |
| **Feature Name** | Bearing & Vibration Health Model |
| **Problem Solved** | Bearing wear is one of the earliest and most diagnosable precursors to mechanical failure, but conventional monitoring rarely analyzes vibration signatures beyond a simple amplitude threshold. |
| **User Flow** | Triaxial vibration stream → FFT feature extraction → bearing fault classifier → fault location + severity score → written to bearing\_health\_readings → contributes to the combined health score. |
| **Inputs** | X/Y/Z vibration signals sampled from the engine/accessory shaft. |
| **Outputs** | Fault location (inner race / outer race / rolling element / healthy) and a severity score. |
| **Technologies Used** | FFT-based feature engineering (NumPy / SciPy), classical ML classifier (scikit-learn), trained on CWRU bearing vibration data. |

## **2.5 Cross-Domain Auxiliary Transfer Learning Model**

|  |  |
| --- | --- |
| **Feature Name** | Cross-Domain Auxiliary Transfer Learning Model |
| **Problem Solved** | Labeled piston-engine failure data is scarce; a model trained only on the limited in-domain data available before deployment will generalize poorly to failure patterns it has never seen. |
| **User Flow** | Pretraining on cross-domain machine-failure data → transfer/fine-tuning on available engine and milling-machine failure data → auxiliary health score → fused with the other three models' outputs. |
| **Inputs** | Tabular operating-condition data (temperature, rotational speed, torque, tool/component wear) from the AI4I 2020 milling dataset and a supplementary engine-failure dataset. |
| **Outputs** | An auxiliary fault-likelihood score used as a supporting signal in health fusion, plus a reusable pretrained backbone for future in-domain fine-tuning. |
| **Technologies Used** | scikit-learn / XGBoost with transfer-learning fine-tuning, tracked in the model registry alongside the other three models. |

## **2.6 Physics-Informed Performance Modeling**

|  |  |
| --- | --- |
| **Feature Name** | Physics-Informed Performance Modeling |
| **Problem Solved** | A purely data-driven model can be confidently wrong outside the conditions it was trained on; there is no independent, physics-grounded check on what the engine 'should' be doing. |
| **User Flow** | Live operating conditions (altitude, throttle, RPM, fuel flow) → thermodynamic/performance solver → expected CHT/EGT/power output → compared against actual sensor readings → deviation signal fed into the AI/ML inference layer. |
| **Inputs** | Live operating conditions plus manufacturer engine performance maps and thermodynamic constants (reference/config data, not a training dataset). |
| **Outputs** | Expected-vs-actual performance deltas, used both as an independent sanity check and as an additional feature for the ML models. |
| **Technologies Used** | Python thermodynamic solver (Otto-cycle based), reference data sourced from FAA Type Certificate Data Sheets and manufacturer operator's manuals. |

## **2.7 Mission Simulation & Post-Flight Replay Engine**

|  |  |
| --- | --- |
| **Feature Name** | Mission Simulation & Post-Flight Replay Engine |
| **Problem Solved** | There is currently no way to evaluate how the engine would behave under a specific mission profile — high altitude, long endurance, hot weather, rapid throttle transitions — before committing to that mission, or to forensically replay what happened afterward. |
| **User Flow** | Select a historical mission or define a hypothetical mission profile → simulation engine runs it through the physics + AI/ML models → time-stepped predicted engine state → rendered as a replay timeline on the dashboard. |
| **Inputs** | Historical mission telemetry (for replay) or a defined environmental/operating profile (for what-if simulation): altitude, ambient temperature, throttle profile, duration. |
| **Outputs** | A time-stepped simulated or replayed engine health trace, flaggable at any point where a fault or RUL threshold would be crossed. |
| **Technologies Used** | Python simulation engine reusing the physics model and ONNX-exported ML models, NASA DASHlink flight-profile data used to validate scenario diversity. |

## **2.8 Predictive Maintenance Dashboard & Health Fusion**

|  |  |
| --- | --- |
| **Feature Name** | Predictive Maintenance Dashboard & Health Fusion |
| **Problem Solved** | Even accurate individual model outputs are not directly actionable unless they are combined into one clear picture and delivered to the right person at the right time. |
| **User Flow** | Fault / RUL / Bearing / Aux model outputs → health fusion service computes a combined health score → threshold breach triggers the alert engine → operator sees real-time status, trends, and advisories on the dashboard; critical alerts also go out by email/webhook. |
| **Inputs** | All four model outputs plus the physics-model deviation signal. |
| **Outputs** | A combined engine health score, prioritized fault alerts, RUL trend charts, and mission-wise health reports. |
| **Technologies Used** | FastAPI fusion/rules service, React + Recharts/Plotly dashboard, WebSocket live updates, SMTP/webhook alerting. |

# **3. Unique Selling Points (USP)**

These are what set AeroTwin apart from a conventional threshold-based engine monitor or a generic predictive-maintenance dashboard — kept separate from the feature list above because they describe why the feature set as a whole is differentiated, not what each feature does.

## **3.1 Why This Is Different / Real-World Applicability**

* Hybrid physics + AI approach: the thermodynamic physics model gives an independent, explainable check on every ML prediction — a pure black-box model cannot do this, and a pure threshold system cannot do prediction at all.
* Built directly against a live DRDO problem statement (SIH26054) with the exact parameter list (CHT, EGT, RPM, oil pressure/temperature, fuel flow, vibration) and mission conditions (high altitude, endurance, hot weather, rapid throttle transients) the end user specified — not a generic IoT predictive-maintenance template retrofitted to aviation.
* Designed for real MALE UAV operating conditions from day one: intermittent connectivity, edge compute constraints, and CAN-bus/FADEC-style data acquisition, rather than assuming a always-connected cloud-first environment.

## **3.2 AI Capabilities**

* Four specialized models (fault classification, RUL regression, bearing/vibration analysis, cross-domain transfer) rather than one generic classifier, each matched to the data and failure mode it is best suited for.
* Physics-informed feature engineering: model inputs include physics-model deviation signals, not just raw sensor values, improving robustness outside the training distribution.
* Transfer learning explicitly designed into the architecture to compensate for scarce piston-engine failure data — the auxiliary model is pretrained cross-domain and fine-tuned as in-domain data becomes available.
* Explainable outputs: every fault prediction carries a confidence score and a physics-model deviation trace an engineer can audit, rather than an opaque single number.

## **3.3 Future Readiness**

* Model registry and versioning built in from the start, so models can be retrained and redeployed as real flight/CAN-bus data replaces the proxy training datasets, without changing the surrounding system.
* Edge-AI/ONNX export path is part of the design, not an afterthought — models can run onboard the UAV or at the GCS with degraded or no connectivity.
* Architecture is explicitly multi-tenant at the data layer (per uav\_asset\_id / engine\_id), so it scales from one test-rig engine to a full fleet without a schema redesign.
* Federated-learning-ready: because each UAV/edge node can train or fine-tune locally before syncing model updates, the design leaves room for fleet-wide learning without centralizing raw sensitive telemetry.

## **3.4 Competitive Advantage**

* Zero licensing cost: the entire stack (FastAPI, React, TimescaleDB/PostgreSQL, Mosquitto, ONNX Runtime, Docker) is open-source, versus commercial engine-monitoring platforms that charge per-aircraft or per-seat licensing.
* Indigenous and self-hostable end to end — no dependency on a foreign SaaS vendor for a defense-relevant health-monitoring capability, which matters specifically for a DRDO deployment.
* Single synchronized system instead of disconnected tools: monitoring, fault prediction, RUL estimation, and mission simulation live in one data model and one dashboard, rather than four separate point solutions an operator has to reconcile manually.

# **4. Complete System Architecture / ML Modeling Flow**

The diagram below is the agreed system architecture for AeroTwin, covering the full path from raw engine sensors through the digital twin core, the physics and AI/ML branches, and out to the maintenance dashboard.

|  |
| --- |
| **[Diagram placeholder]**  *1790074077994\_integrated\_digital\_twin\_full\_architecture.png* |

*Figure 4.1 — AeroTwin integrated digital twin architecture (data ingestion → digital twin core → physics / AI-ML / simulation → health fusion → dashboard).*

## **4.1 Layer-by-Layer Walkthrough**

### **Layer 1 — Data sources**

* Engine sensors: live engine telemetry (RPM, CHT, EGT, oil pressure/temperature, fuel flow, vibration) acquired over CAN bus / SocketCAN.
* Mission & history: past flight profiles and mission metadata, used both to contextualize live data and to drive the simulation engine.

### **Layer 2 — Data ingestion & preprocessing**

* An edge/cloud pipeline validates, timestamps, resamples, and normalizes incoming CAN-bus data before it reaches the digital twin core.

### **Layer 3 — Digital twin core**

* Maintains the live, continuously synchronized virtual engine model that every downstream layer reads from and writes back to.

### **Layer 4 — Physics model, AI/ML analytics, and Simulation engine (parallel branches)**

* Physics model: thermodynamic/performance equations compute expected engine behavior independent of any trained model.
* AI/ML analytics: the four trained models (Fault, RUL, Bearing, Aux) described in Section 2, each consuming the relevant slice of telemetry.
* Simulation engine: scenario replay / what-if tool that reuses the physics model and the trained ML models to project or replay mission behavior.

### **Layer 5 — AI/ML analytics pipeline (expanded)**

* UAV telemetry / fault logs → Fault model → 7-class fault output.
* NASA turbofan degradation data → RUL model → LSTM/XGBoost Remaining Useful Life estimate.
* Bearing vibration data → Bearing model → FFT-based feature classifier.
* Cross-domain support data (milling + engine failure datasets) → Aux model → transfer-learned auxiliary score.

### **Layer 6 — Health fusion & scoring**

* Combines the Fault, RUL, Bearing, and Aux model outputs (plus the physics-model deviation) into a single combined health score.

### **Layer 7 — Maintenance dashboard**

* Surfaces alerts, RUL trends, and fault reports to UAV operators and maintenance engineers, closing the loop back to real-world maintenance action.

## **4.2 Edge vs. Cloud Split**

Data ingestion, the physics model, and a lightweight (ONNX-exported) version of the Fault and RUL models are designed to run at the edge (onboard the UAV or at the Ground Control Station) so that core health monitoring keeps working under degraded connectivity. The full AI/ML analytics pipeline, health fusion, historical storage, and the dashboard backend run in the cloud/server layer — see Section 11 (Deployment Architecture) for the concrete free-tier mapping used for the hackathon build.

# **5. Repository Structure**

A single monorepo keeps the frontend, backend, ML training code, simulation engine, and edge code versioned together against one architecture — appropriate for a team-sized hackathon build that still needs to look production-grade.

aerotwin/  
├── frontend/ # React + TypeScript operator/maintenance dashboard  
│ ├── src/  
│ │ ├── components/ # Reusable UI: charts, alert cards, health gauges  
│ │ ├── pages/ # Route-level views: Dashboard, Missions, Alerts, Fleet  
│ │ ├── hooks/ # useTelemetryStream (WebSocket), useAuth, useApi  
│ │ ├── services/ # apiClient.ts — typed REST client for the backend  
│ │ ├── store/ # Zustand store: live engine state, auth session  
│ │ ├── types/ # Shared TypeScript interfaces (mirrors backend schemas)  
│ │ └── App.tsx # Route definitions and top-level layout  
│ ├── public/ # Static assets, favicon, manifest  
│ ├── tests/ # Jest + React Testing Library specs  
│ ├── .env.example # VITE\_API\_URL, VITE\_WS\_URL placeholders  
│ └── package.json  
│  
├── backend/ # FastAPI application (REST + WebSocket)  
│ ├── app/  
│ │ ├── api/ # Versioned routers: auth, telemetry, faults, rul, missions...  
│ │ │ └── v1/  
│ │ ├── core/ # config.py (env settings), security.py (JWT), logging.py  
│ │ ├── models/ # SQLAlchemy ORM models — one file per entity (Section 7)  
│ │ ├── schemas/ # Pydantic request/response schemas  
│ │ ├── services/ # Business logic: health\_fusion.py, alert\_engine.py  
│ │ ├── ws/ # WebSocket connection manager, live telemetry broadcaster  
│ │ ├── db/ # session.py, base.py, Alembic migration environment  
│ │ └── main.py # FastAPI app instance, router + middleware registration  
│ ├── tests/ # pytest suite (unit + integration, uses a test DB container)  
│ ├── alembic/ # Auto-generated migration scripts  
│ ├── .env.example # DATABASE\_URL, MQTT\_BROKER\_URL, JWT\_SECRET placeholders  
│ └── requirements.txt  
│  
├── ml/ # Model training, evaluation, and export  
│ ├── data/ # raw/ and processed/ — gitignored, tracked via DVC pointers  
│ ├── notebooks/ # EDA and experiment notebooks (one per model)  
│ ├── training/  
│ │ ├── fault\_model/ # ALFA-based 7-class fault classifier training script  
│ │ ├── rul\_model/ # C-MAPSS-based LSTM/XGBoost RUL regressor  
│ │ ├── bearing\_model/ # CWRU-based FFT + classifier training script  
│ │ ├── aux\_model/ # AI4I 2020 + engine-failure transfer-learning script  
│ │ └── physics\_model/ # Thermodynamic solver + calibration against spec sheets  
│ ├── models/ # Exported .onnx artifacts + model\_card.md per model  
│ ├── evaluation/ # Held-out test metrics, confusion matrices, RUL error plots  
│ └── requirements.txt  
│  
├── simulation/ # Mission simulation & replay engine  
│ ├── mission\_profiles/ # Sample/reference profiles (altitude, temp, throttle)  
│ ├── replay\_engine/ # Reconstructs a historical mission from stored telemetry  
│ └── scenario\_generator/ # Builds synthetic what-if profiles for pre-mission testing  
│  
├── edge/ # Onboard / GCS edge-deployment code  
│ ├── can\_interface/ # python-can / SocketCAN listener → MQTT publisher  
│ ├── inference/ # ONNX Runtime inference for Fault + RUL at the edge  
│ └── telemetry\_publisher/ # Buffers and republishes data during connectivity loss  
│  
├── infra/ # Infrastructure as configuration  
│ ├── docker/ # Dockerfiles for frontend, backend, ml-inference  
│ ├── docker-compose.yml # Local dev stack: backend, db, mqtt, redis, frontend  
│ └── nginx/ # Reverse proxy config for production  
│  
├── docs/  
│ ├── architecture/ # Architecture diagram source + exported images  
│ ├── api/ # OpenAPI export / Postman collection  
│ └── dataset-guide/ # Dataset & Model Collection Guide (see project history)  
│  
├── .github/  
│ └── workflows/ # ci.yml (lint+test), deploy.yml (build+deploy on push to main)  
│  
├── .env.example # Root-level shared environment variable reference  
├── README.md # Setup, run, and contribution instructions  
└── LICENSE

***Note:*** *ml/data/ is intentionally gitignored — raw and processed datasets are tracked by pointer (DVC or a documented download script) rather than committed, to keep the repository small and reproducible.*

# **6. Technology Stack**

## **6.1 Frontend**

| **Technology** | **Purpose in AeroTwin** |
| --- | --- |
| React 18 + TypeScript + Vite | Operator/maintenance dashboard SPA — type-safe, fast dev/build cycle. |
| Tailwind CSS | Utility-first styling for the dashboard's health cards, alert banners, and layout. |
| Recharts / Plotly.js | RUL trend lines, health-score gauges, telemetry time-series charts. |
| Zustand | Lightweight client-side state for live engine state and auth session. |
| Native WebSocket API | Live telemetry and alert push from the backend without polling. |

## **6.2 Backend**

| **Technology** | **Purpose in AeroTwin** |
| --- | --- |
| FastAPI (Python 3.11) | REST API + WebSocket server; async-native, matches the ML stack's language. |
| Uvicorn / Gunicorn | ASGI server for running FastAPI in development and production. |
| Pydantic v2 | Request/response validation and schema definitions. |
| SQLAlchemy 2.0 + Alembic | ORM and versioned database migrations. |
| python-can | CAN bus / SocketCAN interface for engine telemetry acquisition. |
| paho-mqtt | MQTT publish/subscribe client used by the edge gateway and ingestion service. |

## **6.3 Database**

| **Technology** | **Purpose in AeroTwin** |
| --- | --- |
| PostgreSQL 15 | Primary relational store: users, missions, fault/RUL predictions, alerts. |
| TimescaleDB (Postgres extension) | Hypertables for high-frequency telemetry\_readings; native time-bucket queries and compression. |
| Redis | Caching layer for dashboard summary queries and WebSocket session/presence state. |

## **6.4 AI / ML**

| **Technology** | **Purpose in AeroTwin** |
| --- | --- |
| PyTorch | Fault classifier and RUL LSTM model training. |
| scikit-learn | Bearing/vibration classifier, Aux model, evaluation metrics. |
| XGBoost | RUL regression baseline and Aux transfer-learning model. |
| ONNX / ONNX Runtime | Framework-agnostic model export for edge inference. |
| NumPy / SciPy / pandas | Signal processing (FFT for bearing model), feature engineering, data wrangling. |
| MLflow (self-hosted) | Experiment tracking and the model registry referenced in Section 7. |

## **6.5 DevOps**

| **Technology** | **Purpose in AeroTwin** |
| --- | --- |
| Docker + Docker Compose | Local and production parity across frontend, backend, DB, MQTT, Redis. |
| GitHub Actions | CI/CD pipelines (Section 6.9). |
| Nginx / Caddy | Reverse proxy, TLS termination, static asset serving. |

## **6.6 Cloud / Deployment**

| **Technology** | **Purpose in AeroTwin** |
| --- | --- |
| Vercel or Netlify (free tier) | Frontend static build hosting with CDN and automatic preview deploys. |
| Render or Railway (free tier) | Backend API + ML inference container hosting. |
| Supabase (free tier) or self-hosted VM | Managed Postgres/Auth, or self-hosted TimescaleDB on a free-tier VM (e.g. Oracle Cloud Free Tier) when the Timescale extension is needed. |
| Cloudflare R2 (free tier) | Object storage for historical CAN logs and exported model artifacts. |
| HiveMQ Cloud (free tier) or self-hosted Mosquitto | MQTT broker for edge-to-cloud telemetry transport. |

## **6.7 Testing**

| **Technology** | **Purpose in AeroTwin** |
| --- | --- |
| pytest + pytest-asyncio | Backend unit and integration tests, including async endpoint tests. |
| httpx.AsyncClient | Programmatic API testing against the FastAPI app. |
| Jest + React Testing Library | Frontend component and hook tests. |
| Locust | Load testing the telemetry ingestion and WebSocket broadcast path. |

## **6.8 Authentication**

| **Technology** | **Purpose in AeroTwin** |
| --- | --- |
| JWT (access + refresh tokens) | Stateless authentication issued by the backend; no third-party identity provider, by design — see Section 10. |
| passlib (bcrypt) | Password hashing for locally managed operator/engineer accounts. |
| Role-based access control (RBAC) | Roles: operator, maintenance\_engineer, program\_manager, admin — enforced per-endpoint. |

## **6.9 CI/CD**

| **Technology** | **Purpose in AeroTwin** |
| --- | --- |
| GitHub Actions — ci.yml | On every pull request: lint (ruff/eslint), type-check, run pytest and Jest suites. |
| GitHub Actions — deploy.yml | On merge to main: build Docker images, push to registry, trigger Render/Vercel deploy hooks. |
| Alembic migration check | CI step that fails the build if a model change has no matching migration. |

## **6.10 New / Complex Technologies Explained**

A few pieces of this stack are less familiar than a typical CRUD web app and are worth explaining individually, since the team is using them for the first time.

### **TimescaleDB**

A PostgreSQL extension purpose-built for time-series data. Engine telemetry arrives at high frequency (potentially per-second per sensor) — TimescaleDB's 'hypertables' automatically partition this data by time, which keeps queries like "show CHT for engine X over the last 6 hours" fast even as the table grows into millions of rows, and its built-in compression keeps storage cost near zero on a free-tier VM. It is used exactly like a normal Postgres table from SQLAlchemy — the partitioning is transparent to the application code.

### **ONNX / ONNX Runtime**

ONNX (Open Neural Network Exchange) is a shared file format that a model trained in PyTorch or scikit-learn/XGBoost can be exported to, then run with ONNX Runtime on hardware that doesn't have the original training framework installed — including a resource-constrained edge device like a Raspberry Pi or Jetson Nano onboard the UAV/GCS. This is what lets the same Fault and RUL models run both in the cloud inference service and at the edge without maintaining two separate implementations.

### **MQTT + python-can (CAN bus telemetry acquisition)**

CAN bus (Controller Area Network) is the standard in-vehicle/in-engine data bus that the UAV's ECU/FADEC communicates over; python-can with SocketCAN reads it directly. MQTT is a lightweight publish/subscribe messaging protocol designed for exactly this kind of intermittent, bandwidth-constrained telemetry link — the edge gateway publishes each reading as a small message, and the cloud ingestion service subscribes and consumes it, decoupling the two so the edge keeps buffering locally if the network briefly drops.

### **Physics-Informed Modeling (hybrid physics + ML)**

Rather than a pure black-box ML model, the physics model independently computes what the engine's temperatures, pressures, and power output should be from thermodynamic first principles (an Otto-cycle-based solver calibrated against manufacturer performance maps). The gap between this expected behavior and the actual sensor reading is then fed into the ML models as an extra feature. This is what allows the system to flag a genuinely novel failure mode the ML models were never trained on — the physics model doesn't need training data to know something is off.

### **WebSocket Live Telemetry Streaming**

Unlike a typical REST request/response cycle, a WebSocket connection stays open, letting the backend push new engine-state updates to the dashboard the moment they're computed, instead of the frontend having to poll an endpoint every few seconds. FastAPI supports this natively; the frontend keeps one connection per session via a custom `useTelemetryStream` hook.

### **Federated-Learning Readiness (design consideration, not yet implemented)**

Because each edge node already runs local ONNX inference, the architecture leaves room for a future federated-learning setup where each UAV/GCS fine-tunes its local model copy and only the model-weight updates (not raw telemetry) are synced back centrally. This is called out in Section 3.3 as a future-readiness point — it is not part of the initial hackathon build, but nothing in the current design would need to be re-architected to add it.

# **7. Database Design**

PostgreSQL 15 with the TimescaleDB extension. telemetry\_readings is implemented as a TimescaleDB hypertable (partitioned on ts) because of its high write volume; every other table is a standard relational table. All primary keys use UUIDs (gen\_random\_uuid()) except telemetry\_readings, which uses a BIGINT identity column for hypertable-compatible ordering.

## **7.1 users**

Operators, maintenance engineers, program managers, and admins who log into the dashboard.

| **Column** | **Data Type** | **Constraints** |
| --- | --- | --- |
| id | UUID | PRIMARY KEY, default gen\_random\_uuid() |
| full\_name | VARCHAR(120) | NOT NULL |
| email | VARCHAR(255) | NOT NULL, UNIQUE |
| password\_hash | VARCHAR(255) | NOT NULL |
| role | VARCHAR(30) | NOT NULL, CHECK IN ('operator','maintenance\_engineer','program\_manager','admin') |
| is\_active | BOOLEAN | NOT NULL, DEFAULT true |
| created\_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() |

**Primary Key:** id **Foreign Keys:** —

**Relationships:** One user acknowledges many alerts; one user logs many maintenance\_logs entries.

**Indexes:** UNIQUE index on email; index on role for RBAC filtering.

## **7.2 uav\_assets**

Each physical MALE UAV airframe tracked by the system.

| **Column** | **Data Type** | **Constraints** |
| --- | --- | --- |
| id | UUID | PRIMARY KEY, default gen\_random\_uuid() |
| tail\_number | VARCHAR(20) | NOT NULL, UNIQUE |
| uav\_model | VARCHAR(60) | NOT NULL |
| status | VARCHAR(20) | NOT NULL, CHECK IN ('active','maintenance','grounded','retired') |
| created\_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() |

**Primary Key:** id **Foreign Keys:** —

**Relationships:** One uav\_asset is fitted with one engine (current); flies many missions.

**Indexes:** UNIQUE index on tail\_number.

## **7.3 engines**

The physical aero-piston engine fitted to a UAV asset — the core entity everything else attaches to.

| **Column** | **Data Type** | **Constraints** |
| --- | --- | --- |
| id | UUID | PRIMARY KEY, default gen\_random\_uuid() |
| uav\_asset\_id | UUID | NOT NULL, REFERENCES uav\_assets(id) |
| engine\_serial\_no | VARCHAR(60) | NOT NULL, UNIQUE |
| engine\_type | VARCHAR(60) | NOT NULL |
| total\_operating\_hours | NUMERIC(10,2) | NOT NULL, DEFAULT 0 |
| installed\_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() |

**Primary Key:** id **Foreign Keys:** uav\_asset\_id → uav\_assets.id

**Relationships:** One engine generates many telemetry\_readings, fault\_predictions, rul\_predictions, bearing\_health\_readings, and maintenance\_logs.

**Indexes:** UNIQUE index on engine\_serial\_no; index on uav\_asset\_id.

## **7.4 missions**

A single UAV flight/mission, with its environmental and operating profile.

| **Column** | **Data Type** | **Constraints** |
| --- | --- | --- |
| id | UUID | PRIMARY KEY, default gen\_random\_uuid() |
| uav\_asset\_id | UUID | NOT NULL, REFERENCES uav\_assets(id) |
| mission\_type | VARCHAR(40) | NOT NULL, e.g. 'ISR', 'test-flight', 'endurance' |
| start\_time | TIMESTAMPTZ | NOT NULL |
| end\_time | TIMESTAMPTZ | NULL — set on mission completion |
| environmental\_profile | JSONB | NOT NULL, DEFAULT '{}' — altitude, ambient temp, throttle profile |

**Primary Key:** id **Foreign Keys:** uav\_asset\_id → uav\_assets.id

**Relationships:** One mission is recorded during many telemetry\_readings.

**Indexes:** Index on uav\_asset\_id; index on start\_time for chronological queries.

## **7.5 telemetry\_readings**

High-frequency raw and preprocessed sensor data — implemented as a TimescaleDB hypertable partitioned on ts.

| **Column** | **Data Type** | **Constraints** |
| --- | --- | --- |
| id | BIGINT | PRIMARY KEY, IDENTITY |
| engine\_id | UUID | NOT NULL, REFERENCES engines(id) |
| mission\_id | UUID | NULL, REFERENCES missions(id) |
| ts | TIMESTAMPTZ | NOT NULL — hypertable partitioning key |
| rpm | REAL | NOT NULL |
| cht | REAL | NOT NULL |
| egt | REAL | NOT NULL |
| oil\_pressure | REAL | NOT NULL |
| oil\_temp | REAL | NOT NULL |
| fuel\_flow | REAL | NOT NULL |
| vibration\_x | REAL | NULL |
| vibration\_y | REAL | NULL |
| vibration\_z | REAL | NULL |

**Primary Key:** id (composite with ts for the hypertable) **Foreign Keys:** engine\_id → engines.id; mission\_id → missions.id

**Relationships:** Many readings belong to one engine and (optionally) one mission.

**Indexes:** Hypertable chunk index on ts; composite index on (engine\_id, ts DESC) for latest-state queries.

## **7.6 fault\_predictions**

Output of the Fault model (7-class classifier) — one row per inference run.

| **Column** | **Data Type** | **Constraints** |
| --- | --- | --- |
| id | UUID | PRIMARY KEY, default gen\_random\_uuid() |
| engine\_id | UUID | NOT NULL, REFERENCES engines(id) |
| model\_version\_id | UUID | NOT NULL, REFERENCES model\_registry(id) |
| ts | TIMESTAMPTZ | NOT NULL, DEFAULT now() |
| fault\_class | VARCHAR(40) | NOT NULL, CHECK IN 7 defined classes |
| confidence | REAL | NOT NULL, CHECK (confidence BETWEEN 0 AND 1) |

**Primary Key:** id **Foreign Keys:** engine\_id → engines.id; model\_version\_id → model\_registry.id

**Relationships:** Many predictions per engine; each produced by exactly one model\_registry version; may trigger an alert.

**Indexes:** Composite index on (engine\_id, ts DESC).

## **7.7 rul\_predictions**

Output of the RUL model — remaining useful life estimate per inference run.

| **Column** | **Data Type** | **Constraints** |
| --- | --- | --- |
| id | UUID | PRIMARY KEY, default gen\_random\_uuid() |
| engine\_id | UUID | NOT NULL, REFERENCES engines(id) |
| model\_version\_id | UUID | NOT NULL, REFERENCES model\_registry(id) |
| ts | TIMESTAMPTZ | NOT NULL, DEFAULT now() |
| rul\_hours | REAL | NOT NULL |
| degradation\_index | REAL | NOT NULL, CHECK (degradation\_index BETWEEN 0 AND 1) |

**Primary Key:** id **Foreign Keys:** engine\_id → engines.id; model\_version\_id → model\_registry.id

**Relationships:** Many predictions per engine; each produced by exactly one model\_registry version; may trigger an alert.

**Indexes:** Composite index on (engine\_id, ts DESC).

## **7.8 bearing\_health\_readings**

Output of the Bearing/vibration model.

| **Column** | **Data Type** | **Constraints** |
| --- | --- | --- |
| id | UUID | PRIMARY KEY, default gen\_random\_uuid() |
| engine\_id | UUID | NOT NULL, REFERENCES engines(id) |
| ts | TIMESTAMPTZ | NOT NULL, DEFAULT now() |
| fault\_location | VARCHAR(40) | NOT NULL, CHECK IN ('healthy','inner\_race','outer\_race','rolling\_element') |
| severity\_score | REAL | NOT NULL, CHECK (severity\_score BETWEEN 0 AND 1) |

**Primary Key:** id **Foreign Keys:** engine\_id → engines.id

**Relationships:** Many readings per engine; may trigger an alert.

**Indexes:** Composite index on (engine\_id, ts DESC).

## **7.9 maintenance\_logs**

Service/maintenance actions recorded against an engine.

| **Column** | **Data Type** | **Constraints** |
| --- | --- | --- |
| id | UUID | PRIMARY KEY, default gen\_random\_uuid() |
| engine\_id | UUID | NOT NULL, REFERENCES engines(id) |
| logged\_by | UUID | NOT NULL, REFERENCES users(id) |
| ts | TIMESTAMPTZ | NOT NULL, DEFAULT now() |
| action\_taken | VARCHAR(120) | NOT NULL |
| notes | TEXT | NULL |

**Primary Key:** id **Foreign Keys:** engine\_id → engines.id; logged\_by → users.id

**Relationships:** Many logs per engine, each attributed to one user.

**Indexes:** Index on engine\_id.

## **7.10 alerts**

Actionable alerts raised by the fault, RUL, or bearing models, or by the health-fusion rule engine.

| **Column** | **Data Type** | **Constraints** |
| --- | --- | --- |
| id | UUID | PRIMARY KEY, default gen\_random\_uuid() |
| engine\_id | UUID | NOT NULL, REFERENCES engines(id) |
| acknowledged\_by | UUID | NULL, REFERENCES users(id) |
| source | VARCHAR(30) | NOT NULL, CHECK IN ('fault\_model','rul\_model','bearing\_model','health\_fusion') |
| severity | VARCHAR(20) | NOT NULL, CHECK IN ('info','warning','critical') |
| is\_acknowledged | BOOLEAN | NOT NULL, DEFAULT false |
| created\_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() |

**Primary Key:** id **Foreign Keys:** engine\_id → engines.id; acknowledged\_by → users.id

**Relationships:** Many alerts per engine; each optionally acknowledged by one user.

**Indexes:** Index on (engine\_id, is\_acknowledged); index on severity for dashboard filtering.

## **7.11 model\_registry**

Version-tracked record of every trained model deployed to the inference service.

| **Column** | **Data Type** | **Constraints** |
| --- | --- | --- |
| id | UUID | PRIMARY KEY, default gen\_random\_uuid() |
| model\_name | VARCHAR(40) | NOT NULL, CHECK IN ('fault\_model','rul\_model','bearing\_model','aux\_model') |
| version | VARCHAR(20) | NOT NULL |
| framework | VARCHAR(20) | NOT NULL, e.g. 'pytorch','xgboost','sklearn' |
| trained\_at | TIMESTAMPTZ | NOT NULL |
| validation\_score | REAL | NOT NULL |
| is\_active | BOOLEAN | NOT NULL, DEFAULT false |

**Primary Key:** id **Foreign Keys:** —

**Relationships:** One model\_registry row is referenced by many fault\_predictions or rul\_predictions rows.

**Indexes:** UNIQUE index on (model\_name, version); index on is\_active for fast lookup of the current production model.

## **7.12 Entity-Relationship Diagram**

|  |
| --- |
| **[Diagram placeholder]**  *er\_diagram.png* |

*Figure 7.1 — AeroTwin entity-relationship diagram.*

# **8. API Design**

All endpoints are versioned under /api/v1. Authentication is via short-lived JWT access tokens (see Section 6.8); role names in the Authentication column indicate the minimum role required in addition to a valid token.

| **Endpoint** | **Method** | **Auth** | **Purpose** |
| --- | --- | --- | --- |
| /api/v1/auth/login | POST | None | Authentication |
| /api/v1/auth/refresh | POST | Refresh token | Authentication |
| /api/v1/telemetry/ingest | POST | Edge device API key | Telemetry |
| /api/v1/engines/{engine\_id}/telemetry/latest | GET | Bearer JWT | Telemetry |
| /api/v1/engines/{engine\_id}/telemetry | GET | Bearer JWT | Telemetry |
| /api/v1/engines/{engine\_id}/faults/latest | GET | Bearer JWT | Fault / RUL / Bearing |
| /api/v1/engines/{engine\_id}/rul | GET | Bearer JWT | Fault / RUL / Bearing |
| /api/v1/engines/{engine\_id}/bearing-health | GET | Bearer JWT | Fault / RUL / Bearing |
| /api/v1/engines/{engine\_id}/health-score | GET | Bearer JWT | Health & Dashboard |
| /api/v1/dashboard/summary | GET | Bearer JWT | Health & Dashboard |
| /api/v1/missions | POST | Bearer JWT | Missions & Simulation |
| /api/v1/missions/{mission\_id} | GET | Bearer JWT | Missions & Simulation |
| /api/v1/simulation/run | POST | Bearer JWT | Missions & Simulation |
| /api/v1/alerts | GET | Bearer JWT | Alerts |
| /api/v1/alerts/{alert\_id}/acknowledge | PATCH | Bearer JWT | Alerts |
| /api/v1/engines/{engine\_id}/maintenance-logs | POST | Bearer JWT | Maintenance |
| /api/v1/models | GET | Bearer JWT | Model Registry |
| /ws/engines/{engine\_id}/live | WebSocket | Bearer JWT | Live streaming |

## **8.1 Authentication**

### **POST /api/v1/auth/login**

|  |  |
| --- | --- |
| **Authentication** | None (issues token) |
| **Request** | { email, password } |
| **Response** | { access\_token, refresh\_token, expires\_in, role } |
| **Validation** | email format; password non-empty; rate-limited to 5 attempts/min per IP. |
| **Errors** | 401 invalid credentials · 423 account locked · 422 malformed body |

### **POST /api/v1/auth/refresh**

|  |  |
| --- | --- |
| **Authentication** | Refresh token (body) |
| **Request** | { refresh\_token } |
| **Response** | { access\_token, expires\_in } |
| **Validation** | Refresh token must be valid, unexpired, and unrevoked. |
| **Errors** | 401 invalid/expired token · 422 malformed body |

## **8.2 Telemetry**

### **POST /api/v1/telemetry/ingest**

|  |  |
| --- | --- |
| **Authentication** | Edge device API key (header) |
| **Request** | { engine\_id, mission\_id?, ts, rpm, cht, egt, oil\_pressure, oil\_temp, fuel\_flow, vibration\_x?, vibration\_y?, vibration\_z? } |
| **Response** | { status: "accepted", id } |
| **Validation** | engine\_id must exist; ts not in the future; numeric fields within physically plausible sensor ranges. |
| **Errors** | 400 out-of-range value · 401 invalid API key · 404 unknown engine\_id · 429 rate limit exceeded |

### **GET /api/v1/engines/{engine\_id}/telemetry/latest**

|  |  |
| --- | --- |
| **Authentication** | Bearer JWT |
| **Request** | Path: engine\_id |
| **Response** | { ts, rpm, cht, egt, oil\_pressure, oil\_temp, fuel\_flow, vibration\_x, vibration\_y, vibration\_z } |
| **Validation** | engine\_id must be a valid UUID the caller has role-based access to. |
| **Errors** | 401 unauthenticated · 403 forbidden (wrong role/asset) · 404 no readings yet |

### **GET /api/v1/engines/{engine\_id}/telemetry**

|  |  |
| --- | --- |
| **Authentication** | Bearer JWT |
| **Request** | Query: from, to, limit (default 500, max 5000) |
| **Response** | [{ ts, rpm, cht, egt, ... }, ...] |
| **Validation** | from < to; range capped at 30 days per request to protect the hypertable. |
| **Errors** | 400 invalid range · 401/403 as above |

## **8.3 Fault / RUL / Bearing**

### **GET /api/v1/engines/{engine\_id}/faults/latest**

|  |  |
| --- | --- |
| **Authentication** | Bearer JWT |
| **Request** | Path: engine\_id |
| **Response** | { ts, fault\_class, confidence, model\_version } |
| **Validation** | engine\_id validity + access check. |
| **Errors** | 401/403 · 404 no prediction yet |

### **GET /api/v1/engines/{engine\_id}/rul**

|  |  |
| --- | --- |
| **Authentication** | Bearer JWT |
| **Request** | Query: from?, to? (defaults to last 90 days) |
| **Response** | [{ ts, rul\_hours, degradation\_index }, ...] |
| **Validation** | engine\_id validity + access check; date range sanity. |
| **Errors** | 400 invalid range · 401/403 · 404 no data |

### **GET /api/v1/engines/{engine\_id}/bearing-health**

|  |  |
| --- | --- |
| **Authentication** | Bearer JWT |
| **Request** | Path: engine\_id |
| **Response** | { ts, fault\_location, severity\_score } |
| **Validation** | engine\_id validity + access check. |
| **Errors** | 401/403 · 404 no data |

## **8.4 Health & Dashboard**

### **GET /api/v1/engines/{engine\_id}/health-score**

|  |  |
| --- | --- |
| **Authentication** | Bearer JWT |
| **Request** | Path: engine\_id |
| **Response** | { combined\_score, contributing\_factors: [...], last\_updated } |
| **Validation** | engine\_id validity + access check. |
| **Errors** | 401/403 · 404 not yet computed |

### **GET /api/v1/dashboard/summary**

|  |  |
| --- | --- |
| **Authentication** | Bearer JWT |
| **Request** | Query: fleet? (admin/program\_manager only) |
| **Response** | { engines: [{ engine\_id, tail\_number, health\_score, open\_alerts }] } |
| **Validation** | fleet-wide view restricted to program\_manager/admin roles. |
| **Errors** | 401 unauthenticated · 403 role not permitted |

## **8.5 Missions & Simulation**

### **POST /api/v1/missions**

|  |  |
| --- | --- |
| **Authentication** | Bearer JWT (operator+) |
| **Request** | { uav\_asset\_id, mission\_type, start\_time, environmental\_profile } |
| **Response** | { id, status: "scheduled" } |
| **Validation** | uav\_asset\_id must exist and be status='active'; start\_time not in the past. |
| **Errors** | 400 invalid profile · 401/403 · 409 asset already on an active mission |

### **GET /api/v1/missions/{mission\_id}**

|  |  |
| --- | --- |
| **Authentication** | Bearer JWT |
| **Request** | Path: mission\_id |
| **Response** | { id, uav\_asset\_id, mission\_type, start\_time, end\_time, environmental\_profile, telemetry\_summary } |
| **Validation** | mission\_id validity + access check. |
| **Errors** | 401/403 · 404 not found |

### **POST /api/v1/simulation/run**

|  |  |
| --- | --- |
| **Authentication** | Bearer JWT (engineer+) |
| **Request** | { engine\_id, mode: "replay"|"what\_if", mission\_id? | environmental\_profile? } |
| **Response** | { simulation\_id, status: "queued" } — result retrieved via GET /simulation/{id} |
| **Validation** | exactly one of mission\_id / environmental\_profile must be supplied depending on mode. |
| **Errors** | 400 conflicting mode/payload · 401/403 · 404 mission not found |

## **8.6 Alerts**

### **GET /api/v1/alerts**

|  |  |
| --- | --- |
| **Authentication** | Bearer JWT |
| **Request** | Query: engine\_id?, severity?, is\_acknowledged? (default: false) |
| **Response** | [{ id, engine\_id, source, severity, is\_acknowledged, created\_at }, ...] |
| **Validation** | severity, if given, must be one of info/warning/critical. |
| **Errors** | 400 invalid filter value · 401/403 |

### **PATCH /api/v1/alerts/{alert\_id}/acknowledge**

|  |  |
| --- | --- |
| **Authentication** | Bearer JWT (maintenance\_engineer+) |
| **Request** | Path: alert\_id (empty body) |
| **Response** | { id, is\_acknowledged: true, acknowledged\_by, acknowledged\_at } |
| **Validation** | alert must not already be acknowledged. |
| **Errors** | 401/403 · 404 not found · 409 already acknowledged |

## **8.7 Maintenance**

### **POST /api/v1/engines/{engine\_id}/maintenance-logs**

|  |  |
| --- | --- |
| **Authentication** | Bearer JWT (maintenance\_engineer+) |
| **Request** | { action\_taken, notes? } |
| **Response** | { id, ts, logged\_by } |
| **Validation** | action\_taken required, max 120 chars. |
| **Errors** | 400 validation error · 401/403 · 404 engine not found |

## **8.8 Model Registry**

### **GET /api/v1/models**

|  |  |
| --- | --- |
| **Authentication** | Bearer JWT (engineer+) |
| **Request** | Query: model\_name? |
| **Response** | [{ id, model\_name, version, framework, trained\_at, validation\_score, is\_active }, ...] |
| **Validation** | model\_name, if given, must be one of the four known model types. |
| **Errors** | 400 invalid filter · 401/403 |

## **8.9 Live streaming**

### **WebSocket /ws/engines/{engine\_id}/live**

|  |  |
| --- | --- |
| **Authentication** | Bearer JWT (as query param at handshake) |
| **Request** | WebSocket upgrade; no body |
| **Response** | Server pushes { type: "telemetry"|"alert"|"health\_score", payload } messages as they occur |
| **Validation** | Token validated at handshake; connection closed (4401) if invalid or expired. |
| **Errors** | 4401 unauthenticated · 4403 forbidden · 1011 server error |

# **9. Data Flow**

## **9.1 Where Data Comes From**

Live data originates at the engine's sensors (RPM, CHT, EGT, oil pressure/temperature, fuel flow, triaxial vibration), read over CAN bus / SocketCAN by an edge gateway. Historical/reference data comes from the four training datasets described in the project's Dataset & Model Collection Guide (ALFA, NASA C-MAPSS, CWRU, AI4I 2020 + engine failure dataset), plus manufacturer performance maps for the physics model and NASA DASHlink flight profiles used to validate simulation scenario diversity.

## **9.2 How It Is Processed**

The edge gateway timestamps each reading and publishes it over MQTT. The backend's ingestion service subscribes, validates the payload against physically plausible sensor ranges, and hands it to a preprocessing pipeline that resamples, converts units, and extracts model-ready features. From there, data splits three ways: straight to storage (TimescaleDB), to the physics model for an expected-vs-actual comparison, and to the AI/ML inference service.

## **9.3 How AI Is Used**

The preprocessed feature window and the physics model's deviation signal are passed to whichever of the four models is relevant — the Fault and Bearing models run on every window for continuous anomaly screening, the RUL model runs on a longer rolling window, and the Aux model contributes a supporting cross-domain score. Their outputs are written back to the database and combined by the health fusion service into one score.

## **9.4 How the Database Stores It**

Raw and preprocessed telemetry lands in the telemetry\_readings hypertable, partitioned by time for fast recent-data queries and automatic compression of older data. Model outputs land in their own tables (fault\_predictions, rul\_predictions, bearing\_health\_readings), each referencing the model\_registry version that produced them, so every prediction is traceable to the exact model that made it.

## **9.5 How the Frontend Receives It**

The dashboard first loads a REST snapshot (latest telemetry, current health score, open alerts) on page load, then opens a WebSocket connection to /ws/engines/{engine\_id}/live to receive incremental telemetry, alert, and health-score updates as they're computed — so the operator's view stays current without polling.

## **9.6 End-to-End Flow Diagram**

***Note:*** *The full sensor-to-dashboard data flow diagram is provided on the following landscape page for readability.*

# **10. External Integrations**

Scoped strictly to what AeroTwin actually needs — a defense-relevant health-monitoring system has no reason to pull in payment, government, or general-purpose AI APIs, and pulling them in anyway would work against the indigenous, self-hosted positioning described in Section 3.4.

| **Integration Type** | **Used?** | **Technology / Provider** | **Purpose & Scope** |
| --- | --- | --- | --- |
| Maps | Yes | Leaflet.js + OpenStreetMap tiles (free, self-hostable) | Visualizing a mission's flight path and environmental context on the dashboard. No commercial maps API — avoids per-request billing and keeps mission location data off a third-party server. |
| Notification — Email | Yes | SMTP (self-hosted) or a free-tier transactional provider (e.g. Resend) | Critical/warning alert delivery to maintenance engineers when the dashboard isn't open. |
| Notification — SMS | Optional / future | Not implemented in the hackathon build | Deferred: adds a recurring per-message cost that conflicts with the zero-cost constraint; email + in-dashboard alerts cover the initial scope. |
| Cloud Storage | Yes | Cloudflare R2 (free tier) or Supabase Storage | Archiving historical CAN logs and versioned ONNX model artifacts referenced by the model\_registry. |
| Webhooks | Yes | Outbound HTTPS webhook on critical alerts | Lets a Ground Control Station or an external fleet-management tool subscribe to AeroTwin alerts without polling. |
| Authentication Providers | No | Not applicable — see Section 6.8 | Deliberate: a defense-context login system uses locally managed JWT auth with RBAC rather than a third-party OAuth provider, to avoid depending on an external identity service for access to a sensitive system. |
| AI APIs (external) | No | Not applicable | All four ML models and the physics model are self-hosted and self-trained — no calls to an external AI/LLM API, preserving data sovereignty over engine telemetry. |
| Government APIs | No | Not applicable | The problem statement is an internal DRDO engine-monitoring system; there is no public government data source in the data path. |
| Payment Gateways | No | Not applicable | AeroTwin is an internal defense monitoring tool, not a billed product. |

# **11. Deployment Architecture**

The deployment is deliberately split into an edge layer (onboard the UAV / at the Ground Control Station) and a cloud layer, so core health monitoring keeps functioning under degraded or intermittent connectivity — a realistic condition for a MALE UAV on a long-endurance mission.

|  |
| --- |
| **[Diagram placeholder]**  *deployment.png* |

*Figure 11.1 — AeroTwin deployment architecture: edge layer (UAV/GCS) and free-tier cloud layer.*

## **11.1 Edge Layer**

* A Raspberry Pi or Jetson Nano-class edge gateway reads the engine ECU over CAN bus / SocketCAN.
* Runs the ONNX-exported Fault and RUL models locally, so a critical fault is flagged even if the MQTT link to the cloud is temporarily down.
* Buffers telemetry locally and republishes on reconnect — no data loss during a short connectivity gap.

## **11.2 Cloud Layer (hackathon / zero-cost configuration)**

* Frontend: React production build hosted on Vercel or Netlify's free tier, served over their CDN.
* Backend API + ML inference: containerized FastAPI app on Render or Railway's free tier.
* Database: self-hosted TimescaleDB + PostgreSQL on a free-tier VM (e.g. Oracle Cloud Free Tier) where the Timescale extension is needed, or Supabase's free tier for the non-time-series tables.
* MQTT broker: self-hosted Mosquitto on the same free VM, or HiveMQ Cloud's free tier.
* Redis cache and Cloudflare R2 object storage, both within their respective free tiers.
* CI/CD: GitHub Actions builds and deploys on every push to main (see Section 6.9).

## **11.3 Environments**

| **Environment** | **Purpose** | **Notes** |
| --- | --- | --- |
| Local development | Developer machines | docker-compose.yml spins up backend, DB, MQTT, Redis, and frontend together. |
| Staging | Pre-demo validation | Same free-tier services as production, separate database and MQTT topics. |
| Production / demo | Hackathon demonstration and any pilot deployment | Free-tier services as shown in Figure 11.1; see Section 11.4 for the upgrade path. |

## **11.4 Upgrade Path Beyond the Hackathon Build**

The free-tier cloud layer is a deliberate choice for the zero-cost constraint of the hackathon phase, not a ceiling on the architecture. For an actual DRDO pilot deployment, the same containers move onto an on-premises or defense-cloud-hosted Kubernetes cluster with no application code changes — only the infra/ configuration and environment variables change, because the backend, database schema, and ML inference service are already fully containerized and stateless where it matters.

# **12. Scalability Strategy**

## **12.1 Data Layer**

* TimescaleDB hypertable chunking on telemetry\_readings keeps per-query cost roughly constant as historical data grows into the millions of rows.
* Continuous aggregates (Timescale materialized rollups) pre-compute hourly/daily summaries for dashboard charts, avoiding a full-resolution scan for long time ranges.
* Native compression on chunks older than 7 days keeps storage cost low even at fleet scale.

## **12.2 Application Layer**

* The FastAPI backend is stateless per request (session state lives in Redis/JWT, not in-process), so it can be horizontally scaled behind the reverse proxy simply by running more container replicas.
* The ML inference service is a separate container from the API service, so inference load (which is CPU/GPU-bound) can be scaled independently of API request load.
* Redis caching absorbs repeated dashboard summary queries so they don't hit PostgreSQL on every page load.

## **12.3 Ingestion Layer**

* MQTT decouples the edge gateway from the ingestion service — if the ingestion service or database is briefly overloaded, MQTT's QoS 1 delivery and the edge's local buffering prevent data loss rather than requiring the edge to retry a synchronous HTTP call.
* The ingestion service consumes asynchronously and can be scaled to multiple consumer instances behind the same MQTT topic as the number of UAVs grows.

## **12.4 Model Serving**

* ONNX Runtime supports batched inference, so the cloud inference service can process telemetry from multiple engines in a single batch rather than one request at a time.
* Edge-deployed models are quantized where needed to fit the resource envelope of the onboard/GCS hardware without materially affecting fault-detection accuracy.

## **12.5 Fleet-Level Scale-Out**

* Every table is already partitioned conceptually by engine\_id / uav\_asset\_id, so scaling from one test-rig engine to a full UAV fleet requires no schema change — only more rows.
* The architecture's edge/cloud split means fleet-wide bandwidth grows with the number of alerts and summarized telemetry, not raw per-second sensor data, since the bulk of inference already happens at the edge.
* Federated-learning readiness (Section 3.3) is the long-term scale-out path for model quality: as the fleet grows, each edge node's local fine-tuning improves the shared model without ever centralizing raw telemetry from every aircraft.