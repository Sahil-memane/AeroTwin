
AeroTwin

ML Model Specification & Frontend Integration Guide

Companion to the Complete Project Implementation Document — covers the 4 trained models, their datasets, and how the dashboard consumes them

Smart India Hackathon 2026  |  Problem Statement ID: 26054

Organization: DRDO — Department of Defence R&D  |  Theme: Robotics and Drones

Team: Antigravity

Document version 1.0 — sourced from the Dataset & Model Collection Guide and the integrated digital twin architecture diagram

Table of Contents

(Right-click below and choose "Update Field" — or press F9 — after opening this document in Word to populate the contents list.)


# 1. Purpose & Scope

This document specifies the four trained machine learning models in AeroTwin's AI/ML analytics pipeline — what each one is trained on, what it consumes from the rest of the system, what it produces, and how that output reaches the operator through the dashboard. It is written directly from the project's Dataset & Model Collection Guide and the integrated digital twin architecture diagram, so every dataset, model, and data-flow claim below traces back to one of those two sources.

The main Project Implementation Document (Sections 2, 7, 8 and 9) already describes these models at a system level. This document goes one level deeper on each model individually and adds the frontend wiring — REST endpoints, WebSocket events, TypeScript interfaces, and example components — needed to actually get a prediction from a model onto the operator's screen.

Note: Two items called out in the Dataset & Model Collection Guide are flagged again at the relevant points below because they affect what this document can specify precisely: the Aux model's second dataset ("engine failure dataset") has no confirmed source link yet, and the Fault model's 7 output classes — as defined by the actual ALFA dataset — are UAV flight-control faults, not the piston-engine-specific faults named in the main Project Implementation Document. Section 10 consolidates both as open items.


# 2. Architecture Recap: Which Components Are Trained Models

The system has 7 labeled components across the architecture diagram, but only 4 of them are trained ML models in the sense of needing a labeled dataset. The table below reproduces that scope mapping from the Dataset & Model Collection Guide so it's explicit which of the remaining sections apply to a trained model versus a supporting component.


Figure 2.1 — AeroTwin digital twin architecture: data sources → digital twin core → physics / AI-ML / simulation branches → health fusion → dashboard.


| # | Component | Trained ML model? | Data status / what it needs |
| --- | --- | --- | --- |
| 1 | Digital twin core | No — live synchronized state | N/A for training. Uses the real-time sensor stream + mission history directly. |
| 2 | Physics model | No — thermodynamic / performance equations | Needs engine performance maps, thermodynamic constants, and manufacturer spec sheets (or a public proxy) — reference/config data, not a labeled dataset. |
| 3 | Fault model | Yes | Covered — ALFA (UAV telemetry). See Section 3. |
| 4 | RUL model | Yes | Covered — NASA turbofan (C-MAPSS). See Section 4. |
| 5 | Bearing model | Yes | Covered — CWRU bearing data. See Section 5. |
| 6 | Aux model | Yes | Covered — AI4I 2020 (milling) + engine failure dataset (source unconfirmed). See Section 6. |
| 7 | Simulation engine | Not really — scenario replay / what-if tool | Needs mission/environmental profile data (altitude, temperature, throttle transients); overlaps with the twin core's 'Mission & history' input. |


Note: The Physics model and Simulation engine are not trained models, so they don't get a full Section 3-style breakdown — they're covered briefly in Section 7 because the 4 trained models depend on the Physics model's output and the Simulation engine depends on all 4 trained models.


# 3. Fault Detection Model (7-Class Classifier)


## 3.1 Dataset


| Dataset | UAV flight telemetry & sensor fault logs (ALFA) |
| --- | --- |
| Source | CMU AirLab — theairlab.org/alfa-dataset (DOI 10.1184/R1/12707963) |
| Format | ROS bag / CSV time-series |
| Key attributes | Flight state (attitude, GPS, IMU), actuator commands, fault injection timestamp, fault type label |
| Licensing | Public / research-use, no restrictive licensing blocking a hackathon demo |


Note: The dataset's actual fault labels are UAV flight-control faults, not piston-engine mechanical faults: No failure, RC failure, GPS failure, Aileron failure, Elevator failure, Rudder failure, and Engine failure (per the architecture diagram's "7 Failure Categories" box). The main Project Implementation Document's Section 2.2 instead lists engine-specific classes (misfire, injector abnormality, cooling degradation, lubrication issue, sensor drift, combustion instability). This is a real mismatch to resolve before submission — see Section 10.1.


## 3.2 Upstream Inputs — Any Previous Model Output Taken?

Preprocessed telemetry feature window from the Digital Twin Core (Section 9.2 of the main document) — the model's primary input.

The Physics model's expected-vs-actual deviation signal is fed in as an additional engineered feature. This is the output of a non-trained component, not of another trained model.

No other trained model's output is consumed here — the Fault, RUL, Bearing, and Aux models all run in parallel on the same feature window, independently of one another.


## 3.3 What the Model Does

A windowed multivariate telemetry slice (RPM, CHT, EGT, vibration, fuel flow, plus the physics-deviation feature) is passed through a trained classifier that scores it against the 7 ALFA-derived classes.

ROS bag / CSV telemetry → resample & window → feature extraction → classifier (PyTorch neural net, with a scikit-learn baseline) → softmax over 7 classes → predicted class + confidence.


## 3.4 Output


| Fields | fault_class (one of the 7 classes), confidence (0–1) |
| --- | --- |
| Database table | fault_predictions — references engine_id and model_registry.id (model_version_id) |
| Alert trigger | A new row with confidence above the configured threshold is written to alerts with source = 'fault_model' |
| Served by | GET /api/v1/engines/{engine_id}/faults/latest |



## 3.5 Related Considerations

Class imbalance: 'no failure' will dominate the training distribution — use class weighting or focal loss rather than plain cross-entropy.

Confidence calibration matters more than raw accuracy here, since the confidence score is what the alert threshold and the dashboard's badge color both key off.

Exported to ONNX so the same trained weights run both in the cloud inference service and at the edge (Raspberry Pi / Jetson Nano) for degraded-connectivity operation.

Every prediction traces to a specific model_registry version, so a relabeling fix (Section 10.1) can ship as a new version without breaking historical predictions.


# 4. Remaining Useful Life (RUL) Prediction Model


## 4.1 Dataset


| Dataset | NASA turbofan engine degradation (C-MAPSS) |
| --- | --- |
| Source | NASA Prognostics Center of Excellence — data.phmsociety.org/nasa (Kaggle mirror: behrad3d/nasa-cmaps) |
| Format | CSV, multivariate time series |
| Key attributes | 26 columns: unit ID, cycle number, 3 operational settings, 21 sensor measurements (temperatures, pressures, fan/core speeds) |
| Licensing | Public / research-use |



## 4.2 Upstream Inputs — Any Previous Model Output Taken?

Historical + live degradation-relevant telemetry from the Digital Twin Core, resampled to the same cycle/window structure the C-MAPSS features use.

The Physics model's deviation signal is fed in as an additional feature, the same as for the Fault model.

No other trained model's output is consumed — RUL runs independently of Fault, Bearing, and Aux.


## 4.3 What the Model Does

A sequence model reads a rolling window of degradation-relevant telemetry and regresses both a remaining-life estimate and a normalized degradation trend, rather than classifying a discrete fault.

Historical + live telemetry → sequence windowing → LSTM (PyTorch) with an XGBoost regression baseline for comparison → predicted RUL in flight-hours + degradation index.


## 4.4 Output


| Fields | rul_cycles (estimated flight-cycles remaining), degradation_index (0–1 normalized trend) |
| --- | --- |
| Database table | rul_predictions — references engine_id and model_registry.id |
| Alert trigger | A degradation_index or rul_cycles crossing a configured threshold is written to alerts with source = 'rul_model' |
| Served by | GET /api/v1/engines/{engine_id}/rul?from=&to= (defaults to last 90 days) |



## 4.5 Related Considerations

C-MAPSS is turbofan data, not piston-engine data — this is the domain gap the Dataset & Model Collection Guide flags in Section 4.2; the mitigation is an engine-agnostic architecture validated on proxy data, designed for drop-in replacement once real piston/CAN-bus run-to-failure data exists.

Held-out test split should be by unit ID (not by row), so the model is evaluated on engines it never saw during training — this is the standard C-MAPSS evaluation protocol.

LSTM vs. XGBoost is still an open decision per the dataset guide's sorting checklist — keep both in the model registry during evaluation and let validation_score decide which becomes is_active.

degradation_index (not just rul_cycles) is what should drive the dashboard's trend chart, since it's normalized and comparable across engines with different total operating-cycle baselines.


# 5. Bearing & Vibration Health Model


## 5.1 Dataset


| Dataset | Bearing fault diagnosis (CWRU) |
| --- | --- |
| Source | Case Western Reserve University Bearing Data Center — engineering.case.edu/bearingdatacenter/download-data-file |
| Format | .mat vibration signal files (12 kHz / 48 kHz sampling) |
| Key attributes | Accelerometer vibration signal, fault location (inner race / outer race / rolling element), fault diameter (7–40 mils), motor load, RPM |
| Licensing | Public, but requires direct registration/download from the CWRU portal — not available via an open mirror, unlike the other 4 datasets |


Note: Complete CWRU portal registration early — per the dataset guide's sorting checklist, this is the one dataset that can't simply be pulled from an open mirror.


## 5.2 Upstream Inputs — Any Previous Model Output Taken?

Triaxial vibration stream (vibration_x/y/z) from the Digital Twin Core is the primary input — this model does not consume the physics-model deviation signal the way Fault and RUL do, since vibration signature analysis is not part of the thermodynamic performance model.

No other trained model's output is consumed here.


## 5.3 What the Model Does

Raw triaxial vibration is converted to frequency-domain features and classified against the CWRU fault taxonomy to localize and score bearing wear — the earliest and most diagnosable mechanical failure precursor available from vibration data alone.

Triaxial vibration stream → FFT feature extraction (NumPy / SciPy) → classical classifier (scikit-learn) → fault location + severity score.


## 5.4 Output


| Fields | fault_location (healthy / inner_race / outer_race / rolling_element), severity_score (0–1) |
| --- | --- |
| Database table | bearing_health_readings — references engine_id (no model_version_id column in the current schema — see Section 10.3) |
| Alert trigger | A non-healthy fault_location with severity_score above threshold is written to alerts with source = 'bearing_model' |
| Served by | GET /api/v1/engines/{engine_id}/bearing-health |



## 5.5 Related Considerations

CWRU is bench-test bearing data at fixed motor loads/RPMs, not in-flight UAV vibration — validate that the FFT feature windowing generalizes to the engine/accessory shaft's actual sampling rate before trusting severity_score numerically.

Because this model doesn't depend on the physics model, it's the one model of the four that keeps working unchanged if the physics/thermodynamic solver is ever unavailable or miscalibrated.

Fault diameter (7–40 mils) in the training data is a severity proxy worth mapping explicitly to the 0–1 severity_score scale rather than leaving that mapping implicit in the classifier.


# 6. Cross-Domain Auxiliary Transfer Learning Model


## 6.1 Dataset


| Dataset 1 | Milling machine predictive maintenance (AI4I 2020) — CONFIRMED |
| --- | --- |
| Source 1 | Kaggle — kaggle.com/datasets/shivamb/machine-predictive-maintenance-classification |
| Format 1 | CSV, tabular |
| Key attributes 1 | Air/process temperature, rotational speed, torque, tool wear (min), machine failure label (5 modes: TWF, HDF, PWF, OSF, RNF) + no-failure |
| Dataset 2 | Engine failure dataset — NOT CONFIRMED |
| Source 2 | Likely a generic Kaggle engine-health dataset — needs re-verification before submission |


Note: Dataset 2 has no captured link. Track down the exact Kaggle/UCI page and paste the URL into the Dataset & Model Collection Guide before this goes into the submission doc — judges may ask for provenance directly, and "we don't remember where we got it" is a preventable gap (guide Section 4.1).


## 6.2 Upstream Inputs — Any Previous Model Output Taken?

Tabular operating-condition data (temperature, rotational speed, torque, tool/component wear) from the two source datasets feeds pretraining and fine-tuning — not live telemetry directly, since neither source dataset is engine-specific time-series data in the same shape as the other three models' inputs.

No trained model's output is consumed as an input here either — the Aux model is the fourth parallel branch, not a downstream consumer.


## 6.3 What the Model Does

Labeled piston-engine failure data is scarce, so a model trained only on that scarce in-domain data would generalize poorly. This model is pretrained cross-domain on the milling dataset, then fine-tuned on whatever engine-failure data becomes available, producing a supporting auxiliary score rather than a primary diagnosis.

Pretrain on AI4I 2020 milling data → fine-tune on the (still-unconfirmed) engine-failure dataset → auxiliary fault-likelihood score, fused with the other three models' outputs.


## 6.4 Output


| Fields | An auxiliary fault-likelihood score (0–1), plus a reusable pretrained backbone for future in-domain fine-tuning |
| --- | --- |
| Database table | Not yet defined in the current schema — the main Project Implementation Document's Section 7 database design has no aux_predictions table. Recommendation: add one, mirroring fault_predictions (engine_id, model_version_id, ts, aux_score), so this model's output is traceable and queryable like the other three — see Section 10.3. |
| Consumed by | Health fusion service, as a supporting signal alongside Fault, RUL, and Bearing outputs |
| Served by | Not yet exposed as its own endpoint — currently only visible indirectly through /api/v1/engines/{engine_id}/health-score's contributing_factors |



## 6.5 Related Considerations

This is the model most exposed to the domain-gap issue: none of milling, turbofan, or UAV-telemetry data is piston-engine-specific (guide Section 4.2) — the mitigation note to carry into the submission sheet is: "engine-agnostic architecture, validated on proxy datasets, designed for drop-in replacement with real piston/CAN-bus data at deployment."

Keep the pretrained backbone versioned separately from the fine-tuned head in the model registry, so future in-domain fine-tuning doesn't require re-running the cross-domain pretraining step.

Because its own dataset provenance is still incomplete, treat this model's score as advisory in the health fusion weighting until Dataset 2 is confirmed and a proper held-out evaluation exists.


# 7. Non-ML Supporting Components

These two components appear in the architecture diagram and feed into or consume the 4 trained models, but neither is itself a trained model — the Dataset & Model Collection Guide tracks them separately because they need reference data or scenario data, not a labeled training dataset.


## 7.1 Physics Model

Computes expected engine behavior (CHT, EGT, power output) from live operating conditions using thermodynamic/performance equations, independent of any trained model. Its output — the gap between expected and actual sensor readings — is fed as an extra feature into the Fault and RUL models (Sections 3.2 and 4.2), giving both an independent, explainable check that isn't available to a pure black-box model.

Needs: engine performance maps, thermodynamic constants, manufacturer spec sheets for a piston engine, or a public proxy — reference/config data, filed separately from the ML training table per the dataset guide.

Does not consume any trained model's output — it runs independently and upstream of the ML layer.


## 7.2 Simulation Engine

A scenario replay / what-if tool: it selects a historical mission or a defined hypothetical mission profile and runs it through the physics model and all 4 trained ML models to produce a time-stepped predicted or replayed engine health trace.

Consumes: the Physics model's output and all 4 trained models' outputs (Fault, RUL, Bearing, Aux) — this is the one component in the architecture that deliberately reuses every other component's output rather than running in parallel with them.

Needs: mission/environmental profile data (altitude, ambient temperature, throttle profile, duration) — this overlaps with the 'Mission & history' input already planned for the Digital Twin Core, so no separate dataset collection is required, only a diversity check.

Note: Confirm the planned 'Mission & history' data collection covers enough scenario diversity — hot weather, high altitude, rapid throttle transients — since DRDO explicitly asked for these conditions (dataset guide Section 4.4).


# 8. Health Fusion & Scoring

Health fusion is where the 4 trained models' outputs stop being 4 separate numbers and become the single combined_score the operator actually looks at. It's the one place in the architecture where a component's job is explicitly to take other models' outputs as input.


## 8.1 What It Consumes


| Input | From | What it contributes |
| --- | --- | --- |
| fault_class + confidence | Fault model | Discrete fault flag; a high-confidence non-'no failure' class should dominate the combined score regardless of the other three. |
| rul_cycles + degradation_index | RUL model | Long-horizon trend signal — drives the maintenance-planning half of the score rather than an immediate alert. |
| fault_location + severity_score | Bearing model | Mechanical-wear signal, independent of the physics/thermodynamic branch. |
| Auxiliary fault-likelihood score | Aux model | Supporting signal only — weighted lower until Dataset 2 (Section 6.1) is confirmed and evaluated. |
| Expected-vs-actual deviation | Physics model | Independent sanity check; a large deviation with low ML confidence is itself worth surfacing rather than being averaged away. |



## 8.2 Suggested Fusion Logic (proposal — not yet implemented)

The main Project Implementation Document names health_fusion.py as the service responsible for this but doesn't specify the formula. A reasonable starting point, to refine once real validation data exists:

Start from 100 and subtract a weighted penalty per signal: fault confidence (highest weight when class ≠ 'no failure'), inverse degradation_index, bearing severity_score, and the physics deviation magnitude.

Treat the Aux score as a modifier (small additive/subtractive nudge) rather than a full peer input, given its unresolved dataset provenance.

Clamp the result to 0–100 and store contributing_factors (each input's individual contribution) alongside combined_score, so the dashboard can show *why* the score moved, not just the number.

Any single input crossing its own critical threshold (e.g. fault confidence > 0.9 on a non-'no failure' class) should be able to force a 'critical' severity on the combined score even if the weighted average would otherwise land in 'warning'.


## 8.3 Output


| Fields | combined_score, contributing_factors (array), last_updated |
| --- | --- |
| Served by | GET /api/v1/dashboard/health-score (per-engine) and /api/v1/dashboard/summary (fleet-wide) |
| Alert trigger | A threshold breach on combined_score is written to alerts with source = 'health_fusion' |



# 9. Frontend / App Integration

This section specifies exactly how each model's output reaches the React dashboard defined in the main document's repository structure (Section 5) and technology stack (Section 6.1) — which endpoint to call, which WebSocket event to listen for, what shape the data arrives in, and which component renders it.


## 9.1 Data Flow Overview

On page load, the dashboard fetches a REST snapshot per engine: latest telemetry, latest fault/RUL/bearing predictions, and the current combined health score.

It then opens one WebSocket connection per session to /ws/engines/{engine_id}/live and applies incremental updates as they're computed, so the view stays current without polling.

Every model-specific value shown on screen should be traceable back to the REST/WS call that produced it — this section maps that 1:1.


## 9.2 REST Endpoints Per Model


| Model | Endpoint | Frontend hook / call site |
| --- | --- | --- |
| Fault | GET /api/v1/engines/{engine_id}/faults/latest | services/apiClient.ts → getLatestFault(engineId) |
| RUL | GET /api/v1/engines/{engine_id}/rul?from=&to= | services/apiClient.ts → getRulTrend(engineId, range) |
| Bearing | GET /api/v1/engines/{engine_id}/bearing-health | services/apiClient.ts → getBearingHealth(engineId) |
| Aux | Not yet exposed directly — see Section 6.4 | Read via getHealthScore(engineId).contributing_factors until an endpoint exists |
| Health fusion | GET /api/v1/engines/{engine_id}/health-score | services/apiClient.ts → getHealthScore(engineId) |



## 9.3 WebSocket Live Updates

The main document's Section 8.9 defines the WebSocket payload shape as { type, payload } with type one of 'telemetry' | 'alert' | 'health_score'. To push model-specific updates the moment they're computed (rather than the frontend re-polling REST after every alert), extend the type union with one event per model:

type LiveMessage =
  | { type: 'telemetry';      payload: TelemetryReading }
  | { type: 'fault_prediction'; payload: FaultPrediction }
  | { type: 'rul_prediction';   payload: RulPrediction }
  | { type: 'bearing_health';   payload: BearingHealthReading }
  | { type: 'health_score';     payload: HealthScore }
  | { type: 'alert';           payload: Alert };

Note: This extends, rather than replaces, the WebSocket contract already specified in the main document — 'telemetry', 'alert', and 'health_score' are unchanged; 'fault_prediction', 'rul_prediction', and 'bearing_health' are the additions this integration needs.


## 9.4 TypeScript Interfaces (frontend/src/types/)

These mirror the backend Pydantic schemas 1:1, per the main document's repository-structure note that frontend/src/types/ 'mirrors backend schemas'.

export interface FaultPrediction {
  ts: string;
  faultClass:
    | 'no_failure' | 'rc_failure' | 'gps_failure'
    | 'aileron_failure' | 'elevator_failure'
    | 'rudder_failure' | 'engine_failure';
  confidence: number;       // 0–1
  modelVersion: string;
}
 
export interface RulPrediction {
  ts: string;
  rulHours: number;
  degradationIndex: number; // 0–1
}
 
export interface BearingHealthReading {
  ts: string;
  faultLocation: 'healthy' | 'inner_race' | 'outer_race' | 'rolling_element';
  severityScore: number;    // 0–1
}
 
export interface HealthScore {
  combinedScore: number;    // 0–100
  contributingFactors: { source: string; contribution: number }[];
  lastUpdated: string;
}

Note: faultClass above uses the 7 ALFA-derived labels from Section 3.1, not the engine-specific labels in the main document — update this union once the class-list mismatch (Section 10.1) is resolved.


## 9.5 Zustand Store Shape (frontend/src/store/)

The main document's repository structure names a single Zustand store for 'live engine state, auth session'. Model outputs slot into that same store as a keyed-by-engine_id map, so the WebSocket handler can update one engine's slice without touching the others:

interface EngineState {
  telemetry?: TelemetryReading;
  fault?: FaultPrediction;
  rul?: RulPrediction;
  bearing?: BearingHealthReading;
  healthScore?: HealthScore;
}
 
interface DashboardStore {
  engines: Record<string, EngineState>;   // keyed by engine_id
  setFault: (engineId: string, p: FaultPrediction) => void;
  setRul: (engineId: string, p: RulPrediction) => void;
  setBearing: (engineId: string, p: BearingHealthReading) => void;
  setHealthScore: (engineId: string, p: HealthScore) => void;
}


## 9.6 useTelemetryStream Hook (frontend/src/hooks/)

The main document names useTelemetryStream as the WebSocket hook. Routing each message type to its store setter is the integration point for all 4 models:

function useTelemetryStream(engineId: string) {
  const setFault = useDashboardStore((s) => s.setFault);
  const setRul = useDashboardStore((s) => s.setRul);
  const setBearing = useDashboardStore((s) => s.setBearing);
  const setHealthScore = useDashboardStore((s) => s.setHealthScore);
 
  useEffect(() => {
    const token = useAuthStore.getState().accessToken;
    const ws = new WebSocket(
      `${WS_URL}/ws/engines/${engineId}/live?token=${token}`
    );
    ws.onmessage = (evt) => {
      const msg: LiveMessage = JSON.parse(evt.data);
      switch (msg.type) {
        case 'fault_prediction': setFault(engineId, msg.payload); break;
        case 'rul_prediction':   setRul(engineId, msg.payload); break;
        case 'bearing_health':   setBearing(engineId, msg.payload); break;
        case 'health_score':     setHealthScore(engineId, msg.payload); break;
        // 'telemetry' and 'alert' handled the same way, per the main document
      }
    };
    return () => ws.close();
  }, [engineId]);
}


## 9.7 Example Components (frontend/src/components/)

One component per model output, each reading from the store slice Section 9.5 defines and falling back to a loading/empty state until the first REST snapshot or WebSocket message arrives.


### FaultAlertBanner.tsx

function FaultAlertBanner({ engineId }: { engineId: string }) {
  const fault = useDashboardStore((s) => s.engines[engineId]?.fault);
  if (!fault) return <EmptyState label="No fault prediction yet" />;
  if (fault.faultClass === 'no_failure') return <HealthyBadge />;
  return (
    <AlertBanner
      severity={fault.confidence > 0.85 ? 'critical' : 'warning'}
      label={formatFaultClass(fault.faultClass)}
      confidence={fault.confidence}
    />
  );
}


### RulTrendChart.tsx

function RulTrendChart({ engineId }: { engineId: string }) {
  const { data } = useQuery(['rul', engineId], () => getRulTrend(engineId));
  return (
    <LineChart data={data}>
      <XAxis dataKey="ts" />
      <YAxis label="RUL (hours)" />
      <Line dataKey="rulHours" stroke={C_BLUE} />
      <Line dataKey="degradationIndex" stroke={C_AMBER} yAxisId="right" />
    </LineChart>
  );
}


### BearingHealthGauge.tsx / HealthScoreGauge.tsx

Same pattern: read the relevant store slice, render a gauge (severity_score or combined_score mapped to 0–100), and color the gauge by the same severity bands the backend alert engine uses (info / warning / critical) so the dashboard and the alert system never disagree about what counts as 'bad'.


## 9.8 Error, Loading, and Empty States

404 'no prediction yet' from any /latest or /rul or /bearing-health endpoint → render an explicit empty state, not a zeroed chart — a missing prediction is not the same as a healthy one.

401/403 → route back through the auth flow (Section 9.9); a JWT expiry mid-session should not silently blank a live engine view.

WebSocket close code 4401/4403 (per the main document's live-streaming endpoint spec) → the hook should attempt one silent token refresh and reconnect before surfacing a connection error to the operator.


## 9.9 Authentication on the Frontend

Access + refresh JWTs are issued by POST /api/v1/auth/login and stored in the auth Zustand slice, per the main document's Section 6.8.

REST calls attach the access token as a Bearer header; the WebSocket attaches it as a ?token= query param at handshake, since browsers can't set custom headers on a WebSocket upgrade.

Role gates in the UI (e.g. hiding maintenance-log write actions from an 'operator' role) should mirror the backend's RBAC roles exactly — operator, maintenance_engineer, program_manager, admin — so the frontend never offers an action the backend will 403.


# 10. Summary Table & Open Items


## 10.1 All 4 Models at a Glance


| Model | Dataset | Output fields | DB table | Live WS event |
| --- | --- | --- | --- | --- |
| Fault | ALFA (CMU AirLab) | class_id, fault_class, confidence, probabilities | fault_predictions | fault_prediction |
| RUL | NASA C-MAPSS | rul_cycles, degradation_index | rul_predictions | rul_prediction |
| Bearing | CWRU | fault_location, severity_score | bearing_health_readings | bearing_health |
| Aux | AI4I 2020 + unconfirmed dataset | auxiliary score | none yet (proposed) | none yet |



## 10.2 Open Item: Fault-Class Mismatch

The main Project Implementation Document's fault taxonomy (misfire, injector abnormality, cooling degradation, lubrication issue, sensor drift, combustion instability) does not match the ALFA dataset's actual labels (no failure, RC failure, GPS failure, aileron failure, elevator failure, rudder failure, engine failure), confirmed directly from the architecture diagram and the dataset guide's dataset sheet.

Option A: retrain the Fault model against the engine-specific taxonomy using a different or relabeled dataset — the cleaner fit for a piston-engine health monitor, but requires sourcing new labeled data.

Option B: keep ALFA and its actual 7 classes, and reframe the Fault model's scope in the main document as broader UAV-system fault detection rather than engine-specific fault detection.

Either way, this should be resolved before the model spec (Section 3), the database CHECK constraint on fault_predictions.fault_class, and the frontend's faultClass union type (Section 9.4) are finalized — right now all three assume different things.


## 10.3 Open Item: Schema Gaps

Add an aux_predictions table (engine_id, model_version_id, ts, aux_score), mirroring the other three prediction tables, so the Aux model's output is queryable and traceable like the rest (Section 6.4).

Add model_version_id to bearing_health_readings so bearing predictions are traceable to a specific model_registry version the same way fault and RUL predictions already are (Section 5.4).


## 10.4 Open Item: Unconfirmed Dataset

The Aux model's second dataset ('engine failure dataset') still has no linked source. Re-verify and paste the exact Kaggle/UCI URL into the Dataset & Model Collection Guide before this goes into a submission — this is the single most likely provenance question a judge will ask.


## 10.5 Non-ML Items Tracked Separately

Physics model: source engine performance maps / thermodynamic constants / manufacturer spec sheets for a piston engine, or a public aero-engine thermodynamic reference as a proxy.

Simulation engine: confirm the 'Mission & history' data collection already covers hot-weather, high-altitude, and rapid-throttle-transient scenario diversity, since DRDO explicitly asked for these conditions.

CWRU bearing data requires direct portal registration, unlike the other 4 datasets which are available via open mirrors — start this early so it doesn't block the Bearing model's training schedule.
