# AeroTwin Q&A

This document tracks common questions, clarifications, and design doubts regarding the AeroTwin project.

## Q: Are we using real physical hardware (e.g. real drone engines) for this project?
**A:** No. The hackathon problem statement is entirely software-focused. Since a real UAV engine isn't available during development, we use a telemetry simulator (`simulate.py`). This Python script generates realistic, physically plausible sensor data (RPM, temperatures, vibration) and publishes it via MQTT to the backend. To the software architecture, the simulator behaves exactly like a real physical edge device. This allows us to build and demo the end-to-end ingestion and ML pipeline completely in software.

## Q: Why is Mosquitto (MQTT broker) required?
**A:** Mosquitto provides a lightweight, low‑latency publish‑subscribe channel for telemetry. Our simulated edge device publishes sensor streams to Mosquitto, and the backend service subscribes to those topics. This mirrors a real UAV where a lightweight MQTT link is ideal for intermittent connectivity and minimal bandwidth usage.

## Q: How do we start the local development stack?
**A:** Run `docker compose -p aerotwin -f infra/docker/docker-compose.yml up -d`. This brings up TimescaleDB, Redis, Mosquitto, and the FastAPI backend (and later the React frontend). All services are healthy and ready to accept telemetry.

## Q: Where are the configuration values (secrets, URLs) stored?
**A:** Environment variables are defined in `.env.example` at the repository root and copied to `.env` for local runs. Variables include `DATABASE_URL`, `JWT_SECRET`, `MQTT_BROKER_URL`, and `REDIS_URL`. The backend reads them via Pydantic's `BaseSettings`.

## Q: What does the physics model do, and how does it work with `specs.py`?
**A:** The physics model (`ml/training/physics_model/otto_cycle_solver.py`) acts as a "thermodynamic digital twin" of the UAV engine. Instead of relying purely on a black-box AI model, it uses first-principles physics (specifically, the Otto cycle and the International Standard Atmosphere) to calculate exactly what the engine's temperatures (CHT, EGT), pressures, and fuel flow *should* be at any given moment, based on the current RPM, altitude, and throttle.

The `specs.py` file acts as the "DNA" of the engine. It contains all the calibration constants (like volumetric efficiency, specific heat capacity, and cooling coefficients) tuned specifically to match the performance envelope of a real Rotax 912/914 class aero-engine. 

By comparing the actual live telemetry coming from the drone against the "expected" values calculated by this physics model, we generate a real-time **deviation signal**. This deviation signal is then fed as a high-value feature into our Machine Learning models, making it much easier for the AI to detect subtle faults (like a slow oil leak or degraded cooling) long before they trigger a hard limit alert.
