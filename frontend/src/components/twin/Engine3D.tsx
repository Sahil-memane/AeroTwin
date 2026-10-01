import { useEffect, useRef, useState, type MutableRefObject } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import type { EngineTwinSpec } from "@/types";
import type { TwinViewModel } from "@/lib/engineTwin";
import type { ModeStyles } from "@/lib/twinModes";
import { buildEngineScene, samePart, type EngineScene, type PartId } from "@/lib/engineScene";

export function partLabel(part: PartId): string {
  switch (part.kind) {
    case "cylinder":
      return `Cylinder ${part.index + 1}`;
    case "block":
      return "Engine block";
    case "turbo":
      return "Turbo (placeholder)";
    case "bearing":
      return "Main bearing (bearing model)";
    case "gearbox":
      return "Propeller gearbox";
    case "prop":
      return "Propeller";
    case "exhaust":
      return "Exhaust system";
    case "oil":
      return "Oil system";
    case "fuel":
      return "Fuel system";
  }
}

interface Engine3DProps {
  spec: EngineTwinSpec;
  /** Latest view model; read every frame (a ref, so live data never re-renders the canvas). */
  viewModelRef: MutableRefObject<TwinViewModel>;
  /** The active view mode's component styles; also read every frame. */
  stylesRef: MutableRefObject<ModeStyles>;
  selected: PartId | null;
  onSelect: (part: PartId | null) => void;
  /** Change to re-frame the camera. */
  resetViewKey?: number;
}

export function Engine3D({ spec, viewModelRef, stylesRef, selected, onSelect, resetViewKey = 0 }: Engine3DProps) {
  const mountRef = useRef<HTMLDivElement>(null);
  const sceneRef = useRef<EngineScene | null>(null);
  const resetRef = useRef<() => void>(() => undefined);
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;
  const [unsupported, setUnsupported] = useState(false);
  const [hover, setHover] = useState<PartId | null>(null);

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;

    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    } catch {
      setUnsupported(true);
      return;
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    mount.appendChild(renderer.domElement);
    renderer.domElement.style.display = "block";
    renderer.domElement.dataset.testid = "twin-canvas";

    const scene = new THREE.Scene();
    const engine = buildEngineScene(spec);
    sceneRef.current = engine;
    scene.add(engine.root);

    const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 100);
    const home = () => {
      camera.position.set(5.2, 2.9, 6.6);
      controls.target.set(0, -0.5, 0.4);
      controls.update();
    };
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.minDistance = 3;
    controls.maxDistance = 28;
    resetRef.current = home;
    home();

    const resize = () => {
      const w = mount.clientWidth || 800;
      const h = mount.clientHeight || 500;
      renderer.setSize(w, h, false);
      renderer.domElement.style.width = "100%";
      renderer.domElement.style.height = "100%";
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(mount);

    // ── picking: hover label + click select (a drag is an orbit, not a click) ──
    const ray = new THREE.Raycaster();
    const ndc = new THREE.Vector2();
    const pick = (ev: PointerEvent): PartId | null => {
      const r = renderer.domElement.getBoundingClientRect();
      ndc.set(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1);
      ray.setFromCamera(ndc, camera);
      const hit = ray.intersectObjects(engine.pickables, false)[0];
      return (hit?.object.userData.part as PartId | undefined) ?? null;
    };
    let down: { x: number; y: number } | null = null;
    const onDown = (e: PointerEvent) => (down = { x: e.clientX, y: e.clientY });
    const onUp = (e: PointerEvent) => {
      if (down && Math.hypot(e.clientX - down.x, e.clientY - down.y) < 5) onSelectRef.current(pick(e));
      down = null;
    };
    const onMove = (e: PointerEvent) => {
      const p = pick(e);
      renderer.domElement.style.cursor = p ? "pointer" : "grab";
      setHover((prev) => (samePart(prev, p) ? prev : p));
    };
    const onLeave = () => setHover(null);
    renderer.domElement.addEventListener("pointerdown", onDown);
    renderer.domElement.addEventListener("pointerup", onUp);
    renderer.domElement.addEventListener("pointermove", onMove);
    renderer.domElement.addEventListener("pointerleave", onLeave);

    // ── animation loop (paused while the tab is hidden) ──
    let raf = 0;
    let last = performance.now();
    let elapsed = 0;
    const loop = (now: number) => {
      raf = requestAnimationFrame(loop);
      const dt = Math.min(0.1, (now - last) / 1000);
      last = now;
      elapsed += dt;
      engine.update(viewModelRef.current, stylesRef.current, dt, elapsed);
      controls.update();
      renderer.render(scene, camera);
    };
    raf = requestAnimationFrame(loop);

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      renderer.domElement.removeEventListener("pointerdown", onDown);
      renderer.domElement.removeEventListener("pointerup", onUp);
      renderer.domElement.removeEventListener("pointermove", onMove);
      renderer.domElement.removeEventListener("pointerleave", onLeave);
      controls.dispose();
      engine.dispose();
      renderer.dispose();
      renderer.domElement.remove();
      sceneRef.current = null;
    };
    // The scene is rebuilt only if the engine's configuration changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [spec.spec.num_cylinders, spec.spec.layout, spec.engine_id]);

  useEffect(() => {
    sceneRef.current?.highlight(selected);
  }, [selected]);

  useEffect(() => {
    if (resetViewKey > 0) resetRef.current();
  }, [resetViewKey]);

  if (unsupported) {
    return (
      <div className="flex h-full items-center justify-center p-6 text-center text-sm text-textMuted" data-testid="twin-unsupported">
        3D view needs WebGL, which this browser or device doesn&apos;t provide. The live readings on the right still work.
      </div>
    );
  }

  return (
    <div className="relative h-full w-full" data-testid="twin-viewport">
      <div ref={mountRef} className="h-full w-full" />
      {hover && (
        <div className="pointer-events-none absolute left-3 top-3 rounded-sm border border-borderStrong bg-surface/90 px-2 py-1 text-[11px] font-semibold" data-testid="twin-hover">
          {partLabel(hover)} — click for details
        </div>
      )}
    </div>
  );
}
