# AeroTwin: Unique Selling Propositions (USPs)

This document outlines the key differentiators of the AeroTwin system for the DRDO Smart India Hackathon (Problem Statement ID 26054). While standard ML models (Fault Classification, Remaining Useful Life) are baseline expectations, AeroTwin implements a robust analytical and interactive layer *around* these models, significantly elevating the system's operational value and directly addressing DRDO's advanced requirements.

## 1. Physics-ML Disagreement Score (Physics-Informed AI)
AeroTwin runs a deterministic physics model and an ML pipeline in parallel. Rather than just processing both separately, we explicitly quantify the gap between them.
- **How it works**: Computes a live "disagreement score" comparing physics-predicted degradation against ML-predicted degradation.
- **Value**: A widening gap serves as an early warning for novel fault types (which the ML model hasn't seen) or physics-model blind spots. It acts as a meta-anomaly detector, providing a highly advanced implementation of DRDO's "physics-informed AI" requirement.

## 2. Explainability Layer (SHAP) on Fusion Output
Moving beyond black-box ML outputs, AeroTwin provides clear reasoning for its predictions.
- **How it works**: Implements a SHAP (SHapley Additive exPlanations) feature-attribution layer on the fusion output.
- **Value**: Instead of just showing a fault/RUL number, the dashboard explicitly states *why* an alert was generated (e.g., "Flagged due to rising vibration + EGT drift, not oil pressure"). This directly fulfills the "Explainable AI for fault diagnosis" wishlist item.

## 3. Data-Drift & Model-Trust Monitor
Given the translation of piston telemetry into synthetic turbofan features (domain adaptation), monitoring model confidence is critical.
- **How it works**: Tracks how far live inputs drift from the training distribution, exposing a "model confidence" indicator alongside predictions.
- **Value**: Operators see not just a fault probability, but how much they should *trust* that prediction at any given moment. This transparently handles domain gaps and demonstrates a mature approach to operational ML safety.

## 4. GARUDA Conversational Maintenance Assistant
AeroTwin integrates an advanced Natural Language interface for operators, leveraging modern GenAI capabilities.
- **How it works**: A lightweight RAG-style assistant grounded in live telemetry, fusion outputs, and SHAP explainability values. 
- **Value**: Operators can ask questions like "Why is this engine flagged?" or "What's driving the RUL drop?" and receive contextual, natural-language answers. This provides a massive usability advantage over static dashboards and stands out as a highly sophisticated differentiator.

## 5. Counterfactual "What-If" Simulation Queries
AeroTwin elevates simulation from a passive replay tool to an active decision-support engine.
- **How it works**: Operators can input hypothetical parameters (e.g., "If I hold throttle at 70% for the next 30 minutes, what's the projected RUL impact?") and see simulated outcomes without affecting live telemetry.
- **Value**: This turns the "mission replay capability" requirement into a proactive mission planning and safety tool, allowing operators to test recovery strategies safely.

## 6. Secure, Tamper-Evident Telemetry Log
Security and data integrity are paramount for defense applications.
- **How it works**: Implements a hash-chained audit trail for maintenance actions and alerts, where each record's hash includes the previous one.
- **Value**: Directly addresses the "secure telemetry architecture" requirement, ensuring that historical data and maintenance logs cannot be silently altered.

## 7. Fleet-Level Aggregation View
AeroTwin is designed for scalable deployment, not just isolated engine demonstrations.
- **How it works**: A fleet aggregation dashboard that identifies correlated trends across multiple engines (e.g., "3 of 12 UAVs show correlated vibration drift under the same mission profile").
- **Value**: Demonstrates systems-thinking and aligns closely with how DRDO would operationally deploy a health monitoring system across multiple drone assets.

---

## Technical Stack Overview
*Based on recent additions (post-commit `eedd4ee3cc02a890eef1a4ed796e816901664f45`):*

### Edge & Data Ingestion
- **Edge Inference**: Python scripts, ONNX Runtime (for offline Fault & RUL buffering).
- **CAN Interface**: Hardware abstraction layer for reading CAN bus telemetry.
- **Messaging**: Eclipse Mosquitto (MQTT Broker).

### Backend & Core Services
- **Framework**: FastAPI (Python).
- **Database**: TimescaleDB (PostgreSQL extension for high-ingestion time-series data).
- **ORM & Migrations**: SQLAlchemy & Alembic (managing schema for telemetry limits and fault states).
- **Cache / PubSub**: Redis (for caching and WebSocket message broadcasting).
- **Simulation**: Sandboxed "What-If" Scenario Generator and Mission Replay Engine.

### AI & Machine Learning
- **Models**: XGBoost / LightGBM pipelines for Fault classification and Remaining Useful Life (RUL).
- **Physics Integration**: Deterministic Otto Cycle simulator for physics-informed deviations.
- **GARUDA Copilot**: LLM-powered Retrieval-Augmented Generation (RAG) assistant.

### Frontend & User Interface
- **Core**: React 18, Vite, TypeScript, Tailwind CSS.
- **Visualization**: WebGL / Three.js (for the interactive 3D Engine Twin).
- **Real-Time Delivery**: Native WebSockets via custom React hooks (`useEngineWebSocket.ts`).

### Infrastructure, DevOps & QA
- **Containerization**: Docker & Docker Compose (with development and production parity).
- **Reverse Proxy**: Nginx & Caddy (for SSL and edge routing).
- **Cloud Deployment**: Google Cloud Platform (GCP) with automated provisioning and bash scripts.
- **Testing**: Pytest (for extensive E2E simulation testing) and Locust (for WebSocket load testing).