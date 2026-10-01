import { describe, expect, it } from "vitest";
import { BEARING_NORMAL, BEARING_OR21, makeSpec, makeTelemetry, makeVm, minutesAgoNaive } from "@/test/twinFixtures";
import { ADVISORY_COLOR, NEUTRAL_COLOR, STATUS_COLOR, healthColor, type HealthInput } from "@/lib/engineTwin";
import { STATUS_INTENSITY, TWIN_MODES, modeStyles, worstStatus, type ModeStyles, type TwinMode } from "./twinModes";

const health = (over: Partial<HealthInput> = {}): HealthInput => ({ score: 64, factors: [], missing: [], excluded: [], primaryConcern: null, ...over });
const COMPONENTS = ["block", "turbo", "bearing", "gearbox", "prop", "exhaust", "oil", "fuel"] as const;
const isNeutral = (s: { color: string; intensity: number }) => s.color === NEUTRAL_COLOR && s.intensity === 0;

describe("TWIN_MODES", () => {
  it("lists the six modes with labels", () => {
    expect(TWIN_MODES.map((m) => m.id)).toEqual(["health", "thermal", "fault", "bearing", "physics", "vibration"]);
    for (const m of TWIN_MODES) expect(m.label.length).toBeGreaterThan(0);
  });
});

describe("worstStatus", () => {
  it("picks the more severe status and tolerates nulls", () => {
    expect(worstStatus("CONSISTENT", "ANOMALY")).toBe("ANOMALY");
    expect(worstStatus("REVIEW", "ELEVATED")).toBe("REVIEW");
    expect(worstStatus(null, "ELEVATED")).toBe("ELEVATED");
    expect(worstStatus("ELEVATED", null)).toBe("ELEVATED");
    expect(worstStatus(null, null)).toBeNull();
  });
});

describe("every mode", () => {
  it.each(TWIN_MODES.map((m) => m.id))("%s: one style per cylinder (count from spec), turbo stays neutral, has notes", (mode) => {
    const s = modeStyles(makeVm({ spec: makeSpec({ num_cylinders: 6 }), health: health(), bearing: BEARING_OR21 }), mode);
    expect(s.mode).toBe(mode);
    expect(s.cylinders).toHaveLength(6);
    expect(isNeutral(s.turbo)).toBe(true); // no turbo data exists -> ghost, never coloured
    expect(isNeutral(s.gearbox)).toBe(true);
    expect(isNeutral(s.prop)).toBe(true);
    expect(s.notes.length).toBeGreaterThan(0);
  });

  it("with no spec there are no cylinder styles (no cylinder count is assumed)", () => {
    expect(modeStyles(makeVm({ spec: null }), "thermal").cylinders).toHaveLength(0);
  });

  it("no data at all leaves every component neutral in every mode", () => {
    for (const { id } of TWIN_MODES) {
      const s = modeStyles(makeVm({ telemetry: undefined, physics: undefined }), id);
      for (const k of COMPONENTS) expect(isNeutral(s[k])).toBe(true);
      for (const c of s.cylinders) expect(isNeutral(c)).toBe(true);
    }
  });
});

describe("health mode", () => {
  it("colours the block from the backend score only", () => {
    const s = modeStyles(makeVm({ health: health({ score: 80 }) }), "health");
    expect(s.block.color).toBe(healthColor(80));
    expect(s.block.pulse).toBe(false);
    const low = modeStyles(makeVm({ health: health({ score: 10 }) }), "health");
    expect(low.block.color).toBe(STATUS_COLOR.ANOMALY);
    expect(low.block.pulse).toBe(true);
  });

  it("no score => block neutral (nothing is computed from other model outputs)", () => {
    const noHealth = modeStyles(makeVm({ fault: { fault_class: "Compass Failure", confidence: 1 }, bearing: BEARING_OR21 }), "health");
    expect(isNeutral(noHealth.block)).toBe(true);
    expect(isNeutral(modeStyles(makeVm({ health: health({ score: null }) }), "health").block)).toBe(true);
  });

  it("cylinders and other parts carry no per-component health", () => {
    const s = modeStyles(makeVm({ health: health({ score: 10 }), bearing: BEARING_OR21 }), "health");
    for (const c of s.cylinders) expect(isNeutral(c)).toBe(true);
    for (const k of ["turbo", "gearbox", "prop", "exhaust", "oil", "fuel"] as const) expect(isNeutral(s[k])).toBe(true);
  });

  it("bearing gets its own model colour; a bearing inactive in Health Fusion is shown green", () => {
    const active = modeStyles(makeVm({ health: health({ factors: [{ source: "bearing", penalty: 20 }] }), bearing: BEARING_OR21 }), "health");
    expect(active.bearing.color).toBe(STATUS_COLOR.ANOMALY);
    const inactive = modeStyles(makeVm({ health: health(), bearing: BEARING_NORMAL }), "health");
    expect(inactive.bearing.color).toBe(STATUS_COLOR.CONSISTENT);
  });
});

describe("thermal mode", () => {
  it("every cylinder gets the SAME engine-level CHT style (no per-cylinder variation)", () => {
    const s = modeStyles(makeVm(), "thermal");
    expect(s.cylinders).toHaveLength(4);
    for (const c of s.cylinders) expect(c).toEqual(s.cylinders[0]);
    expect(s.cylinders[0].intensity).toBeCloseTo(0.12 + 0.88 * 0.5, 9); // CHT 200/400
    expect(s.notes.join(" ")).toMatch(/one CHT and one EGT sensor serve the whole engine/i);
    expect(s.notes.join(" ")).toMatch(/not a per-cylinder measurement/i);
  });

  it("hotter CHT => more intensity; physics REVIEW/ANOMALY pulses the outline", () => {
    const cool = modeStyles(makeVm({ telemetry: makeTelemetry({ cht: 100 }), physics: [] }), "thermal");
    const hot = modeStyles(makeVm({ telemetry: makeTelemetry({ cht: 350 }), physics: [] }), "thermal");
    expect(hot.cylinders[0].intensity).toBeGreaterThan(cool.cylinders[0].intensity);
    expect(cool.cylinders[0].pulse).toBe(false);
    expect(cool.cylinders[0].outline).toBeNull();
    const review = modeStyles(makeVm(), "thermal"); // fixture: CHT REVIEW
    expect(review.cylinders[0].pulse).toBe(true);
    expect(review.cylinders[0].outline).toBe(STATUS_COLOR.REVIEW);
  });

  it("EGT drives the exhaust, oil temperature the sump", () => {
    const s = modeStyles(makeVm({ telemetry: makeTelemetry({ egt: 900, oil_temp: 20 }) }), "thermal");
    expect(s.exhaust.intensity).toBeGreaterThan(s.oil.intensity);
  });

  it("without a range or reading the parts stay neutral; with a per-cylinder spec the note changes", () => {
    const s = modeStyles(makeVm({ spec: makeSpec({}, true) }), "thermal");
    expect(s.notes.join(" ")).toMatch(/per-cylinder sensors are reported/i);
    const none = modeStyles(makeVm({ spec: null }), "thermal");
    expect(none.exhaust).toEqual({ color: NEUTRAL_COLOR, intensity: 0, outline: null, pulse: false });
  });
});

describe("fault mode", () => {
  const f = { fault_class: "Compass Failure", confidence: 0.9, state: "FAULT_CONFIRMED" as const, reliable: true };
  it("advisory result is a muted blue, not red", () => {
    const s = modeStyles(makeVm({ fault: { ...f, reliable: false } }), "fault");
    expect(s.block.color).toBe(ADVISORY_COLOR);
    expect(s.block.pulse).toBe(false);
  });
  it("No Failure is green; a confirmed fault is red and pulses; unconfirmed does not pulse", () => {
    expect(modeStyles(makeVm({ fault: { fault_class: "No Failure", confidence: 0.9 } }), "fault").block.color).toBe(STATUS_COLOR.CONSISTENT);
    const confirmed = modeStyles(makeVm({ fault: f }), "fault").block;
    expect(confirmed.color).toBe(STATUS_COLOR.ANOMALY);
    expect(confirmed.pulse).toBe(true);
    expect(modeStyles(makeVm({ fault: { ...f, state: "ANOMALY_DETECTED" } }), "fault").block.pulse).toBe(false);
  });
  it("the fault is shown on the block only — never on a cylinder", () => {
    const s = modeStyles(makeVm({ fault: f }), "fault");
    for (const c of s.cylinders) expect(isNeutral(c)).toBe(true);
    expect(s.notes.join(" ")).toMatch(/does not localise/i);
  });
  it("no fault prediction => block neutral", () => {
    expect(isNeutral(modeStyles(makeVm(), "fault").block)).toBe(true);
  });
});

describe("bearing and vibration modes", () => {
  it("the bearing ring uses the bearing model's colour and pulses only with non-zero severity", () => {
    const s = modeStyles(makeVm({ bearing: BEARING_OR21 }), "bearing");
    expect(s.bearing.color).toBe(STATUS_COLOR.ANOMALY);
    expect(s.bearing.pulse).toBe(true);
    const normal = modeStyles(makeVm({ bearing: BEARING_NORMAL }), "bearing");
    expect(normal.bearing.pulse).toBe(false);
    expect(normal.bearing.color).toBe(STATUS_COLOR.CONSISTENT);
  });
  it("no bearing prediction => neutral in both modes", () => {
    expect(isNeutral(modeStyles(makeVm(), "bearing").bearing)).toBe(true);
    expect(isNeutral(modeStyles(makeVm(), "vibration").bearing)).toBe(true);
  });
  it("vibration mode notes that no FFT is provided", () => {
    expect(modeStyles(makeVm({ bearing: BEARING_OR21 }), "vibration").notes.join(" ")).toMatch(/FFT.*not provided/i);
  });
});

describe("physics mode", () => {
  it("colours each part from the physics status of the sensor that feeds it", () => {
    const s = modeStyles(makeVm(), "physics"); // fixture: cht REVIEW, egt CONSISTENT, oil_pressure CONSISTENT, oil_temp ELEVATED, fuel ANOMALY
    for (const c of s.cylinders) expect(c.color).toBe(STATUS_COLOR.REVIEW);
    expect(s.exhaust.color).toBe(STATUS_COLOR.CONSISTENT);
    expect(s.oil.color).toBe(STATUS_COLOR.ELEVATED); // worst of oil pressure / oil temp
    expect(s.fuel.color).toBe(STATUS_COLOR.ANOMALY);
    expect(s.fuel.pulse).toBe(true);
    expect(s.fuel.intensity).toBe(STATUS_INTENSITY.ANOMALY);
    expect(s.exhaust.intensity).toBe(STATUS_INTENSITY.CONSISTENT);
  });
  it("without physics results everything is neutral", () => {
    const s = modeStyles(makeVm({ physics: [] }), "physics");
    for (const c of s.cylinders) expect(isNeutral(c)).toBe(true);
    expect(isNeutral(s.oil)).toBe(true);
  });
});

describe("stale data is dimmed", () => {
  const modes: TwinMode[] = ["health", "thermal", "physics", "fault"];
  it.each(modes)("%s: stale glow is weaker than live and never pulses", (mode) => {
    const extra = { health: health({ score: 10 }), fault: { fault_class: "Compass Failure", confidence: 1, state: "FAULT_CONFIRMED" as const } };
    const live: ModeStyles = modeStyles(makeVm(extra), mode);
    const stale: ModeStyles = modeStyles(makeVm({ ...extra, telemetry: makeTelemetry({ ts: minutesAgoNaive(60) }) }), mode);
    const lit = [live.block, ...live.cylinders, live.exhaust, live.oil, live.fuel].filter((c) => c.intensity > 0);
    expect(lit.length).toBeGreaterThan(0);
    const all = (s: ModeStyles) => [s.block, ...s.cylinders, s.exhaust, s.oil, s.fuel];
    all(live).forEach((c, i) => {
      const d = all(stale)[i];
      expect(d.intensity).toBeCloseTo(c.intensity * 0.35, 9);
      expect(d.pulse).toBe(false);
    });
  });
});
