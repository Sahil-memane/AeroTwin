# Understanding the RUL Domain Gap & Translation Architecture

**Context**: The AeroTwin engine is a Rotax 912/914 class piston aero-engine. True run-to-failure (R2F) datasets for this specific class of engine are not publicly available at the scale required to train a robust deep learning or gradient-boosted regression model from scratch.

To validate the machine learning architecture end-to-end without waiting years to collect physical R2F data, we integrated the **NASA C-MAPSS dataset**. 

## The Domain Gap
The C-MAPSS dataset is built for **turbofan** engines, not piston engines. 
It features 24 inputs: 3 operating settings (Altitude, Mach, Throttle) and 21 thermodynamic sensors (e.g., HPC Outlet Pressure, Fan Inlet Temp).

Our edge digital twin simulates **piston telemetry**:
- `RPM`
- `CHT` (Cylinder Head Temperature)
- `EGT` (Exhaust Gas Temperature)
- `Oil Pressure`
- `Oil Temp`
- `Fuel Flow`
- `Vibration Magnitude`
- `Physics Deviation Score` (from our thermodynamic solver)

## The Mitigation Strategy: The Translating Adapter
Rather than training a dummy model that proves nothing about real-world ML integration, we built a **Translating Adapter** (`backend/app/services/rul_adapter.py`).

This adapter acts as a mathematical bridge. It takes our live piston-engine telemetry and maps it into synthetic turbofan sensor values within the exact numerical bounds the trained XGBoost model expects.

**Key Mapping Logic**:
The C-MAPSS XGBoost model relies heavily on a subset of sensors for its degradation signal (accounting for >70% of feature importance): `s_11`, `s_4`, `s_17`, and `s_3`.

We mapped our highest-value piston degradation indicators directly to these sensors:
1. **`deviation_score`** (from our physics solver) → **`s_11`** (HPC Outlet Pressure)
2. **`vibration_magnitude`** → **`s_17`** (Bleed Enthalpy)
3. **`CHT`** → **`s_4`** (LPT Outlet Temp)
4. **`EGT`** → **`s_3`** (HPC Outlet Temp)

The remaining 17 sensors are linearly interpolated into their nominal bounds using our other telemetry variables (RPM, Oil Temp, Fuel Flow).

## Why this Architecture?
1. **End-to-End Validation**: This allows us to prove the entire pipeline (Edge Simulator → MQTT → TimescaleDB → Sliding Window → Feature Engineering → XGBoost Inference → WebSocket Broadcast) works reliably under load.
2. **Swappable Design**: The adapter isolates the domain gap. When real piston-engine run-to-failure data becomes available, the adapter can simply be deleted, and a new native XGBoost model swapped into the `rul_service.py` with zero changes to the underlying ingestion or streaming infrastructure. 
3. **Fault Responsiveness**: Because we mapped our injected physical faults (like CHT overheating or high vibration) directly to the turbofan model's most sensitive features, the dashboard accurately reflects an immediate, mathematically sound drop in Remaining Useful Life (RUL) when a fault occurs in the digital twin.
