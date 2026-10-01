// Mirrors backend/app/schemas/*.py — keep in sync with the API contract
// (docs/api/openapi.yaml is generated straight from the live FastAPI app).

export type Role = "operator" | "maintenance_engineer" | "program_manager" | "admin";

export interface User {
  id: string;
  email: string;
  role: Role;
  is_active: boolean;
}

export interface UAVAsset {
  id: string;
  tail_number: string;
  status: string;
}

export interface Engine {
  id: string;
  serial_number: string;
  uav_asset_id: string | null;
  status: string;
}

export interface Mission {
  id: string;
  uav_asset_id: string;
  mission_type: string;
  start_time: string;
  end_time: string | null;
  environmental_profile: Record<string, unknown> | null;
  status: string;
  // Only present when listed with `?include_stats=true`: how much telemetry is stored for this mission
  // (0, not undefined, means "none").
  reading_count?: number | null;
  first_ts?: string | null;
  last_ts?: string | null;
}

export interface TelemetrySummary {
  reading_count: number;
  first_ts: string | null;
  last_ts: string | null;
  rpm_avg: number | null;
  rpm_max: number | null;
  cht_avg: number | null;
  cht_max: number | null;
  egt_avg: number | null;
  egt_max: number | null;
  oil_pressure_min: number | null;
  fuel_flow_avg: number | null;
}

export interface MissionDetail extends Mission {
  telemetry_summary: TelemetrySummary | null;
}

export interface TelemetryReading {
  engine_id: string;
  mission_id: string | null;
  ts: string;
  rpm: number;
  cht: number;
  egt: number;
  oil_pressure: number;
  oil_temp: number;
  fuel_flow: number;
  vibration_x: number | null;
  vibration_y: number | null;
  vibration_z: number | null;
  /** VALID / STALE / SUSPICIOUS — the data-quality classification the backend gave this reading. */
  quality_status?: string | null;
}

export interface RulPrediction {
  engine_id: string;
  ts: string;
  rul_cycles: number;
  degradation_index: number;
  // Accuracy-First Phase 2 — real split-conformal interval + what the
  // service observed at prediction time. Absent/null on rows written
  // before these existed.
  rul_lower?: number | null;
  rul_upper?: number | null;
  status?: string | null;
}

export interface RulStatus {
  engine_id: string;
  status: "INITIALIZING" | "INSUFFICIENT_DATA" | "VALID" | "MODEL_ERROR";
  samples_collected: number;
  samples_required: number;
  last_prediction_ts: string | null;
}

export const FAULT_CLASSES = [
  "No Failure",
  "RC Failure",
  "GPS Failure",
  "Accelerometer Failure",
  "Gyro Failure",
  "Compass Failure",
  "Barometer Failure",
] as const;

export type FaultState =
  | "NORMAL"
  | "ANOMALY_DETECTED"
  | "FAULT_SUSPECTED"
  | "FAULT_CONFIRMED"
  | "RECOVERED"
  | "SENSOR_ANOMALY";

export interface FaultPrediction {
  ts: string;
  engine_id: string;
  model_version_id: string;
  class_id: number;
  fault_class: string;
  confidence: number;
  probabilities: number[];
  // Accuracy-First Phase 3 — temporal-consistency state machine state.
  // Absent/null on rows written before this column existed.
  state?: FaultState | null;
  // Share of the model's 32 input channels driven by measured telemetry (the rest are
  // fixed placeholders for a piston engine). `reliable === false` means ADVISORY: shown for
  // information but excluded from Health Fusion and alerts. Absent on legacy rows (= reliable).
  input_coverage?: number | null;
  reliable?: boolean;
}

export interface BearingHealthReading {
  ts: string;
  engine_id: string;
  model_version_id: string;
  class_id: number;
  class_label: string;
  fault_location: string;
  severity_inches: number | null;
  confidence: number;
}

export interface AuxFailureType {
  code: string;
  full_name: string;
  probability: number;
  active: boolean;
  cause: string;
}

export interface AuxPrediction {
  ts: string;
  engine_id: string;
  model_version_id: string;
  failure_status: string;
  risk_level: string;
  failure_probability_pct: number;
  detected_failure_types: AuxFailureType[];
  primary_failure_cause: string | null;
  recommended_action: string | null;
}

// Accuracy-First Phase 4 — Otto-cycle physics model vs. measured
// telemetry, one entry per channel the solver covers.
export type PhysicsConsistencyStatus = "CONSISTENT" | "ELEVATED" | "REVIEW" | "ANOMALY";

export interface PhysicsConsistencyParameter {
  parameter: "cht" | "egt" | "oil_pressure" | "oil_temp" | "fuel_flow";
  ts?: string;
  expected: number;
  measured: number;
  residual: number;
  status: PhysicsConsistencyStatus;
  method: string;
}

export interface PhysicsConsistencyResponse {
  engine_id: string;
  parameters: PhysicsConsistencyParameter[];
}

export type AlertSeverity = "warning" | "critical";

export interface Alert {
  id: string;
  engine_id: string;
  source: string;
  severity: AlertSeverity;
  message: string;
  created_at: string;
  is_acknowledged: boolean;
  acknowledged_by: string | null;
  acknowledged_at: string | null;
}

export interface MaintenanceLog {
  id: string;
  engine_id: string;
  user_id: string;
  logged_at: string;
  action_taken: string;
  notes: string | null;
}

export interface ModelRegistryEntry {
  id: string;
  model_name: string;
  version: string;
  is_active: boolean;
  validation_score: number | null;
  registered_at: string;
}

export interface ContributingFactor {
  source: "rul" | "fault" | "bearing" | "aux";
  penalty?: number;
  forced_zero?: boolean;
  // Accuracy-First Phase 5 — set on both factors of a correlated
  // fault+bearing pair whose combined penalty was capped (double-
  // counting mitigation); see health_fusion.py.
  correlated_with?: string;
  dedup_note?: string;
  [key: string]: unknown;
}

export type HealthStatus = "healthy" | "warning" | "critical";

export interface HealthScoreResponse {
  engine_id: string;
  // null when no health_scores row exists yet for this engine —
  // Accuracy-First Phase 2: never fabricated as 100.
  combined_score: number | null;
  contributing_factors: ContributingFactor[];
  // Accuracy-First Phase 5 — one-line summary of the single largest
  // contributing factor. Null/absent on rows written before this
  // existed, or when there's genuinely nothing to report.
  primary_concern?: string | null;
  status: HealthStatus | "insufficient_data";
  last_updated: string | null;
  /** Seconds since `last_updated`; null when there is no score yet. */
  age_seconds?: number | null;
  /** True when the newest persisted score is old (engine likely stopped streaming). Flagged, not hidden. */
  stale?: boolean;
  history: { ts: string; combined_score: number }[];
}

export interface FleetHealth {
  average_score: number | null;
  engines_critical: number;
  engines_warning: number;
  engines_healthy: number;
}

export interface DashboardSummary {
  total_engines: number;
  total_uav_assets: number;
  active_missions: number;
  open_alerts: number;
  fleet_health: FleetHealth;
  recent_alerts: Alert[];
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  role: Role;
}

export interface CopilotResponse {
  answer: string;
  sources: string[];
}

// ── Simulation (replay / what-if) ────────────────────────────────────
export type SimulationMode = "replay" | "what_if";
export type SimulationStatus = "queued" | "running" | "completed" | "failed";

export interface SimulationStepResult {
  step: number;
  ts: string | null;
  telemetry: {
    rpm: number | null;
    cht: number | null;
    egt: number | null;
    oil_pressure: number | null;
    oil_temp: number | null;
    fuel_flow: number | null;
    vibration_x?: number | null;
    vibration_y?: number | null;
    vibration_z?: number | null;
  };
  /** Physics consistency for THIS step (expected / measured / residual / status). */
  physics?: { parameter: "cht" | "egt" | "oil_pressure" | "oil_temp" | "fuel_flow"; expected: number; measured: number; residual: number; status: PhysicsConsistencyStatus }[] | null;
  rul: { rul_cycles: number; rul_lower: number; rul_upper: number; degradation_index: number } | null;
  fault: FaultPrediction | null;
  bearing: BearingHealthReading | null;
  aux: AuxPrediction | null;
  health_score: { combined_score: number; contributing_factors: ContributingFactor[] };
}

export interface SimulationRunResponse {
  simulation_id: string;
  status: SimulationStatus;
  mode: SimulationMode;
  error: string | null;
  results: SimulationStepResult[] | null;
  created_at: string;
  completed_at: string | null;
}

// ── WebSocket live-stream message envelope ──────────────────────────
export type LiveMessageType =
  | "telemetry"
  | "rul_prediction"
  | "fault_prediction"
  | "bearing_prediction"
  | "aux_prediction"
  | "health_score"
  | "physics_consistency"
  | "alert";

export interface LiveMessage<T = unknown> {
  type: LiveMessageType;
  payload: T;
}

// ── Parameter What-If (POST /simulation/what-if) ─────────────────────
// Mirrors backend/app/services/what_if_scenario.py. Every value the What-If
// result UI shows comes from these fields — nothing is derived client-side
// except display formatting and the sliders' own current/scenario/delta.
export const WHAT_IF_PARAMS = ["rpm", "cht", "egt", "oil_pressure", "oil_temperature", "fuel_flow"] as const;
export type WhatIfParam = (typeof WHAT_IF_PARAMS)[number];

export type WhatIfValues = Record<WhatIfParam, number>;

export interface WhatIfParamConfig {
  min: number;
  max: number;
  step: number;
  unit: string;
}

export interface WhatIfConfig {
  parameters: Record<WhatIfParam, WhatIfParamConfig>;
  perturbation_window: number;
  required_readings: { fault: number; rul: number };
  feature_mapping: Record<string, { direct: WhatIfParam[]; note: string }>;
}

export type WhatIfSimulationStatus =
  | "COMPLETED"
  | "INSUFFICIENT_DATA"
  | "MODEL_UNAVAILABLE"
  | "INVALID_INPUT"
  | "ERROR";

export type WhatIfModelStatus = "COMPLETED" | "INSUFFICIENT_DATA" | "MODEL_UNAVAILABLE" | "ERROR";

interface WhatIfModelBase {
  status: WhatIfModelStatus;
  message?: string;
}

export interface WhatIfRulResult extends WhatIfModelBase {
  rul_cycles?: number;
  rul_lower?: number;
  rul_upper?: number;
  degradation_index?: number;
  /** The RUL model's own status (VALID | MODEL_ERROR); `status` above is the What-If block status. */
  model_status?: string;
}

export interface WhatIfFaultResult extends WhatIfModelBase {
  fault_class?: string;
  class_id?: number;
  confidence?: number;
  state?: string;
  inferences?: number;
  probabilities?: number[];
  input_coverage?: number;
  /** false => advisory only: shown, but set aside by Health Fusion. */
  reliable?: boolean;
}

export interface WhatIfBearingResult extends WhatIfModelBase {
  class_label?: string;
  fault_location?: string;
  severity_inches?: number | null;
  confidence?: number;
  class_id?: number;
  probabilities?: number[];
  inputs?: { vibration_magnitude: number | null; rpm: number | null };
}

export interface WhatIfAuxResult extends WhatIfModelBase {
  failure_status?: string;
  risk_level?: string;
  failure_probability_pct?: number;
  primary_failure_cause?: string | null;
  detected_failure_types?: { code: string; full_name?: string; probability?: number; active?: boolean }[];
  recommended_action?: string;
}

interface WhatIfComparison<T> {
  baseline: T;
  scenario: T;
  changed: boolean;
}

export interface WhatIfModelResults {
  rul: WhatIfComparison<WhatIfRulResult> & { delta_cycles: number | null };
  fault: WhatIfComparison<WhatIfFaultResult> & { delta_confidence: number | null };
  bearing: WhatIfComparison<WhatIfBearingResult> & { input_changed: boolean; note: string };
  auxiliary: WhatIfComparison<WhatIfAuxResult> & {
    input_changed: boolean;
    note: string | null;
    delta_failure_probability_pct: number | null;
  };
}

export type WhatIfFusionSource = "rul" | "fault" | "bearing" | "aux";

export interface WhatIfFusionSourceView {
  /** null when the source forced the score to 0 (no single penalty applies). */
  penalty: number | null;
  active: boolean;
  forced_zero: boolean;
  /** false when the source produced no usable model output (so 0 does NOT mean "healthy"). */
  available: boolean;
  /** true when the source reported but was deliberately not scored (fault: input coverage too low). */
  excluded: boolean;
}

export interface WhatIfFusionSide {
  score: number;
  contributing_factors: ContributingFactor[];
  sources: Record<WhatIfFusionSource, WhatIfFusionSourceView>;
  primary_concern: string | null;
  forced_zero: boolean;
  missing_sources: WhatIfFusionSource[];
  /** Reported but set aside (advisory) — distinct from missing: the score is still a real assessment of the rest. */
  excluded_sources: WhatIfFusionSource[];
}

export interface WhatIfHealthFusion extends WhatIfFusionSide {
  baseline: WhatIfFusionSide;
  scenario: WhatIfFusionSide;
  score_delta: number;
}

export type PhysicsResidualStatus = "CONSISTENT" | "ELEVATED" | "REVIEW" | "ANOMALY";

export interface WhatIfPhysicsParameter {
  expected: number;
  measured: number;
  residual: number;
  status: PhysicsResidualStatus;
  method: string;
  baseline_residual: number;
  baseline_status: PhysicsResidualStatus;
}

export interface WhatIfSimulationAlert {
  source: string;
  severity: "warning" | "critical";
  message: string;
  simulation: true;
}

export type WhatIfAlertChange = "NONE" | "NEW" | "CLEARED" | "UNCHANGED" | "ESCALATED" | "DEESCALATED";

export interface WhatIfResponse {
  mode: "WHAT_IF";
  scenario_type: "PARAMETER_PERTURBATION";
  perturbation_count: number;
  perturbation_window_config: number;
  perturbation_method: string;
  engine_id: string;
  simulation_status: WhatIfSimulationStatus;
  message?: string;
  baseline_timestamp: string | null;
  /** null only when the engine has no telemetry at all. */
  baseline: WhatIfValues | null;
  scenario: WhatIfValues | null;
  delta: WhatIfValues | null;
  window: {
    total_readings: number;
    perturbed_readings: number;
    required_readings: { fault: number; rul: number };
    loaded_target: number;
    data_sufficiency: "SUFFICIENT" | "PARTIAL" | "INSUFFICIENT_DATA";
    clamped_values?: number;
    aux_wear_seed?: number;
    aux_wear_source?: string;
  };
  feature_mapping?: WhatIfConfig["feature_mapping"];
  model_results: WhatIfModelResults | null;
  health_fusion: WhatIfHealthFusion | null;
  physics_consistency: {
    deviation_score: { baseline: number; scenario: number };
    parameters: Partial<Record<Exclude<WhatIfParam, "rpm">, WhatIfPhysicsParameter>>;
  } | null;
  alerts: {
    simulation: true;
    baseline: WhatIfSimulationAlert | null;
    scenario: WhatIfSimulationAlert | null;
    change: WhatIfAlertChange;
  } | null;
  assumptions?: string[];
  model_versions?: Record<string, string>;
  live_reference?: { combined_score: number; ts: string } | null;
}

// ── 3D digital twin (GET /engines/{id}/twin) ─────────────────────────
export interface EngineTwinSpec {
  engine_id: string;
  serial_number: string;
  spec: {
    num_cylinders: number;
    layout: "horizontally_opposed" | string;
    displacement_cc: number;
    compression_ratio: number;
    rpm_idle: number;
    rpm_cruise: number;
    rpm_max: number;
    rated_power_kw: number;
    /** null = NOT declared in the engine spec (unknown) — never assume true or false. */
    turbocharged: boolean | null;
    /** Where these numbers come from (shown to the operator). */
    source: string;
  };
  /** Configured sensor ranges [min, max] — impossible-value ceilings, not verified operating limits. */
  sensor_ranges: Record<"rpm" | "cht" | "egt" | "oil_pressure" | "oil_temp" | "fuel_flow", [number, number]>;
  physics_tolerances: Record<string, number>;
  sensors: {
    /** false => ONE CHT and ONE EGT for the whole engine; per-cylinder temperatures are not measured. */
    per_cylinder: boolean;
    per_cylinder_columns: string[];
    note: string;
  };
}
