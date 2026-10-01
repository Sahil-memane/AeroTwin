/**
 * Component inspection: what the twin can honestly say about each part when it is clicked.
 * Every row is either a real value from the view model / engine spec, or an explicit
 * "Unavailable" with the reason — never an invented number.
 */
import type { EngineTwinSpec } from "@/types";
import type { PartId } from "@/lib/engineScene";
import { FUSION_SOURCES, type FusionSource, type SensorView, type TwinViewModel } from "@/lib/engineTwin";

export interface InspectRow {
  label: string;
  value: string;
  unavailable?: boolean;
  reason?: string;
  color?: string;
}
export interface InspectSection {
  title: string;
  rows: InspectRow[];
}
export interface Inspection {
  title: string;
  sections: InspectSection[];
  notes: string[];
}

export const UNAVAILABLE = "Unavailable";

export const num = (v: number | null | undefined, digits = 1): string =>
  v === null || v === undefined || !Number.isFinite(v) ? UNAVAILABLE : Number(v.toFixed(digits)).toString();

const row = (label: string, value: string, color?: string): InspectRow => ({ label, value, ...(color ? { color } : {}) });
export const unavailable = (label: string, reason: string): InspectRow => ({ label, value: UNAVAILABLE, unavailable: true, reason });

export const SOURCE_LABEL: Record<FusionSource, string> = { rul: "RUL", fault: "Fault", bearing: "Bearing", aux: "Auxiliary" };

export function sensorRows(s: SensorView, opts: { prefix?: string } = {}): InspectRow[] {
  const p = opts.prefix ?? "";
  const rows: InspectRow[] = [
    s.value === null ? unavailable(`${p}${s.label}`, "no reading") : row(`${p}${s.label}`, `${num(s.value, s.key === "rpm" ? 0 : 1)} ${s.unit}`),
  ];
  if (s.key === "rpm") {
    rows.push(unavailable(`${p}Physics expected`, "RPM is an input to the physics model, not a checked channel"));
    return rows;
  }
  rows.push(s.expected === null ? unavailable(`${p}Physics expected`, "no physics result for this source") : row(`${p}Physics expected`, `${num(s.expected)} ${s.unit}`));
  rows.push(
    s.residual === null
      ? unavailable(`${p}Residual`, "no physics result for this source")
      : row(`${p}Residual`, `${s.residual > 0 ? "+" : ""}${num(s.residual)} ${s.unit}`),
  );
  rows.push(s.status === null ? unavailable(`${p}Physics status`, "no physics result for this source") : row(`${p}Physics status`, s.status, s.statusColor));
  return rows;
}

export function healthRow(vm: TwinViewModel): InspectRow {
  if (!vm.health || vm.health.score === null) return unavailable("Engine health (Health Fusion)", "no health score for this source");
  return row("Engine health (Health Fusion)", num(vm.health.score), undefined);
}

export function faultRows(vm: TwinViewModel): InspectRow[] {
  if (!vm.fault) return [unavailable("Fault model", "no fault prediction for this source")];
  const f = vm.fault;
  const rows = [row("Fault model", `${f.label}${f.advisory ? " (advisory — not scored)" : ""}`)];
  rows.push(f.confidence === null ? unavailable("Model confidence", "not reported") : row("Model confidence", `${num(f.confidence * 100, 1)}%`));
  if (f.state) rows.push(row("Detection state", f.state.replace(/_/g, " ").toLowerCase()));
  return rows;
}

export const vibrationRows = (vm: TwinViewModel): InspectRow[] => [
  vm.vibration.magnitude === null ? unavailable("Vibration magnitude", "no vibration reading for this source") : row("Vibration magnitude", num(vm.vibration.magnitude, 3)),
  vm.vibration.rms
    ? row(`Vibration RMS (last ${vm.vibration.rms.samples} readings)`, num(vm.vibration.rms.value, 3))
    : unavailable("Vibration RMS", "needs a window of recent readings (not available for this source yet)"),
  unavailable("Dominant frequency (FFT)", "the backend does not compute or provide a vibration spectrum"),
];

export function inspect(part: PartId, vm: TwinViewModel, spec: EngineTwinSpec): Inspection {
  switch (part.kind) {
    case "cylinder": {
      const per = vm.cylinders.perCylinderSensors;
      const why = per ? "this cylinder's sensor did not report" : "the engine has one CHT / EGT sensor shared by all cylinders";
      return {
        title: `Cylinder ${part.index + 1} · bank ${part.index % 2 === 0 ? "A" : "B"}`,
        sections: [
          {
            title: "Temperatures",
            rows: [
              unavailable("CHT — this cylinder", why),
              ...sensorRows(vm.sensors.cht, { prefix: "" }).slice(0, 1).map((r) => ({ ...r, label: "CHT — engine-level" })),
              unavailable("EGT — this cylinder", why),
              ...sensorRows(vm.sensors.egt).slice(0, 1).map((r) => ({ ...r, label: "EGT — engine-level" })),
            ],
          },
          { title: "Physics ↔ AI (engine-level CHT)", rows: sensorRows(vm.sensors.cht).slice(1) },
          {
            title: "Condition",
            rows: [unavailable("Cylinder health / status", "AeroTwin computes engine-level health, not per-component health"), healthRow(vm)],
          },
          {
            title: "Fault evidence",
            rows: [unavailable("Fault localised to this cylinder", "the fault model does not localise a fault to a component"), ...faultRows(vm)],
          },
        ],
        notes: [
          per
            ? "Per-cylinder sensors are available for this engine."
            : "This engine has one CHT and one EGT sensor for all cylinders. The temperatures shown are engine-level values, identical for every cylinder — not a per-cylinder measurement.",
        ],
      };
    }
    case "block":
      return {
        title: "Engine block",
        sections: [
          {
            title: "Condition",
            rows: [
              healthRow(vm),
              vm.rul ? row("RUL", `${num(vm.rul.cycles)} cycles`) : unavailable("RUL", "no RUL prediction (window not full or model unavailable)"),
              vm.aux ? row("Auxiliary risk", `${vm.aux.risk} · ${num(vm.aux.probabilityPct)}%`) : unavailable("Auxiliary risk", "no auxiliary prediction for this source"),
              ...faultRows(vm),
              vm.quality ? row("Telemetry quality", vm.quality) : unavailable("Telemetry quality", "not recorded for this source"),
            ],
          },
          {
            title: "Configuration",
            rows: [
              row("Cylinders", `${spec.spec.num_cylinders} (${spec.spec.layout.replace(/_/g, " ")})`),
              row("Displacement", `${num(spec.spec.displacement_cc, 0)} cc`),
              row("Compression ratio", `${num(spec.spec.compression_ratio)}:1`),
              row("Rated power", `${num(spec.spec.rated_power_kw)} kW`),
            ],
          },
        ],
        notes: [`Engine configuration from ${spec.spec.source}.`],
      };
    case "turbo":
      return {
        title: "Turbo",
        sections: [
          {
            title: "Turbocharger",
            rows: [
              {
                label: "Installed",
                value: spec.spec.turbocharged === null ? "Unknown" : spec.spec.turbocharged ? "Yes" : "No",
                ...(spec.spec.turbocharged === null ? { unavailable: true, reason: "the engine spec does not declare whether a turbo is fitted" } : {}),
              },
              unavailable("Boost pressure", "AeroTwin has no boost sensor"),
              unavailable("Turbine speed", "AeroTwin has no turbo sensor"),
              unavailable("Turbo health", "AeroTwin has no turbo model"),
            ],
          },
        ],
        notes: ["Drawn as a translucent placeholder: the engine spec doesn't say whether a turbo is fitted, and no turbo data exists in AeroTwin."],
      };
    case "bearing": {
      const b = vm.bearing;
      const src = vm.health?.sources.bearing;
      return {
        title: "Main bearing (bearing model)",
        sections: [
          {
            title: "Bearing model output",
            rows: b.present
              ? [
                  unavailable("Bearing ID", "the model reports a fault class, not which physical bearing"),
                  row("Model class", b.label ?? UNAVAILABLE, b.color),
                  row("Fault location", b.location ?? UNAVAILABLE),
                  b.severity === null ? row("Severity", "none detected") : row("Severity", `${num(b.severity, 3)} in`, b.color),
                  b.confidence === null ? unavailable("Confidence", "not reported") : row("Confidence", `${num(b.confidence * 100, 0)}%`),
                  src && src.active
                    ? row("Health Fusion penalty", `${num(src.penalty)} pts`)
                    : src
                      ? row("Health Fusion penalty", "0 pts")
                      : unavailable("Health Fusion penalty", "no Health Fusion result for this source"),
                ]
              : [unavailable("Bearing model", "no bearing prediction for this source")],
          },
          { title: "Vibration & speed", rows: [...vibrationRows(vm), ...sensorRows(vm.sensors.rpm).slice(0, 1)] },
        ],
        notes: ["The bearing model classifies a vibration signal; the ring on the model is a schematic marker for its output."],
      };
    }
    case "gearbox":
    case "prop": {
      const what = part.kind === "gearbox" ? "Gearbox" : "Propeller";
      return {
        title: what === "Gearbox" ? "Propeller gearbox" : "Propeller",
        sections: [
          {
            title: "Speed",
            rows: [
              ...sensorRows(vm.sensors.rpm).slice(0, 1).map((r) => ({ ...r, label: "Engine RPM" })),
              row("Rated maximum", `${num(spec.spec.rpm_max, 0)} rpm`),
              unavailable("Gear ratio", "not part of the engine spec"),
              unavailable("Propeller RPM", "would need the gear ratio; AeroTwin measures engine RPM only"),
            ],
          },
          { title: "Condition", rows: [unavailable(`${what} health`, "AeroTwin has no gearbox or propeller model")] },
        ],
        notes: ["The propeller turns in proportion to the measured engine RPM, at a small fraction of real speed so it is visible."],
      };
    }
    case "exhaust":
      return { title: "Exhaust system", sections: [{ title: "EGT", rows: sensorRows(vm.sensors.egt) }], notes: ["One EGT sensor for the whole engine; there is no per-pipe measurement."] };
    case "oil":
      return {
        title: "Oil system",
        sections: [
          { title: "Oil temperature", rows: sensorRows(vm.sensors.oil_temp) },
          { title: "Oil pressure", rows: sensorRows(vm.sensors.oil_pressure) },
        ],
        notes: ["Sump colour follows oil temperature; the bar's height follows oil pressure within its configured sensor range."],
      };
    case "fuel":
      return { title: "Fuel system", sections: [{ title: "Fuel flow", rows: sensorRows(vm.sensors.fuel_flow) }], notes: ["The flowing dashes move faster with higher measured fuel flow."] };
  }
}

/** The four Health Fusion sources as a flat list for display (penalty / forced / excluded / missing). */
export function fusionRows(vm: TwinViewModel): { source: FusionSource; label: string; text: string; state: "ok" | "forced" | "excluded" | "missing" | "penalty" }[] {
  return FUSION_SOURCES.map((s) => {
    const f = vm.health?.sources[s];
    if (!vm.health || !f) return { source: s, label: SOURCE_LABEL[s], text: UNAVAILABLE, state: "missing" as const };
    if (f.forcedZero) return { source: s, label: SOURCE_LABEL[s], text: "forced health to 0", state: "forced" as const };
    if (f.excluded) return { source: s, label: SOURCE_LABEL[s], text: "reported — set aside (advisory)", state: "excluded" as const };
    if (f.missing) return { source: s, label: SOURCE_LABEL[s], text: "no usable output yet", state: "missing" as const };
    if (f.active) return { source: s, label: SOURCE_LABEL[s], text: `−${num(f.penalty)} pts`, state: "penalty" as const };
    return { source: s, label: SOURCE_LABEL[s], text: "0 pts", state: "ok" as const };
  });
}
