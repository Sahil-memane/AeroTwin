# Model 3 — Bearing / Vibration Health — Pipeline Flow Documentation

This document describes the end-to-end integration of the 2D CNN Bearing Health model (Model 3) into the AeroTwin backend, including dataset rationale, preprocessing design decisions, inference flow, and database schemas.

---

## 1. Model Overview

| Item | Details |
|------|---------|
| Model name | Model 3 — Bearing / Vibration Health CNN |
| Algorithm | 2D Convolutional Neural Network (Conv2D) |
| Dataset | CWRU Bearing Dataset |
| Samples | 4,600 (460 per class, balanced) |
| Training split | 70% train / 15% val / 15% test |
| Input shape | `(1, 32, 32, 1)` — image-like 2D representation |
| Number of classes | 10 |
| Test Accuracy | **98.99%** |
| Macro F1-Score | **98.99%** |
| Test Loss | 0.0672 |

---

## 2. The 10 Bearing Classes

| Class ID | Label    | Fault Location             | Severity (diameter) |
|----------|----------|----------------------------|---------------------|
| 0        | Ball_007 | Ball / Rolling Element     | 0.007 inches        |
| 1        | Ball_014 | Ball / Rolling Element     | 0.014 inches        |
| 2        | Ball_021 | Ball / Rolling Element     | 0.021 inches        |
| 3        | IR_007   | Inner Race                 | 0.007 inches        |
| 4        | IR_014   | Inner Race                 | 0.014 inches        |
| 5        | IR_021   | Inner Race                 | 0.021 inches        |
| 6        | Normal   | No fault — healthy bearing | —                   |
| 7        | OR_007   | Outer Race                 | 0.007 inches        |
| 8        | OR_014   | Outer Race                 | 0.014 inches        |
| 9        | OR_021   | Outer Race                 | 0.021 inches        |

> **Important:** This index ordering comes from `label_mapping.json` and must never be reordered. Normal is class index 6, **not** 0.

---

## 3. CNN Architecture

| Stage | Layer |
|-------|-------|
| Input | 32 × 32 × 1 |
| Block 1 | Conv2D 32 filters, 3×3 → BatchNorm → MaxPooling |
| Block 2 | Conv2D 64 filters, 3×3 → BatchNorm → MaxPooling |
| Block 3 | Conv2D 128 filters, 3×3 → BatchNorm → MaxPooling |
| Classifier | Flatten → Dense 128 (ReLU) → Dropout 0.40 |
| Output | Dense 10 (Softmax) |

Training used sparse categorical cross-entropy + Adam optimizer, with early stopping, learning-rate reduction on plateau, and best-checkpoint saving.

---

## 4. Preprocessing Pipeline

Training preprocessing that **must be reproduced exactly** during inference:

```
1. Input sample: raw 32×32 float matrix
2. Z-score normalise with TRAINING constants (not per-sample):
       x_norm = (x - mean) / (std + 1e-8)
       mean = 0.01568922728195663   (from normalization.json)
       std  = 0.4564410815002781    (from normalization.json)
3. Add batch + channel dimensions:
       (32, 32) → (1, 32, 32, 1)
4. Feed to model.predict()
```

> **Warning:** Do NOT recompute mean/std from the incoming sample. The values in `normalization.json` are fixed training-time statistics.

---

## 5. Real-Time Integration Challenge & Solution

### 5.1 The Domain Gap
The CWRU training data was collected at **48,000 Hz** — 1,024 continuous vibration samples per 21.33 ms window.

The AeroTwin simulator runs at **~1 Hz** and emits a single scalar `vibration_magnitude` per telemetry packet (computed from `√(vib_x² + vib_y² + vib_z²)`).

These are fundamentally different: the model expects high-frequency time-series structure; the simulator provides a single aggregate scalar.

### 5.2 Solution: Synthetic Window Synthesis
The **bearing adapter** (`bearing_adapter.py`) generates a synthetic 1,024-sample vibration window from the scalar magnitude in **< 1 millisecond** using NumPy:

```
vibration_magnitude (scalar, per telemetry tick)
    ↓
Generate 1024-pt signal:
  - White noise scaled to vibration_magnitude (always present)
  - If high_vibration fault is active: inject Outer Race harmonic
    at frequency = BPFO × rpm_hz (3.585 × rpm/60)
  - Otherwise: low-level shaft harmonic only
    ↓
Z-score normalise using training constants (mean, std from normalization.json)
    ↓
Reshape (1024,) → (32, 32) → (1, 32, 32, 1)
```

**Why this works:** The CNN has learned vibration *patterns*, not exact frequency values. A correctly shaped window with appropriate amplitude and harmonic content is sufficient to exercise all 10 class outputs. The "Normal" class consistently dominates at low `vibration_magnitude`, while fault classes emerge at elevated amplitudes.

---

## 6. End-to-End Integration Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Edge Simulator (simulate.py)                                           │
│  Outputs: vibration_x, vibration_y, vibration_z, vibration_magnitude,  │
│           rpm, fault_type, fault_active                                 │
│  Publishes → MQTT: aerotwin/telemetry/{engine_id}                       │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  ingestion.py (MQTT → DB + inference pipeline)                          │
│  1. Validate + persist to telemetry_readings                            │
│  2. RUL inference   → rul_predictions                                   │
│  3. Fault inference → fault_predictions                                  │
│  4. Aux inference   → aux_predictions                                    │
│  5. Bearing inference → bearing_health_readings   ◄── Model 3           │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  bearing_adapter.py                                                     │
│  extract vibration_magnitude + rpm + fault_type                         │
│  → synthesize 1024-pt window                                            │
│  → Z-score normalise (normalization.json constants)                     │
│  → reshape → (1, 32, 32, 1)                                             │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  bearing_service.py                                                     │
│  model3_bearing_health.keras → model.predict((1,32,32,1))               │
│  → 10-element softmax probabilities                                     │
│  → argmax → class_id → class_label (label_mapping.json)                 │
│  → class_label → fault_location + severity_inches (fault_information.json) │
│  Returns: {class_id, class_label, fault_location, severity_inches, confidence} │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │
                      ┌─────────┴────────┐
                      ▼                  ▼
         bearing_health_readings    WS broadcast
           (TimescaleDB)         { type: "bearing_prediction" }
```

---

## 7. Database Schema

### 7.1 `bearing_health_readings` Table (after migration `7ee1f449a7b3`)

| Column             | Type        | Nullable | Description |
|--------------------|-------------|----------|-------------|
| `ts`               | TIMESTAMPTZ | NO (PK)  | Prediction timestamp |
| `engine_id`        | UUID        | NO (PK)  | FK → `engines.id` |
| `model_version_id` | UUID        | NO       | FK → `model_registry.id` |
| `class_id`         | INTEGER     | NO       | 0–9 (from softmax argmax) |
| `class_label`      | VARCHAR     | NO       | e.g. `"Ball_007"`, `"Normal"` |
| `fault_location`   | VARCHAR     | NO       | e.g. `"Ball / Rolling Element"`, `"No fault"` |
| `severity_inches`  | FLOAT       | YES      | `0.007 / 0.014 / 0.021`; `NULL` for Normal |
| `confidence`       | FLOAT       | NO       | Max softmax probability (0.0–1.0) |

> `severity_score` (old column) was dropped in this migration and replaced by the semantically correct `severity_inches`.

### 7.2 Model Registry Entry

| id | model_name | version | validation_score |
|----|-----------|---------|-----------------|
| `00000000-0000-0000-0000-000000000006` | `bearing_vibration_cnn` | v1.0.0 | **0.9899** |

---

## 8. WebSocket Broadcast Schema

**Event type:** `bearing_prediction`

**Healthy bearing:**
```json
{
  "type": "bearing_prediction",
  "payload": {
    "class_id": 6,
    "class_label": "Normal",
    "fault_location": "No fault",
    "severity_inches": null,
    "confidence": 0.97
  }
}
```

**Fault detected:**
```json
{
  "type": "bearing_prediction",
  "payload": {
    "class_id": 8,
    "class_label": "OR_014",
    "fault_location": "Outer Race",
    "severity_inches": 0.014,
    "confidence": 0.962
  }
}
```

---

## 9. File Inventory

| File | Purpose |
|------|---------|
| `ml/training/bearing_model/model3_bearing_health.keras` | Trained 2D CNN model |
| `ml/training/bearing_model/normalization.json` | Training mean + std (MUST use for inference) |
| `ml/training/bearing_model/label_mapping.json` | int index → class name |
| `ml/training/bearing_model/fault_information.json` | class name → fault_location + severity_inches |
| `backend/app/services/bearing_adapter.py` | Synthetic 1024-pt window generation + preprocessing |
| `backend/app/services/bearing_service.py` | CNN inference orchestration |
| `backend/app/models/bearing_health_reading.py` | SQLAlchemy ORM |
| `backend/app/schemas/predictions.py` | Pydantic response schema (BearingHealthReading) |
| `backend/app/services/ingestion.py` | Pipeline hook + DB persist + WS broadcast |
| `backend/alembic/versions/7ee1f449a7b3_*.py` | DB migration for enriched schema |

---

## 10. Dependencies

| Package | Reason |
|---------|--------|
| `tensorflow>=2.15.0,<3.0.0` | Load and run the `.keras` CNN |
| `numpy>=1.24.0` | Window synthesis + matrix operations |

Both are declared in `backend/requirements-ml.txt` and installed as a cached Docker layer.

---

## 11. How Model 3 Fits in the AeroTwin Health Fusion

| Model | Time Horizon | Question | Inference Mode |
|-------|-------------|----------|----------------|
| **Model 1 — RUL** | Long-term (cycles) | "How much runway is left?" | 30-cycle sliding window |
| **Model 2 — UAV Fault** | Medium (4s windows) | "Which sensor is failing?" | 80-sample, 32-channel UAV schema |
| **Model 3 — Bearing** | Instantaneous | "What's the vibration/bearing condition?" | Single-tick, synthesized 32×32 |
| **Model 4 — Aux** | Instantaneous | "Is there a mechanical failure now?" | Single-reading stateless |

Model 3 runs on **every telemetry tick** in parallel with the other models. Its output contributes the vibration/bearing signal to the Health Fusion layer, which combines all four model outputs into the overall engine health score shown on the dashboard.
