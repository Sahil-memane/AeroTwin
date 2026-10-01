/**
 * How each 3D component is styled in each view mode. Pure and data-driven: a component is only
 * coloured by a value AeroTwin actually has for it; anything else stays neutral, and the `notes`
 * say why. Nothing here invents component-level health, localisation or per-cylinder values.
 */
import type { PhysicsConsistencyStatus } from "@/types";
import {
  ADVISORY_COLOR,
  NEUTRAL_COLOR,
  STATUS_COLOR,
  healthColor,
  type SensorView,
  type TwinViewModel,
} from "@/lib/engineTwin";

export type TwinMode = "health" | "thermal" | "fault" | "bearing" | "physics" | "vibration";

export const TWIN_MODES: { id: TwinMode; label: string; blurb: string }[] = [
  { id: "health", label: "Health", blurb: "Health Fusion result, as computed by the backend" },
  { id: "thermal", label: "Thermal", blurb: "Measured CHT / EGT / oil temperature" },
  { id: "fault", label: "Fault", blurb: "Fault model output" },
  { id: "bearing", label: "Bearing", blurb: "Bearing model output and vibration" },
  { id: "physics", label: "Physics ↔ AI", blurb: "Measured vs physics-model expectation" },
  { id: "vibration", label: "Vibration", blurb: "Measured vibration and RPM" },
];

/** Components that can be coloured. (Cylinders are styled as an array.) */
export type ComponentId = "block" | "turbo" | "bearing" | "gearbox" | "prop" | "exhaust" | "oil" | "fuel";

export interface ComponentStyle {
  /** Base tint, "#rrggbb". */
  color: string;
  /** Glow 0..1 (already dimmed for stale data). */
  intensity: number;
  /** Outline colour, or null for the default outline. */
  outline: string | null;
  pulse: boolean;
}

export interface ModeStyles {
  mode: TwinMode;
  block: ComponentStyle;
  cylinders: ComponentStyle[];
  turbo: ComponentStyle;
  bearing: ComponentStyle;
  gearbox: ComponentStyle;
  prop: ComponentStyle;
  exhaust: ComponentStyle;
  oil: ComponentStyle;
  fuel: ComponentStyle;
  /** Short statements of what this mode can and cannot show (displayed to the operator). */
  notes: string[];
}

export const STATUS_INTENSITY: Record<PhysicsConsistencyStatus, number> = {
  CONSISTENT: 0.25,
  ELEVATED: 0.5,
  REVIEW: 0.7,
  ANOMALY: 1,
};
const STATUS_ORDER: PhysicsConsistencyStatus[] = ["CONSISTENT", "ELEVATED", "REVIEW", "ANOMALY"];

export function worstStatus(a: PhysicsConsistencyStatus | null, b: PhysicsConsistencyStatus | null): PhysicsConsistencyStatus | null {
  if (!a) return b;
  if (!b) return a;
  return STATUS_ORDER.indexOf(a) >= STATUS_ORDER.indexOf(b) ? a : b;
}

const neutral = (): ComponentStyle => ({ color: NEUTRAL_COLOR, intensity: 0, outline: null, pulse: false });

function fromStatus(status: PhysicsConsistencyStatus | null): ComponentStyle {
  if (!status) return neutral();
  return { color: STATUS_COLOR[status], intensity: STATUS_INTENSITY[status], outline: STATUS_COLOR[status], pulse: status === "ANOMALY" };
}

/** Temperature tint from the configured range; the outline pulses only when physics calls it REVIEW/ANOMALY. */
function thermal(s: SensorView): ComponentStyle {
  if (s.norm === null) return neutral();
  const abnormal = s.status === "REVIEW" || s.status === "ANOMALY";
  return {
    color: s.color,
    intensity: 0.12 + 0.88 * s.norm,
    outline: s.status ? s.statusColor : null,
    pulse: abnormal,
  };
}

function bearingStyle(vm: TwinViewModel): ComponentStyle {
  if (!vm.bearing.present) return neutral();
  const sev = vm.bearing.severity ?? 0;
  return { color: vm.bearing.color, intensity: 0.9, outline: vm.bearing.color, pulse: sev > 0 };
}

function dim(style: ComponentStyle, factor: number): ComponentStyle {
  return factor === 1 ? style : { ...style, intensity: style.intensity * factor, pulse: false };
}

export function modeStyles(vm: TwinViewModel, mode: TwinMode): ModeStyles {
  const n = vm.cylinders.count;
  const out: ModeStyles = {
    mode,
    block: neutral(),
    cylinders: Array.from({ length: n }, neutral),
    turbo: neutral(),
    bearing: neutral(),
    gearbox: neutral(),
    prop: neutral(),
    exhaust: neutral(),
    oil: neutral(),
    fuel: neutral(),
    notes: [],
  };

  switch (mode) {
    case "health": {
      const h = vm.health;
      if (h && h.score !== null) {
        out.block = { color: healthColor(h.score, h.forcedZero), intensity: 0.55, outline: healthColor(h.score, h.forcedZero), pulse: h.score < 20 };
      }
      // Health Fusion's bearing contribution is the only component-attributed health AeroTwin has.
      if (vm.bearing.present) {
        const src = h?.sources.bearing;
        out.bearing = src && !src.active ? { color: STATUS_COLOR.CONSISTENT, intensity: 0.35, outline: STATUS_COLOR.CONSISTENT, pulse: false } : bearingStyle(vm);
      }
      out.notes.push(
        "The block shows the engine-level Health Fusion score. Health is not computed per component, so every other part stays neutral — except the bearing, which has its own model and Health Fusion contribution.",
      );
      break;
    }
    case "thermal": {
      out.cylinders = out.cylinders.map(() => thermal(vm.sensors.cht));
      out.exhaust = thermal(vm.sensors.egt);
      out.oil = thermal(vm.sensors.oil_temp);
      out.notes.push(
        vm.cylinders.perCylinderSensors
          ? "Per-cylinder sensors are reported by the backend."
          : "One CHT and one EGT sensor serve the whole engine, so all cylinders show the same engine-level CHT — this is not a per-cylinder measurement.",
      );
      out.notes.push("Tint = position in the configured sensor range; a pulsing outline means the physics model rates that channel REVIEW or ANOMALY.");
      break;
    }
    case "fault": {
      const f = vm.fault;
      if (f) {
        if (f.advisory) out.block = { color: ADVISORY_COLOR, intensity: 0.15, outline: ADVISORY_COLOR, pulse: false };
        else if (f.label === "No Failure") out.block = { color: STATUS_COLOR.CONSISTENT, intensity: 0.2, outline: STATUS_COLOR.CONSISTENT, pulse: false };
        else out.block = { color: STATUS_COLOR.ANOMALY, intensity: 0.45, outline: STATUS_COLOR.ANOMALY, pulse: f.state === "FAULT_CONFIRMED" };
      }
      out.notes.push("The fault model classifies the system from a window of readings; it does not localise a fault to a component, so the result is shown at engine level on the block.");
      break;
    }
    case "bearing": {
      out.bearing = bearingStyle(vm);
      out.notes.push("The bearing model classifies a vibration signal. It does not say which physical bearing it is, so the highlighted ring is a schematic marker for the model's output.");
      break;
    }
    case "physics": {
      out.cylinders = out.cylinders.map(() => fromStatus(vm.sensors.cht.status));
      out.exhaust = fromStatus(vm.sensors.egt.status);
      out.oil = fromStatus(worstStatus(vm.sensors.oil_pressure.status, vm.sensors.oil_temp.status));
      out.fuel = fromStatus(vm.sensors.fuel_flow.status);
      out.notes.push("Colour = physics-consistency status of the sensor that feeds each part (CHT → cylinders, EGT → exhaust, oil pressure/temperature → sump, fuel flow → fuel rail). RPM is an input to the physics model, not a checked channel.");
      break;
    }
    case "vibration": {
      out.bearing = bearingStyle(vm);
      out.notes.push("The whole model shakes in proportion to the measured vibration magnitude and the crank turns with RPM. Vibration frequency (FFT) is not provided by the backend.");
      break;
    }
  }

  const factor = vm.state === "stale" ? 0.35 : 1;
  if (factor !== 1) {
    out.block = dim(out.block, factor);
    out.cylinders = out.cylinders.map((c) => dim(c, factor));
    for (const k of ["turbo", "bearing", "gearbox", "prop", "exhaust", "oil", "fuel"] as const) out[k] = dim(out[k], factor);
  }
  return out;
}
