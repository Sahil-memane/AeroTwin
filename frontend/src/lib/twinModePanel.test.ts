import { describe, expect, it } from "vitest";
import { BEARING_NORMAL, BEARING_OR21, makeTelemetry, makeVm } from "@/test/twinFixtures";
import type { HealthInput, TwinViewModel } from "@/lib/engineTwin";
import { TWIN_MODES, modeStyles, type TwinMode } from "@/lib/twinModes";
import { UNAVAILABLE, type InspectRow } from "@/lib/twinInspect";
import { modePanel, physicsTable } from "./twinModePanel";

const health = (over: Partial<HealthInput> = {}): HealthInput => ({ score: 64, factors: [], missing: [], excluded: [], primaryConcern: null, ...over });
const panel = (vm: TwinViewModel, mode: TwinMode) => modePanel(vm, mode, modeStyles(vm, mode));
const rows = (vm: TwinViewModel, mode: TwinMode): InspectRow[] => panel(vm, mode).sections.flatMap((s) => s.rows);
const find = (r: InspectRow[], label: string) => r.find((x) => x.label === label);

describe("physicsTable", () => {
  it("one row per sensor with measured / expected / signed residual / status", () => {
    const t = physicsTable(makeVm());
    expect(t.map((r) => r.key)).toEqual(["rpm", "cht", "egt", "oil_pressure", "oil_temp", "fuel_flow"]);
    const cht = t.find((r) => r.key === "cht")!;
    expect(cht).toMatchObject({ measured: "200", expected: "150", residual: "+50", status: "REVIEW" });
    const egt = t.find((r) => r.key === "egt")!;
    expect(egt.residual).toBe("-20");
  });
  it("RPM is flagged as an input, with no expected/residual/status", () => {
    const rpm = physicsTable(makeVm())[0];
    expect(rpm).toMatchObject({ measured: "3000", expected: UNAVAILABLE, residual: UNAVAILABLE, status: null });
    expect(rpm.note).toMatch(/input/);
  });
  it("no data => every cell Unavailable, never a number", () => {
    for (const r of physicsTable(makeVm({ telemetry: undefined, physics: [] }))) {
      expect(r.measured).toBe(UNAVAILABLE);
      expect(r.expected).toBe(UNAVAILABLE);
      expect(r.residual).toBe(UNAVAILABLE);
      expect(r.status).toBeNull();
    }
  });
});

describe("modePanel: structure", () => {
  it.each(TWIN_MODES.map((m) => m.id))("%s: title, blurb and the style notes come through", (mode) => {
    const vm = makeVm();
    const p = panel(vm, mode);
    expect(p.mode).toBe(mode);
    expect(p.title).toBe(TWIN_MODES.find((m) => m.id === mode)!.label);
    expect(p.blurb.length).toBeGreaterThan(0);
    expect(p.notes).toEqual(modeStyles(vm, mode).notes);
  });

  it("only the health mode has a fusion list; only physics has the table", () => {
    const vm = makeVm({ health: health() });
    for (const { id } of TWIN_MODES) {
      const p = panel(vm, id);
      expect(p.fusion !== null).toBe(id === "health");
      expect(p.physicsTable !== null).toBe(id === "physics");
    }
  });

  it("no mode leaks NaN / undefined / null into any displayed value", () => {
    for (const vm of [makeVm({ health: health(), bearing: BEARING_OR21 }), makeVm({ telemetry: undefined, physics: [] })]) {
      for (const { id } of TWIN_MODES) {
        const p = panel(vm, id);
        for (const r of [...p.sections.flatMap((s) => s.rows), ...(p.headline ? [p.headline] : [])]) {
          expect(r.value).not.toMatch(/NaN|undefined|null/);
          if (r.value === UNAVAILABLE) expect(r.unavailable).toBe(true);
        }
      }
    }
  });
});

describe("health mode: only the backend's score", () => {
  it("headline is the backend score", () => {
    expect(panel(makeVm({ health: health({ score: 64 }) }), "health").headline?.value).toBe("64");
  });
  it("no health (even with bad model outputs) => headline Unavailable, not derived", () => {
    const vm = makeVm({ fault: { fault_class: "Compass Failure", confidence: 1 }, bearing: BEARING_OR21, rul: { rul_cycles: 1 } });
    expect(panel(vm, "health").headline).toMatchObject({ value: UNAVAILABLE, unavailable: true });
    expect(panel(makeVm({ health: health({ score: null }) }), "health").headline?.value).toBe(UNAVAILABLE);
  });
  it("shows the primary concern, a partial-assessment row, RUL and aux only when present", () => {
    const vm = makeVm({
      health: health({ primaryConcern: "Bearing wear", missing: ["rul", "fault"] }),
      rul: { rul_cycles: 12 },
      aux: { risk_level: "HIGH", failure_probability_pct: 55, primary_failure_cause: null },
    });
    const r = rows(vm, "health");
    expect(find(r, "Primary concern")?.value).toBe("Bearing wear");
    expect(find(r, "Partial assessment")?.value).toBe("no usable output from rul, fault");
    expect(find(r, "RUL")?.value).toBe("12 cycles");
    expect(find(r, "Auxiliary risk")?.value).toBe("HIGH · 55%");
    const bare = rows(makeVm({ health: health() }), "health");
    expect(find(bare, "Primary concern")?.unavailable).toBe(true);
    expect(find(bare, "Partial assessment")).toBeUndefined();
    expect(find(bare, "RUL")?.unavailable).toBe(true);
    expect(find(bare, "Auxiliary risk")?.unavailable).toBe(true);
  });
  it("the fusion list has the four sources", () => {
    expect(panel(makeVm({ health: health() }), "health").fusion?.map((f) => f.source)).toEqual(["rul", "fault", "bearing", "aux"]);
  });
});

describe("thermal mode", () => {
  it("has CHT, EGT and oil temperature sections only — no per-cylinder section", () => {
    const p = panel(makeVm(), "thermal");
    expect(p.sections.map((s) => s.title)).toEqual(["CHT", "EGT", "Oil temperature"]);
    expect(p.notes.join(" ")).toMatch(/not a per-cylinder measurement/i);
    expect(p.sections.flatMap((s) => s.rows).some((r) => /cylinder/i.test(r.label))).toBe(false);
  });
});

describe("fault mode", () => {
  it("no prediction => every model row Unavailable, and the affected component is always Unavailable", () => {
    const r = rows(makeVm(), "fault");
    for (const l of ["Fault state", "Fault type", "Model confidence", "Detection status", "Input coverage", "Affected component"]) {
      expect(find(r, l)).toMatchObject({ value: UNAVAILABLE, unavailable: true });
    }
  });
  it("confirmed fault is reported as such, with confidence and coverage", () => {
    const vm = makeVm({ fault: { fault_class: "Compass Failure", confidence: 0.876, state: "FAULT_CONFIRMED", reliable: true, input_coverage: 0.47 } });
    const r = rows(vm, "fault");
    expect(find(r, "Fault state")?.value).toBe("fault confirmed");
    expect(find(r, "Fault type")?.value).toBe("Compass Failure");
    expect(find(r, "Model confidence")?.value).toBe("87.6%");
    expect(find(r, "Detection status")?.value).toBe("Fault confirmed");
    expect(find(r, "Input coverage")?.value).toContain("47%");
    expect(find(r, "Affected component")?.unavailable).toBe(true);
  });
  it("advisory, No Failure and possible-fault wording", () => {
    const f = { fault_class: "Compass Failure", confidence: 0.9 };
    expect(find(rows(makeVm({ fault: { ...f, reliable: false } }), "fault"), "Detection status")?.value).toMatch(/advisory only, not scored/);
    expect(find(rows(makeVm({ fault: { fault_class: "No Failure", confidence: 0.9 } }), "fault"), "Detection status")?.value).toBe("No fault detected");
    expect(find(rows(makeVm({ fault: { ...f, state: "ANOMALY_DETECTED" } }), "fault"), "Detection status")?.value).toMatch(/Possible fault/);
    expect(find(rows(makeVm({ fault: f }), "fault"), "Detection status")?.value).toBe("Fault reported");
  });
  it("a fault without a state machine value flags the state Unavailable", () => {
    expect(find(rows(makeVm({ fault: { fault_class: "No Failure", confidence: 0.9 } }), "fault"), "Fault state")).toMatchObject({ value: UNAVAILABLE, unavailable: true });
  });
});

describe("bearing mode", () => {
  it("bearing output with bearing ID Unavailable", () => {
    const r = rows(makeVm({ bearing: BEARING_OR21 }), "bearing");
    expect(find(r, "Bearing ID")?.unavailable).toBe(true);
    expect(find(r, "Model class")?.value).toBe("OR_021");
    expect(find(r, "Fault type / location")?.value).toBe("Outer Race");
    expect(find(r, "Severity")?.value).toBe("0.021 in");
    expect(find(r, "Confidence")?.value).toBe("90%");
  });
  it("normal => 'none detected'; none => Bearing model Unavailable", () => {
    expect(find(rows(makeVm({ bearing: BEARING_NORMAL }), "bearing"), "Severity")?.value).toBe("none detected");
    expect(find(rows(makeVm(), "bearing"), "Bearing model")).toMatchObject({ value: UNAVAILABLE, unavailable: true });
  });
  it("RMS is Unavailable with fewer than 10 samples, a number with 10+", () => {
    expect(find(rows(makeVm({ vibrationHistory: Array(9).fill(1) }), "bearing"), "Vibration RMS")).toMatchObject({ value: UNAVAILABLE, unavailable: true });
    const ok = rows(makeVm({ vibrationHistory: Array(10).fill(1) }), "bearing").find((x) => x.label.startsWith("Vibration RMS"));
    expect(ok?.value).toBe("1");
  });
});

describe("vibration mode", () => {
  it("axes, magnitude, RPM, bearing result and fault context", () => {
    const r = rows(makeVm({ bearing: BEARING_OR21 }), "vibration");
    expect(find(r, "Axes (x / y / z)")?.value).toBe("0.3 / 0.4 / 0");
    expect(find(r, "Vibration magnitude")?.value).toBe("0.5");
    expect(find(r, "RPM")?.value).toBe("3000 rpm");
    expect(find(r, "Model class")?.value).toBe("OR_021");
    expect(find(r, "Dominant frequency (FFT)")?.unavailable).toBe(true);
    expect(find(r, "Fault model")?.unavailable).toBe(true);
  });
  it("no vibration reading => axes and magnitude Unavailable", () => {
    const vm = makeVm({ telemetry: makeTelemetry({ vibration_x: null, vibration_y: null, vibration_z: null }) });
    const r = rows(vm, "vibration");
    expect(find(r, "Axes (x / y / z)")).toMatchObject({ value: UNAVAILABLE, unavailable: true });
    expect(find(r, "Vibration magnitude")).toMatchObject({ value: UNAVAILABLE, unavailable: true });
  });
});

describe("physics mode", () => {
  it("has the physics table and no sections", () => {
    const p = panel(makeVm(), "physics");
    expect(p.physicsTable).toHaveLength(6);
    expect(p.sections).toHaveLength(0);
  });
});
