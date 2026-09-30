import type {
  TelemetryReading,
  WhatIfConfig,
  WhatIfFusionSide,
  WhatIfFusionSourceView,
  WhatIfResponse,
  WhatIfValues,
} from "@/types";

// Deliberately NOT the real backend bounds: the tests prove the UI takes
// slider ranges from GET /simulation/what-if/config rather than hardcoding.
export const CONFIG: WhatIfConfig = {
  parameters: {
    rpm: { min: 111, max: 6400, step: 10, unit: "RPM" },
    cht: { min: 11, max: 399, step: 1, unit: "°C" },
    egt: { min: 12, max: 999, step: 1, unit: "°C" },
    oil_pressure: { min: 13, max: 149, step: 0.5, unit: "psi" },
    oil_temperature: { min: 14, max: 199, step: 0.5, unit: "°C" },
    fuel_flow: { min: 1, max: 29, step: 0.1, unit: "GPH" },
  },
  perturbation_window: 10,
  required_readings: { fault: 80, rul: 30 },
  feature_mapping: {
    rul: { direct: ["rpm", "cht", "egt", "oil_pressure", "oil_temperature", "fuel_flow"], note: "" },
    fault: { direct: ["rpm", "cht", "egt", "oil_pressure", "oil_temperature", "fuel_flow"], note: "" },
    bearing: { direct: ["rpm"], note: "" },
    auxiliary: { direct: ["rpm", "cht"], note: "" },
  },
};

export const TELEMETRY: TelemetryReading = {
  engine_id: "eng-1",
  mission_id: null,
  ts: "2026-09-30T07:52:47.695035",
  rpm: 4908.7,
  cht: 154.69,
  egt: 841.19,
  oil_pressure: 93.07,
  oil_temp: 98.84,
  fuel_flow: 3.41,
  vibration_x: 0.3,
  vibration_y: 0.2,
  vibration_z: 0.1,
};

export const CURRENT: WhatIfValues = {
  rpm: 4908.7,
  cht: 154.69,
  egt: 841.19,
  oil_pressure: 93.07,
  oil_temperature: 98.84,
  fuel_flow: 3.41,
};

const src = (over: Partial<WhatIfFusionSourceView> = {}): WhatIfFusionSourceView => ({
  penalty: 0,
  active: false,
  forced_zero: false,
  available: true,
  excluded: false,
  ...over,
});

const fusionSide = (score: number, over: Partial<WhatIfFusionSide["sources"]> = {}): WhatIfFusionSide => ({
  score,
  contributing_factors: [],
  sources: { rul: src(), fault: src(), bearing: src(), aux: src(), ...over },
  primary_concern: null,
  forced_zero: false,
  missing_sources: [],
  excluded_sources: [],
});

export function makeResponse(over: Partial<WhatIfResponse> = {}): WhatIfResponse {
  const scenario: WhatIfValues = { ...CURRENT, rpm: 5300, egt: 880 };
  const baselineFusion = fusionSide(65, {
    rul: src({ penalty: 5, active: true }),
    bearing: src({ penalty: 20, active: true }),
    aux: src({ penalty: 10, active: true }),
  });
  const scenarioFusion = fusionSide(54, {
    rul: src({ penalty: 18, active: true }),
    bearing: src({ penalty: 20, active: true }),
    aux: src({ penalty: 8, active: true }),
  });
  return {
    mode: "WHAT_IF",
    scenario_type: "PARAMETER_PERTURBATION",
    perturbation_count: 10,
    perturbation_window_config: 10,
    perturbation_method: "delta_applied_to_last_k_readings",
    engine_id: "eng-1",
    simulation_status: "COMPLETED",
    baseline_timestamp: TELEMETRY.ts,
    baseline: CURRENT,
    scenario,
    delta: {
      rpm: 391.3,
      cht: 0,
      egt: 38.81,
      oil_pressure: 0,
      oil_temperature: 0,
      fuel_flow: 0,
    },
    window: {
      total_readings: 89,
      perturbed_readings: 10,
      required_readings: { fault: 80, rul: 30 },
      loaded_target: 89,
      data_sufficiency: "SUFFICIENT",
      clamped_values: 0,
    },
    model_results: {
      rul: {
        baseline: { status: "COMPLETED", rul_cycles: 126, rul_lower: 100, rul_upper: 125, degradation_index: 0 },
        scenario: { status: "COMPLETED", rul_cycles: 91, rul_lower: 70, rul_upper: 115, degradation_index: 0.27 },
        changed: true,
        delta_cycles: -35,
      },
      fault: {
        baseline: { status: "COMPLETED", fault_class: "No Failure", state: "NORMAL", confidence: 0.98 },
        scenario: { status: "COMPLETED", fault_class: "Compass Failure", state: "ANOMALY_DETECTED", confidence: 0.78 },
        changed: true,
        delta_confidence: -0.2,
      },
      bearing: {
        baseline: { status: "COMPLETED", class_label: "OR_021", fault_location: "Outer Race", severity_inches: 0.021, confidence: 0.67 },
        scenario: { status: "COMPLETED", class_label: "OR_021", fault_location: "Outer Race", severity_inches: 0.021, confidence: 0.67 },
        changed: false,
        input_changed: false,
        note: "Bearing prediction unchanged: the scenario did not modify the bearing model's inputs (vibration magnitude, RPM).",
      },
      auxiliary: {
        baseline: { status: "COMPLETED", risk_level: "MODERATE", failure_probability_pct: 30.8, primary_failure_cause: null },
        scenario: { status: "COMPLETED", risk_level: "MODERATE", failure_probability_pct: 30.8, primary_failure_cause: null },
        changed: false,
        input_changed: true,
        note: null,
        delta_failure_probability_pct: 0,
      },
    },
    health_fusion: { ...scenarioFusion, baseline: baselineFusion, scenario: scenarioFusion, score_delta: -11 },
    physics_consistency: {
      deviation_score: { baseline: 0.4, scenario: 0.9 },
      parameters: {
        cht: { expected: 150, measured: 154.69, residual: 4.69, status: "CONSISTENT", method: "m", baseline_residual: 4.69, baseline_status: "CONSISTENT" },
        egt: { expected: 830, measured: 880, residual: 50, status: "REVIEW", method: "m", baseline_residual: 11.19, baseline_status: "CONSISTENT" },
        oil_pressure: { expected: 90, measured: 93.07, residual: 3.07, status: "CONSISTENT", method: "m", baseline_residual: 3.07, baseline_status: "CONSISTENT" },
        oil_temperature: { expected: 97, measured: 98.84, residual: 1.84, status: "CONSISTENT", method: "m", baseline_residual: 1.84, baseline_status: "CONSISTENT" },
        fuel_flow: { expected: 3.2, measured: 3.41, residual: 0.21, status: "CONSISTENT", method: "m", baseline_residual: 0.21, baseline_status: "CONSISTENT" },
      },
    },
    alerts: {
      simulation: true,
      baseline: null,
      scenario: { source: "fusion", severity: "warning", message: "RUL: 91 cycles remaining (-18pts)", simulation: true },
      change: "NEW",
    },
    assumptions: ["telemetry_readings does not persist throttle/altitude_m."],
    model_versions: { rul_model: "unregistered" },
    live_reference: { combined_score: 55.92, ts: "2026-09-30T07:52:47" },
    ...over,
  };
}

/** Backend response when the window is too short: RUL/Fault unavailable, Health Fusion missing sources. */
export function makeInsufficientResponse(): WhatIfResponse {
  const base = makeResponse();
  const unavailable = { status: "INSUFFICIENT_DATA" as const, message: "20/30 readings available" };
  const fusion = fusionSide(100, {
    rul: src({ available: false }),
    fault: src({ available: false }),
  });
  fusion.missing_sources = ["rul", "fault"];
  return {
    ...base,
    simulation_status: "INSUFFICIENT_DATA",
    window: { ...base.window, total_readings: 20, perturbed_readings: 10, data_sufficiency: "INSUFFICIENT_DATA" },
    model_results: {
      ...base.model_results!,
      rul: { baseline: unavailable, scenario: unavailable, changed: false, delta_cycles: null },
      fault: {
        baseline: { status: "INSUFFICIENT_DATA", message: "20/80 readings available" },
        scenario: { status: "INSUFFICIENT_DATA", message: "20/80 readings available" },
        changed: false,
        delta_confidence: null,
      },
    },
    health_fusion: { ...fusion, baseline: fusion, scenario: fusion, score_delta: 0 },
    alerts: { simulation: true, baseline: null, scenario: null, change: "NONE" },
  };
}
