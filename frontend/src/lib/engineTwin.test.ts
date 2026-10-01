import { describe, expect, it } from "vitest";
import { BEARING_NORMAL, BEARING_OR21, makeSpec, makeTelemetry, makeVm, minutesAgoNaive } from "@/test/twinFixtures";
import {
  ADVISORY_COLOR,
  FUSION_SOURCES,
  MIN_RMS_SAMPLES,
  NEUTRAL_COLOR,
  SHAKE_MAX,
  STALE_AFTER_MS,
  STATUS_COLOR,
  VISUAL_TIME_SCALE,
  bearingSeverityColor,
  healthColor,
  heatColor,
  normalise,
  shakeAmplitude,
  spinRate,
  vibrationMagnitude,
  vibrationRms,
  type HealthInput,
} from "./engineTwin";

describe("scales and colours", () => {
  it("normalise clamps to [0,1] inside the configured range and refuses bad input", () => {
    expect(normalise(200, 0, 400)).toBe(0.5);
    expect(normalise(-50, 0, 400)).toBe(0);
    expect(normalise(9999, 0, 400)).toBe(1);
    expect(normalise(null, 0, 400)).toBeNull();
    expect(normalise(undefined, 0, 400)).toBeNull();
    expect(normalise(NaN, 0, 400)).toBeNull();
    expect(normalise(5, 10, 10)).toBeNull();
  });

  it("heatColor: no data is neutral grey, hotter is redder / less blue, out of range is clamped", () => {
    expect(heatColor(null)).toBe(NEUTRAL_COLOR);
    const rgb = (h: string) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
    const cold = rgb(heatColor(0));
    const hot = rgb(heatColor(1));
    expect(hot[0]).toBeGreaterThan(cold[0]);
    expect(hot[2]).toBeLessThan(cold[2]);
    expect(heatColor(2)).toBe(heatColor(1));
    expect(heatColor(-1)).toBe(heatColor(0));
  });

  it("healthColor: unknown is neutral; <20 or forced-zero is red; <50 amber; else green", () => {
    expect(healthColor(null)).toBe(NEUTRAL_COLOR);
    expect(healthColor(undefined)).toBe(NEUTRAL_COLOR);
    expect(healthColor(10)).toBe(STATUS_COLOR.ANOMALY);
    expect(healthColor(90, true)).toBe(STATUS_COLOR.ANOMALY);
    expect(healthColor(35)).toBe(STATUS_COLOR.ELEVATED);
    expect(healthColor(80)).toBe(STATUS_COLOR.CONSISTENT);
  });

  it("bearingSeverityColor: normal green, small amber, large red", () => {
    expect(bearingSeverityColor(null, "Normal")).toBe(STATUS_COLOR.CONSISTENT);
    expect(bearingSeverityColor(0.014, "OR_014")).toBe(STATUS_COLOR.ELEVATED);
    expect(bearingSeverityColor(0.021, "OR_021")).toBe(STATUS_COLOR.ANOMALY);
  });
});

describe("motion is proportional to measured data", () => {
  it("spin rate is proportional to RPM and zero without a usable reading", () => {
    expect(spinRate(3000)).toBeCloseTo(2 * spinRate(1500), 9);
    expect(spinRate(3000)).toBeCloseTo((3000 / 60) * 2 * Math.PI * VISUAL_TIME_SCALE, 9);
    for (const bad of [0, -5, null, undefined, NaN]) expect(spinRate(bad as number)).toBe(0);
  });

  it("vibration magnitude is the vector norm; any missing axis gives null", () => {
    expect(vibrationMagnitude({ vibration_x: 0.3, vibration_y: 0.4, vibration_z: 0 })).toBeCloseTo(0.5, 9);
    expect(vibrationMagnitude({ vibration_x: 0.3, vibration_y: null, vibration_z: 0 })).toBeNull();
    expect(vibrationMagnitude(null)).toBeNull();
    expect(vibrationMagnitude(undefined)).toBeNull();
  });

  it("shake follows the magnitude and is capped", () => {
    expect(shakeAmplitude(0.5)).toBeGreaterThan(shakeAmplitude(0.25));
    expect(shakeAmplitude(1e6)).toBe(SHAKE_MAX);
    expect(shakeAmplitude(null)).toBe(0);
    expect(shakeAmplitude(0)).toBe(0);
  });
});

describe("vibration RMS is only reported with enough samples", () => {
  it("fewer than MIN_RMS_SAMPLES (10) readings => null, never a number", () => {
    expect(MIN_RMS_SAMPLES).toBe(10);
    expect(vibrationRms(undefined)).toBeNull();
    expect(vibrationRms([])).toBeNull();
    expect(vibrationRms(Array(9).fill(1))).toBeNull();
  });

  it("10 or more readings => the real RMS with its sample count", () => {
    const r = vibrationRms(Array(10).fill(2));
    expect(r).toEqual({ value: 2, samples: 10 });
    const mixed = vibrationRms([...Array(5).fill(3), ...Array(5).fill(4)]);
    expect(mixed?.value).toBeCloseTo(Math.sqrt((5 * 9 + 5 * 16) / 10), 9);
  });

  it("non-finite values don't count toward the window", () => {
    expect(vibrationRms([...Array(9).fill(1), NaN])).toBeNull();
    expect(vibrationRms([...Array(10).fill(1), NaN])?.samples).toBe(10);
  });

  it("the view model carries the RMS only when the history is long enough", () => {
    expect(makeVm({ vibrationHistory: [0.5, 0.5] }).vibration.rms).toBeNull();
    expect(makeVm({ vibrationHistory: Array(12).fill(0.5) }).vibration.rms).toEqual({ value: 0.5, samples: 12 });
    expect(makeVm().vibration.rms).toBeNull();
  });
});

describe("buildTwinViewModel: sensors", () => {
  it("sensor values, normalised positions and physics status come from the inputs", () => {
    const vm = makeVm();
    expect(vm.state).toBe("live");
    expect(vm.sensors.cht.value).toBe(200);
    expect(vm.sensors.cht.norm).toBe(0.5);
    expect(vm.sensors.cht.expected).toBe(150);
    expect(vm.sensors.cht.residual).toBe(50);
    expect(vm.sensors.cht.status).toBe("REVIEW");
    expect(vm.sensors.cht.statusColor).toBe(STATUS_COLOR.REVIEW);
    expect(vm.sensors.rpm.status).toBeNull(); // RPM is a physics input, not a checked channel
    expect(vm.motion.rpm).toBe(3000);
    expect(vm.motion.vibration).toBeCloseTo(0.5, 9);
    expect(vm.vibration).toMatchObject({ x: 0.3, y: 0.4, z: 0 });
  });

  it("uses the spec's sensor ranges, not built-in ones", () => {
    const spec = makeSpec();
    spec.sensor_ranges.cht = [100, 300];
    expect(makeVm({ spec }).sensors.cht.norm).toBe(0.5);
  });

  it("without a spec nothing is coloured from an assumed range and no cylinders are assumed", () => {
    const vm = makeVm({ spec: null });
    expect(vm.sensors.cht.norm).toBeNull();
    expect(vm.sensors.cht.color).toBe(NEUTRAL_COLOR);
    expect(vm.cylinders.count).toBe(0);
    expect(vm.cylinders.perCylinderSensors).toBe(false);
    expect(vm.turbocharged).toBeNull();
  });

  it("a channel without a physics result has null expected/residual/status", () => {
    const vm = makeVm({ physics: [] });
    expect(vm.sensors.cht.expected).toBeNull();
    expect(vm.sensors.cht.residual).toBeNull();
    expect(vm.sensors.cht.status).toBeNull();
    expect(vm.sensors.cht.statusColor).toBe(NEUTRAL_COLOR);
  });
});

describe("buildTwinViewModel: state (live / stale / no data / replay / whatif)", () => {
  it("no telemetry => no_data, null values, no animation", () => {
    const vm = makeVm({ telemetry: undefined });
    expect(vm.state).toBe("no_data");
    expect(vm.animate).toBe(false);
    expect(vm.sensors.cht.value).toBeNull();
    expect(vm.motion.rpm).toBeNull();
    expect(vm.motion.spin).toBe(0);
    expect(vm.ageMs).toBeNull();
  });

  it("the stale threshold is 5 minutes: 4 min old is live, 6 min old is stale", () => {
    expect(STALE_AFTER_MS).toBe(5 * 60_000);
    expect(makeVm({ telemetry: makeTelemetry({ ts: minutesAgoNaive(4) }) }).state).toBe("live");
    const stale = makeVm({ telemetry: makeTelemetry({ ts: minutesAgoNaive(6) }) });
    expect(stale.state).toBe("stale");
    expect(stale.animate).toBe(false);
    expect(stale.ageMs).toBeGreaterThan(5 * 60_000);
  });

  it("a fresh reading is live and animated", () => {
    const vm = makeVm();
    expect(vm.state).toBe("live");
    expect(vm.animate).toBe(true);
  });

  it("replay and what-if are never 'stale', even with an old timestamp", () => {
    const old = makeTelemetry({ ts: minutesAgoNaive(600) });
    const replay = makeVm({ kind: "replay", telemetry: old, sourceLabel: "Step 3 / 10" });
    expect(replay.state).toBe("replay");
    expect(replay.animate).toBe(true);
    expect(replay.sourceLabel).toBe("Step 3 / 10");
    const wi = makeVm({ kind: "whatif", telemetry: makeTelemetry({ ts: null as unknown as string }) });
    expect(wi.state).toBe("whatif");
    expect(wi.ageMs).toBeNull();
  });

  it("replay/what-if without a telemetry frame is no_data", () => {
    expect(makeVm({ kind: "replay", telemetry: undefined }).state).toBe("no_data");
    expect(makeVm({ kind: "whatif", telemetry: undefined }).state).toBe("no_data");
  });
});

describe("buildTwinViewModel: cylinders and turbo come from the spec, never per-cylinder temperature", () => {
  it("count and layout come from the spec", () => {
    expect(makeVm({ spec: makeSpec({ num_cylinders: 6 }) }).cylinders.count).toBe(6);
    expect(makeVm().cylinders.layout).toBe("horizontally_opposed");
  });

  it("perCylinderSensors reflects the spec flag, and the view model has no per-cylinder temperature field", () => {
    expect(makeVm().cylinders.perCylinderSensors).toBe(false);
    expect(makeVm({ spec: makeSpec({}, true) }).cylinders.perCylinderSensors).toBe(true);
    const vm = makeVm();
    expect(Object.keys(vm.cylinders).sort()).toEqual(["count", "layout", "perCylinderSensors"]);
    // exactly one CHT and one EGT sensor view for the entire engine
    expect(Object.keys(vm.sensors).filter((k) => /cht|egt/.test(k)).sort()).toEqual(["cht", "egt"]);
  });

  it("turbocharged stays null (unknown) unless the spec declares it", () => {
    expect(makeVm().turbocharged).toBeNull();
    expect(makeVm({ spec: makeSpec({ turbocharged: true }) }).turbocharged).toBe(true);
    expect(makeVm({ spec: makeSpec({ turbocharged: false }) }).turbocharged).toBe(false);
  });
});

describe("buildTwinViewModel: model outputs pass through", () => {
  const fault = { fault_class: "Compass Failure", confidence: 0.99, state: "FAULT_CONFIRMED" as const, reliable: false, input_coverage: 0.47 };

  it("flags an advisory fault (reliable === false) and passes state/coverage through", () => {
    expect(makeVm({ fault }).fault).toEqual({ advisory: true, label: "Compass Failure", confidence: 0.99, state: "FAULT_CONFIRMED", coverage: 0.47 });
    expect(makeVm({ fault: { ...fault, reliable: true } }).fault?.advisory).toBe(false);
    expect(makeVm({ fault: { ...fault, reliable: undefined } }).fault?.advisory).toBe(false); // legacy row
    expect(makeVm().fault).toBeNull();
  });

  it("bearing colour follows the model output; absent bearing is neutral", () => {
    expect(makeVm({ bearing: BEARING_NORMAL }).bearing.color).toBe(STATUS_COLOR.CONSISTENT);
    expect(makeVm({ bearing: { ...BEARING_OR21, severity_inches: 0.014, class_label: "OR_014" } }).bearing.color).toBe(STATUS_COLOR.ELEVATED);
    expect(makeVm({ bearing: BEARING_OR21 }).bearing.color).toBe(STATUS_COLOR.ANOMALY);
    const none = makeVm().bearing;
    expect(none).toMatchObject({ present: false, label: null, severity: null, confidence: null, color: NEUTRAL_COLOR });
  });

  it("aux and rul are null when the source has none", () => {
    const vm = makeVm();
    expect(vm.aux).toBeNull();
    expect(vm.rul).toBeNull();
    const withBoth = makeVm({ aux: { risk_level: "HIGH", failure_probability_pct: 71, primary_failure_cause: "oil" }, rul: { rul_cycles: 42 } });
    expect(withBoth.aux).toEqual({ risk: "HIGH", probabilityPct: 71, cause: "oil" });
    expect(withBoth.rul).toEqual({ cycles: 42 });
  });

  it("quality flag passes through, and is null when not recorded", () => {
    expect(makeVm({ quality: "VALID" }).quality).toBe("VALID");
    expect(makeVm().quality).toBeNull();
  });

  it("the advisory colour constant exists and differs from the status palette", () => {
    expect(Object.values(STATUS_COLOR)).not.toContain(ADVISORY_COLOR);
  });
});

describe("buildTwinViewModel: health is only what the backend gave", () => {
  const health = (over: Partial<HealthInput> = {}): HealthInput => ({ score: 64, factors: [], missing: [], excluded: [], primaryConcern: null, ...over });

  it("no health input => vm.health is null (nothing computed from other data)", () => {
    const vm = makeVm({ fault: { fault_class: "Compass Failure", confidence: 1 }, bearing: BEARING_OR21, rul: { rul_cycles: 1 } });
    expect(vm.health).toBeNull();
  });

  it("the score is passed through unchanged, including null", () => {
    expect(makeVm({ health: health() }).health?.score).toBe(64);
    expect(makeVm({ health: health({ score: null }) }).health?.score).toBeNull();
  });

  it("fusion sources: penalty, forced-zero, missing and excluded come from the backend lists", () => {
    const vm = makeVm({
      health: health({
        score: 0,
        factors: [{ source: "rul", penalty: 12 }, { source: "bearing", forced_zero: true }, { source: "aux" }],
        missing: ["fault"],
        excluded: ["fault"],
        primaryConcern: "Bearing",
      }),
    });
    const h = vm.health!;
    expect(Object.keys(h.sources).sort()).toEqual([...FUSION_SOURCES].sort());
    expect(h.sources.rul).toMatchObject({ penalty: 12, active: true, forcedZero: false });
    expect(h.sources.bearing).toMatchObject({ penalty: null, active: true, forcedZero: true });
    expect(h.sources.aux).toMatchObject({ penalty: null, active: true }); // active with no numeric penalty
    expect(h.sources.fault).toMatchObject({ penalty: 0, active: false, missing: true, excluded: true });
    expect(h.forcedZero).toBe(true);
    expect(h.primaryConcern).toBe("Bearing");
    expect(h.missing).toEqual(["fault"]);
    expect(h.excluded).toEqual(["fault"]);
  });

  it("no forced-zero factor => forcedZero false", () => {
    expect(makeVm({ health: health({ factors: [{ source: "rul", penalty: 3 }] }) }).health?.forcedZero).toBe(false);
  });
});
