import { describe, expect, it } from "vitest";
import { BEARING_NORMAL, BEARING_OR21, makeSpec, makeTelemetry, makeVm } from "@/test/twinFixtures";
import type { HealthInput } from "@/lib/engineTwin";
import type { PartId } from "@/lib/engineScene";
import { UNAVAILABLE, fusionRows, inspect, num, sensorRows, unavailable, vibrationRows, type Inspection, type InspectRow } from "./twinInspect";

const spec = makeSpec();
const health = (over: Partial<HealthInput> = {}): HealthInput => ({ score: 64, factors: [], missing: [], excluded: [], primaryConcern: null, ...over });
const rowsOf = (i: Inspection): InspectRow[] => i.sections.flatMap((s) => s.rows);
const find = (i: Inspection, label: string | RegExp) => rowsOf(i).find((r) => (typeof label === "string" ? r.label === label : label.test(r.label)));
const ALL_PARTS: PartId[] = [{ kind: "cylinder", index: 0 }, { kind: "block" }, { kind: "turbo" }, { kind: "bearing" }, { kind: "gearbox" }, { kind: "prop" }, { kind: "exhaust" }, { kind: "oil" }, { kind: "fuel" }];

describe("num", () => {
  it("formats finite numbers and is 'Unavailable' for null/undefined/NaN/Infinity", () => {
    expect(num(3.14159, 2)).toBe("3.14");
    expect(num(2, 1)).toBe("2");
    expect(num(0)).toBe("0");
    for (const bad of [null, undefined, NaN, Infinity]) expect(num(bad as number)).toBe(UNAVAILABLE);
  });
});

describe("sensorRows", () => {
  it("shows the reading, physics expectation, residual (signed) and status", () => {
    const vm = makeVm();
    const rows = sensorRows(vm.sensors.cht);
    expect(rows.map((r) => r.label)).toEqual(["CHT", "Physics expected", "Residual", "Physics status"]);
    expect(rows[0].value).toBe("200 °C");
    expect(rows[1].value).toBe("150 °C");
    expect(rows[2].value).toBe("+50 °C");
    expect(rows[3].value).toBe("REVIEW");
  });

  it("missing reading and missing physics are explicit Unavailable rows with a reason", () => {
    const vm = makeVm({ telemetry: undefined, physics: [] });
    const rows = sensorRows(vm.sensors.cht);
    for (const r of rows) {
      expect(r.value).toBe(UNAVAILABLE);
      expect(r.unavailable).toBe(true);
      expect(r.reason).toBeTruthy();
    }
  });

  it("RPM has no physics expectation: it is an input, not a checked channel", () => {
    const rows = sensorRows(makeVm().sensors.rpm);
    expect(rows[0].value).toBe("3000 rpm");
    expect(rows[1]).toMatchObject({ value: UNAVAILABLE, unavailable: true });
    expect(rows[1].reason).toMatch(/input/i);
    expect(rows).toHaveLength(2);
  });
});

describe("vibrationRows", () => {
  it("RMS is Unavailable with too few samples; FFT is always Unavailable", () => {
    const rows = vibrationRows(makeVm({ vibrationHistory: [0.5, 0.5, 0.5] }));
    expect(rows[0].value).toBe("0.5");
    expect(rows[1]).toMatchObject({ value: UNAVAILABLE, unavailable: true });
    expect(rows[2]).toMatchObject({ label: expect.stringMatching(/FFT/), value: UNAVAILABLE, unavailable: true });
  });
  it("RMS is shown with its sample count once there are 10+ readings", () => {
    const rows = vibrationRows(makeVm({ vibrationHistory: Array(12).fill(0.5) }));
    expect(rows[1].label).toMatch(/last 12 readings/);
    expect(rows[1].value).toBe("0.5");
  });
  it("no vibration reading => magnitude Unavailable", () => {
    const rows = vibrationRows(makeVm({ telemetry: makeTelemetry({ vibration_x: null, vibration_y: null, vibration_z: null }) }));
    expect(rows[0]).toMatchObject({ value: UNAVAILABLE, unavailable: true });
  });
});

describe("cylinder inspection never claims a per-cylinder temperature", () => {
  it.each([0, 1, 2, 3])("cylinder %i: own CHT/EGT are Unavailable; the shown values are labelled engine-level", (i) => {
    const vm = makeVm();
    const ins = inspect({ kind: "cylinder", index: i }, vm, spec);
    expect(ins.title).toBe(`Cylinder ${i + 1} · bank ${i % 2 === 0 ? "A" : "B"}`);
    expect(find(ins, "CHT — this cylinder")).toMatchObject({ value: UNAVAILABLE, unavailable: true });
    expect(find(ins, "EGT — this cylinder")).toMatchObject({ value: UNAVAILABLE, unavailable: true });
    expect(find(ins, "CHT — this cylinder")?.reason).toMatch(/one CHT \/ EGT sensor shared by all cylinders/);
    expect(find(ins, "CHT — engine-level")?.value).toBe("200 °C");
    expect(find(ins, "EGT — engine-level")?.value).toBe("500 °C");
    expect(ins.notes.join(" ")).toMatch(/one CHT and one EGT sensor for all cylinders/i);
    expect(ins.notes.join(" ")).toMatch(/not a per-cylinder measurement/i);
  });

  it("every cylinder shows the identical engine-level values", () => {
    const vm = makeVm();
    const a = inspect({ kind: "cylinder", index: 0 }, vm, spec);
    const b = inspect({ kind: "cylinder", index: 3 }, vm, spec);
    expect(find(a, "CHT — engine-level")).toEqual(find(b, "CHT — engine-level"));
  });

  it("per-cylinder health and fault localisation are Unavailable", () => {
    const ins = inspect({ kind: "cylinder", index: 1 }, makeVm({ health: health() }), spec);
    expect(find(ins, "Cylinder health / status")).toMatchObject({ value: UNAVAILABLE, unavailable: true });
    expect(find(ins, "Fault localised to this cylinder")).toMatchObject({ value: UNAVAILABLE, unavailable: true });
    // the engine-level health is the backend's
    expect(find(ins, "Engine health (Health Fusion)")?.value).toBe("64");
  });

  it("when the spec says per-cylinder sensors exist the reason changes", () => {
    const s = makeSpec({}, true);
    const ins = inspect({ kind: "cylinder", index: 0 }, makeVm({ spec: s }), s);
    expect(find(ins, "CHT — this cylinder")?.reason).toMatch(/did not report/);
    expect(ins.notes.join(" ")).toMatch(/per-cylinder sensors are available/i);
  });

  it("with no telemetry even the engine-level values are Unavailable", () => {
    const ins = inspect({ kind: "cylinder", index: 0 }, makeVm({ telemetry: undefined }), spec);
    expect(find(ins, "CHT — engine-level")?.value).toBe(UNAVAILABLE);
  });
});

describe("block inspection", () => {
  it("no health score => Unavailable (never computed); missing models are Unavailable", () => {
    const ins = inspect({ kind: "block" }, makeVm(), spec);
    expect(find(ins, "Engine health (Health Fusion)")).toMatchObject({ value: UNAVAILABLE, unavailable: true });
    expect(find(ins, "RUL")).toMatchObject({ value: UNAVAILABLE, unavailable: true });
    expect(find(ins, "Auxiliary risk")).toMatchObject({ value: UNAVAILABLE, unavailable: true });
    expect(find(ins, "Fault model")).toMatchObject({ value: UNAVAILABLE, unavailable: true });
    expect(find(ins, "Telemetry quality")).toMatchObject({ value: UNAVAILABLE, unavailable: true });
  });
  it("a null backend score is Unavailable too", () => {
    expect(find(inspect({ kind: "block" }, makeVm({ health: health({ score: null }) }), spec), "Engine health (Health Fusion)")?.unavailable).toBe(true);
  });
  it("real values are shown and the configuration comes from the spec", () => {
    const vm = makeVm({
      health: health({ score: 71.26 }),
      rul: { rul_cycles: 55 },
      aux: { risk_level: "HIGH", failure_probability_pct: 62, primary_failure_cause: null },
      fault: { fault_class: "Compass Failure", confidence: 0.9, state: "FAULT_CONFIRMED", reliable: false },
      quality: "VALID",
    });
    const ins = inspect({ kind: "block" }, vm, spec);
    expect(find(ins, "Engine health (Health Fusion)")?.value).toBe("71.3");
    expect(find(ins, "RUL")?.value).toBe("55 cycles");
    expect(find(ins, "Auxiliary risk")?.value).toBe("HIGH · 62%");
    expect(find(ins, "Fault model")?.value).toMatch(/Compass Failure \(advisory — not scored\)/);
    expect(find(ins, "Detection state")?.value).toBe("fault confirmed");
    expect(find(ins, "Telemetry quality")?.value).toBe("VALID");
    expect(find(ins, "Displacement")?.value).toBe("1234 cc");
    expect(find(ins, "Cylinders")?.value).toBe("4 (horizontally opposed)");
    expect(ins.notes[0]).toContain("test/specs.py");
  });
});

describe("turbo inspection", () => {
  it.each([
    [null, "Unknown", true],
    [true, "Yes", undefined],
    [false, "No", undefined],
  ])("turbocharged=%s => Installed '%s'", (turbocharged, value, unavail) => {
    const s = makeSpec({ turbocharged });
    const ins = inspect({ kind: "turbo" }, makeVm({ spec: s }), s);
    const r = find(ins, "Installed")!;
    expect(r.value).toBe(value);
    expect(r.unavailable).toBe(unavail);
  });
  it("boost, turbine speed and health are Unavailable (no turbo sensor or model)", () => {
    const ins = inspect({ kind: "turbo" }, makeVm(), spec);
    for (const l of ["Boost pressure", "Turbine speed", "Turbo health"]) expect(find(ins, l)).toMatchObject({ value: UNAVAILABLE, unavailable: true });
    expect(ins.notes.join(" ")).toMatch(/placeholder/i);
  });
});

describe("bearing inspection", () => {
  it("shows the model output, says the bearing ID is unavailable, and includes vibration rows", () => {
    const vm = makeVm({ bearing: BEARING_OR21, health: health({ factors: [{ source: "bearing", penalty: 20 }] }) });
    const ins = inspect({ kind: "bearing" }, vm, spec);
    expect(find(ins, "Bearing ID")).toMatchObject({ value: UNAVAILABLE, unavailable: true });
    expect(find(ins, "Model class")?.value).toBe("OR_021");
    expect(find(ins, "Severity")?.value).toBe("0.021 in");
    expect(find(ins, "Confidence")?.value).toBe("90%");
    expect(find(ins, "Health Fusion penalty")?.value).toBe("20 pts");
    expect(find(ins, "Dominant frequency (FFT)")?.unavailable).toBe(true);
  });
  it("a normal bearing shows 'none detected' severity and 0 pts when inactive in fusion", () => {
    const ins = inspect({ kind: "bearing" }, makeVm({ bearing: BEARING_NORMAL, health: health() }), spec);
    expect(find(ins, "Severity")?.value).toBe("none detected");
    expect(find(ins, "Health Fusion penalty")?.value).toBe("0 pts");
  });
  it("no health input => the fusion penalty is Unavailable", () => {
    expect(find(inspect({ kind: "bearing" }, makeVm({ bearing: BEARING_NORMAL }), spec), "Health Fusion penalty")?.value).toBe(UNAVAILABLE);
    expect(find(inspect({ kind: "bearing" }, makeVm({ bearing: BEARING_NORMAL }), spec), "Health Fusion penalty")?.unavailable).toBe(true);
  });
  it("no prediction => 'Bearing model' Unavailable", () => {
    expect(find(inspect({ kind: "bearing" }, makeVm(), spec), "Bearing model")).toMatchObject({ value: UNAVAILABLE, unavailable: true });
  });
});

describe("gearbox and propeller inspection are separate and honest", () => {
  it("different titles; both give engine RPM and the rated max from the spec; gear ratio and prop RPM Unavailable", () => {
    const g = inspect({ kind: "gearbox" }, makeVm(), spec);
    const p = inspect({ kind: "prop" }, makeVm(), spec);
    expect(g.title).toBe("Propeller gearbox");
    expect(p.title).toBe("Propeller");
    for (const ins of [g, p]) {
      expect(find(ins, "Engine RPM")?.value).toBe("3000 rpm");
      expect(find(ins, "Rated maximum")?.value).toBe("5900 rpm");
      expect(find(ins, "Gear ratio")).toMatchObject({ value: UNAVAILABLE, unavailable: true });
      expect(find(ins, "Propeller RPM")).toMatchObject({ value: UNAVAILABLE, unavailable: true });
    }
    expect(find(g, "Gearbox health")?.unavailable).toBe(true);
    expect(find(p, "Propeller health")?.unavailable).toBe(true);
  });
  it("no RPM reading => Engine RPM Unavailable", () => {
    expect(find(inspect({ kind: "prop" }, makeVm({ telemetry: undefined }), spec), "Engine RPM")?.value).toBe(UNAVAILABLE);
  });
});

describe("exhaust, oil and fuel", () => {
  it("exhaust shows EGT rows; one sensor for the engine", () => {
    const ins = inspect({ kind: "exhaust" }, makeVm(), spec);
    expect(find(ins, "EGT")?.value).toBe("500 °C");
    expect(ins.notes.join(" ")).toMatch(/no per-pipe/i);
  });
  it("oil shows temperature and pressure rows", () => {
    const ins = inspect({ kind: "oil" }, makeVm(), spec);
    expect(find(ins, "Oil temperature")?.value).toBe("100 °C");
    expect(find(ins, "Oil pressure")?.value).toBe("75 psi");
  });
  it("fuel shows flow; unavailable when missing", () => {
    expect(find(inspect({ kind: "fuel" }, makeVm(), spec), "Fuel flow")?.value).toBe("15 GPH");
    expect(find(inspect({ kind: "fuel" }, makeVm({ telemetry: undefined }), spec), "Fuel flow")?.value).toBe(UNAVAILABLE);
  });
});

describe("every inspection row is either a real value or flagged Unavailable", () => {
  it.each(ALL_PARTS.map((p) => [p.kind, p] as const))("%s: no empty values; Unavailable rows are flagged, with a reason", (_k, part) => {
    for (const vm of [makeVm({ health: health() }), makeVm({ telemetry: undefined, physics: [] })]) {
      const ins = inspect(part, vm, spec);
      expect(ins.title.length).toBeGreaterThan(0);
      for (const r of rowsOf(ins)) {
        expect(r.value).not.toBe("");
        expect(r.value).not.toMatch(/NaN|undefined|null/);
        if (r.value === UNAVAILABLE) {
          expect(r.unavailable).toBe(true);
          expect(r.reason).toBeTruthy();
        }
      }
    }
  });
});

describe("fusionRows", () => {
  it("no health => all four sources Unavailable", () => {
    const rows = fusionRows(makeVm());
    expect(rows.map((r) => r.source)).toEqual(["rul", "fault", "bearing", "aux"]);
    for (const r of rows) expect(r).toMatchObject({ text: UNAVAILABLE, state: "missing" });
  });
  it("classifies forced / excluded / missing / penalty / ok from the backend", () => {
    const vm = makeVm({
      health: health({
        factors: [{ source: "rul", penalty: 12.5 }, { source: "bearing", forced_zero: true }, { source: "fault", penalty: 3 }],
        missing: ["aux"],
        excluded: ["fault"],
      }),
    });
    const by = Object.fromEntries(fusionRows(vm).map((r) => [r.source, r]));
    expect(by.rul).toMatchObject({ state: "penalty", text: "−12.5 pts" });
    expect(by.bearing).toMatchObject({ state: "forced", text: "forced health to 0" });
    expect(by.fault.state).toBe("excluded");
    expect(by.aux.state).toBe("missing");
    const ok = fusionRows(makeVm({ health: health() }));
    for (const r of ok) expect(r).toMatchObject({ state: "ok", text: "0 pts" });
  });
});

describe("unavailable helper", () => {
  it("builds a flagged row", () => {
    expect(unavailable("X", "why")).toEqual({ label: "X", value: UNAVAILABLE, unavailable: true, reason: "why" });
  });
});
