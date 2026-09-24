# Auxiliary Predictive Maintenance — Pipeline Flow & Integration Documentation

This document outlines the end-to-end data flow for the Auxiliary Predictive Maintenance model (Model 4) in the AeroTwin application, including the rationale behind key design decisions.

---

## 1. Background & Dataset Selection

### 1.1 Original Proposal
The original specification proposed training Model 4 on a **combination of two datasets**:
1. **AI4I 2020 Predictive Maintenance Dataset** — 10,000 CNC milling machine operations with 5 failure modes.
2. **Engine Failure Dataset** — an additional dataset of engine-specific failure records intended to improve domain relevance for the AeroTwin piston-engine context.

### 1.2 Why Engine Failure Data Was Dropped
During experimentation, combining both datasets resulted in **significantly degraded model accuracy**:
- The two datasets have fundamentally different feature distributions, physical units, and failure mechanisms.
- The engine failure data introduced noise into the feature space that the milling-trained classifiers could not reconcile — precision and recall both dropped below acceptable thresholds.
- Class imbalance became even more severe when merging, making minority-class learning nearly impossible.

**Decision:** We retained only the AI4I 2020 Milling dataset for training. The model achieves **98.90% test accuracy** on binary failure detection and near-perfect ROC-AUC on individual failure type classifiers — metrics that would have been unachievable with the combined dataset.

### 1.3 Why This Still Works for AeroTwin
The AI4I dataset models generic **industrial equipment failure physics** — thermal stress, mechanical overload, tool degradation, and power consumption — which are universal failure mechanisms shared by CNC mills and piston engines alike. The adapter layer (Section 4) maps piston engine telemetry into the model's expected feature space, preserving the physical relationships the model learned.

---

## 2. Model Architecture

### 2.1 Two-Stage Inference Design
The model uses a **two-stage classification pipeline** instead of a single multiclass classifier, because:
- The dataset is extremely imbalanced (96.6% healthy, 3.4% failure).
- A single model would almost certainly learn to always predict "healthy."
- Splitting into two stages allows each stage to be independently optimised for its specific task.

```
Stage 1: Binary Failure Detection
  └─ "Is the machine failing right now?"
  └─ Balanced Random Forest (class-weighted)
  └─ Outputs: is_failure (bool), failure_probability_pct (float)

Stage 2: Failure Type Isolation (only invoked if Stage 1 flags failure OR probability ≥ 50%)
  └─ "What specific failure mode is occurring?"
  └─ Per-type LightGBM classifiers (HDF, PWF, OSF)
  └─ Rule-based fallbacks for TWF and RNF
  └─ Outputs: detected_failure_types (list), primary_failure_cause (string)
```

### 2.2 Stage 1 — Binary Failure Model
- **Algorithm:** Balanced Random Forest Classifier with class weights
- **Training:** 5-fold cross-validation, 80/20 stratified train-test split
- **Performance:** 98.90% accuracy, 85.94% precision, 80.88% recall, 0.97 ROC-AUC
- **File:** `ml/training/aux_model/final_model/binary_failure_model.joblib`
- **Scaler:** StandardScaler saved in `binary_failure_metadata.joblib`

### 2.3 Stage 2 — Failure Type Classifiers

| Code | Full Name                | Cases     | Method            | Test Acc | F1     | ROC-AUC |
|------|--------------------------|-----------|-------------------|----------|--------|---------|
| HDF  | Heat Dissipation Failure | 115 (1.2%)| LightGBM + SMOTE  | 100.00%  | 1.0000 | 1.0000  |
| PWF  | Power Failure            | 95 (0.95%)| LightGBM + SMOTE  | 100.00%  | 1.0000 | 1.0000  |
| OSF  | Overstrain Failure       | 98 (0.98%)| LightGBM + SMOTE  | 99.80%   | 0.8947 | 0.9996  |
| TWF  | Tool Wear Failure        | 46 (0.46%)| Physics rule       | N/A      | N/A    | N/A     |
| RNF  | Random / Unknown Failure | 19 (0.19%)| Catch-all fallback | N/A      | N/A    | N/A     |

**TWF Rule Fallback:** With only 46 positive samples, the ML classifier achieved 0.0 F1. Instead, a deterministic physics rule is used: `tool_wear > 200 min AND torque > 60 Nm`.

**RNF Fallback:** Random failures are inherently stochastic (only 19 samples, ~12% baseline). If Stage 1 flags a failure but no Stage 2 classifier activates, RNF is assigned by default.

- **File:** `ml/training/aux_model/final_model/failure_type_classifiers.joblib`
- **Metadata:** `ml/training/aux_model/final_model/failure_type_metadata.joblib`

---

## 3. Feature Engineering

### 3.1 Raw Inputs (6 fields from AI4I schema)
| Field                     | Type   | Description                              |
|---------------------------|--------|------------------------------------------|
| `Type`                    | String | Product quality variant (L / M / H)      |
| `Air temperature [K]`    | Float  | Ambient room temperature in Kelvin       |
| `Process temperature [K]`| Float  | Machining process temperature in Kelvin  |
| `Rotational speed [rpm]` | Float  | Spindle rotational speed                 |
| `Torque [Nm]`            | Float  | Motor torque output                      |
| `Tool wear [min]`        | Float  | Accumulated tool usage time              |

### 3.2 Engineered Features (11 features fed to models)
The adapter transforms the 6 raw inputs into 11 physically meaningful features:

| #  | Feature Name      | Formula / Source                              | Physical Meaning                        |
|----|-------------------|-----------------------------------------------|-----------------------------------------|
| 1  | `Type_Code`       | L→0, M→1, H→2                                | Quality grade (ordinal encoded)         |
| 2  | `Air_Temp_C`      | `Air temperature [K]` − 273.15                | Ambient temp in °C                      |
| 3  | `Process_Temp_C`  | `Process temperature [K]` − 273.15            | Process temp in °C                      |
| 4  | `Temp_Diff`       | `Process_Temp_C` − `Air_Temp_C`               | Thermal gradient (heat dissipation)     |
| 5  | `RPM`             | Direct passthrough                            | Rotational speed                        |
| 6  | `Torque`          | Direct passthrough                            | Mechanical load                         |
| 7  | `Power_kW`        | `2π × RPM × Torque / 60000`                  | Mechanical power output                 |
| 8  | `Tool_Wear_min`   | Direct passthrough                            | Cumulative degradation                  |
| 9  | `Overstrain`      | `Tool_Wear_min × Torque`                      | Combined load-degradation stress        |
| 10 | `Heat_Stress`     | `Temp_Diff × RPM`                             | Thermal-mechanical coupling             |
| 11 | `Torque_per_RPM`  | `Torque / RPM` (0 if RPM=0)                   | Specific load per revolution            |

**Top predictors of failure** (by feature importance): Overstrain > Torque > Power_kW > Tool_Wear_min > RPM.

---

## 4. Telemetry-to-Feature Adapter (`aux_adapter.py`)

Since the model was trained on CNC milling data but AeroTwin produces **piston engine telemetry**, the adapter layer bridges the domain gap:

### 4.1 Piston Engine → AI4I Mapping
| AI4I Field                | Piston Source                          | Notes                                             |
|---------------------------|----------------------------------------|---------------------------------------------------|
| `Type`                    | Hardcoded `'M'`                        | Medium quality — reasonable default for demo       |
| `Air temperature [K]`    | Fixed `298.15 K` (25°C)               | Ambient temp not available from simulator          |
| `Process temperature [K]`| `298.15 + (CHT / 10.0)`               | CHT (cylinder head temp) as proxy for process heat |
| `Rotational speed [rpm]` | `rpm` direct                           | Direct mapping — both represent rotational speed   |
| `Torque [Nm]`            | `(rpm / 100) + vibration_x`            | Synthetic torque from RPM + vibration load         |
| `Tool wear [min]`        | Accumulated wear counter               | Incremented proportionally to RPM each reading     |

### 4.2 Wear Accumulation Logic
- Wear increments by `(rpm / 3000) × (0.5 / 60)` minutes per reading (assuming ~0.5s intervals).
- Resets to 0 after 300 minutes to prevent permanent failure state in demo mode.
- In production, this would be sourced from a persistent database state or the RUL model's degradation index.

### 4.3 Statelessness Note
Unlike Model 2 (RUL) which requires a 30-cycle sliding window, the Aux Model is **fully stateless per reading** — each prediction is computed from a single telemetry packet with no historical buffer needed. The only state maintained is the per-engine `tool_wear` accumulator.

**File:** [`backend/app/services/aux_adapter.py`](file:///e:/Projects/AeroTwin/backend/app/services/aux_adapter.py)

---

## 5. Integration Flow (End-to-End)

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Edge Simulator (simulate.py)                                          │
│  Generates: rpm, cht, egt, oil_pressure, oil_temp, fuel_flow,          │
│             vibration_x/y/z, throttle, altitude_m                      │
│  Publishes → MQTT topic: aerotwin/telemetry/{engine_id}                │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Backend Ingestion Service (ingestion.py)                              │
│  1. Receives MQTT payload                                              │
│  2. Validates & stores in telemetry_readings (TimescaleDB)             │
│  3. Broadcasts raw telemetry via WebSocket                             │
│  4. Triggers RUL inference  → rul_predictions table                    │
│  5. Triggers Fault inference → fault_predictions table                 │
│  6. Triggers Aux inference  → aux_predictions table       ◄── NEW      │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Aux Adapter (aux_adapter.py)                                          │
│  Maps piston telemetry → 6 AI4I raw features → 11 engineered features  │
│  Maintains per-engine tool wear accumulator                            │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Aux Service (aux_service.py)                                          │
│  Stage 1: binary_failure_model.joblib → is_failure + probability       │
│     ↓ (if failure OR prob ≥ 50%)                                       │
│  Stage 2: failure_type_classifiers.joblib → per-type classifiers       │
│     + TWF physics rule (wear > 200 AND torque > 60)                    │
│     + RNF catch-all fallback                                           │
│  Assembles risk_level + recommended_action                             │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Database: aux_predictions (TimescaleDB)                               │
│  + WebSocket broadcast: { type: "aux_prediction", payload: {...} }     │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 6. Database Schema

### 6.1 `aux_predictions` Table
| Column                    | Type        | Nullable | Description                                |
|---------------------------|-------------|----------|--------------------------------------------|
| `ts`                      | TIMESTAMPTZ | NO (PK)  | Prediction timestamp                       |
| `engine_id`               | UUID        | NO (PK)  | Foreign key → `engines.id`                 |
| `model_version_id`        | UUID        | NO       | Foreign key → `model_registry.id`          |
| `failure_status`          | VARCHAR     | NO       | `HEALTHY` / `MACHINE FAILURE` / `CRITICAL` |
| `risk_level`              | VARCHAR     | NO       | `LOW` / `MODERATE` / `HIGH` / `CRITICAL`   |
| `failure_probability_pct` | FLOAT       | NO       | 0.0 – 100.0                                |
| `detected_failure_types`  | JSONB       | NO       | Array of `{code, full_name, probability, active, cause}` |
| `primary_failure_cause`   | VARCHAR     | YES      | e.g. `"OSF - Overstrain Failure"` or null  |
| `recommended_action`      | VARCHAR     | YES      | Human-readable maintenance recommendation  |

### 6.2 Model Registry Entry
| id                                   | model_name                 | version | is_active |
|--------------------------------------|----------------------------|---------|-----------|
| `00000000-0000-0000-0000-000000000005` | `aux_predictive_maintenance` | v1.0.0  | true      |

### 6.3 Pydantic Schema (`schemas/predictions.py`)
```python
class AuxPrediction(BaseModel):
    ts: datetime
    engine_id: UUID
    model_version_id: UUID
    failure_status: str
    risk_level: str
    failure_probability_pct: float
    detected_failure_types: list[dict]
    primary_failure_cause: Optional[str]
    recommended_action: Optional[str]
```

---

## 7. Risk Level Thresholds & Actions

| Failure Probability | Risk Level | Recommended Action                      |
|---------------------|------------|-----------------------------------------|
| 0% – 15%           | LOW        | Continue normal operation               |
| 15% – 50%          | MODERATE   | Schedule preventive inspection          |
| 50% – 80%          | HIGH       | Halt and service before next shift      |
| 80% – 100%         | CRITICAL   | Emergency shutdown — immediate maintenance |

---

## 8. WebSocket Broadcast

When a prediction is made, the ingestion service broadcasts to all connected clients for that engine:

```json
{
  "type": "aux_prediction",
  "payload": {
    "failure_status": "HEALTHY",
    "risk_level": "LOW",
    "failure_probability_pct": 5.23,
    "detected_failure_types": [],
    "primary_failure_cause": null,
    "recommended_action": "Continue normal operation"
  }
}
```

On failure detection:
```json
{
  "type": "aux_prediction",
  "payload": {
    "failure_status": "MACHINE FAILURE",
    "risk_level": "CRITICAL",
    "failure_probability_pct": 99.67,
    "detected_failure_types": [
      {
        "code": "OSF",
        "full_name": "Overstrain Failure",
        "probability": 0.96,
        "active": true,
        "cause": "Overstrain Failure"
      }
    ],
    "primary_failure_cause": "OSF - Overstrain Failure",
    "recommended_action": "Emergency shutdown — immediate maintenance"
  }
}
```

---

## 9. File Inventory

| File | Purpose |
|------|---------|
| `ml/training/aux_model/final_model/binary_failure_model.joblib` | Stage 1 Random Forest binary classifier |
| `ml/training/aux_model/final_model/binary_failure_metadata.joblib` | StandardScaler + feature column ordering |
| `ml/training/aux_model/final_model/failure_type_classifiers.joblib` | Stage 2 per-type LightGBM classifiers |
| `ml/training/aux_model/final_model/failure_type_metadata.joblib` | Failure type code-to-name mapping |
| `backend/app/services/aux_adapter.py` | Piston telemetry → AI4I feature translation |
| `backend/app/services/aux_service.py` | Two-stage inference orchestration |
| `backend/app/models/aux_prediction.py` | SQLAlchemy ORM model for `aux_predictions` table |
| `backend/app/schemas/predictions.py` | Pydantic response schema (AuxPrediction class) |
| `backend/app/services/ingestion.py` | MQTT subscriber + DB persistence + WS broadcast |

---

## 10. Dependencies

Runtime packages required for the Aux model:
- `numpy` — array operations
- `scikit-learn` — StandardScaler, Random Forest (Stage 1)
- `lightgbm` — LightGBM classifiers (Stage 2: HDF, PWF, OSF)
- `joblib` — model deserialization (`.joblib` files)

These are declared in `backend/requirements-ml.txt` and installed as a separate Docker layer in the backend image.

---

## 11. How This Model Complements Other Models

| Model | Time Horizon | Question Answered | Inference Style |
|-------|-------------|-------------------|-----------------|
| **Model 2 — RUL** | Long-term (cycles ahead) | "How much runway is left?" | 30-cycle sliding window |
| **Model 3 — Fault** | Medium-term (4-sec windows) | "Which sensor is failing?" | 80-sample buffer, 32-channel UAV schema |
| **Model 4 — Aux** | Instantaneous | "Is something mechanically wrong right now?" | Single-reading stateless |

All three models run in parallel on every incoming telemetry packet in `ingestion.py`, producing independent predictions that are stored in separate tables and broadcast via separate WebSocket event types.
