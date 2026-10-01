// @vitest-environment node
import * as THREE from "three";
import { describe, expect, it, vi } from "vitest";
import { BEARING_OR21, makeSpec, makeTelemetry, makeVm, minutesAgoNaive } from "@/test/twinFixtures";
import { STATUS_COLOR, healthColor, spinRate, type HealthInput, type TwinInputs } from "@/lib/engineTwin";
import { modeStyles, type TwinMode } from "@/lib/twinModes";
import { buildEngineScene, samePart, type EngineScene, type PartId } from "./engineScene";

const hex = (c: string) => new THREE.Color(c).getHexString();
const health = (score: number): HealthInput => ({ score, factors: [], missing: [], excluded: [], primaryConcern: null });

/** Build a view model + its mode styles and push them through scene.update(). */
function apply(s: EngineScene, over: Partial<TwinInputs> = {}, mode: TwinMode = "thermal", dt = 0.016, elapsed = 0) {
  const vm = makeVm(over);
  const styles = modeStyles(vm, mode);
  s.update(vm, styles, dt, elapsed);
  return { vm, styles };
}

describe("the model is built from the engine spec", () => {
  it.each([2, 4, 6])("%i cylinders in the spec => that many cylinder groups, heads and materials", (n) => {
    const s = buildEngineScene(makeSpec({ num_cylinders: n }));
    expect(s.parts.cylinders).toHaveLength(n);
    expect(s.parts.heads).toHaveLength(n);
    expect(s.parts.headMaterials).toHaveLength(n);
    expect(s.parts.headEdges).toHaveLength(n);
    s.dispose();
  });

  it("a longer engine is physically longer", () => {
    const two = buildEngineScene(makeSpec({ num_cylinders: 2 }));
    const six = buildEngineScene(makeSpec({ num_cylinders: 6 }));
    expect(six.parts.length).toBeGreaterThan(two.parts.length);
    two.dispose();
    six.dispose();
  });

  it("cylinders alternate banks and every one is pickable with its own index", () => {
    const s = buildEngineScene(makeSpec({ num_cylinders: 4 }));
    expect(s.parts.heads.map((h) => Math.sign(h.position.x))).toEqual([-1, 1, -1, 1]);
    const picked = new Set<number>();
    for (const o of s.pickables) {
      const part = o.userData.part as PartId;
      if (part.kind === "cylinder") picked.add(part.index);
    }
    expect([...picked].sort()).toEqual([0, 1, 2, 3]);
    s.dispose();
  });

  it("every part kind is pickable", () => {
    const s = buildEngineScene(makeSpec());
    const kinds = new Set(s.pickables.map((o) => (o.userData.part as PartId).kind));
    for (const k of ["cylinder", "block", "turbo", "bearing", "gearbox", "prop", "exhaust", "oil", "fuel"]) expect(kinds.has(k as PartId["kind"])).toBe(true);
    s.dispose();
  });

  it("samePart compares kinds and cylinder indexes", () => {
    expect(samePart({ kind: "cylinder", index: 1 }, { kind: "cylinder", index: 1 })).toBe(true);
    expect(samePart({ kind: "cylinder", index: 1 }, { kind: "cylinder", index: 2 })).toBe(false);
    expect(samePart({ kind: "oil" }, { kind: "oil" })).toBe(true);
    expect(samePart({ kind: "oil" }, { kind: "fuel" })).toBe(false);
    expect(samePart({ kind: "oil" }, null)).toBe(false);
    expect(samePart(null, null)).toBe(true);
  });
});

describe("turbo is a ghost placeholder", () => {
  it.each([null, true, false])("translucent regardless of spec.turbocharged = %s", (turbocharged) => {
    const s = buildEngineScene(makeSpec({ turbocharged }));
    expect(s.parts.turboMaterial.transparent).toBe(true);
    expect(s.parts.turboMaterial.opacity).toBeLessThan(0.5);
    expect(s.parts.turboMaterial.depthWrite).toBe(false);
    s.dispose();
  });

  it("stays translucent and unlit after update in every mode (no data to colour it)", () => {
    const s = buildEngineScene(makeSpec());
    for (const mode of ["health", "thermal", "fault", "bearing", "physics", "vibration"] as TwinMode[]) {
      apply(s, { health: health(10), bearing: BEARING_OR21 }, mode);
      expect(s.parts.turboMaterial.opacity).toBeLessThan(0.5);
      expect(s.parts.turboMaterial.emissiveIntensity).toBe(0);
    }
    s.dispose();
  });

  it("is its own pickable part", () => {
    const s = buildEngineScene(makeSpec());
    const turboMeshes = s.pickables.filter((o) => (o.userData.part as PartId).kind === "turbo");
    expect(turboMeshes.length).toBeGreaterThan(0);
    s.dispose();
  });
});

describe("gearbox and propeller are separate parts", () => {
  it("distinct objects, materials and pick tags", () => {
    const s = buildEngineScene(makeSpec());
    expect(s.parts.gearbox).not.toBe(s.parts.prop);
    expect(s.parts.gearboxMaterial).not.toBe(s.parts.propMaterial);
    expect((s.parts.gearbox.userData.part as PartId).kind).toBe("gearbox");
    const propMeshes = s.pickables.filter((o) => (o.userData.part as PartId).kind === "prop");
    expect(propMeshes.length).toBeGreaterThan(1); // hub + blades
    expect(propMeshes).not.toContain(s.parts.gearbox);
    // the propeller sits in front of the gearbox
    expect(s.parts.prop.position.z).toBeGreaterThan(s.parts.gearbox.position.z);
    s.dispose();
  });

  it("are styled independently", () => {
    const s = buildEngineScene(makeSpec());
    const vm = makeVm();
    const styles = modeStyles(vm, "health");
    styles.gearbox = { color: "#C64F44", intensity: 1, outline: null, pulse: false };
    s.update(vm, styles, 0.016, 0);
    expect(s.parts.gearboxMaterial.emissive.getHexString()).toBe(hex("#C64F44"));
    expect(s.parts.propMaterial.emissiveIntensity).toBe(0);
    s.dispose();
  });
});

describe("update(vm, styles, dt, elapsed) applies the mode styles", () => {
  it("thermal: a hotter CHT makes every head glow brighter and shifts its colour; all heads identical", () => {
    const s = buildEngineScene(makeSpec());
    apply(s, { telemetry: makeTelemetry({ cht: 100 }), physics: [] });
    const coolI = s.parts.headMaterials[0].emissiveIntensity;
    const coolHex = s.parts.headMaterials[0].emissive.getHexString();
    apply(s, { telemetry: makeTelemetry({ cht: 350 }), physics: [] });
    expect(s.parts.headMaterials[0].emissiveIntensity).toBeGreaterThan(coolI);
    expect(s.parts.headMaterials[0].emissive.getHexString()).not.toBe(coolHex);
    for (const m of s.parts.headMaterials) {
      expect(m.emissive.getHexString()).toBe(s.parts.headMaterials[0].emissive.getHexString());
      expect(m.emissiveIntensity).toBe(s.parts.headMaterials[0].emissiveIntensity);
    }
    s.dispose();
  });

  it("head outlines take the physics status colour (fixture: CHT is REVIEW)", () => {
    const s = buildEngineScene(makeSpec());
    apply(s);
    for (const e of s.parts.headEdges) expect(e.color.getHexString()).toBe(hex(STATUS_COLOR.REVIEW));
    s.dispose();
  });

  it("health mode: the block takes the backend score's colour; heads stay unlit", () => {
    const s = buildEngineScene(makeSpec());
    apply(s, { health: health(80) }, "health");
    expect(s.parts.blockMaterial.emissive.getHexString()).toBe(hex(healthColor(80)));
    expect(s.parts.blockMaterial.emissiveIntensity).toBeGreaterThan(0);
    for (const m of s.parts.headMaterials) expect(m.emissiveIntensity).toBe(0);
    apply(s, { health: health(10) }, "health");
    expect(s.parts.blockMaterial.emissive.getHexString()).toBe(hex(STATUS_COLOR.ANOMALY));
    s.dispose();
  });

  it("health mode without a score leaves the block unlit", () => {
    const s = buildEngineScene(makeSpec());
    apply(s, {}, "health");
    expect(s.parts.blockMaterial.emissiveIntensity).toBe(0);
    s.dispose();
  });

  it("a pulsing style modulates the glow with elapsed time", () => {
    const s = buildEngineScene(makeSpec());
    const vm = makeVm({ health: health(10) });
    const styles = modeStyles(vm, "health"); // score 10 => pulse
    s.update(vm, styles, 0.016, 0);
    const a = s.parts.blockMaterial.emissiveIntensity;
    s.update(vm, styles, 0.016, Math.PI / 10); // sin(pi/2) = 1
    const b = s.parts.blockMaterial.emissiveIntensity;
    expect(b).toBeGreaterThan(a);
    s.dispose();
  });

  it("EGT drives the exhaust, oil temperature drives the sump", () => {
    const s = buildEngineScene(makeSpec());
    apply(s, { telemetry: makeTelemetry({ egt: 100, oil_temp: 20 }), physics: [] });
    const [egtLow, oilLow] = [s.parts.exhaustMaterial.emissiveIntensity, s.parts.oilMaterial.emissiveIntensity];
    apply(s, { telemetry: makeTelemetry({ egt: 900, oil_temp: 180 }), physics: [] });
    expect(s.parts.exhaustMaterial.emissiveIntensity).toBeGreaterThan(egtLow);
    expect(s.parts.oilMaterial.emissiveIntensity).toBeGreaterThan(oilLow);
    s.dispose();
  });

  it("physics mode: a part takes the colour of its sensor's physics status", () => {
    const s = buildEngineScene(makeSpec());
    apply(s, {}, "physics");
    expect(s.parts.exhaustMaterial.emissive.getHexString()).toBe(hex(STATUS_COLOR.CONSISTENT));
    expect(s.parts.headMaterials[0].emissive.getHexString()).toBe(hex(STATUS_COLOR.REVIEW));
    s.dispose();
  });

  it("oil pressure bar height is proportional to pressure within the configured range", () => {
    const s = buildEngineScene(makeSpec());
    apply(s, { telemetry: makeTelemetry({ oil_pressure: 30 }) });
    expect(s.parts.oilPressureBar.scale.y).toBeCloseTo(0.2, 6);
    apply(s, { telemetry: makeTelemetry({ oil_pressure: 120 }) });
    expect(s.parts.oilPressureBar.scale.y).toBeCloseTo(0.8, 6);
    s.dispose();
  });

  it("with no telemetry nothing glows, the pressure bar is at its floor and the fuel dashes are hidden", () => {
    const s = buildEngineScene(makeSpec());
    apply(s, { telemetry: undefined, physics: undefined });
    for (const m of s.parts.headMaterials) expect(m.emissiveIntensity).toBe(0);
    expect(s.parts.exhaustMaterial.emissiveIntensity).toBe(0);
    expect(s.parts.oilPressureBar.scale.y).toBeCloseTo(0.02, 6);
    expect(s.parts.fuelDashes.every((d) => !d.visible)).toBe(true);
    s.dispose();
  });

  it("bearing ring colour follows the bearing model output, and is unlit-grey with none", () => {
    const s = buildEngineScene(makeSpec());
    apply(s, { bearing: BEARING_OR21 }, "bearing");
    expect(s.parts.bearingMaterial.color.getHexString()).toBe(hex(STATUS_COLOR.ANOMALY));
    apply(s, {}, "bearing");
    expect(s.parts.bearingMaterial.color.getHexString()).toBe(hex("#4a515c"));
    s.dispose();
  });

  it("updating with fewer style entries than cylinders does not throw", () => {
    const s = buildEngineScene(makeSpec({ num_cylinders: 4 }));
    const vm = makeVm();
    const styles = modeStyles(vm, "thermal");
    styles.cylinders = styles.cylinders.slice(0, 1);
    expect(() => s.update(vm, styles, 0.016, 0)).not.toThrow();
    s.dispose();
  });
});

describe("live data drives motion", () => {
  it("propeller and crank turn in proportion to RPM", () => {
    const a = buildEngineScene(makeSpec());
    const b = buildEngineScene(makeSpec());
    apply(a, { telemetry: makeTelemetry({ rpm: 1500 }) }, "thermal", 0.5);
    apply(b, { telemetry: makeTelemetry({ rpm: 3000 }) }, "thermal", 0.5);
    expect(a.parts.prop.rotation.z).toBeCloseTo(spinRate(1500) * 0.5, 9);
    expect(b.parts.prop.rotation.z).toBeCloseTo(2 * a.parts.prop.rotation.z, 9);
    expect(b.parts.crank.rotation.y).toBeCloseTo(2 * a.parts.crank.rotation.y, 9);
    a.dispose();
    b.dispose();
  });

  it("no motion at zero RPM or without telemetry", () => {
    const s = buildEngineScene(makeSpec());
    apply(s, { telemetry: makeTelemetry({ rpm: 0 }) }, "thermal", 1);
    expect(s.parts.prop.rotation.z).toBe(0);
    apply(s, { telemetry: undefined }, "thermal", 1);
    expect(s.parts.prop.rotation.z).toBe(0);
    s.dispose();
  });

  it("replay data animates too", () => {
    const s = buildEngineScene(makeSpec());
    apply(s, { kind: "replay", telemetry: makeTelemetry({ rpm: 3000, ts: minutesAgoNaive(600) }) }, "thermal", 0.5);
    expect(s.parts.prop.rotation.z).toBeGreaterThan(0);
    s.dispose();
  });

  it("fuel dashes flow at different speeds for different fuel flow", () => {
    const slow = buildEngineScene(makeSpec());
    const fast = buildEngineScene(makeSpec());
    const before = slow.parts.fuelDashes[0].position.z;
    apply(slow, { telemetry: makeTelemetry({ fuel_flow: 3 }) }, "thermal", 0.1, 1.0);
    apply(fast, { telemetry: makeTelemetry({ fuel_flow: 27 }) }, "thermal", 0.1, 1.0);
    const travel = (x: EngineScene) => (x.parts.fuelDashes[0].position.z - before + x.parts.length) % x.parts.length;
    expect(travel(fast)).not.toBeCloseTo(travel(slow), 3);
    expect(fast.parts.fuelDashes.every((d) => d.visible)).toBe(true);
    slow.dispose();
    fast.dispose();
  });

  it("the engine shakes only when vibration is measured", () => {
    const rnd = vi.spyOn(Math, "random").mockReturnValue(0.9);
    const s = buildEngineScene(makeSpec());
    apply(s, { telemetry: makeTelemetry({ vibration_x: 0, vibration_y: 0, vibration_z: 0 }) });
    expect(s.parts.engine.position.length()).toBe(0);
    apply(s, { telemetry: makeTelemetry({ vibration_x: 2, vibration_y: 2, vibration_z: 2 }) });
    expect(s.parts.engine.position.length()).toBeGreaterThan(0);
    apply(s, { telemetry: makeTelemetry({ vibration_x: null, vibration_y: null, vibration_z: null }) });
    expect(s.parts.engine.position.length()).toBe(0);
    rnd.mockRestore();
    s.dispose();
  });
});

describe("stale data is not presented as live", () => {
  it("stale => dimmer glow, no rotation, no shake", () => {
    const rnd = vi.spyOn(Math, "random").mockReturnValue(0.9);
    const live = buildEngineScene(makeSpec());
    const stale = buildEngineScene(makeSpec());
    const old = minutesAgoNaive(60);
    apply(live, { telemetry: makeTelemetry({ cht: 350 }) }, "thermal", 0.5);
    apply(stale, { telemetry: makeTelemetry({ cht: 350, ts: old }) }, "thermal", 0.5);
    expect(stale.parts.headMaterials[0].emissiveIntensity).toBeLessThan(live.parts.headMaterials[0].emissiveIntensity);
    expect(stale.parts.prop.rotation.z).toBe(0);
    expect(live.parts.prop.rotation.z).toBeGreaterThan(0);
    apply(stale, { telemetry: makeTelemetry({ vibration_x: 2, vibration_y: 2, vibration_z: 2, ts: old }) }, "thermal", 0.5);
    expect(stale.parts.engine.position.length()).toBe(0);
    rnd.mockRestore();
    live.dispose();
    stale.dispose();
  });
});

describe("selection highlight", () => {
  it("adds, replaces and removes a single highlight helper", () => {
    const s = buildEngineScene(makeSpec());
    const before = s.root.children.length;
    s.highlight({ kind: "cylinder", index: 1 });
    expect(s.root.children.length).toBe(before + 1);
    s.highlight({ kind: "oil" });
    expect(s.root.children.length).toBe(before + 1);
    s.highlight(null);
    expect(s.root.children.length).toBe(before);
    s.dispose();
  });

  it.each(["block", "turbo", "bearing", "gearbox", "prop", "exhaust", "oil", "fuel"] as const)("can highlight %s", (kind) => {
    const s = buildEngineScene(makeSpec());
    const before = s.root.children.length;
    s.highlight({ kind });
    expect(s.root.children.length).toBe(before + 1);
    expect(() => apply(s)).not.toThrow(); // helper follows the object on update
    s.dispose();
  });

  it("an unknown cylinder index highlights nothing", () => {
    const s = buildEngineScene(makeSpec({ num_cylinders: 4 }));
    const before = s.root.children.length;
    s.highlight({ kind: "cylinder", index: 9 });
    expect(s.root.children.length).toBe(before);
    s.dispose();
  });
});

describe("dispose", () => {
  it("releases geometries and materials", () => {
    const s = buildEngineScene(makeSpec());
    const geoSpy = vi.spyOn(s.parts.block.geometry, "dispose");
    const matSpies = [s.parts.blockMaterial, s.parts.turboMaterial, s.parts.propMaterial, s.parts.gearboxMaterial, ...s.parts.headMaterials].map((m) => vi.spyOn(m, "dispose"));
    s.dispose();
    expect(geoSpy).toHaveBeenCalled();
    for (const spy of matSpies) expect(spy).toHaveBeenCalled();
  });

  it("also releases an active highlight helper", () => {
    const s = buildEngineScene(makeSpec());
    s.highlight({ kind: "block" });
    const helper = s.root.children.find((c) => c instanceof THREE.BoxHelper) as THREE.BoxHelper;
    const spy = vi.spyOn(helper.geometry, "dispose");
    s.dispose();
    expect(spy).toHaveBeenCalled();
  });
});
