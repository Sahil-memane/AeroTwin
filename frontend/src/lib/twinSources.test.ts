import { describe, expect, it } from "vitest";
import { makeInsufficientResponse, makeResponse } from "@/test/whatIfFixtures";
import { BEARING_OR21, PHYSICS, makeFrame, makeSpec, makeTelemetry } from "@/test/twinFixtures";
import { buildTwinViewModel } from "@/lib/engineTwin";
import { useTelemetryStore, type EngineLiveState } from "@/store/telemetryStore";
import { inputsFromLive, inputsFromReplayFrame, inputsFromWhatIf } from "./twinSources";

const NOW = Date.now();
const spec = makeSpec();

describe("inputsFromLive", () => {
  it("no live state => live kind with no telemetry and no health", () => {
    const i = inputsFromLive({ spec, live: undefined, vibrationHistory: [], nowMs: NOW });
    expect(i.kind).toBe("live");
    expect(i.telemetry).toBeUndefined();
    expect(i.health).toBeNull();
    expect(i.quality).toBeNull();
    expect(buildTwinViewModel(i).state).toBe("no_data");
  });

  it("passes backend values through untouched, including the backend health score and missing/excluded lists", () => {
    const live: EngineLiveState = {
      telemetry: { ...makeTelemetry(), quality_status: "VALID" } as EngineLiveState["telemetry"],
      physicsConsistency: PHYSICS,
      bearing: BEARING_OR21,
      healthScore: {
        combined_score: 41.5,
        contributing_factors: [{ source: "rul", penalty: 9 }],
        primary_concern: "RUL",
        missing_sources: ["aux"],
        excluded_sources: ["fault"],
        ts: "2026-09-30T00:00:00",
      },
    };
    const i = inputsFromLive({ spec, live, vibrationHistory: [1, 2], nowMs: NOW });
    expect(i.health).toEqual({ score: 41.5, factors: [{ source: "rul", penalty: 9 }], missing: ["aux"], excluded: ["fault"], primaryConcern: "RUL" });
    expect(i.quality).toBe("VALID");
    expect(i.physics).toBe(PHYSICS);
    expect(i.bearing).toBe(BEARING_OR21);
    expect(i.vibrationHistory).toEqual([1, 2]);
    expect(i.nowMs).toBe(NOW);
  });

  it("a null backend score stays null (it is not replaced by a computed one)", () => {
    const live: EngineLiveState = { telemetry: makeTelemetry(), healthScore: { combined_score: null, contributing_factors: [], ts: "t" } };
    const i = inputsFromLive({ spec, live, vibrationHistory: [], nowMs: NOW });
    expect(i.health?.score).toBeNull();
    expect(i.health?.missing).toEqual([]);
    expect(i.health?.primaryConcern).toBeNull();
  });

  it("without a healthScore in the store there is no health, whatever the other models say", () => {
    const live: EngineLiveState = { telemetry: makeTelemetry(), bearing: BEARING_OR21, fault: { ts: "t", engine_id: "e", model_version_id: "m", class_id: 1, fault_class: "Compass Failure", confidence: 1, probabilities: [] } };
    expect(buildTwinViewModel(inputsFromLive({ spec, live, vibrationHistory: [], nowMs: NOW })).health).toBeNull();
  });
});

describe("inputsFromReplayFrame", () => {
  const base = { spec, index: 2, total: 10, vibrationHistory: [0.5], nowMs: NOW };

  it("no frame => replay kind with no telemetry (no data, not stale, not live)", () => {
    const i = inputsFromReplayFrame({ ...base, frame: undefined });
    expect(i.kind).toBe("replay");
    expect(i.telemetry).toBeUndefined();
    expect(buildTwinViewModel(i).state).toBe("no_data");
  });

  it("maps a complete frame: telemetry, physics (method 'replay'), RUL, step label", () => {
    const f = makeFrame();
    const i = inputsFromReplayFrame({ ...base, frame: f });
    expect(i.kind).toBe("replay");
    expect(i.telemetry).toMatchObject({ rpm: 3000, cht: 120, oil_temp: 90, vibration_x: 0.3, ts: "2026-09-30T07:00:00" });
    expect(i.physics).toEqual([{ parameter: "cht", expected: 110, measured: 120, residual: 10, status: "ELEVATED", method: "replay" }]);
    expect(i.rul).toEqual(f.rul);
    expect(i.sourceLabel).toBe("Step 3 / 10");
    expect(i.quality).toBeNull();
    expect(i.vibrationHistory).toEqual([0.5]);
  });

  it("health is the frame's backend score, unchanged", () => {
    const i = inputsFromReplayFrame({ ...base, frame: makeFrame({ health_score: { combined_score: 12.3, contributing_factors: [{ source: "rul", penalty: 5 }] } }) });
    expect(i.health).toMatchObject({ score: 12.3, factors: [{ source: "rul", penalty: 5 }], primaryConcern: null });
  });

  it("a source with no output at that step is listed as missing; an advisory fault is excluded", () => {
    const none = inputsFromReplayFrame({ ...base, frame: makeFrame({ rul: null, fault: null }) });
    expect(none.health?.missing).toEqual(["rul", "fault"]);
    expect(none.health?.excluded).toEqual([]);
    const advisory = inputsFromReplayFrame({
      ...base,
      frame: makeFrame({ fault: { ts: "t", engine_id: "e", model_version_id: "m", class_id: 1, fault_class: "Compass Failure", confidence: 0.9, probabilities: [], reliable: false } }),
    });
    expect(advisory.health?.missing).toEqual([]);
    expect(advisory.health?.excluded).toEqual(["fault"]);
  });

  it("a frame missing any of the six sensors yields no telemetry rather than a partial/invented one", () => {
    const f = makeFrame({ telemetry: { rpm: 3000, cht: null, egt: 700, oil_pressure: 70, oil_temp: 90, fuel_flow: 5 } });
    const i = inputsFromReplayFrame({ ...base, frame: f });
    expect(i.telemetry).toBeUndefined();
    expect(buildTwinViewModel(i).sensors.cht.value).toBeNull();
  });

  it("a frame without vibration leaves the axes null", () => {
    const f = makeFrame({ telemetry: { rpm: 3000, cht: 1, egt: 2, oil_pressure: 3, oil_temp: 4, fuel_flow: 5 } });
    const vm = buildTwinViewModel(inputsFromReplayFrame({ ...base, frame: f }));
    expect(vm.vibration.magnitude).toBeNull();
    expect(vm.vibration.x).toBeNull();
  });

  it("frame without physics => no physics statuses", () => {
    const vm = buildTwinViewModel(inputsFromReplayFrame({ ...base, frame: makeFrame({ physics: null }) }));
    expect(vm.sensors.cht.status).toBeNull();
  });

  it("is pure: building replay inputs never touches the live store", () => {
    useTelemetryStore.setState({ engines: { e: { telemetry: makeTelemetry({ cht: 111 }) } } });
    const before = useTelemetryStore.getState().engines;
    inputsFromReplayFrame({ ...base, frame: makeFrame() });
    expect(useTelemetryStore.getState().engines).toBe(before);
    expect(useTelemetryStore.getState().engines.e.telemetry?.cht).toBe(111);
    useTelemetryStore.setState({ engines: {} });
  });
});

describe("inputsFromWhatIf", () => {
  it("null or incomplete result => what-if kind with nothing shown", () => {
    const i = inputsFromWhatIf({ spec, result: null, nowMs: NOW });
    expect(i.kind).toBe("whatif");
    expect(i.telemetry).toBeUndefined();
    expect(buildTwinViewModel(i).state).toBe("no_data");
    const partial = { ...makeResponse(), model_results: undefined } as never;
    expect(inputsFromWhatIf({ spec, result: partial, nowMs: NOW }).telemetry).toBeUndefined();
  });

  it("uses the SCENARIO side: six parameters, no vibration, no timestamp", () => {
    const r = makeResponse();
    const i = inputsFromWhatIf({ spec, result: r, nowMs: NOW });
    expect(i.telemetry).toMatchObject({ rpm: 5300, egt: 880, oil_temp: r.scenario!.oil_temperature, ts: null });
    const vm = buildTwinViewModel(i);
    expect(vm.state).toBe("whatif");
    expect(vm.vibration.magnitude).toBeNull();
    expect(vm.vibration.rms).toBeNull();
    expect(i.sourceLabel).toMatch(/Scenario/);
  });

  it("maps physics names (oil_temperature -> oil_temp) and statuses from the response", () => {
    const vm = buildTwinViewModel(inputsFromWhatIf({ spec, result: makeResponse(), nowMs: NOW }));
    expect(vm.sensors.egt.status).toBe("REVIEW");
    expect(vm.sensors.egt.expected).toBe(830);
    expect(vm.sensors.oil_temp.status).toBe("CONSISTENT");
    expect(vm.sensors.oil_temp.expected).toBe(97);
  });

  it("model outputs are the scenario side of each block", () => {
    const vm = buildTwinViewModel(inputsFromWhatIf({ spec, result: makeResponse(), nowMs: NOW }));
    expect(vm.fault).toMatchObject({ label: "Compass Failure", confidence: 0.78, state: "ANOMALY_DETECTED" });
    expect(vm.rul).toEqual({ cycles: 91 });
    expect(vm.bearing).toMatchObject({ present: true, label: "OR_021" });
    expect(vm.aux).toMatchObject({ risk: "MODERATE", probabilityPct: 30.8 });
  });

  it("health is the backend scenario score when every source is present", () => {
    const vm = buildTwinViewModel(inputsFromWhatIf({ spec, result: makeResponse(), nowMs: NOW }));
    expect(vm.health?.score).toBe(54);
    expect(vm.health?.missing).toEqual([]);
  });

  it("health score is null when any source is missing (partial assessment), and unavailable models are absent", () => {
    const r = makeInsufficientResponse();
    expect(r.health_fusion!.scenario.score).toBe(100); // the backend's own (misleading) partial number...
    const i = inputsFromWhatIf({ spec, result: r, nowMs: NOW });
    expect(i.health?.score).toBeNull(); // ...is not displayed
    expect(i.health?.missing).toEqual(["rul", "fault"]);
    const vm = buildTwinViewModel(i);
    expect(vm.rul).toBeNull();
    expect(vm.fault).toBeNull();
    expect(vm.bearing.present).toBe(true);
  });
});
