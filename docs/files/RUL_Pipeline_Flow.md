# RUL Model Integration Flow

This document outlines the end-to-end data flow for the Remaining Useful Life (RUL) prediction model in the AeroTwin application.

## 1. Data Generation (Edge Simulator)
The flow begins with the edge simulator (`edge/telemetry_publisher/simulate.py`), which simulates a Rotax 912/914 aero-piston engine. 
- It generates core telemetry metrics: `rpm`, `cht`, `egt`, `oil_pressure`, `oil_temp`, `fuel_flow`, and `vibration_x/y/z`.
- **Physics Integration**: For every cycle, the simulator uses a thermodynamic physics solver (`ml/training/physics_model`) to compute the real-time engine deviation from its ideal state (`deviation_score`), as well as missing external metrics like `throttle` and `altitude_m`.
- The telemetry is published to the local MQTT broker (`aerotwin-mqtt`) on the topic `aerotwin/telemetry/{engine_id}`.

## 2. Ingestion & Storage (Backend)
The FastAPI backend runs an MQTT subscriber (`backend/app/services/ingestion.py`).
- Upon receiving a telemetry payload, the ingestion service validates it and inserts it into the **TimescaleDB hypertable** named `telemetry_readings`. 
- TimescaleDB ensures high-performance time-series ingestion and partitioning.

## 3. RUL Pipeline & Translating Adapter
Immediately after storing the telemetry, the ingestion service passes the data to the RUL Inference Service (`backend/app/services/rul_service.py`).
- **Translating Adapter**: Because the XGBoost model was trained on NASA C-MAPSS turbofan data, the piston engine telemetry cannot be fed directly into it. The `rul_adapter.py` acts as a translating layer. It maps the piston parameters (like `rpm`, `throttle`, and the physics `deviation_score`) into equivalent C-MAPSS sensor variables using linear interpolation based on predefined physical boundaries (`input_ranges.csv`).

### The 24 C-MAPSS Mappings
The adapter maps the incoming telemetry into the exact 24-feature vector expected by the model. The most critical degradation signals are mapped to the model's highest-importance features:
1. `setting_1`: Altitude (converted from meters to kft)
2. `setting_2`: Mach number proxy (derived from throttle & RPM)
3. `setting_3`: Throttle resolver angle
4. `s_11` *(27.4% importance)*: HPC outlet static pressure ← **Physics `deviation_score`**
5. `s_4` *(19.1% importance)*: LPT outlet total temp ← **CHT (Cylinder Head Temp)**
6. `s_17` *(16.8% importance)*: Bleed enthalpy ← **Vibration Magnitude**
7. `s_3` *(6.9% importance)*: HPC outlet total temp ← **EGT (Exhaust Gas Temp)**
8. `s_9` *(3.5% importance)*: Physical core speed ← **RPM**

The remaining secondary sensors (`s_1`, `s_2`, `s_5`-`s_8`, `s_10`, `s_12`-`s_16`, `s_18`-`s_21`) are mapped via linear interpolation from other telemetry values like `oil_temp`, `oil_pressure`, `fuel_flow`, and `throttle`.

- **Sliding Window**: The RUL service maintains an in-memory 30-cycle sliding window (buffer) for each active engine. 

## 4. Feature Extraction & XGBoost Inference
Once the sliding window reaches 30 cycles, feature extraction begins:
- The service extracts **216 statistical features** in total. For each of the 24 scaled C-MAPSS variables over the 30-cycle window, it computes 9 distinct metrics:
  1. Mean
  2. Standard Deviation
  3. Slope (via simple linear regression)
  4. Mean of the last 5 cycles
  5. Last value
  6. Difference between first and last value
  7. Maximum value
  8. Minimum value
  9. Range (Max - Min)
- These 216 features are fed into the loaded **XGBoost** model (`xgb_rul_model.json`).
- The model outputs a raw RUL prediction (in cycles/hours), which is clamped to a maximum of 125 cycles. A degradation index (0.0 to 1.0) and conformal prediction intervals are also computed.

## 5. Storage & Broadcast
The final step is persisting and broadcasting the prediction:
- The predicted RUL is stored in the TimescaleDB table `rul_predictions`.
- The backend's Connection Manager (`backend/app/ws/connection_manager.py`) broadcasts both the raw telemetry and the computed RUL prediction over WebSockets to any connected frontend clients (e.g., the web dashboard).

## Summary Diagram
`Edge Simulator (MQTT) -> Ingestion Service -> TimescaleDB (Telemetry) -> Translating Adapter -> Sliding Window -> XGBoost Model -> TimescaleDB (RUL) -> WebSockets`
