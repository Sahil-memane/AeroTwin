/**
 * Adapters that turn the three data sources the twin can show — the live store, one replay step,
 * a What-If result — into the same `TwinInputs`. They only rename and pass through backend
 * values; no health, physics or confidence is computed here.
 */
import type { EngineLiveState } from "@/store/telemetryStore";
import type { EngineTwinSpec, PhysicsConsistencyParameter, SimulationStepResult, WhatIfResponse } from "@/types";
import type { HealthInput, TwinInputs } from "@/lib/engineTwin";

// ── live ────────────────────────────────────────────────────────────

export function inputsFromLive(args: {
  spec: EngineTwinSpec | null;
  live: EngineLiveState | undefined;
  vibrationHistory: number[];
  nowMs: number;
}): TwinInputs {
  const { spec, live, vibrationHistory, nowMs } = args;
  const hs = live?.healthScore;
  const health: HealthInput | null = hs
    ? {
        score: hs.combined_score,
        factors: hs.contributing_factors,
        missing: hs.missing_sources ?? [],
        excluded: hs.excluded_sources ?? [],
        primaryConcern: hs.primary_concern ?? null,
      }
    : null;
  return {
    kind: "live",
    spec,
    telemetry: live?.telemetry,
    quality: live?.telemetry?.quality_status ?? null,
    physics: live?.physicsConsistency,
    bearing: live?.bearing,
    fault: live?.fault,
    aux: live?.aux,
    rul: live?.rul,
    health,
    vibrationHistory,
    nowMs,
  };
}

// ── replay ──────────────────────────────────────────────────────────

const SENSORS = ["rpm", "cht", "egt", "oil_pressure", "oil_temp", "fuel_flow"] as const;

export function inputsFromReplayFrame(args: {
  spec: EngineTwinSpec | null;
  frame: SimulationStepResult | undefined;
  index: number;
  total: number;
  /** Vibration magnitudes of the steps up to and including this one (oldest -> newest). */
  vibrationHistory: number[];
  nowMs: number;
}): TwinInputs {
  const { spec, frame, index, total, vibrationHistory, nowMs } = args;
  if (!frame) return { kind: "replay", spec, nowMs };
  const t = frame.telemetry;
  const complete = SENSORS.every((k) => typeof t[k] === "number");
  const physics: PhysicsConsistencyParameter[] | undefined = frame.physics
    ? frame.physics.map((p) => ({ ...p, method: "replay" }))
    : undefined;
  const fault = frame.fault ?? undefined;
  const health: HealthInput = {
    score: frame.health_score.combined_score,
    factors: frame.health_score.contributing_factors,
    // A replay frame has no "missing" list of its own: a source with no output at that step is simply absent.
    missing: [...(frame.rul ? [] : ["rul"]), ...(frame.fault ? [] : ["fault"])],
    excluded: fault && fault.reliable === false ? ["fault"] : [],
    primaryConcern: null,
  };
  return {
    kind: "replay",
    spec,
    telemetry: complete
      ? {
          rpm: t.rpm as number,
          cht: t.cht as number,
          egt: t.egt as number,
          oil_pressure: t.oil_pressure as number,
          oil_temp: t.oil_temp as number,
          fuel_flow: t.fuel_flow as number,
          vibration_x: t.vibration_x ?? null,
          vibration_y: t.vibration_y ?? null,
          vibration_z: t.vibration_z ?? null,
          ts: frame.ts,
        }
      : undefined,
    quality: null, // the per-reading quality flag isn't part of a replay frame
    physics,
    bearing: frame.bearing ?? undefined,
    fault,
    aux: frame.aux ?? undefined,
    rul: frame.rul ?? undefined,
    health,
    vibrationHistory,
    sourceLabel: `Step ${index + 1} / ${total}`,
    nowMs,
  };
}

// ── what-if ─────────────────────────────────────────────────────────

const WHATIF_TO_SENSOR: Record<string, PhysicsConsistencyParameter["parameter"]> = {
  cht: "cht",
  egt: "egt",
  oil_pressure: "oil_pressure",
  oil_temperature: "oil_temp",
  fuel_flow: "fuel_flow",
};

/** The SCENARIO side of a What-If result. (The "current" side is simply the live source.) */
export function inputsFromWhatIf(args: { spec: EngineTwinSpec | null; result: WhatIfResponse | null; nowMs: number }): TwinInputs {
  const { spec, result: r, nowMs } = args;
  if (!r || !r.scenario || !r.model_results || !r.health_fusion) return { kind: "whatif", spec, nowMs };
  const s = r.scenario;
  const m = r.model_results;
  const fusion = r.health_fusion.scenario;

  const physics: PhysicsConsistencyParameter[] | undefined = r.physics_consistency
    ? Object.entries(r.physics_consistency.parameters).flatMap(([name, p]) =>
        p && WHATIF_TO_SENSOR[name]
          ? [{ parameter: WHATIF_TO_SENSOR[name], expected: p.expected, measured: p.measured, residual: p.residual, status: p.status, method: p.method }]
          : [],
      )
    : undefined;

  const fault = m.fault.scenario;
  const bearing = m.bearing.scenario;
  const aux = m.auxiliary.scenario;
  const rul = m.rul.scenario;

  return {
    kind: "whatif",
    spec,
    // A What-If changes only the six parameters: vibration isn't part of the scenario, so it is left unavailable.
    telemetry: { rpm: s.rpm, cht: s.cht, egt: s.egt, oil_pressure: s.oil_pressure, oil_temp: s.oil_temperature, fuel_flow: s.fuel_flow, ts: null },
    quality: null,
    physics,
    fault:
      fault.status === "COMPLETED" && fault.fault_class !== undefined
        ? { fault_class: fault.fault_class, confidence: fault.confidence ?? 0, state: fault.state as never, reliable: fault.reliable, input_coverage: fault.input_coverage }
        : undefined,
    bearing:
      bearing.status === "COMPLETED" && bearing.class_label !== undefined
        ? { class_label: bearing.class_label, fault_location: bearing.fault_location ?? "", severity_inches: bearing.severity_inches ?? null, confidence: bearing.confidence ?? 0 }
        : undefined,
    aux:
      aux.status === "COMPLETED" && aux.risk_level !== undefined
        ? { risk_level: aux.risk_level, failure_probability_pct: aux.failure_probability_pct ?? 0, primary_failure_cause: aux.primary_failure_cause ?? null }
        : undefined,
    rul: rul.status === "COMPLETED" && rul.rul_cycles !== undefined ? { rul_cycles: rul.rul_cycles } : undefined,
    health: {
      // With sources missing the backend-side assessment is partial: show no score rather than a misleading one.
      score: fusion.missing_sources.length > 0 ? null : fusion.score,
      factors: fusion.contributing_factors,
      missing: fusion.missing_sources,
      excluded: fusion.excluded_sources,
      primaryConcern: fusion.primary_concern,
    },
    sourceLabel: "Scenario (PARAMETER PERTURBATION)",
    nowMs,
  };
}
