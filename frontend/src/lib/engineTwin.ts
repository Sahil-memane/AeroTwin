/**
 * Pure logic for the 3D digital twin. Turns REAL data — live telemetry, a replayed step, or a
 * What-If result — plus the engine's configuration into a view model the 3D scene and the
 * panels render. No React, no three.js, so every rule is unit-testable and nothing the twin
 * shows can be hardcoded in the scene.
 *
 * Source of truth: Telemetry -> ML models -> Physics consistency -> Health Fusion -> this view model.
 * The twin never computes a health score, a confidence, a physics value or a per-component health:
 * it only displays what the backend produced, and says "Unavailable" for anything it didn't.
 *
 * Honesty rules baked in:
 *  - ONE CHT and ONE EGT exist for the whole engine (`spec.sensors.per_cylinder === false`),
 *    so no per-cylinder temperature is ever produced here.
 *  - A live reading older than STALE_AFTER_MS is "stale": last-known, not live.
 *  - Colour scales use the CONFIGURED sensor range (impossible-value ceilings, not verified
 *    operating limits); the physics-consistency status is the meaningful signal and is shown apart.
 */
import type {
  AuxPrediction,
  BearingHealthReading,
  ContributingFactor,
  EngineTwinSpec,
  FaultPrediction,
  PhysicsConsistencyParameter,
  PhysicsConsistencyStatus,
  RulPrediction,
  TelemetryReading,
} from "@/types";
import { parseBackendTs } from "@/lib/utils";

export type SensorKey = "rpm" | "cht" | "egt" | "oil_pressure" | "oil_temp" | "fuel_flow";
export const SENSOR_KEYS: SensorKey[] = ["rpm", "cht", "egt", "oil_pressure", "oil_temp", "fuel_flow"];

export const SENSOR_META: Record<SensorKey, { label: string; unit: string }> = {
  rpm: { label: "RPM", unit: "rpm" },
  cht: { label: "CHT", unit: "°C" },
  egt: { label: "EGT", unit: "°C" },
  oil_pressure: { label: "Oil pressure", unit: "psi" },
  oil_temp: { label: "Oil temperature", unit: "°C" },
  fuel_flow: { label: "Fuel flow", unit: "GPH" },
};

export const STALE_AFTER_MS = 5 * 60_000;

/** Real rotation is far too fast to see (5000 rpm = 83 rev/s), so the animation runs at this
 * fraction of real speed. It is proportional to the measured RPM and stated on screen. */
export const VISUAL_TIME_SCALE = 1 / 60;

/** Visual shake (scene units) per unit of measured vibration magnitude, capped so the model stays legible. */
export const SHAKE_GAIN = 0.02;
export const SHAKE_MAX = 0.06;

/** RMS of the recent vibration magnitude needs at least this many readings to mean anything. */
export const MIN_RMS_SAMPLES = 10;

export const STATUS_COLOR: Record<PhysicsConsistencyStatus, string> = {
  CONSISTENT: "#4C9A6A",
  ELEVATED: "#C9962F",
  REVIEW: "#D97A2B",
  ANOMALY: "#C64F44",
};
export const NEUTRAL_COLOR = "#4A515C";
export const ADVISORY_COLOR = "#6C8EBF";

export function clamp01(x: number): number {
  return Math.max(0, Math.min(1, x));
}

/** Position of `value` inside [min, max] as 0..1; null when it can't be computed. */
export function normalise(value: number | null | undefined, min: number, max: number): number | null {
  if (value === null || value === undefined || !Number.isFinite(value) || !(max > min)) return null;
  return clamp01((value - min) / (max - min));
}

const HEAT_STOPS: [number, [number, number, number]][] = [
  [0.0, [38, 70, 130]],
  [0.35, [42, 140, 150]],
  [0.55, [76, 154, 106]],
  [0.75, [201, 150, 47]],
  [1.0, [214, 60, 48]],
];

/** Heat gradient; returns "#rrggbb". `null` (no data) gives the neutral grey. */
export function heatColor(t: number | null): string {
  if (t === null) return NEUTRAL_COLOR;
  const x = clamp01(t);
  for (let i = 1; i < HEAT_STOPS.length; i++) {
    const [t1, c1] = HEAT_STOPS[i];
    const [t0, c0] = HEAT_STOPS[i - 1];
    if (x <= t1) {
      const f = (x - t0) / (t1 - t0);
      const rgb = c0.map((v, k) => Math.round(v + (c1[k] - v) * f));
      return `#${rgb.map((v) => v.toString(16).padStart(2, "0")).join("")}`;
    }
  }
  return "#d63c30";
}

/** Radians per second the crank/propeller turns on screen for a measured RPM. */
export function spinRate(rpm: number | null | undefined): number {
  if (rpm === null || rpm === undefined || !Number.isFinite(rpm) || rpm <= 0) return 0;
  return (rpm / 60) * 2 * Math.PI * VISUAL_TIME_SCALE;
}

type VibrationAxes = { vibration_x?: number | null; vibration_y?: number | null; vibration_z?: number | null };

export function vibrationMagnitude(t?: VibrationAxes | null): number | null {
  if (!t || t.vibration_x == null || t.vibration_y == null || t.vibration_z == null) return null;
  return Math.sqrt(t.vibration_x ** 2 + t.vibration_y ** 2 + t.vibration_z ** 2);
}

/** RMS of a window of vibration magnitudes; null unless there are enough samples to be meaningful. */
export function vibrationRms(history: number[] | undefined): { value: number; samples: number } | null {
  const v = (history ?? []).filter((x) => Number.isFinite(x));
  if (v.length < MIN_RMS_SAMPLES) return null;
  return { value: Math.sqrt(v.reduce((s, x) => s + x * x, 0) / v.length), samples: v.length };
}

export function shakeAmplitude(vibMag: number | null): number {
  if (vibMag === null || !Number.isFinite(vibMag) || vibMag <= 0) return 0;
  return Math.min(SHAKE_MAX, vibMag * SHAKE_GAIN);
}

export function bearingSeverityColor(severity: number | null | undefined, classLabel?: string): string {
  if (!classLabel || classLabel === "Normal" || !severity) return STATUS_COLOR.CONSISTENT;
  if (severity >= 0.021) return STATUS_COLOR.ANOMALY;
  return STATUS_COLOR.ELEVATED;
}

export function healthColor(score: number | null | undefined, forcedZero = false): string {
  if (score === null || score === undefined) return NEUTRAL_COLOR;
  if (forcedZero || score < 20) return STATUS_COLOR.ANOMALY;
  if (score < 50) return STATUS_COLOR.ELEVATED;
  return STATUS_COLOR.CONSISTENT;
}

// ── inputs ──────────────────────────────────────────────────────────

export type TwinSourceKind = "live" | "replay" | "whatif";

export interface HealthInput {
  /** The backend's combined score — displayed, never recomputed. */
  score: number | null;
  factors: ContributingFactor[];
  /** Health Fusion sources with no usable output (partial assessment). */
  missing: string[];
  /** Sources that reported but were set aside (e.g. an advisory fault result). */
  excluded: string[];
  primaryConcern: string | null;
}

export interface TwinInputs {
  kind: TwinSourceKind;
  spec: EngineTwinSpec | null;
  telemetry?: Pick<TelemetryReading, SensorKey> & Partial<Pick<TelemetryReading, "vibration_x" | "vibration_y" | "vibration_z">> & { ts?: string | null };
  /** Telemetry data-quality flag (VALID / STALE / SUSPICIOUS) when the source records one. */
  quality?: string | null;
  physics?: PhysicsConsistencyParameter[];
  bearing?: BearingHealthReading | Pick<BearingHealthReading, "class_label" | "fault_location" | "severity_inches" | "confidence"> & { class_id?: number };
  fault?: Pick<FaultPrediction, "fault_class" | "confidence"> & Partial<Pick<FaultPrediction, "state" | "reliable" | "input_coverage">>;
  aux?: Pick<AuxPrediction, "risk_level" | "failure_probability_pct" | "primary_failure_cause"> & Partial<Pick<AuxPrediction, "recommended_action">>;
  rul?: Pick<RulPrediction, "rul_cycles"> & Partial<Pick<RulPrediction, "rul_lower" | "rul_upper">>;
  health?: HealthInput | null;
  /** Recent vibration magnitudes (oldest -> newest) for the RMS. */
  vibrationHistory?: number[];
  /** Replay/What-If: a label such as "Step 12 / 300". */
  sourceLabel?: string | null;
  nowMs: number;
}

export type TwinState = "no_data" | "live" | "stale" | "replay" | "whatif";

export interface SensorView {
  key: SensorKey;
  label: string;
  unit: string;
  value: number | null;
  range: [number, number] | null;
  norm: number | null;
  expected: number | null;
  residual: number | null;
  status: PhysicsConsistencyStatus | null;
  color: string;
  statusColor: string;
}

export type FusionSource = "rul" | "fault" | "bearing" | "aux";
export const FUSION_SOURCES: FusionSource[] = ["rul", "fault", "bearing", "aux"];

export interface FusionSourceView {
  source: FusionSource;
  /** Penalty points the backend applied; null when it forced the score to 0 or none applies. */
  penalty: number | null;
  active: boolean;
  forcedZero: boolean;
  missing: boolean;
  excluded: boolean;
}

export interface TwinViewModel {
  kind: TwinSourceKind;
  state: TwinState;
  /** Motion (rotation, flow, shake) is shown only for live, replay and what-if data — never for stale/no data. */
  animate: boolean;
  ageMs: number | null;
  timestamp: string | null;
  sourceLabel: string | null;
  sensors: Record<SensorKey, SensorView>;
  motion: { rpm: number | null; spin: number; vibration: number | null; shake: number };
  vibration: { x: number | null; y: number | null; z: number | null; magnitude: number | null; rms: { value: number; samples: number } | null };
  quality: string | null;
  bearing: { present: boolean; label: string | null; location: string | null; severity: number | null; confidence: number | null; color: string };
  fault: { advisory: boolean; label: string | null; confidence: number | null; state: string | null; coverage: number | null } | null;
  aux: { risk: string | null; probabilityPct: number | null; cause: string | null } | null;
  rul: { cycles: number | null } | null;
  health: {
    score: number | null;
    forcedZero: boolean;
    primaryConcern: string | null;
    sources: Record<FusionSource, FusionSourceView>;
    missing: string[];
    excluded: string[];
  } | null;
  cylinders: { count: number; layout: string; perCylinderSensors: boolean };
  turbocharged: boolean | null;
}

const PHYSICS_KEY: Partial<Record<SensorKey, PhysicsConsistencyParameter["parameter"]>> = {
  cht: "cht",
  egt: "egt",
  oil_pressure: "oil_pressure",
  oil_temp: "oil_temp",
  fuel_flow: "fuel_flow",
};

function fusionSources(h: HealthInput): Record<FusionSource, FusionSourceView> {
  const out = {} as Record<FusionSource, FusionSourceView>;
  for (const s of FUSION_SOURCES) {
    const f = h.factors.find((x) => x.source === s);
    const forced = !!f?.forced_zero;
    out[s] = {
      source: s,
      penalty: forced ? null : f && typeof f.penalty === "number" ? f.penalty : f ? null : 0,
      active: !!f,
      forcedZero: forced,
      missing: h.missing.includes(s),
      excluded: h.excluded.includes(s),
    };
  }
  return out;
}

export function buildTwinViewModel(inp: TwinInputs): TwinViewModel {
  const t = inp.telemetry;
  const ts = t?.ts ?? null;
  const ageMs = ts ? inp.nowMs - parseBackendTs(ts).getTime() : null;

  let state: TwinState;
  if (!t) state = "no_data";
  else if (inp.kind === "replay") state = "replay";
  else if (inp.kind === "whatif") state = "whatif";
  else state = ageMs !== null && ageMs > STALE_AFTER_MS ? "stale" : "live";
  const animate = state === "live" || state === "replay" || state === "whatif";

  const sensors = {} as Record<SensorKey, SensorView>;
  for (const key of SENSOR_KEYS) {
    const value = t ? (t[key] as number) : null;
    const range = inp.spec?.sensor_ranges[key] ?? null;
    const norm = range ? normalise(value, range[0], range[1]) : null;
    const phys = inp.physics?.find((p) => p.parameter === PHYSICS_KEY[key]);
    sensors[key] = {
      key,
      ...SENSOR_META[key],
      value,
      range,
      norm,
      expected: phys ? phys.expected : null,
      residual: phys ? phys.residual : null,
      status: phys ? phys.status : null,
      color: heatColor(norm),
      statusColor: phys ? STATUS_COLOR[phys.status] : NEUTRAL_COLOR,
    };
  }

  const mag = vibrationMagnitude(t);
  const b = inp.bearing;
  const health = inp.health ?? null;

  return {
    kind: inp.kind,
    state,
    animate,
    ageMs,
    timestamp: ts,
    sourceLabel: inp.sourceLabel ?? null,
    sensors,
    motion: { rpm: t ? t.rpm : null, spin: spinRate(t?.rpm), vibration: mag, shake: shakeAmplitude(mag) },
    vibration: {
      x: t?.vibration_x ?? null,
      y: t?.vibration_y ?? null,
      z: t?.vibration_z ?? null,
      magnitude: mag,
      rms: vibrationRms(inp.vibrationHistory),
    },
    quality: inp.quality ?? null,
    bearing: {
      present: !!b,
      label: b?.class_label ?? null,
      location: b?.fault_location ?? null,
      severity: b?.severity_inches ?? null,
      confidence: b?.confidence ?? null,
      color: b ? bearingSeverityColor(b.severity_inches, b.class_label) : NEUTRAL_COLOR,
    },
    fault: inp.fault
      ? {
          advisory: inp.fault.reliable === false,
          label: inp.fault.fault_class,
          confidence: inp.fault.confidence,
          state: inp.fault.state ?? null,
          coverage: inp.fault.input_coverage ?? null,
        }
      : null,
    aux: inp.aux ? { risk: inp.aux.risk_level, probabilityPct: inp.aux.failure_probability_pct, cause: inp.aux.primary_failure_cause } : null,
    rul: inp.rul ? { cycles: inp.rul.rul_cycles } : null,
    health: health
      ? {
          score: health.score,
          forcedZero: health.factors.some((f) => f.forced_zero),
          primaryConcern: health.primaryConcern,
          sources: fusionSources(health),
          missing: health.missing,
          excluded: health.excluded,
        }
      : null,
    cylinders: {
      count: inp.spec?.spec.num_cylinders ?? 0,
      layout: inp.spec?.spec.layout ?? "unknown",
      perCylinderSensors: inp.spec?.sensors.per_cylinder ?? false,
    },
    turbocharged: inp.spec?.spec.turbocharged ?? null,
  };
}
