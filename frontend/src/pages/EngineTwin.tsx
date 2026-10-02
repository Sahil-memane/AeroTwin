import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import { Engine3D } from "@/components/twin/Engine3D";
import { InspectorView, ModePanelView, SourceChip, SummaryBar, TwinCompare, sourceAge, sourceChip } from "@/components/twin/TwinPanels";
import { WhatIfPanel } from "@/components/whatif/WhatIfPanel";
import { useEngineWebSocket } from "@/hooks/useEngineWebSocket";
import { useReplayRun } from "@/hooks/useReplayRun";
import { useTelemetryStore } from "@/store/telemetryStore";
import { enginesApi } from "@/services/resources";
import { fmtDateTime } from "@/lib/utils";
import { SENSOR_KEYS, VISUAL_TIME_SCALE, buildTwinViewModel, heatColor, vibrationMagnitude } from "@/lib/engineTwin";
import type { PartId } from "@/lib/engineScene";
import { inspect, num } from "@/lib/twinInspect";
import { missionLabel, hasRecordedData } from "@/lib/missionInfo";
import { modePanel } from "@/lib/twinModePanel";
import { TWIN_MODES, modeStyles, type TwinMode } from "@/lib/twinModes";
import { inputsFromLive, inputsFromReplayFrame, inputsFromWhatIf } from "@/lib/twinSources";
import type { EngineTwinSpec, WhatIfResponse } from "@/types";

type Source = "live" | "replay" | "whatif";
const SOURCES: { id: Source; label: string; color: string }[] = [
  { id: "live", label: "LIVE", color: "#4C9A6A" },
  { id: "replay", label: "REPLAY", color: "#6C8EBF" },
  { id: "whatif", label: "WHAT-IF", color: "#C9962F" },
];
const SIM = "#C9962F";
const VIB_WINDOW = 60;

export function EngineTwin() {
  const { engineId = "" } = useParams();
  useEngineWebSocket(engineId);
  const live = useTelemetryStore((s) => s.engines[engineId]);
  const store = useTelemetryStore.getState;

  const [spec, setSpec] = useState<EngineTwinSpec | null>(null);
  const [specError, setSpecError] = useState(false);
  const [serial, setSerial] = useState<string | null>(null);
  const [source, setSource] = useState<Source>("live");
  const [mode, setMode] = useState<TwinMode>("health");
  const [selected, setSelected] = useState<PartId | null>(null);
  const [resetKey, setResetKey] = useState(0);
  const [nowMs, setNowMs] = useState(() => Date.now());
  const [vibHist, setVibHist] = useState<number[]>([]);
  const [whatIf, setWhatIf] = useState<{ result: WhatIfResponse | null; stale: boolean }>({ result: null, stale: false });
  const [whatIfView, setWhatIfView] = useState<"scenario" | "live">("scenario");
  const replay = useReplayRun(engineId, source === "replay");

  useEffect(() => {
    const id = setInterval(() => setNowMs(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  // Seed the live store from REST (so the twin isn't empty until the next WebSocket message); the WebSocket keeps it live.
  useEffect(() => {
    if (!engineId) return;
    let cancelled = false;
    setSpec(null);
    setSpecError(false);
    setSelected(null);
    setVibHist([]);
    (async () => {
      const [twinRes, telemetry, physics, fault, bearing, aux, rul, health] = await Promise.allSettled([
        enginesApi.twin(engineId),
        enginesApi.telemetryLatest(engineId),
        enginesApi.physicsConsistency(engineId),
        enginesApi.faultsLatest(engineId),
        enginesApi.bearingHealth(engineId),
        enginesApi.auxLatest(engineId),
        enginesApi.rul(engineId, 1),
        enginesApi.healthScore(engineId, 1),
      ]);
      if (cancelled) return;
      const s = store();
      if (twinRes.status === "fulfilled") {
        setSpec(twinRes.value);
        setSerial(twinRes.value.serial_number);
      } else setSpecError(true);
      if (telemetry.status === "fulfilled") s.setTelemetry(engineId, telemetry.value);
      if (physics.status === "fulfilled") s.setPhysicsConsistency(engineId, physics.value.parameters);
      if (fault.status === "fulfilled") s.setFault(engineId, fault.value);
      if (bearing.status === "fulfilled") s.setBearing(engineId, bearing.value);
      if (aux.status === "fulfilled") s.setAux(engineId, aux.value);
      if (rul.status === "fulfilled" && rul.value[0]) s.setRul(engineId, rul.value[0]);
      if (health.status === "fulfilled")
        s.setHealthScore(engineId, {
          combined_score: health.value.combined_score,
          contributing_factors: health.value.contributing_factors,
          primary_concern: health.value.primary_concern,
          ts: health.value.last_updated ?? new Date().toISOString(),
        });
    })();
    return () => {
      cancelled = true;
    };
  }, [engineId, store]);

  // Recent live vibration magnitudes (for the RMS): built from the actual stream.
  useEffect(() => {
    const m = vibrationMagnitude(live?.telemetry);
    if (m === null) return;
    setVibHist((h) => [...h.slice(-(VIB_WINDOW - 1)), m]);
  }, [live?.telemetry]);

  // ── the three data sources, all funnelled into the same view model ──
  const liveInputs = useMemo(() => inputsFromLive({ spec, live, vibrationHistory: vibHist, nowMs }), [spec, live, vibHist, nowMs]);
  const replayInputs = useMemo(() => {
    const frames = replay.frames;
    const hist = frames
      .slice(Math.max(0, replay.frameIndex - 29), replay.frameIndex + 1)
      .map((f) => vibrationMagnitude(f.telemetry))
      .filter((x): x is number => x !== null);
    return inputsFromReplayFrame({ spec, frame: frames[replay.frameIndex], index: replay.frameIndex, total: frames.length, vibrationHistory: hist, nowMs });
  }, [spec, replay.frames, replay.frameIndex, nowMs]);
  const whatIfInputs = useMemo(() => inputsFromWhatIf({ spec, result: whatIf.result, nowMs }), [spec, whatIf.result, nowMs]);

  const showingScenario = source === "whatif" && !!whatIf.result && whatIfView === "scenario";
  const inputs = source === "replay" ? replayInputs : showingScenario ? whatIfInputs : liveInputs;
  const vm = useMemo(() => buildTwinViewModel(inputs), [inputs]);
  const styles = useMemo(() => modeStyles(vm, mode), [vm, mode]);
  const panel = useMemo(() => modePanel(vm, mode, styles), [vm, mode, styles]);
  const inspection = selected && spec ? inspect(selected, vm, spec) : null;

  // The 3D loop reads these every frame without re-rendering React.
  const vmRef = useRef(vm);
  vmRef.current = vm;
  const stylesRef = useRef(styles);
  stylesRef.current = styles;

  const chip = sourceChip(vm);
  const replayReady = replay.frames.length > 0;

  return (
    <AppShell breadcrumb={["Fleet", "3D Twin", serial ?? engineId.slice(0, 8)]} copilotEngineId={engineId} copilotEngineSerial={serial ?? undefined}>
      <div className="flex min-w-0 flex-col gap-3.5 p-5 lg:pr-12">
        {/* Header */}
        <div className="flex flex-wrap items-center gap-3 rounded-sm border border-border bg-surface px-4 py-3">
          <div>
            <div className="text-[15px] font-semibold">3D Digital Twin{serial ? ` — ${serial}` : ""}</div>
            <div className="mt-0.5 text-[11px] text-textMuted">Telemetry → ML models → physics consistency → Health Fusion → this view. Drag to orbit, right-drag to pan, scroll to zoom, click a part.</div>
          </div>
          <span className="flex-grow" />
          <div className="inline-flex rounded-sm border border-border bg-surface2 p-0.5" role="tablist" aria-label="Data source">
            {SOURCES.map((s) => (
              <button
                key={s.id}
                role="tab"
                aria-selected={source === s.id}
                onClick={() => setSource(s.id)}
                data-testid={`source-tab-${s.id}`}
                className={`rounded-sm px-3 py-1 text-xs font-bold tracking-wide transition-colors ${source === s.id ? "text-bg" : "text-textMuted hover:text-text"}`}
                style={source === s.id ? { backgroundColor: s.color } : undefined}
              >
                {s.label}
              </button>
            ))}
          </div>
          <SourceChip vm={vm} />
          <span className="font-mono text-[11px] text-textMuted" data-testid="twin-age">
            {sourceAge(vm)}
          </span>
          <button onClick={() => setResetKey((k) => k + 1)} className="rounded-sm border border-borderStrong bg-surface2 px-3 py-1.5 text-xs font-semibold hover:border-accent hover:text-accent">
            Reset view
          </button>
          <Link to={`/engines/${engineId}`} className="rounded-sm border border-borderStrong bg-surface2 px-3 py-1.5 text-xs font-semibold hover:border-accent hover:text-accent hover:no-underline">
            ← Engine dashboard
          </Link>
        </div>

        {/* Source banners — the 3D view must never be mistaken for live data */}
        {vm.state === "stale" && (
          <div className="rounded-sm border border-warning bg-warningBg px-3 py-2 text-xs text-warning" data-testid="twin-stale-banner">
            The engine is not streaming. The twin shows the last known values, dimmed and not animated — it is not a live view.
          </div>
        )}
        {source === "replay" && (
          <div className="rounded-sm border px-3 py-2 text-xs" style={{ borderColor: "#6C8EBF", color: "#6C8EBF", backgroundColor: "rgba(108,142,191,0.1)" }} data-testid="twin-replay-banner">
            REPLAY — the engine shows one recorded step of a past mission, re-run through the real models. It is not live data.
          </div>
        )}
        {source === "whatif" && (
          <div className="rounded-sm border px-3 py-2 text-xs" style={{ borderColor: SIM, color: SIM, backgroundColor: "rgba(201,150,47,0.1)" }} data-testid="twin-whatif-banner">
            {showingScenario
              ? "WHAT-IF SIMULATION — the engine shows the scenario's values and the models' response to them. The live engine is unchanged."
              : whatIf.result
                ? "Showing the LIVE engine. Switch to “Scenario” to see the what-if result on the model."
                : "Change parameters and run a What-If below to preview the scenario on the engine. Until then the twin shows the LIVE engine."}
          </div>
        )}

        <SummaryBar vm={vm} />

        <div className="grid min-w-0 grid-cols-1 gap-3.5 xl:grid-cols-[minmax(0,1fr)_400px]">
          {/* ── left: viewport + source controls ── */}
          <div className="flex min-w-0 flex-col gap-3.5">
            <div className="min-w-0 rounded-sm border border-border bg-surface">
              <div className="flex flex-wrap gap-1 border-b border-border px-3 py-2" role="tablist" aria-label="View mode">
                {TWIN_MODES.map((m) => (
                  <button
                    key={m.id}
                    role="tab"
                    aria-selected={mode === m.id}
                    onClick={() => setMode(m.id)}
                    title={m.blurb}
                    data-testid={`mode-tab-${m.id}`}
                    className={`rounded-sm border px-2.5 py-1 text-xs font-semibold transition-colors ${
                      mode === m.id ? "border-accent bg-surface3 text-text" : "border-transparent text-textMuted hover:text-text"
                    }`}
                  >
                    {m.label}
                  </button>
                ))}
              </div>

              <div className="relative h-[540px] w-full" data-testid="twin-stage">
                {spec ? (
                  <Engine3D spec={spec} viewModelRef={vmRef} stylesRef={stylesRef} selected={selected} onSelect={setSelected} resetViewKey={resetKey} />
                ) : (
                  <div className="flex h-full items-center justify-center p-6 text-center text-sm text-textMuted" data-testid="twin-no-spec">
                    {specError
                      ? "Couldn't load this engine's configuration, so the 3D model can't be built (no cylinder count is assumed)."
                      : "Loading engine configuration…"}
                  </div>
                )}
                {/* always-visible source label ON the 3D view */}
                <div className="pointer-events-none absolute right-3 top-3 flex flex-col items-end gap-1" data-testid="twin-overlay">
                  <span className="rounded-sm border bg-surface/90 px-2 py-0.5 text-[10px] font-bold tracking-wider" style={{ borderColor: chip.color, color: chip.color }}>
                    {chip.text}
                  </span>
                  {(vm.state === "replay" || vm.state === "whatif") && vm.sourceLabel && (
                    <span className="rounded-sm border border-border bg-surface/90 px-2 py-0.5 font-mono text-[10px] text-textMuted">{vm.sourceLabel}</span>
                  )}
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-x-6 gap-y-2 border-t border-border px-4 py-2.5 text-[10px] text-textFaint" data-testid="twin-legend">
                <div className="flex items-center gap-2">
                  <span>Tint (configured sensor range)</span>
                  <span className="h-2 w-24 rounded-sm" style={{ background: `linear-gradient(90deg, ${[0, 0.35, 0.55, 0.75, 1].map(heatColor).join(",")})` }} />
                  <span>low → high</span>
                </div>
                <span>Outline / bar = physics status</span>
                <span>Rotation ∝ RPM at 1/{Math.round(1 / VISUAL_TIME_SCALE)} real speed</span>
                <span>Shake ∝ measured vibration</span>
                <span>Translucent part = placeholder (no data)</span>
              </div>
              {spec && (
                <div className="border-t border-border px-4 py-2 text-[11px] text-textMuted" data-testid="twin-spec-line">
                  {spec.spec.num_cylinders} cylinders · {spec.spec.layout.replace(/_/g, " ")} · {num(spec.spec.displacement_cc, 0)} cc · rated {num(spec.spec.rated_power_kw)} kW · idle{" "}
                  {num(spec.spec.rpm_idle, 0)} / max {num(spec.spec.rpm_max, 0)} rpm
                  <span className="text-textFaint"> — {spec.spec.source}</span>
                </div>
              )}
            </div>

            {/* REPLAY controls */}
            {source === "replay" && (
              <div className="rounded-sm border border-border bg-surface p-4" data-testid="replay-controls">
                <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-textFaint">Mission replay</div>
                <div className="flex flex-wrap items-end gap-2.5">
                  <label className="flex flex-col gap-1 text-[10px] font-semibold uppercase text-textFaint">
                    Mission
                    <select
                      value={replay.missionId}
                      onChange={(e) => replay.setMissionId(e.target.value)}
                      data-testid="replay-mission"
                      className="min-w-[280px] rounded-sm border border-borderStrong bg-surface2 px-2 py-1.5 text-xs font-normal normal-case text-text"
                    >
                      <option value="">Select a mission…</option>
                      {replay.missions.map((m) => (
                        <option key={m.id} value={m.id} disabled={!hasRecordedData(m)}>
                          {missionLabel(m)}
                        </option>
                      ))}
                    </select>
                  </label>
                  <button
                    onClick={() => void replay.start()}
                    disabled={!replay.missionId || replay.starting || replay.run?.status === "queued" || replay.run?.status === "running"}
                    className="rounded-sm bg-accent px-3 py-1.5 text-xs font-semibold text-bg disabled:opacity-50"
                    data-testid="replay-run"
                  >
                    {replay.run?.status === "queued" || replay.run?.status === "running" ? "Replaying…" : "Run replay"}
                  </button>
                  {replay.run && <span className="text-xs text-textMuted" data-testid="replay-status">Status: <b className="text-text">{replay.run.status}</b>{replayReady ? ` · ${replay.frames.length} steps` : ""}</span>}
                </div>
                {replay.error && (
                  <div role="alert" className="mt-2 rounded-sm border border-critical bg-criticalBg px-2.5 py-1.5 text-xs text-critical" data-testid="replay-error">
                    {replay.error}
                  </div>
                )}
                {replayReady ? (
                  <div className="mt-3 flex flex-col gap-1.5">
                    <div className="flex items-center gap-3">
                      <button
                        onClick={() => replay.setPlaying(!replay.playing)}
                        className="rounded-sm border border-borderStrong bg-surface2 px-3 py-1 text-xs font-semibold hover:border-accent hover:text-accent"
                        data-testid="replay-play"
                      >
                        {replay.playing ? "Pause" : "Play"}
                      </button>
                      <span className="font-mono text-xs text-textMuted" data-testid="replay-step">
                        Step {replay.frameIndex + 1} / {replay.frames.length}
                        {replay.frames[replay.frameIndex]?.ts ? ` · ${fmtDateTime(replay.frames[replay.frameIndex].ts as string)}` : ""}
                      </span>
                    </div>
                    <input
                      type="range"
                      aria-label="Replay step"
                      min={0}
                      max={replay.frames.length - 1}
                      value={replay.frameIndex}
                      onChange={(e) => {
                        replay.setPlaying(false);
                        replay.setFrameIndex(Number(e.target.value));
                      }}
                      className="w-full accent-accent"
                      data-testid="replay-scrubber"
                    />
                  </div>
                ) : (
                  <div className="mt-2 text-[11px] text-textFaint">Run a replay, then scrub the timeline: the engine above shows the state at that step.</div>
                )}
              </div>
            )}

            {/* WHAT-IF controls (kept mounted, just hidden, so slider edits and results survive a tab flip) */}
            <div className={source === "whatif" ? "flex flex-col gap-3.5" : "hidden"}>
              {whatIf.result && (
                <div className="flex items-center gap-2 rounded-sm border border-border bg-surface px-3 py-2 text-xs" data-testid="whatif-view-toggle">
                  <span className="text-textFaint">Show on the engine:</span>
                  {(["scenario", "live"] as const).map((v) => (
                    <button
                      key={v}
                      onClick={() => setWhatIfView(v)}
                      aria-pressed={whatIfView === v}
                      data-testid={`whatif-show-${v}`}
                      className={`rounded-sm border px-2.5 py-1 font-semibold ${whatIfView === v ? "border-accent text-accent" : "border-borderStrong text-textMuted"}`}
                    >
                      {v === "scenario" ? "WHAT-IF scenario" : "LIVE engine"}
                    </button>
                  ))}
                </div>
              )}
              <WhatIfPanel engineId={engineId} onResult={(result, stale) => setWhatIf({ result, stale })} />
            </div>
          </div>

          {/* ── right: mode panel, inspector, compare, sensors ── */}
          <div className="flex min-w-0 flex-col gap-3.5">
            <ModePanelView data={panel} />
            <InspectorView inspection={inspection} onClear={() => setSelected(null)} />
            {source === "whatif" && whatIf.result && <TwinCompare result={whatIf.result} stale={whatIf.stale} />}

            <div className="rounded-sm border border-border bg-surface p-4" data-testid="twin-sensors">
              <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-textFaint">Sensors ({chip.text.toLowerCase()})</div>
              <table className="w-full table-fixed text-xs">
                <tbody className="font-mono">
                  {SENSOR_KEYS.map((k) => {
                    const s = vm.sensors[k];
                    return (
                      <tr key={k} className="border-t border-border first:border-t-0" data-testid={`twin-sensor-${k}`}>
                        <td className="w-[38%] py-1.5 font-sans font-semibold text-textMuted">{s.label}</td>
                        <td className="py-1.5 text-right" data-testid={`twin-sensor-${k}-value`}>
                          {s.value === null ? "—" : `${num(s.value, k === "rpm" ? 0 : 1)} ${s.unit}`}
                        </td>
                        <td className="w-[26%] py-1.5 text-right font-sans text-[10px] font-semibold" style={{ color: s.statusColor }}>
                          {s.status ?? (k === "rpm" ? "input" : "—")}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              <div className="mt-2 text-[10px] text-textFaint" data-testid="twin-sensor-note">
                {spec?.sensors.per_cylinder ? "Per-cylinder temperature sensors are available." : "One CHT and one EGT for the whole engine — per-cylinder temperatures are not measured."}
              </div>
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
