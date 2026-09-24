# Model 4 — Auxiliary Predictive Maintenance (Milling Machine + Engine Failure)

**Domain:** Industrial Equipment — CNC Milling Machine (AI4I 2020)
**Task:** Binary Machine Failure Detection + Specific Failure Type Identification
**Dataset:** ai4i2020-selected-columns.csv (10,000 records) & ai4i2020.csv (full, 14 columns)
**Final models saved in:** final_model/

## 1. Overview
The Auxiliary Predictive Maintenance model (Model 4) is designed to run real-time inference on a stream of incoming telemetry to predict whether a machine failure is occurring or imminent, and if so, classify the specific root cause.

## 2. Dataset Properties
- **Total records:** 10,000 machining operations
- **Healthy operations:** 9,661 (96.61%)
- **Machine failures:** 339 (3.39%) — severe class imbalance
- **Failure types:** 5 distinct failure modes (TWF, HDF, PWF, OSF, RNF)
- **ML task:** Binary classification + multi-label failure type identification

## 3. Inputs & Outputs

### 3.1 Input — 6 Raw Sensor Readings
| Input Field | Type | Example | Description |
|---|---|---|---|
| Type | String | 'L' / 'M' / 'H' | Product quality variant (Low / Medium / High) |
| Air temperature [K] | Float | 298.1 | Ambient room temperature in Kelvin |
| Process temperature [K] | Float | 308.6 | Machining process temperature in Kelvin |
| Rotational speed [rpm] | Float | 1551.0 | Spindle rotational speed in RPM |
| Torque [Nm] | Float | 42.8 | Motor torque output in Newton-metres |
| Tool wear [min] | Float | 230.0 | Accumulated tool usage time in minutes |

The model internally engineers 11 physical features — Power_kW, Overstrain (Torque × Wear), Heat_Stress (ΔT × RPM), Temp_Diff, Torque_per_RPM, and others — from these 6 raw fields before either stage sees the data.

### 3.2 Output — Complete Failure Analysis
| Output Field | Type | Example |
|---|---|---|
| failure_status | String | CRITICAL / MACHINE FAILURE |
| risk_level | String | LOW / MODERATE / HIGH / CRITICAL |
| failure_probability_pct | Float | 99.67% |
| detected_failure_types | JSON | [{"code": "OSF", "full_name": "Overstrain Failure", "probability": 0.96}] |
| primary_failure_cause | String | OSF — Overstrain Failure |
| recommended_action | String | Replace worn tooling. Reduce cutting depth. |

## 4. Stage 1: Binary Failure Model — Results
Six candidate binary classifiers, each paired with a different class-imbalance strategy, were trained and compared on the same feature set.
**Winning model:** Balanced Random Forest Classifier — highest accuracy and best precision/recall balance.

| Model | Balancing | 5-Fold CV Acc | Test Acc | Precision | Recall | F1 | ROC-AUC |
|---|---|---|---|---|---|---|---|
| Balanced RF — selected | Class weights | 98.88% | 98.90% | 85.94% | 80.88% | 0.8333 | 0.9691 |
| LightGBM | SMOTE | 98.97% | 98.55% | 76.00% | 83.82% | 0.7972 | 0.9771 |

**Feature Importance — Top Predictors of Machine Failure**
- Overstrain = Tool_Wear_min × Torque — the dominant physical overload indicator
- Torque [Nm] — direct mechanical load on the spindle
- Power_kW = 2π × N × τ / 60000 — electrical-to-mechanical energy load
- Tool_Wear_min — accumulated physical degradation
- RPM & Temp_Diff — heat dissipation and speed limits

## 5. Stage 2: Failure Type Classification — Results
One dedicated classifier is trained per failure mode, since each mode has a different mechanism and a different (very small) number of positive cases.

| Code | Full Name | Cases | Test Acc | F1 | ROC-AUC | Method |
|---|---|---|---|---|---|---|
| HDF | Heat Dissipation Failure | 115 (1.15%) | 100.00% | 1.0000 | 1.0000 | LightGBM + SMOTE |
| PWF | Power Failure | 95 (0.95%) | 100.00% | 1.0000 | 1.0000 | LightGBM + SMOTE |
| OSF | Overstrain Failure | 98 (0.98%) | 99.80% | 0.8947 | 0.9996 | LightGBM + SMOTE |
| TWF | Tool Wear Failure | 46 (0.46%) | 98.45% | 0.0 (ML) | 0.9605 | RF + rule: Wear>200 & Torque>60 |
| RNF | Random / Unknown Failure | 19 (0.19%) | 99.75% | 0.0 (ML) | 0.5987 | Inherently stochastic — 12% baseline |

Note on TWF & RNF: with fewer than 50 positive cases, the ML classifiers cannot learn a reliable minority-class pattern. TWF falls back to a physics-based rule (tool wear > 200 min AND torque > 60 Nm), and RNF is treated as inherently random by definition rather than being modeled.

## 6. Risk Level Thresholds
| Failure Probability | Risk Level | Recommended Action |
|---|---|---|
| 0% – 15% | LOW | Continue normal operation |
| 15% – 50% | MODERATE | Schedule preventive inspection |
| 50% – 80% | HIGH | Halt and service before next shift |
| 80% – 100% | CRITICAL | Emergency shutdown — immediate maintenance |

## 7. System Integration — Plugging Model 4 Into the Production Pipeline

### 7.1 Real-Time Integration Flow
New sensor reading arrives (per machining cycle)
↓
Load `final_model/*.joblib` once at service startup — keep in memory
↓
Internal feature engineering — 11 physical features, using metadata's pinned column order
↓
Stage 1 — `binary_failure_model.joblib` scores is_failure / failure_probability_pct
↓
failure_probability_pct  →  risk_level via thresholds (Section 7)
↓
If is_failure = True  →  `failure_type_classifiers.joblib` runs Stage 2 (+ TWF/RNF rule fallbacks)
↓
Unified output assembled: failure_status, risk_level, failure_probability_pct, detected_failure_types, primary_failure_cause, recommended_action
↓
Pushed to alerting / maintenance-scheduling layer

### 7.2 Combining Model 4 With Model 2 (RUL) for a Unified Health Signal
Model 4 and Model 2 answer different questions on different time horizons, and the production system is designed to combine both rather than pick one:
- Model 2 (RUL) runs on a rolling 30-cycle sensor window and outputs a countdown in cycles — it answers "how much runway is left?"
- Model 4 runs on the single latest reading and outputs a risk level plus (if relevant) a specific failure mode — it answers "is something wrong right now, and what?"

### 7.3 Statelessness & Latency
Unlike Model 2, Model 4 requires no rolling window or historical buffer — every prediction is computed from the single latest sensor reading, so it can score a new reading the instant it arrives without waiting to accumulate cycle history. 

### 7.4 Dependencies & Versioning
Required at runtime: `joblib`, `numpy`, `pandas`, `scikit-learn`, and `lightgbm` (used by the HDF/PWF/OSF classifiers in Stage 2). No other services or feature stores are required — the model is fully self-contained once the `final_model/` folder is deployed.
