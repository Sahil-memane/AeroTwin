/**
 * Builds the 3D engine (a schematic horizontally-opposed piston engine) from the engine's REAL
 * configuration (`EngineTwinSpec`: cylinder count, layout) and applies a `TwinViewModel` plus the
 * active view mode's `ModeStyles` to it every frame. The geometry is procedural and schematic — it
 * does not claim to be a CAD model — but every colour, motion and readout is driven by data.
 *
 * Deliberately renderer-free: it only builds a scene graph, so the data binding is unit-tested in
 * Node without WebGL.
 */
import * as THREE from "three";
import type { EngineTwinSpec } from "@/types";
import type { TwinViewModel } from "@/lib/engineTwin";
import type { ComponentStyle, ModeStyles } from "@/lib/twinModes";

export type PartId =
  | { kind: "cylinder"; index: number }
  | { kind: "block" | "turbo" | "bearing" | "gearbox" | "prop" | "exhaust" | "oil" | "fuel" };

export function samePart(a: PartId | null, b: PartId | null): boolean {
  if (!a || !b) return a === b;
  if (a.kind !== b.kind) return false;
  return a.kind === "cylinder" && b.kind === "cylinder" ? a.index === b.index : true;
}

const METAL = 0x505b70;
const BODY_NEUTRAL = new THREE.Color(0x556070);
const EDGE_DEFAULT = 0x4a515c;
const FUEL_DASHES = 10;

export interface EngineScene {
  root: THREE.Group;
  /** Meshes that respond to clicks (each carries `userData.part`). */
  pickables: THREE.Object3D[];
  update(vm: TwinViewModel, styles: ModeStyles, dtSeconds: number, elapsedSeconds: number): void;
  highlight(part: PartId | null): void;
  dispose(): void;
  /** Exposed for tests / inspection. */
  parts: {
    engine: THREE.Group;
    block: THREE.Mesh;
    blockMaterial: THREE.MeshStandardMaterial;
    blockEdges: THREE.LineBasicMaterial;
    cylinders: THREE.Group[];
    heads: THREE.Mesh[];
    headMaterials: THREE.MeshStandardMaterial[];
    headEdges: THREE.LineBasicMaterial[];
    turbo: THREE.Group;
    turboMaterial: THREE.MeshStandardMaterial;
    bearingRing: THREE.Mesh;
    bearingMaterial: THREE.MeshStandardMaterial;
    gearbox: THREE.Mesh;
    gearboxMaterial: THREE.MeshStandardMaterial;
    prop: THREE.Group;
    propMaterial: THREE.MeshStandardMaterial;
    crank: THREE.Mesh;
    exhaustMaterial: THREE.MeshStandardMaterial;
    oilMaterial: THREE.MeshStandardMaterial;
    oilPressureBar: THREE.Mesh;
    fuelMaterial: THREE.MeshStandardMaterial;
    fuelDashes: THREE.Mesh[];
    length: number;
  };
}

function mat(color: number, opts: Partial<THREE.MeshStandardMaterialParameters> = {}): THREE.MeshStandardMaterial {
  return new THREE.MeshStandardMaterial({ color, metalness: 0.55, roughness: 0.5, ...opts });
}
const tag = (o: THREE.Object3D, part: PartId) => {
  o.userData.part = part;
};

export function buildEngineScene(spec: EngineTwinSpec): EngineScene {
  const n = Math.max(1, spec.spec.num_cylinders);
  const rows = Math.ceil(n / 2);
  const spacing = 1.3;
  const length = rows * spacing + 0.7;
  const half = length / 2;

  const root = new THREE.Group();
  const engine = new THREE.Group(); // shaken as a whole by measured vibration
  root.add(engine);
  const pickables: THREE.Object3D[] = [];
  const add = (obj: THREE.Object3D, part: PartId | null, parent: THREE.Object3D = engine) => {
    if (part) {
      obj.traverse((o) => {
        if ((o as THREE.Mesh).isMesh) {
          tag(o, part);
          pickables.push(o);
        }
      });
    }
    parent.add(obj);
    return obj;
  };

  // Engine block (crankcase)
  const blockMaterial = mat(METAL, { emissive: new THREE.Color("#000000"), emissiveIntensity: 0 });
  const block = new THREE.Mesh(new THREE.BoxGeometry(1.5, 1.2, length), blockMaterial);
  const blockEdges = new THREE.LineBasicMaterial({ color: EDGE_DEFAULT });
  block.add(new THREE.LineSegments(new THREE.EdgesGeometry(block.geometry), blockEdges));
  add(block, { kind: "block" });

  // Cylinders — count and bank layout come from the spec.
  const cylinders: THREE.Group[] = [];
  const heads: THREE.Mesh[] = [];
  const headMaterials: THREE.MeshStandardMaterial[] = [];
  const headEdges: THREE.LineBasicMaterial[] = [];
  for (let i = 0; i < n; i++) {
    const side = i % 2 === 0 ? -1 : 1;
    const row = Math.floor(i / 2);
    const g = new THREE.Group();
    g.position.set(0, 0, (row - (rows - 1) / 2) * spacing);
    const barrel = new THREE.Mesh(new THREE.CylinderGeometry(0.36, 0.36, 1.1, 28), mat(0x6a768c, { metalness: 0.6 }));
    barrel.rotation.z = Math.PI / 2;
    barrel.position.x = side * 1.3;
    g.add(barrel);
    for (let f = 0; f < 5; f++) {
      const fin = new THREE.Mesh(new THREE.CylinderGeometry(0.5, 0.5, 0.05, 28), mat(0x7b879e, { metalness: 0.6 }));
      fin.rotation.z = Math.PI / 2;
      fin.position.x = side * (0.95 + f * 0.2);
      g.add(fin);
    }
    const headMat = mat(0x556070, { emissive: new THREE.Color("#000000"), emissiveIntensity: 0 });
    const head = new THREE.Mesh(new THREE.BoxGeometry(0.75, 0.95, 0.95), headMat);
    head.position.x = side * 2.1;
    g.add(head);
    const edgeMat = new THREE.LineBasicMaterial({ color: EDGE_DEFAULT });
    const edges = new THREE.LineSegments(new THREE.EdgesGeometry(head.geometry), edgeMat);
    edges.position.copy(head.position);
    g.add(edges);
    heads.push(head);
    headMaterials.push(headMat);
    headEdges.push(edgeMat);
    add(g, { kind: "cylinder", index: i });
    cylinders.push(g);
  }

  // Exhaust: a short pipe per cylinder + a collector per bank.
  const exhaustMaterial = mat(0x6a5a52, { emissive: new THREE.Color("#000000"), emissiveIntensity: 0 });
  const exhaust = new THREE.Group();
  for (let i = 0; i < n; i++) {
    const side = i % 2 === 0 ? -1 : 1;
    const row = Math.floor(i / 2);
    const stub = new THREE.Mesh(new THREE.CylinderGeometry(0.1, 0.1, 0.9, 16), exhaustMaterial);
    stub.position.set(side * 2.1, -0.9, (row - (rows - 1) / 2) * spacing);
    exhaust.add(stub);
  }
  for (const side of [-1, 1]) {
    const collector = new THREE.Mesh(new THREE.CylinderGeometry(0.15, 0.15, length + 0.6, 20), exhaustMaterial);
    collector.rotation.x = Math.PI / 2;
    collector.position.set(side * 2.1, -1.35, -0.3);
    exhaust.add(collector);
  }
  add(exhaust, { kind: "exhaust" });

  // Turbo — shown as a translucent GHOST: the engine spec does not declare whether a turbo is fitted
  // and AeroTwin has no boost/turbo data, so it is a layout placeholder, never a measured part.
  const turboMaterial = mat(0x8a93a8, { transparent: true, opacity: 0.3, depthWrite: false, emissive: new THREE.Color("#000000"), emissiveIntensity: 0 });
  const turbo = new THREE.Group();
  const housing = new THREE.Mesh(new THREE.CylinderGeometry(0.42, 0.42, 0.6, 24), turboMaterial);
  housing.rotation.z = Math.PI / 2;
  const volute = new THREE.Mesh(new THREE.TorusGeometry(0.46, 0.18, 14, 28), turboMaterial);
  volute.rotation.y = Math.PI / 2;
  turbo.add(housing, volute);
  turbo.position.set(0, -0.35, -half - 1.0);
  add(turbo, { kind: "turbo" });

  // Fuel rail along the top, with dashes that flow at a speed proportional to measured fuel flow.
  const fuelMaterial = mat(0x2f4a70, { emissive: new THREE.Color("#5B8FD6"), emissiveIntensity: 0.4 });
  const rail = new THREE.Mesh(new THREE.CylinderGeometry(0.07, 0.07, length + 0.4, 12), fuelMaterial);
  rail.rotation.x = Math.PI / 2;
  rail.position.y = 0.95;
  const fuel = new THREE.Group();
  fuel.add(rail);
  const fuelDashes: THREE.Mesh[] = [];
  for (let k = 0; k < FUEL_DASHES; k++) {
    const d = new THREE.Mesh(new THREE.SphereGeometry(0.11, 12, 12), fuelMaterial);
    d.position.set(0, 0.95, -half + (k / FUEL_DASHES) * length);
    fuel.add(d);
    fuelDashes.push(d);
  }
  add(fuel, { kind: "fuel" });

  // Oil sump + pressure bar (height = oil pressure in its configured range).
  const oilMaterial = mat(0x3d3a36, { emissive: new THREE.Color("#000000"), emissiveIntensity: 0 });
  const sump = new THREE.Mesh(new THREE.BoxGeometry(1.3, 0.5, length * 0.75), oilMaterial);
  sump.position.y = -0.85;
  const oil = new THREE.Group();
  oil.add(sump);
  const track = new THREE.Mesh(new THREE.BoxGeometry(0.16, 1.0, 0.16), mat(0x1d2330));
  track.position.set(0, -1.85, 0);
  oil.add(track);
  const barMat = mat(0x4c9a6a, { emissive: new THREE.Color("#4c9a6a"), emissiveIntensity: 0.6 });
  const oilPressureBar = new THREE.Mesh(new THREE.BoxGeometry(0.2, 1.0, 0.2), barMat);
  oilPressureBar.position.set(0, -2.35, 0);
  oilPressureBar.scale.y = 0.02;
  oil.add(oilPressureBar);
  add(oil, { kind: "oil" });

  // Gearbox (front, +z) and the spinning propeller on its own pivot.
  const front = half + 0.35;
  const gearboxMaterial = mat(0x46506a, { emissive: new THREE.Color("#000000"), emissiveIntensity: 0 });
  const gearbox = new THREE.Mesh(new THREE.CylinderGeometry(0.6, 0.6, 0.7, 28), gearboxMaterial);
  gearbox.rotation.x = Math.PI / 2;
  gearbox.position.z = front;
  add(gearbox, { kind: "gearbox" });
  const propMaterial = mat(0xa4adc2, { metalness: 0.3, emissive: new THREE.Color("#000000"), emissiveIntensity: 0 });
  const prop = new THREE.Group();
  prop.position.z = front + 0.55;
  const hub = new THREE.Mesh(new THREE.CylinderGeometry(0.22, 0.22, 0.3, 20), propMaterial);
  hub.rotation.x = Math.PI / 2;
  prop.add(hub);
  for (const a of [0, Math.PI]) {
    const blade = new THREE.Mesh(new THREE.BoxGeometry(0.3, 2.5, 0.07), propMaterial);
    blade.position.y = 1.25 * Math.cos(a);
    blade.rotation.z = a;
    prop.add(blade);
  }
  add(prop, { kind: "prop" });

  // Flywheel (rear) — turns with the prop; the marker makes the rotation visible.
  const crank = new THREE.Mesh(new THREE.CylinderGeometry(0.72, 0.72, 0.22, 32), mat(0x55607a));
  crank.rotation.x = Math.PI / 2;
  crank.position.z = -half - 0.15;
  const mark = new THREE.Mesh(new THREE.BoxGeometry(0.16, 0.16, 0.26), mat(0xd9dde6));
  mark.position.set(0.5, 0, 0);
  crank.add(mark);
  const crankWrap = new THREE.Group();
  crankWrap.add(crank);
  add(crankWrap, null);

  // Main-bearing marker (colour/pulse = bearing model output).
  const bearingMaterial = mat(0x4c9a6a, { emissive: new THREE.Color("#4c9a6a"), emissiveIntensity: 0.05 });
  const bearingRing = new THREE.Mesh(new THREE.TorusGeometry(0.66, 0.07, 14, 40), bearingMaterial);
  bearingRing.position.z = half - 0.1;
  add(bearingRing, { kind: "bearing" });

  const grid = new THREE.GridHelper(14, 14, 0x333d4a, 0x1d2330);
  grid.position.y = -2.9;
  root.add(grid);
  root.add(new THREE.AmbientLight(0xffffff, 0.85));
  const key = new THREE.DirectionalLight(0xffffff, 1.1);
  key.position.set(6, 8, 7);
  root.add(key);
  const rim = new THREE.DirectionalLight(0x6c8ebf, 0.5);
  rim.position.set(-7, 3, -6);
  root.add(rim);

  // ── selection highlight ────────────────────────────────────────────
  let helper: THREE.BoxHelper | null = null;
  let selected: THREE.Object3D | null = null;
  const objectFor = (part: PartId): THREE.Object3D | null => {
    switch (part.kind) {
      case "cylinder":
        return cylinders[part.index] ?? null;
      case "block":
        return block;
      case "turbo":
        return turbo;
      case "bearing":
        return bearingRing;
      case "gearbox":
        return gearbox;
      case "prop":
        return prop;
      case "exhaust":
        return exhaust;
      case "oil":
        return oil;
      case "fuel":
        return fuel;
    }
  };
  function highlight(part: PartId | null) {
    if (helper) {
      root.remove(helper);
      helper.geometry.dispose();
      (helper.material as THREE.Material).dispose();
      helper = null;
    }
    selected = part ? objectFor(part) : null;
    if (selected) {
      helper = new THREE.BoxHelper(selected, 0xffffff);
      root.add(helper);
    }
  }

  // ── per-frame data binding ─────────────────────────────────────────
  const tmp = new THREE.Color();
  /** Tint a material from a mode style: base colour leans toward the style colour, glow = intensity (pulsing if asked). */
  function applyStyle(m: THREE.MeshStandardMaterial, s: ComponentStyle, elapsed: number, baseHex?: number) {
    tmp.set(s.color);
    if (s.intensity <= 0) {
      m.emissive.set(0x000000);
      m.emissiveIntensity = 0;
      if (baseHex !== undefined) m.color.set(baseHex);
      return;
    }
    const base = baseHex !== undefined ? new THREE.Color(baseHex) : BODY_NEUTRAL;
    m.color.copy(base).lerp(tmp, 0.35 + 0.4 * Math.min(1, s.intensity));
    m.emissive.copy(tmp);
    const pulse = s.pulse ? 0.75 + 0.25 * Math.sin(elapsed * 5) : 1;
    m.emissiveIntensity = Math.min(1, s.intensity) * 0.9 * pulse;
  }
  const edgeColor = (line: THREE.LineBasicMaterial, s: ComponentStyle) => line.color.set(s.outline ?? EDGE_DEFAULT);

  function update(vm: TwinViewModel, styles: ModeStyles, dt: number, elapsed: number) {
    const live = vm.animate;
    const dimF = vm.state === "stale" ? 0.35 : 1;

    applyStyle(blockMaterial, styles.block, elapsed, METAL);
    edgeColor(blockEdges, styles.block);
    for (let i = 0; i < headMaterials.length; i++) {
      const s = styles.cylinders[i] ?? styles.cylinders[0];
      if (!s) continue;
      applyStyle(headMaterials[i], s, elapsed);
      edgeColor(headEdges[i], s);
    }
    applyStyle(exhaustMaterial, styles.exhaust, elapsed, 0x6a5a52);
    applyStyle(oilMaterial, styles.oil, elapsed, 0x3d3a36);
    applyStyle(gearboxMaterial, styles.gearbox, elapsed, 0x46506a);
    applyStyle(propMaterial, styles.prop, elapsed, 0xa4adc2);
    applyStyle(turboMaterial, styles.turbo, elapsed, 0x8a93a8);

    // Bearing ring: always shows the bearing model's output colour when there is one.
    const bs = styles.bearing;
    bearingMaterial.color.set(bs.intensity > 0 ? bs.color : vm.bearing.present ? vm.bearing.color : 0x4a515c);
    bearingMaterial.emissive.set(bs.intensity > 0 ? bs.color : vm.bearing.present ? vm.bearing.color : 0x000000);
    bearingMaterial.emissiveIntensity = (bs.intensity > 0 ? bs.intensity * 0.9 : vm.bearing.present ? 0.25 : 0.05) * dimF;
    const sev = vm.bearing.severity ?? 0;
    bearingRing.scale.setScalar(live && (bs.pulse || sev > 0) && bs.intensity > 0 ? 1 + 0.08 * Math.sin(elapsed * 4) : 1);

    // Oil pressure bar: height ∝ position in the configured range, colour = physics status.
    const pn = vm.sensors.oil_pressure.norm;
    const h = pn === null ? 0.02 : Math.max(0.02, pn);
    oilPressureBar.scale.y = h;
    oilPressureBar.position.y = -2.35 + (h - 1) * 0.5;
    barMat.color.set(vm.sensors.oil_pressure.statusColor);
    barMat.emissive.set(vm.sensors.oil_pressure.statusColor);
    barMat.emissiveIntensity = pn === null ? 0 : 0.6 * dimF;

    // Fuel rail: dashes flow ∝ fuel flow; the rail takes the mode's fuel style.
    const fn = vm.sensors.fuel_flow.norm;
    const flowing = live && fn !== null && fn > 0;
    if (styles.fuel.intensity > 0) applyStyle(fuelMaterial, styles.fuel, elapsed, 0x2f4a70);
    else {
      fuelMaterial.color.set(0x2f4a70);
      fuelMaterial.emissive.set("#5B8FD6");
      fuelMaterial.emissiveIntensity = fn === null ? 0 : (0.25 + 0.75 * fn) * dimF;
    }
    for (let k = 0; k < fuelDashes.length; k++) {
      fuelDashes[k].visible = fn !== null;
      if (flowing) {
        const speed = 0.08 + 1.4 * (fn as number);
        fuelDashes[k].position.z = -half + ((k / FUEL_DASHES + (elapsed * speed) / length * 2) % 1) * length;
      }
    }

    // Rotation ∝ measured RPM (at VISUAL_TIME_SCALE of real speed) — only while the data is live/replay/what-if.
    const spin = live ? vm.motion.spin : 0;
    prop.rotation.z += spin * dt;
    crank.rotation.y += spin * dt;

    // Vibration shake ∝ measured vibration magnitude — only while animating.
    if (live && vm.motion.shake > 0) {
      engine.position.set((Math.random() - 0.5) * vm.motion.shake, (Math.random() - 0.5) * vm.motion.shake, (Math.random() - 0.5) * vm.motion.shake);
    } else engine.position.set(0, 0, 0);

    if (helper && selected) helper.update();
  }

  function dispose() {
    if (helper) {
      helper.geometry.dispose();
      (helper.material as THREE.Material).dispose();
    }
    root.traverse((o) => {
      const m = o as THREE.Mesh;
      if (m.geometry) m.geometry.dispose();
      const material = m.material as THREE.Material | THREE.Material[] | undefined;
      if (Array.isArray(material)) material.forEach((x) => x.dispose());
      else material?.dispose();
    });
  }

  return {
    root,
    pickables,
    update,
    highlight,
    dispose,
    parts: {
      engine, block, blockMaterial, blockEdges, cylinders, heads, headMaterials, headEdges,
      turbo, turboMaterial, bearingRing, bearingMaterial, gearbox, gearboxMaterial, prop, propMaterial, crank,
      exhaustMaterial, oilMaterial, oilPressureBar, fuelMaterial, fuelDashes, length,
    },
  };
}
