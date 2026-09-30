# AeroTwin — Accuracy-First Enhancement Plan
## Phase-by-Phase Implementation Plan for Claude Code

### Purpose

This document is the implementation plan for improving the existing **AeroTwin** system.

The goal is **not to copy another team's UI or feature list**. Do not turn AeroTwin into a collection of demos.

The goal is:

> **Make the existing AeroTwin Digital Twin technically trustworthy, accurate, explainable, testable, and useful for actual engine-health monitoring and mission decision support.**

Prioritize **model/data correctness, validation, uncertainty, physics consistency, fault isolation, and reliable decision support** over adding many visual features.

---

# 0. Current System — Preserve This Architecture

Before changing anything, inspect the existing repository and understand the actual implementation.

Current AeroTwin architecture:

```text
Physical / Simulated Engine
        ↓
Telemetry / MQTT
        ↓
Edge Agent
        ↓
ONNX Fault + RUL inference
        ↓
Backend / FastAPI
        ↓
TimescaleDB / PostgreSQL + Redis
        ↓
┌──────────────────────────────────────────────┐
│ ML Intelligence                              │
│                                              │
│ RUL (XGBoost)                                │
│ Fault Detection (2-stage LightGBM)           │
│ Bearing Health (CNN)                         │
│ Auxiliary Prediction (sklearn)               │
│ Health Fusion                                │
│ Alert Engine                                 │
└──────────────────────────────────────────────┘
        ↓
Digital Twin / Dashboard / Missions / Alerts
        ↓
AI Copilot
        ↓
ChromaDB + Live Backend Data + LLM
```

Existing important capabilities that must NOT be broken:

- FastAPI backend
- PostgreSQL / TimescaleDB
- Redis
- MQTT
- JWT authentication
- Refresh tokens
- RBAC
- Rate limiting
- Existing API routers
- Existing WebSocket streaming
- RUL model
- Fault model
- Bearing model
- Auxiliary prediction model
- Health Fusion
- Alert engine
- Edge ONNX inference
- Offline buffering and reconnect/flush
- Mission Replay
- What-If simulation
- AI Copilot / RAG
- Existing frontend structure
- Existing tests and CI
- Docker deployment structure

Do not rewrite working modules merely to change their architecture.

---

# 1. Engineering Philosophy

Use these principles throughout every phase.

## 1.1 Accuracy before feature count

Do not add a feature merely because another project has it.

For every proposed feature ask:

1. What real problem does it solve?
2. What data does it require?
3. Can AeroTwin calculate it correctly?
4. How will it be validated?
5. What happens when the required data is missing?
6. Does it improve an operator's decision?

If these cannot be answered, do not implement the feature.

---

## 1.2 Never fabricate aerospace/engine values

The system must distinguish:

- measured telemetry
- model prediction
- derived engineering quantity
- simulation result
- historical value
- documented knowledge

Never display a simulated or placeholder value as live engine data.

Never invent:

- RUL
- fault severity
- failure threshold
- engine limits
- maintenance interval
- regulatory requirement
- physics value
- confidence
- sensor reading

---

## 1.3 Every new model output needs validation

For each model:

```text
Input
  ↓
Preprocessing
  ↓
Model
  ↓
Prediction
  ↓
Validation / sanity checks
  ↓
Confidence / quality state
  ↓
Database
  ↓
Health Fusion
  ↓
UI / Alerts / Copilot
```

Do not send raw model predictions directly to critical decision logic without validation.

---

## 1.4 Prefer graceful uncertainty

If the system does not have enough data:

```text
INSUFFICIENT DATA
```

is better than:

```text
RUL = 0
```

or an invented prediction.

The UI should explicitly distinguish:

- `VALID`
- `INSUFFICIENT_DATA`
- `STALE`
- `INVALID`
- `MODEL_UNAVAILABLE`
- `SIMULATION`
- `LIVE`

---

# 2. Phase 0 — Repository and Architecture Audit

### Objective

Before implementing anything, Claude Code must understand the current codebase.

### Tasks

Inspect:

```text
backend/
frontend/
ml/
edge/
simulation/
database/
docker/
tests/
copilot/
```

or the actual equivalent directory structure.

Find:

- model implementations
- model preprocessing
- feature engineering
- model training artifacts
- inference endpoints
- telemetry schemas
- database schemas
- WebSocket implementation
- MQTT ingestion
- Health Fusion
- alert generation
- simulation
- RUL calculation
- Copilot/RAG
- frontend data hooks
- existing tests

### Required output before modifying code

Create or update a short technical inventory:

```text
Component
Purpose
Input
Output
Source of truth
Validation
Current test coverage
Known limitation
```

### Important

Do not modify code during the first audit unless required to run the existing system.

Run the existing test suite and record the baseline.

Expected baseline should include:

- backend tests
- frontend build/typecheck
- edge tests
- model inference tests
- E2E tests if available

Do not proceed while silently ignoring existing failures.

---

# 3. Phase 1 — Establish a Model Accuracy & Data Quality Layer

## Priority: VERY HIGH

This is the most important phase.

Before adding new UI features, make sure the current intelligence is trustworthy.

### 3.1 Create a unified inference result schema

Every ML model should return structured metadata.

Example:

```json
{
  "model": "rul",
  "model_version": "rul-xgb-v1",
  "prediction": 126.4,
  "unit": "cycles",
  "status": "VALID",
  "confidence": null,
  "input_quality": "GOOD",
  "timestamp": "...",
  "latency_ms": 12.4
}
```

For a model without a statistically valid confidence value, do NOT invent one.

---

## 3.2 Add input-quality validation

Validate:

- missing values
- NaN
- infinity
- impossible values
- stale telemetry
- duplicated timestamps
- out-of-order packets
- sudden unrealistic jumps
- sensor range violations
- insufficient history/window size

Example:

```text
RPM:
  missing → INVALID
  stale → STALE
  impossible → INVALID
  valid → VALID
```

Do not hard-code arbitrary limits unless they are documented/configured.

Use configuration for engineering limits:

```yaml
telemetry_limits:
  rpm:
    min: ...
    max: ...
```

Document the source of each limit.

---

## 3.3 Add data-quality score

Create a telemetry quality indicator based on measurable properties such as:

- completeness
- freshness
- timestamp continuity
- sensor validity
- required feature availability

Do not use this as a fake "health score."

Keep:

```text
Engine Health
Telemetry Quality
Model Confidence / Validity
```

as separate concepts.

---

## 3.4 Test corrupted telemetry

Create automated tests for:

- missing RPM
- missing EGT
- NaN
- infinity
- stale telemetry
- duplicate telemetry
- out-of-order telemetry
- extreme but valid values
- impossible values
- partial telemetry

Expected behavior must be explicit.

---

# 4. Phase 2 — Fix RUL Reliability and Uncertainty

## Priority: VERY HIGH

The current system has an important UX/model issue where RUL can appear as `0 cycles` or `"window not yet full"`.

This must be corrected before adding more features.

### 4.1 Define RUL lifecycle

RUL should have states:

```text
INITIALIZING
INSUFFICIENT_DATA
VALID
STALE
MODEL_ERROR
```

Example:

```text
RUL
Collecting history
18 / 50 samples
Prediction unavailable
```

Do NOT convert insufficient history into:

```text
RUL = 0
```

---

## 4.2 Verify the complete RUL pipeline

Trace:

```text
telemetry
→ feature engineering
→ scaler
→ KMeans/preprocessing if applicable
→ XGBoost
→ post-processing
→ RUL API
→ DB
→ Health Fusion
→ UI
```

Compare every stage against the original training/inference pipeline.

The edge implementation must remain numerically consistent with the backend model.

---

## 4.3 Add RUL stability checks

Monitor:

- prediction jumps
- prediction oscillation
- impossible increases/decreases
- missing history
- stale prediction

Do not arbitrarily smooth predictions without documenting why.

If smoothing is necessary, make it configurable and test its effect.

---

## 4.4 Add RUL confidence only if defensible

Do not display:

```text
95% confidence
```

unless a statistically valid method exists.

Possible future implementation:

```text
RUL = 126 cycles
Prediction interval = 112–139 cycles
Method = ...
Coverage validated on held-out dataset
```

If no validated uncertainty method exists:

```text
RUL = 126 cycles
Uncertainty estimate: unavailable
```

This is preferable to fake confidence.

---

## 4.5 RUL validation suite

Create tests for:

- known test sequences
- monotonic degradation scenarios
- normal operation
- fault injection
- missing data
- noisy telemetry
- restart/recovery
- edge/backend parity

Generate an evaluation report containing:

- MAE
- RMSE
- median absolute error
- error distribution
- degradation trend consistency
- edge/backend numerical difference

Do not claim accuracy numbers unless measured.

---

# 5. Phase 3 — Improve Fault Detection Reliability

## Priority: VERY HIGH

Current system already has a 2-stage LightGBM fault pipeline.

Improve reliability rather than replacing it.

### 5.1 Document the fault pipeline

For every fault:

```text
Telemetry
→ preprocessing
→ stage 1 anomaly detection
→ stage 2 classification
→ probability
→ validation
→ final fault state
```

Document:

- features
- preprocessing
- classes
- thresholds
- model version
- expected latency

---

## 5.2 Add confidence and abstention

A classifier should not be forced to select a fault when evidence is weak.

Example:

```text
Fault:
Unknown / insufficient evidence

Top candidates:
Bearing anomaly — 41%
Oil pressure anomaly — 32%
No confirmed fault
```

Only use thresholds that are validated on evaluation data.

---

## 5.3 Separate anomaly from confirmed fault

Use explicit states:

```text
NORMAL
ANOMALY_DETECTED
FAULT_SUSPECTED
FAULT_CONFIRMED
SENSOR_ANOMALY
UNKNOWN
```

This prevents an early anomaly signal from becoming an immediate "engine failure."

---

## 5.4 Add temporal consistency

A single abnormal sample should not necessarily trigger a critical fault.

Evaluate:

- consecutive abnormal samples
- persistence
- trend
- recovery
- sensor agreement

Implement this as a configurable state machine, not arbitrary frontend logic.

---

# 6. Phase 4 — Sensor Fault vs Engine Fault Isolation

## Priority: HIGH

This is a useful reliability improvement.

The system should distinguish:

```text
Sensor abnormality
```

from:

```text
Engine abnormality
```

Example:

If EGT sensor 3 suddenly jumps while:

- other EGT values remain stable
- CHT remains stable
- RPM remains stable
- physics/expected value remains stable

then the system should be able to flag:

```text
Possible EGT3 sensor anomaly
```

rather than immediately claiming:

```text
Engine overheating
```

### Implementation

Build a sensor consistency layer using:

- cross-sensor comparison
- temporal behavior
- model residuals
- physics baseline when available
- sensor health history

Do not use a complex new neural network unless evaluation shows it is necessary.

---

# 7. Phase 5 — Add a Lightweight Physics Baseline

## Priority: HIGH

Do NOT build a giant physics simulator just to match another project.

Build a small, validated physics/engineering baseline that improves model trust.

### Objective

For selected telemetry:

```text
Expected value from physics/engineering relationship
             ↓
Actual telemetry
             ↓
Residual
             ↓
Validation
```

Example:

```text
Expected EGT: 760°C
Measured EGT: 772°C
Residual: +12°C
```

The actual equations and limits must come from documented engineering assumptions or project data.

Do not invent aerospace constants or operational limits.

---

## 7.1 Start with a small set

Potential candidates:

- RPM
- manifold pressure
- EGT
- CHT
- oil pressure
- oil temperature
- coolant temperature
- turbo boost

Only implement parameters for which a defensible relationship exists.

---

## 7.2 Physics residual object

Example:

```json
{
  "parameter": "EGT",
  "expected": 760,
  "measured": 772,
  "residual": 12,
  "unit": "C",
  "status": "ELEVATED",
  "method": "documented_baseline_v1"
}
```

---

## 7.3 Never use physics as a fake oracle

The physics baseline is not automatically more correct than ML.

Its role is:

```text
ML prediction
+
Physics consistency
+
Telemetry quality
=
better evidence
```

If the two disagree, show the disagreement.

---

# 8. Phase 6 — Physics vs AI Verification

## Priority: HIGH

Create a backend service that combines:

```text
Measured
Physics Expected
AI Prediction
Residual
Validation Status
```

Example:

| Parameter | Measured | Physics | AI | Residual | Status |
|---|---:|---:|---:|---:|---|
| EGT | 772°C | 760°C | 768°C | +12°C | REVIEW |
| CHT | 114°C | 116°C | 115°C | -2°C | CONSISTENT |

Do not add impressive-looking values that are not generated by actual calculations.

### UI

Add a compact section to Engine Detail:

```text
PHYSICS ↔ AI CONSISTENCY

EGT       CONSISTENT
CHT       CONSISTENT
Oil Press REVIEW
Vibration ANOMALY
```

Clicking a row should show the underlying values and calculation method.

---

# 9. Phase 7 — Improve Health Fusion

## Priority: VERY HIGH

Health Fusion is one of AeroTwin's central features.

Make it explainable and stable.

### Current concept

```text
RUL
Fault
Bearing
Auxiliary
→ Health Fusion
→ 0–100 health
```

Improve it to:

```text
Health Score
+
Data Quality
+
Contributing Factors
+
Model Validity
```

---

## 9.1 Explain every score

Example:

```text
ENGINE HEALTH: 76

Contributors:
RUL             -8
Bearing Health  -7
Fault Risk      -5
Auxiliary Risk  -4
Telemetry Quality +0

Primary concern:
Bearing degradation
```

Only show contributors actually used by the calculation.

---

## 9.2 Prevent double counting

Check whether multiple models are detecting the same underlying problem.

For example:

```text
Bearing model → vibration anomaly
Fault model → bearing fault
Health Fusion → subtracts both independently
```

This may incorrectly penalize the engine twice.

Audit correlation between model outputs.

---

## 9.3 Add health-score validation tests

Create synthetic cases:

```text
All normal
RUL degradation only
Bearing degradation only
Fault only
Auxiliary degradation only
Multiple simultaneous faults
Missing model output
Invalid telemetry
```

Verify health behaves consistently.

---

# 10. Phase 8 — Fault Injection Testbed Using Real Models

## Priority: HIGH

Add a controlled simulation layer.

Do not create a fake frontend-only fault simulator.

Fault injection must modify the simulation/telemetry pipeline and pass through the real inference stack.

Example:

```text
Normal telemetry
      ↓
Fault injection
      ↓
Modified telemetry
      ↓
Real ML models
      ↓
Health Fusion
      ↓
Alerts
      ↓
RUL
```

### Initial fault types

Use only faults supported by your existing models/data.

Possible examples:

- oil pressure degradation
- overheating
- vibration/bearing anomaly
- misfire
- turbo/boost anomaly
- sensor drift
- sensor dropout

Do not add fault types that the models cannot actually detect.

---

## 10.1 Severity

Use:

```text
0–100% severity
```

only if the simulator has a defined mathematical mapping.

Document:

```text
severity → telemetry transformation
```

---

## 10.2 Expected output

When injecting a fault, automatically capture:

```text
Fault injected
Detection time
Model detection
Health change
RUL change
Alert generated
Recovery behavior
```

This becomes a repeatable validation tool.

---

# 11. Phase 9 — Mission What-If Accuracy

## Priority: MEDIUM-HIGH

Do not add many controls just for appearance.

Expand the current What-If system only where the simulation has real mathematical meaning.

Possible parameters:

```text
Altitude
Ambient temperature
Throttle/load
Payload
Mission duration
Fault severity
```

Only expose a parameter if the simulation actually uses it.

---

## 9.1 Compare Current vs Scenario

Display:

```text
                CURRENT     SCENARIO     DELTA

Health            82          68         -14
RUL              126          91         -35
EGT              770         820         +50
Fuel Flow        10.2        12.1        +1.9
Fault Risk        12%         34%        +22%
```

Every scenario number must come from the simulation.

---

## 9.2 Scenario reproducibility

Save:

```text
scenario_id
engine_id
parameters
model_versions
timestamp
results
```

Allow the same scenario to be reproduced later.

---

# 12. Phase 10 — Mission-Level Decision Support

## Priority: MEDIUM

Do not build a large military mission-control system.

Add only information that can be calculated from AeroTwin's existing data.

Mission Details should show:

```text
Mission
├── UAV
├── Engine
├── Current Health
├── RUL
├── Fault State
├── Bearing State
├── Fuel / endurance if available
├── Alerts
├── Telemetry quality
├── Mission timeline
├── Replay
└── What-If
```

---

## 12.1 Mission risk

If implementing mission risk, make the formula transparent.

Example structure:

```text
Mission Risk
=
engine health evidence
+ fault risk
+ RUL suitability
+ telemetry quality
+ mission conditions
```

Do not display a percentage such as `94% readiness` unless the calculation is formally defined and validated.

Prefer:

```text
Risk factors:
- Bearing degradation
- RUL uncertainty
- Telemetry quality

Assessment:
REVIEW REQUIRED
```

until a validated risk model exists.

---

# 13. Phase 11 — Add Cylinder-Level and Engine-Specific Telemetry Only If Data Exists

## Priority: MEDIUM

Potential additions:

- cylinder 1–4 CHT
- cylinder 1–4 EGT
- manifold pressure
- turbo boost
- coolant temperature
- alternator/battery
- injection timing

But:

> Do not generate fake cylinder telemetry.

If real or simulated data exists, integrate it end-to-end:

```text
MQTT
→ schema
→ database
→ model features
→ WebSocket
→ dashboard
→ simulation
→ alerts
```

Otherwise leave the field as:

```text
Unavailable
```

---

# 14. Phase 12 — Vibration Analytics

## Priority: MEDIUM

AeroTwin already has vibration XYZ.

Improve the existing system before adding another ML model.

### Add signal processing

If sampling frequency and data quality support it:

```text
raw vibration
→ filtering
→ FFT
→ frequency spectrum
→ RMS
→ dominant frequencies
```

Display:

```text
RMS
Dominant frequency
Frequency bands
Trend
```

Only associate a frequency with a bearing/component when that relationship is supported by the model or documented engineering knowledge.

---

# 15. Phase 13 — 3D Digital Twin Only After Intelligence Is Reliable

## Priority: LOW

Do not make 3D the center of the project.

If time permits, add a lightweight Three.js/WebGL engine visualization.

It should visualize actual AeroTwin state:

```text
Engine
├── cylinders
├── turbo
├── gearbox
└── bearing areas
```

Component colors should come from real health values.

Example:

```text
Cylinder 1 → health from actual data
Cylinder 2 → health from actual data
Bearing → actual bearing result
Turbo → actual auxiliary result
```

Do not create a decorative 3D model disconnected from the backend.

---

# 16. Phase 14 — Copilot Accuracy and Grounding

## Priority: VERY HIGH

The Copilot must be treated as a decision-support interface, not a generic chatbot.

Use the provider-independent architecture already planned:

```text
LLM_PROVIDER=groq|gemini|ollama
```

Keep:

```text
ChromaDB = static/documented knowledge
Backend = live engine state
LLM = explanation/reasoning layer
```

---

## 16.1 Context selection

For each query decide:

```text
STATIC
LIVE
COMBINED
```

Do not send unnecessary data.

---

## 16.2 Copilot grounding rules

The LLM must never invent:

- current RUL
- current RPM
- current fault
- telemetry
- maintenance records
- alert state
- thresholds
- regulatory requirements

If live data is unavailable:

```text
Live engine data is currently unavailable.
```

If documentation is unavailable:

```text
The requested documented information is not available.
```

---

## 16.3 Add source labels

Responses should identify information type:

```text
LIVE TELEMETRY
MODEL PREDICTION
HISTORICAL DATA
DOCUMENTED KNOWLEDGE
SIMULATION
```

This makes the Copilot more trustworthy.

---

## 16.4 Add quick actions

Use buttons such as:

```text
Explain Current Health
Why Did Health Drop?
Explain RUL
Explain Active Alerts
Analyze Current Fault
Compare Current vs Previous Mission
```

These should call the existing Copilot API.

Do not build a separate AI system for each button.

---

# 17. Phase 15 — End-to-End Accuracy Validation Framework

## Priority: VERY HIGH

Create one repeatable validation framework for the entire system.

### Scenario A — Normal operation

Expected:

```text
No false critical alerts
Stable health
Stable RUL
No unexplained model disagreement
```

### Scenario B — Progressive degradation

Expected:

```text
Telemetry trend
→ model response
→ health degradation
→ alert
→ RUL degradation
```

### Scenario C — Sudden fault

Expected:

```text
fault injected
→ detection
→ alert
→ health impact
→ Copilot explanation
```

### Scenario D — Sensor failure

Expected:

```text
sensor anomaly
→ sensor fault isolation
→ no unjustified engine failure
```

### Scenario E — Network outage

Expected:

```text
MQTT disconnect
→ edge buffer
→ reconnect
→ ordered flush
→ backend recovery
```

### Scenario F — Missing/invalid data

Expected:

```text
invalid telemetry
→ quality flag
→ model handling
→ no fabricated prediction
```

### Scenario G — Simulation

Expected:

```text
scenario
→ simulation
→ models
→ health
→ RUL
→ alerts
→ explainable result
```

---

# 18. Phase 16 — Accuracy Dashboard for Developers

Create an internal/developer-only validation page.

Do not expose it as an operator feature unless useful.

Display:

```text
MODEL PERFORMANCE

RUL
MAE
RMSE
prediction error
data coverage

FAULT
precision
recall
F1
false positive rate
false negative rate
detection latency

BEARING
classification metrics
false alarms

AUXILIARY
classification metrics

HEALTH FUSION
scenario validation

EDGE PARITY
backend vs ONNX difference
```

Metrics must be calculated from actual evaluation data.

Never hard-code benchmark numbers.

---

# 19. Phase 17 — Model Versioning and Reproducibility

Every prediction should be traceable to:

```text
model name
model version
feature version
preprocessing version
timestamp
input data timestamp
```

Example:

```json
{
  "model": "fault_detector",
  "model_version": "2.1.0",
  "feature_version": "1.4.0",
  "prediction": "bearing_anomaly",
  "probability": 0.91,
  "timestamp": "..."
}
```

This is important for debugging and future model retraining.

---

# 20. Phase 18 — Edge/Backend Parity Validation

The existing ONNX parity work must remain protected.

For every exported model:

```text
Original model
vs
ONNX model
```

compare:

- output values
- class predictions
- preprocessing
- feature ordering
- numerical tolerance

Run parity tests automatically in CI.

Do not accept an ONNX export that silently changes predictions.

---

# 21. Phase 19 — Performance and Reliability Regression

After each major phase run:

```text
Backend tests
Frontend typecheck/build
ML tests
Edge tests
E2E tests
Docker stack
MQTT test
WebSocket test
Load test
```

Keep the current targets as regression baselines:

- existing 96 backend tests
- existing coverage baseline
- existing 50-engine load test
- existing WebSocket performance
- existing edge offline buffering test
- existing ONNX parity test

Do not sacrifice reliability for additional UI features.

---

# 22. Phase 20 — UI Improvements Only After Backend Accuracy

Once the intelligence is reliable, update UI.

## Engine Detail

Add:

```text
LIVE
Telemetry Quality
Health
RUL + status
Fault
Bearing
Auxiliary
Physics vs AI
Health Contributors
Model validity
```

## Alerts

Replace repeated alerts with grouped incidents.

Example:

```text
Bearing degradation
Engine: ENG001
First detected: 14:32
Last updated: 14:41
Occurrences: 17
Severity: Warning
Status: Open
```

Show the underlying events when expanded.

## Simulation

Clearly show:

```text
SIMULATION MODE
```

and never mix simulation values with live values.

## RUL

Never show:

```text
0 cycles
```

when the model has insufficient history.

---

# 23. Final Target Architecture

After all high-priority phases, the system should look like:

```text
                     PHYSICAL / SIMULATED ENGINE
                              │
                              ▼
                        TELEMETRY
                              │
                     MQTT / EDGE AGENT
                              │
              ┌───────────────┴───────────────┐
              │                               │
        EDGE INFERENCE                 BACKEND INGESTION
              │                               │
        ONNX Fault/RUL                        │
              │                               ▼
              │                       Data Quality Layer
              │                               │
              └───────────────┬───────────────┘
                              ▼
                    Physics Baseline
                              │
             ┌────────────────┼────────────────┐
             ▼                ▼                ▼
          Fault              RUL            Bearing
          Model              Model            Model
             │                │                │
             └────────────────┼────────────────┘
                              ▼
                    Auxiliary Prediction
                              │
                              ▼
                       Health Fusion
                              │
                 ┌────────────┼────────────┐
                 ▼            ▼            ▼
               Alerts      Mission       Digital
                            Risk           Twin
                 │            │            │
                 └────────────┼────────────┘
                              ▼
                 Replay / What-If Simulation
                              │
                              ▼
                      AI Copilot / RAG
                       │              │
                  ChromaDB        Live Backend
                       │              │
                       └──────┬───────┘
                              ▼
                             LLM
                              │
                              ▼
                     Explainable Response
```

---

# 24. Recommended Priority Order

Do NOT implement everything simultaneously.

Use this order:

## Tier 1 — Must Do

1. Repository audit
2. Data-quality layer
3. RUL reliability/state handling
4. Fault confidence/abstention
5. Health Fusion validation
6. Copilot provider fix + grounding
7. End-to-end accuracy test scenarios

## Tier 2 — High Value

8. Sensor-vs-engine fault isolation
9. Lightweight physics baseline
10. Physics vs AI verification
11. Real fault injection through existing models
12. What-If current-vs-scenario comparison
13. Model versioning
14. Edge/backend parity CI

## Tier 3 — Useful

15. Mission Details
16. Cylinder-level telemetry if data exists
17. Vibration FFT
18. Mission-level risk based on validated inputs

## Tier 4 — Optional

19. 3D Digital Twin
20. Advanced mission optimization
21. Advanced flight-envelope logic
22. Additional AI agents

Do not start Tier 4 until Tier 1 and Tier 2 are stable.

---

# 25. What NOT To Build

Do not add these simply because another project has them:

- decorative 3D engine
- fake real-time gauges
- fake confidence percentages
- fake mission readiness percentages
- fake physics numbers
- fake benchmark metrics
- additional AI agents without a real task
- large multi-agent architecture
- duplicate dashboards
- duplicate fault models
- unnecessary microservices
- unnecessary LangChain abstraction
- separate chatbot implementations
- huge frontend redesign
- physics simulation without validation
- unsupported engine parameters
- unsupported fault classes

The project should become **deeper**, not merely **larger**.

---

# 26. Claude Code Execution Rules

For every phase:

### Step 1 — Inspect

Before editing:

```text
Find the relevant files.
Read the existing implementation.
Understand data flow.
Find existing tests.
```

### Step 2 — Plan

State:

```text
Files to modify
Files to create
API changes
Database changes
Model changes
Frontend changes
Tests required
Risks
```

### Step 3 — Implement the smallest change

Do not refactor unrelated code.

### Step 4 — Test immediately

Run the smallest relevant test suite first.

Then run the complete regression suite.

### Step 5 — Verify actual data flow

Do not stop at:

```text
API returns 200
```

Verify:

```text
Telemetry
→ DB
→ Model
→ Health Fusion
→ WebSocket/API
→ UI
```

### Step 6 — Test failure states

Every feature should be tested for:

```text
missing data
invalid data
stale data
model failure
database failure
network failure
simulation mode
```

### Step 7 — Report

At the end of each phase provide:

```text
Implemented:
...

Files changed:
...

Tests:
...

Measured results:
...

Known limitations:
...

Next phase:
...
```

---

# 27. Definition of Done

A phase is NOT complete merely because the UI looks correct.

A phase is complete when:

- implementation exists
- backend integration works
- real data flows through it
- tests exist
- failure states are handled
- existing functionality still works
- model outputs are traceable
- no values are fabricated
- documentation is updated
- performance has not regressed

---

# 28. Final Goal

The final AeroTwin should be presented as:

> **An accuracy-first, explainable Digital Twin platform for aero piston engine health monitoring, fault prediction, RUL estimation, mission-aware simulation, and evidence-grounded decision support.**

The strongest differentiator should not be the number of screens.

It should be the chain of evidence:

```text
Telemetry
   ↓
Data Quality
   ↓
Physics / Engineering Consistency
   ↓
Validated ML Models
   ↓
Health Fusion
   ↓
Fault / RUL / Bearing / Auxiliary Evidence
   ↓
Mission Context
   ↓
Explainable Decision Support
   ↓
Grounded AI Copilot
```

Build this chain correctly before adding more features.

---

# 29. First Claude Code Prompt

Start implementation by giving Claude Code this instruction:

```text
Read the entire AeroTwin repository and this implementation plan.

Do NOT start by adding UI features.

First perform Phase 0: Repository and Architecture Audit.

Inspect:
- backend
- frontend
- ML models
- preprocessing
- inference
- telemetry
- MQTT
- edge agent
- database
- Health Fusion
- alerts
- simulation
- Copilot/RAG
- tests
- Docker
- CI

Run the existing test suite and establish a baseline.

Then report:
1. Current architecture
2. Actual data flow
3. Existing model pipelines
4. Existing validation
5. Existing test coverage
6. Current weaknesses affecting accuracy/reliability
7. Exact files that should be changed for Phase 1
8. Any discrepancy between this plan and the actual repository

Do not implement Phase 1 yet.

Do not redesign the application.

Do not copy another team's architecture or UI.

The objective is to make AeroTwin more accurate, reliable, explainable, and useful for real engine-monitoring workflows.
```

After Phase 0 is reviewed, proceed one phase at a time.

