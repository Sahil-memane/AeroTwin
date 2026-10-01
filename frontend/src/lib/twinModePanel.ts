/**
 * Data for the side panel of each view mode. Pure: everything shown comes from the view model,
 * and anything the backend didn't provide is an explicit "Unavailable" with the reason.
 */
import type { PhysicsConsistencyStatus } from "@/types";
import { SENSOR_KEYS, type SensorKey, type TwinViewModel } from "@/lib/engineTwin";
import type { ModeStyles, TwinMode } from "@/lib/twinModes";
import { TWIN_MODES } from "@/lib/twinModes";
import {
  UNAVAILABLE,
  faultRows,
  fusionRows,
  healthRow,
  num,
  sensorRows,
  unavailable,
  vibrationRows,
  type InspectRow,
  type InspectSection,
} from "@/lib/twinInspect";

export interface PhysicsTableRow {
  key: SensorKey;
  label: string;
  unit: string;
  measured: string;
  expected: string;
  residual: string;
  status: PhysicsConsistencyStatus | null;
  statusColor: string;
  /** Why a cell is unavailable (e.g. RPM is an input, not a checked channel). */
  note?: string;
}

export interface ModePanelData {
  mode: TwinMode;
  title: string;
  blurb: string;
  headline: InspectRow | null;
  sections: InspectSection[];
  physicsTable: PhysicsTableRow[] | null;
  fusion: ReturnType<typeof fusionRows> | null;
  notes: string[];
}

export function physicsTable(vm: TwinViewModel): PhysicsTableRow[] {
  return SENSOR_KEYS.map((k) => {
    const s = vm.sensors[k];
    const isRpm = k === "rpm";
    return {
      key: k,
      label: s.label,
      unit: s.unit,
      measured: s.value === null ? UNAVAILABLE : `${num(s.value, isRpm ? 0 : 1)}`,
      expected: s.expected === null ? UNAVAILABLE : num(s.expected),
      residual: s.residual === null ? UNAVAILABLE : `${s.residual > 0 ? "+" : ""}${num(s.residual)}`,
      status: s.status,
      statusColor: s.statusColor,
      ...(isRpm ? { note: "input to the physics model, not a checked channel" } : {}),
    };
  });
}

function detection(vm: TwinViewModel): string {
  const f = vm.fault;
  if (!f) return UNAVAILABLE;
  if (f.advisory) return "Suspected — advisory only, not scored";
  if (f.label === "No Failure") return "No fault detected";
  return f.state === "FAULT_CONFIRMED" ? "Fault confirmed" : f.state ? `Possible fault (${f.state.replace(/_/g, " ").toLowerCase()})` : "Fault reported";
}

export function modePanel(vm: TwinViewModel, mode: TwinMode, styles: ModeStyles): ModePanelData {
  const meta = TWIN_MODES.find((m) => m.id === mode)!;
  const base: ModePanelData = {
    mode,
    title: meta.label,
    blurb: meta.blurb,
    headline: null,
    sections: [],
    physicsTable: null,
    fusion: null,
    notes: styles.notes,
  };

  switch (mode) {
    case "health":
      return {
        ...base,
        headline: healthRow(vm),
        fusion: fusionRows(vm),
        sections: [
          {
            title: "Health Fusion",
            rows: [
              vm.health?.primaryConcern ? { label: "Primary concern", value: vm.health.primaryConcern } : unavailable("Primary concern", "none reported for this source"),
              ...(vm.health && vm.health.missing.length > 0
                ? [{ label: "Partial assessment", value: `no usable output from ${vm.health.missing.join(", ")}` } as InspectRow]
                : []),
              vm.rul ? { label: "RUL", value: `${num(vm.rul.cycles)} cycles` } : unavailable("RUL", "no RUL prediction"),
              vm.aux ? { label: "Auxiliary risk", value: `${vm.aux.risk} · ${num(vm.aux.probabilityPct)}%` } : unavailable("Auxiliary risk", "no auxiliary prediction"),
            ],
          },
        ],
      };
    case "thermal":
      return {
        ...base,
        sections: (["cht", "egt", "oil_temp"] as SensorKey[]).map((k) => ({ title: vm.sensors[k].label, rows: sensorRows(vm.sensors[k]) })),
      };
    case "fault": {
      const f = vm.fault;
      return {
        ...base,
        sections: [
          {
            title: "Fault model",
            rows: [
              f ? { label: "Fault state", value: f.state ? f.state.replace(/_/g, " ").toLowerCase() : UNAVAILABLE, ...(f.state ? {} : { unavailable: true, reason: "state machine not reported for this source" }) } : unavailable("Fault state", "no fault prediction for this source"),
              f ? { label: "Fault type", value: f.label ?? UNAVAILABLE } : unavailable("Fault type", "no fault prediction for this source"),
              f && f.confidence !== null ? { label: "Model confidence", value: `${num(f.confidence * 100, 1)}%` } : unavailable("Model confidence", "no fault prediction for this source"),
              { label: "Detection status", value: detection(vm), ...(f ? {} : { unavailable: true, reason: "no fault prediction for this source" }) },
              f && f.coverage !== null ? { label: "Input coverage", value: `${num(f.coverage * 100, 0)}% of model channels measured` } : unavailable("Input coverage", "not reported for this source"),
              unavailable("Affected component", "the fault model classifies the whole system; it does not localise a fault to a component"),
            ],
          },
        ],
      };
    }
    case "bearing": {
      const b = vm.bearing;
      return {
        ...base,
        sections: [
          {
            title: "Bearing model",
            rows: b.present
              ? [
                  unavailable("Bearing ID", "the model reports a fault class, not which physical bearing"),
                  { label: "Model class", value: b.label ?? UNAVAILABLE, color: b.color },
                  { label: "Fault type / location", value: b.location ?? UNAVAILABLE },
                  b.severity === null ? { label: "Severity", value: "none detected" } : { label: "Severity", value: `${num(b.severity, 3)} in`, color: b.color },
                  b.confidence === null ? unavailable("Confidence", "not reported") : { label: "Confidence", value: `${num(b.confidence * 100, 0)}%` },
                ]
              : [unavailable("Bearing model", "no bearing prediction for this source")],
          },
          { title: "Vibration & speed", rows: [...vibrationRows(vm), ...sensorRows(vm.sensors.rpm).slice(0, 1)] },
        ],
      };
    }
    case "physics":
      return { ...base, physicsTable: physicsTable(vm) };
    case "vibration":
      return {
        ...base,
        sections: [
          {
            title: "Vibration",
            rows: [
              ...vibrationRows(vm),
              vm.vibration.x === null
                ? unavailable("Axes (x / y / z)", "no vibration reading for this source")
                : { label: "Axes (x / y / z)", value: `${num(vm.vibration.x, 3)} / ${num(vm.vibration.y, 3)} / ${num(vm.vibration.z, 3)}` },
              ...sensorRows(vm.sensors.rpm).slice(0, 1),
            ],
          },
          {
            title: "Bearing result",
            rows: vm.bearing.present
              ? [{ label: "Model class", value: vm.bearing.label ?? UNAVAILABLE, color: vm.bearing.color }, vm.bearing.severity === null ? { label: "Severity", value: "none detected" } : { label: "Severity", value: `${num(vm.bearing.severity, 3)} in` }]
              : [unavailable("Bearing model", "no bearing prediction for this source")],
          },
          { title: "Fault model (context)", rows: faultRows(vm) },
        ],
      };
  }
}
