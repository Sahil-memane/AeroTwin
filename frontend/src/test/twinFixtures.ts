import type { EngineTwinSpec, PhysicsConsistencyParameter, SimulationStepResult, TelemetryReading } from "@/types";
import { buildTwinViewModel, type TwinInputs, type TwinViewModel } from "@/lib/engineTwin";

/** Deliberately not the real engine's numbers: tests prove the UI reads them from the API response. */
export function makeSpec(over: Partial<EngineTwinSpec["spec"]> = {}, per_cylinder = false): EngineTwinSpec {
  return {
    engine_id: "eng-1",
    serial_number: "TEST-ENGINE-9",
    spec: {
      num_cylinders: 4,
      layout: "horizontally_opposed",
      displacement_cc: 1234,
      compression_ratio: 9.5,
      rpm_idle: 1300,
      rpm_cruise: 4700,
      rpm_max: 5900,
      rated_power_kw: 77.7,
      turbocharged: null,
      source: "test/specs.py",
      ...over,
    },
    sensor_ranges: { rpm: [0, 6000], cht: [0, 400], egt: [0, 1000], oil_pressure: [0, 150], oil_temp: [0, 200], fuel_flow: [0, 30] },
    physics_tolerances: { cht: 15 },
    sensors: {
      per_cylinder,
      per_cylinder_columns: per_cylinder ? ["cht_1"] : [],
      note: per_cylinder ? "Per-cylinder CHT/EGT sensors are available." : "One CHT and one EGT for the whole engine; per-cylinder temperatures are not measured.",
    },
  };
}

export function makeTelemetry(over: Partial<TelemetryReading> = {}): TelemetryReading {
  return {
    engine_id: "eng-1",
    mission_id: null,
    ts: new Date().toISOString().replace("Z", ""), // naive UTC "now" — fresh
    rpm: 3000,
    cht: 200,
    egt: 500,
    oil_pressure: 75,
    oil_temp: 100,
    fuel_flow: 15,
    vibration_x: 0.3,
    vibration_y: 0.4,
    vibration_z: 0.0,
    ...over,
  };
}

export const PHYSICS: PhysicsConsistencyParameter[] = [
  { parameter: "cht", expected: 150, measured: 200, residual: 50, status: "REVIEW", method: "m" },
  { parameter: "egt", expected: 520, measured: 500, residual: -20, status: "CONSISTENT", method: "m" },
  { parameter: "oil_pressure", expected: 70, measured: 75, residual: 5, status: "CONSISTENT", method: "m" },
  { parameter: "oil_temp", expected: 95, measured: 100, residual: 5, status: "ELEVATED", method: "m" },
  { parameter: "fuel_flow", expected: 14, measured: 15, residual: 1, status: "ANOMALY", method: "m" },
];

export const minutesAgoNaive = (min: number) => new Date(Date.now() - min * 60_000).toISOString().replace("Z", "");

/** Live-kind inputs with a fresh reading, the spec and the physics fixture; override anything. */
export function liveInputs(over: Partial<TwinInputs> = {}): TwinInputs {
  return { kind: "live", spec: makeSpec(), telemetry: makeTelemetry(), physics: PHYSICS, nowMs: Date.now(), ...over };
}

export function makeVm(over: Partial<TwinInputs> = {}): TwinViewModel {
  return buildTwinViewModel(liveInputs(over));
}

export const BEARING_OR21 = { ts: "t", engine_id: "e", model_version_id: "m", class_id: 9, class_label: "OR_021", fault_location: "Outer Race", severity_inches: 0.021, confidence: 0.9 };
export const BEARING_NORMAL = { ts: "t", engine_id: "e", model_version_id: "m", class_id: 0, class_label: "Normal", fault_location: "None", severity_inches: null, confidence: 0.95 };

export function makeFrame(over: Partial<SimulationStepResult> = {}): SimulationStepResult {
  return {
    step: 0,
    ts: "2026-09-30T07:00:00",
    telemetry: { rpm: 3000, cht: 120, egt: 700, oil_pressure: 70, oil_temp: 90, fuel_flow: 5, vibration_x: 0.3, vibration_y: 0.4, vibration_z: 0 },
    physics: [{ parameter: "cht", expected: 110, measured: 120, residual: 10, status: "ELEVATED" }],
    rul: { rul_cycles: 88, rul_lower: 70, rul_upper: 100, degradation_index: 0.2 },
    fault: null,
    bearing: null,
    aux: null,
    health_score: { combined_score: 77, contributing_factors: [{ source: "rul", penalty: 12 }] },
    ...over,
  };
}
