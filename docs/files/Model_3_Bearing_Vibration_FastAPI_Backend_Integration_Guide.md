# Model 3 — Bearing / Vibration Health
## FastAPI Backend Integration Guide

AeroTwin — AI-Enabled Real-Time Digital Twin for Aero-Piston Engines

**Purpose**: This document is a backend handoff guide for integrating Model 3 into the AeroTwin backend using FastAPI. It describes the trained model's inputs, outputs, classes, and preprocessing requirements to ensure correct real-time predictions.

---

## 1. Model 3 Overview

Model 3 is the bearing/vibration health classification model. It is a CNN-based multiclass classifier trained to recognize 10 bearing-condition classes based on high-frequency vibration data.

**Inference Flow:**
1. Vibration / bearing input
2. 32 × 32 representation
3. Add channel dimension
4. `(1, 32, 32, 1)`
5. CNN Model 3
6. 10-class Softmax Output

---

## 2. Model 3 Training / Data Contract

- **Algorithm**: 2D Convolutional Neural Network (CNN)
- **Dataset**: CWRU Vibration Dataset (10-Class Vibration Signal Fault Classification)
- **Input Dimensions**: `(1, 32, 32, 1)`
- **Data Type**: `float64`
- **Normalization**: Z-score normalized (mean and std). Normalized values range from ~-6.29 to +6.83.
- **Sampling**: 1024 vibration samples over 21.33 ms (48,000 Hz).

---

## 3. Model Classes

The backend must preserve the exact class names and the exact index-to-class mapping used when the model was trained. 

| Class ID | String Label | Fault Location / Component | Severity (Damage Diameter) |
|----------|--------------|----------------------------|----------------------------|
| 0        | Normal       | No fault — healthy bearing | —                          |
| 1        | IR_007       | Fault on the Inner Race    | 0.007 inches               |
| 2        | IR_014       | Fault on the Inner Race    | 0.014 inches               |
| 3        | IR_021       | Fault on the Inner Race    | 0.021 inches               |
| 4        | Ball_007     | Fault on the Ball          | 0.007 inches               |
| 5        | Ball_014     | Fault on the Ball          | 0.014 inches               |
| 6        | Ball_021     | Fault on the Ball          | 0.021 inches               |
| 7        | OR_007       | Fault on the Outer Race    | 0.007 inches               |
| 8        | OR_014       | Fault on the Outer Race    | 0.014 inches               |
| 9        | OR_021       | Fault on the Outer Race    | 0.021 inches               |

---

## 4. What Model 3 Returns

The CNN produces a 10-element softmax probability vector. The backend should derive:
- `predicted_class_index` — index of the maximum probability
- `predicted_class` — human-readable class name
- `confidence` — maximum softmax probability
- `probabilities` — optional full 10-class probability vector

---

## 5. Important Input Requirement

Model 3 does not accept arbitrary raw telemetry fields such as RPM, temperature, torque, or power as its direct model input. The trained model expects a specifically transformed vibration signature (a 32x32 image-like representation). 

The accelerometer collects 1024 continuous vibration values over ~21.3 milliseconds. These 1024 values are Z-score normalized and reshaped into a 32 × 32 matrix.

---

## 6. Recommended Backend Architecture

```text
AeroTwin telemetry / vibration pipeline
              ↓
      Vibration preprocessing (Z-score norm)
              ↓
       32 × 32 representation
              ↓
     Add channel (1, 32, 32, 1)
              ↓
            Model 3
```

---

## 7. Model Files Required
- `model3_bearing_health.keras` (or `.h5` equivalent)
- `label_mapping.json` (Optional but recommended for consistency)

---

## 8. Recommended Folder Structure

```text
backend/
├── main.py
├── models/
│   └── model_3_bearing/
│       ├── model3_bearing_health.keras
│       ├── label_mapping.json
│       └── preprocessing_config.json
```

---

## 9. FastAPI Request Options

There are two possible API designs. Option B is recommended for AeroTwin since the edge simulator sends raw vibration data.

### Option B — Backend sends a raw vibration window
```json
POST /model3/predict-raw

{
  "vibration_x": [...],
  "vibration_y": [...],
  "vibration_z": [...]
}
```
This option requires implementing the exact training-time preprocessing inside the backend (collecting 1024 samples, normalizing, and reshaping).

---

## 10. Requirements

- `fastapi`
- `uvicorn`
- `tensorflow` (Required to load `.keras` CNN model)
- `numpy`
- `pydantic`

---

## 11. How Backend Should Use the Result

```text
Model 3 prediction
       ↓
predicted_class + confidence
       ↓
bearing_health_readings (Database) + WebSocket Broadcast
       ↓
Dashboard
```

Model 3 should provide the classification result to the health-fusion layer. The health-fusion layer can decide how this signal contributes to the overall Engine Status.

---
End of Model 3 FastAPI Backend Integration Guide
