import { useEffect, useRef, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import { HealthScoreRing } from "@/components/HealthScoreRing";
import { FaultAlertBanner } from "@/components/FaultAlertBanner";
import { BearingHealthVisualizer } from "@/components/BearingHealthVisualizer";
import { AuxRadarChart } from "@/components/AuxRadarChart";
import { WhatIfPanel } from "@/components/whatif/WhatIfPanel";
import { MissionInfoCard } from "@/components/MissionInfoCard";
import { enginesApi, missionsApi, simulationApi, uavAssetsApi } from "@/services/resources";
import { hasRecordedData, missionLabel } from "@/lib/missionInfo";
import type { Engine, Mission, SimulationMode, SimulationRunResponse, UAVAsset } from "@/types";
import { fmtDateTime } from "@/lib/utils";

const PRESETS = [
  { value: "nominal_cruise", label: "Nominal Cruise" },
  { value: "hot_weather_endurance", label: "Hot Weather Endurance (45°C)" },
  { value: "high_altitude_patrol", label: "High Altitude Patrol (6000m)" },
  { value: "aggressive_throttle", label: "Aggressive Throttle" },
];

export function SimulationReplay() {
  const { engineId = "" } = useParams();
  const [searchParams] = useSearchParams();
  const preselectedMissionId = searchParams.get("mission") ?? "";
  const [engine, setEngine] = useState<Engine | null>(null);
  const [missions, setMissions] = useState<Mission[]>([]);
  const [assets, setAssets] = useState<UAVAsset[]>([]);
  const [mode, setMode] = useState<SimulationMode>("replay");
  const [missionId, setMissionId] = useState(preselectedMissionId);
  const [preset, setPreset] = useState(PRESETS[0].value);
  // What-If has two tools: the parameter-perturbation simulator (primary) and the
  // legacy preset mission envelopes (42-step synthetic run).
  const [whatIfTab, setWhatIfTab] = useState<"parameters" | "preset">("parameters");

  const [run, setRun] = useState<SimulationRunResponse | null>(null);
  const [starting, setStarting] = useState(false);
  const [frameIndex, setFrameIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const pollTimer = useRef<ReturnType<typeof setInterval> | null>(null);
  const playTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    enginesApi.get(engineId).then(setEngine);
    // Stats tell the picker which missions actually have recorded telemetry to replay.
    missionsApi.list(true).then((all) => {
      // Missions link to a UAV asset, not an engine directly — scope to
      // this engine's asset once the engine itself has loaded.
      setMissions(all);
    });
    // Aircraft tail numbers, so a mission reads "N123AB · Endurance · …" not just "endurance".
    Promise.resolve(uavAssetsApi.list())
      .then((a) => setAssets(a ?? []))
      .catch(() => setAssets([]));
  }, [engineId]);

  const relevantMissions = engine ? missions.filter((m) => m.uav_asset_id === engine.uav_asset_id) : missions;
  const tailFor = (m: Mission) => assets.find((a) => a.id === m.uav_asset_id)?.tail_number;
  const selectedMission = relevantMissions.find((m) => m.id === missionId);

  // Nothing pre-selected (no ?mission= in the URL): default to the newest mission that
  // actually has telemetry, so Replay opens on something runnable. Never overrides a choice.
  useEffect(() => {
    if (missionId || relevantMissions.length === 0) return;
    const runnable = relevantMissions.find((m) => m.reading_count !== undefined && m.reading_count !== null && m.reading_count > 0);
    if (runnable) setMissionId(runnable.id);
  }, [relevantMissions, missionId]);

  async function startRun() {
    setStarting(true);
    setRun(null);
    setFrameIndex(0);
    try {
      const created =
        mode === "replay"
          ? await simulationApi.runReplay(engineId, missionId)
          : await simulationApi.runWhatIf(engineId, { preset });

      if (pollTimer.current) clearInterval(pollTimer.current);
      pollTimer.current = setInterval(async () => {
        const polled = await simulationApi.get(created.simulation_id);
        setRun(polled);
        if (polled.status === "completed" || polled.status === "failed") {
          if (pollTimer.current) clearInterval(pollTimer.current);
        }
      }, 1500);
    } finally {
      setStarting(false);
    }
  }

  useEffect(() => () => {
    if (pollTimer.current) clearInterval(pollTimer.current);
    if (playTimer.current) clearInterval(playTimer.current);
  }, []);

  useEffect(() => {
    if (!playing || !run?.results) return;
    playTimer.current = setInterval(() => {
      setFrameIndex((i) => {
        if (i >= (run.results?.length ?? 1) - 1) {
          setPlaying(false);
          return i;
        }
        return i + 1;
      });
    }, 250);
    return () => {
      if (playTimer.current) clearInterval(playTimer.current);
    };
  }, [playing, run?.results]);

  // A run belongs to the mode that started it — never render replay results
  // under What-If (or vice versa) after the user switches tabs.
  const visibleRun = run && run.mode === mode ? run : null;
  const showSteps = mode === "replay" || whatIfTab === "preset";
  const frame = visibleRun?.results?.[frameIndex];
  const nowIso = frame?.ts ?? new Date().toISOString();

  const segBtn = (active: boolean) =>
    `rounded-sm px-3 py-1 text-xs font-semibold transition-colors ${active ? "bg-accent text-bg" : "text-textMuted hover:text-text"}`;
  const tabBtn = (active: boolean) =>
    `-mb-px border-b-2 px-3 py-2 text-xs font-semibold transition-colors ${active ? "border-accent text-text" : "border-transparent text-textMuted hover:text-text"}`;

  const runStatus = visibleRun && (
    <span className="text-xs text-textMuted">
      Status: <span className="font-semibold text-text">{visibleRun.status}</span>
      {visibleRun.status === "failed" && <span className="text-critical"> — {visibleRun.error}</span>}
      {visibleRun.results && ` · ${visibleRun.results.length} steps`}
    </span>
  );

  return (
    <AppShell breadcrumb={["Fleet", "Dashboard", engine?.serial_number ?? engineId.slice(0, 8), "Simulation"]}>
      <div className="flex min-w-0 flex-col gap-4 p-5 lg:pr-12">
        <div className="rounded-sm border border-border bg-surface">
          <div className="flex flex-wrap items-center gap-3 px-4 pb-3 pt-4">
            <div>
              <div className="text-[15px] font-semibold">Mission Replay &amp; What-If</div>
              <div className="mt-0.5 text-[11px] text-textMuted">
                {mode === "replay"
                  ? "Re-run a recorded mission through the real models."
                  : "Ask how the engine-health models respond if operating parameters change."}
              </div>
            </div>
            <div className="flex-grow" />
            <div className="inline-flex rounded-sm border border-border bg-surface2 p-0.5" role="group" aria-label="Simulation mode">
              <button
                onClick={() => {
                  setPlaying(false);
                  setMode("replay");
                }}
                aria-pressed={mode === "replay"}
                className={segBtn(mode === "replay")}
              >
                Replay
              </button>
              <button
                onClick={() => {
                  setPlaying(false);
                  setMode("what_if");
                }}
                aria-pressed={mode === "what_if"}
                className={segBtn(mode === "what_if")}
              >
                What-If
              </button>
            </div>
          </div>

          {mode === "what_if" && (
            <div className="flex gap-1 border-b border-border px-3" role="tablist" aria-label="What-If tool">
              <button role="tab" aria-selected={whatIfTab === "parameters"} onClick={() => setWhatIfTab("parameters")} className={tabBtn(whatIfTab === "parameters")}>
                Parameter What-If
              </button>
              <button role="tab" aria-selected={whatIfTab === "preset"} onClick={() => setWhatIfTab("preset")} className={tabBtn(whatIfTab === "preset")}>
                Preset mission
              </button>
            </div>
          )}

          {(mode === "replay" || whatIfTab === "preset") && (
            <div className="px-4 py-4">
              {mode === "what_if" && (
                <div className="mb-3 text-[11px] font-semibold uppercase tracking-wide text-textFaint" data-testid="preset-section-label">
                  Preset mission envelope — 42-step synthetic run
                </div>
              )}
              <div className="flex flex-wrap items-end gap-2.5">
                {mode === "replay" ? (
                  <div className="flex flex-col gap-1">
                    <label className="text-[10px] font-semibold uppercase text-textFaint">Mission</label>
                    <select
                      value={missionId}
                      onChange={(e) => setMissionId(e.target.value)}
                      className="rounded-sm border border-borderStrong bg-surface2 px-2 py-1.5 text-xs"
                    >
                      <option value="">Select a mission…</option>
                      {relevantMissions.map((m) => (
                        <option key={m.id} value={m.id} disabled={!hasRecordedData(m)}>
                          {missionLabel(m, tailFor(m))}
                        </option>
                      ))}
                    </select>
                  </div>
                ) : (
                  <div className="flex flex-col gap-1">
                    <label className="text-[10px] font-semibold uppercase text-textFaint">Scenario Preset</label>
                    <select
                      value={preset}
                      onChange={(e) => setPreset(e.target.value)}
                      className="rounded-sm border border-borderStrong bg-surface2 px-2 py-1.5 text-xs"
                    >
                      {PRESETS.map((p) => (
                        <option key={p.value} value={p.value}>
                          {p.label}
                        </option>
                      ))}
                    </select>
                  </div>
                )}
                <button
                  onClick={startRun}
                  disabled={starting || (mode === "replay" && (!missionId || (!!selectedMission && !hasRecordedData(selectedMission)))) || visibleRun?.status === "running" || visibleRun?.status === "queued"}
                  className="rounded-sm bg-accent px-3 py-1.5 text-xs font-semibold text-bg disabled:opacity-50"
                >
                  {mode === "what_if" ? "Run Preset Simulation" : "Run Simulation"}
                </button>
                {runStatus}
              </div>
              {mode === "replay" &&
                (selectedMission ? (
                  <MissionInfoCard mission={selectedMission} tailNumber={tailFor(selectedMission)} />
                ) : (
                  <div className="mt-3 text-[11px] text-textFaint" data-testid="mission-info-hint">
                    {relevantMissions.length === 0
                      ? "No missions are recorded for this aircraft yet."
                      : "Select a mission to see its details: aircraft, dates, and how much telemetry is stored."}
                  </div>
                ))}
            </div>
          )}
        </div>

        {/* Kept mounted (just hidden) on the Preset tab so slider edits and results survive a tab flip. */}
        {mode === "what_if" && (
          <div className={whatIfTab === "parameters" ? "" : "hidden"}>
            <WhatIfPanel engineId={engineId} />
          </div>
        )}

        {showSteps && visibleRun?.results && visibleRun.results.length > 0 && (
          <>
            {mode === "what_if" && (
              <div
                className="text-[11px] font-semibold uppercase tracking-wide"
                style={{ color: "#C9962F" }}
                data-testid="preset-results-label"
              >
                Preset simulation — synthetic mission, not live data
              </div>
            )}
            {/* Scrubber */}
            <div className="rounded-sm border border-border bg-surface p-4">
              <div className="mb-2 flex items-center gap-3">
                <button
                  onClick={() => setPlaying((p) => !p)}
                  className="rounded-sm border border-borderStrong bg-surface2 px-3 py-1 text-xs font-semibold hover:border-accent hover:text-accent"
                >
                  {playing ? "Pause" : "Play"}
                </button>
                <span className="font-mono text-xs text-textMuted">
                  Step {frameIndex + 1} / {visibleRun.results.length} · {frame?.ts ? fmtDateTime(frame.ts) : "—"}
                </span>
              </div>
              <input
                type="range"
                min={0}
                max={visibleRun.results.length - 1}
                value={frameIndex}
                onChange={(e) => {
                  setPlaying(false);
                  setFrameIndex(Number(e.target.value));
                }}
                className="w-full accent-accent"
              />
            </div>

            {frame && (
              <>
                <FaultAlertBanner
                  fault={
                    frame.fault
                      ? { ...frame.fault, ts: nowIso, engine_id: engineId, model_version_id: "replay" }
                      : undefined
                  }
                />

                <div className="flex items-center gap-6 rounded-sm border border-border bg-surface p-4.5">
                  <HealthScoreRing
                    score={frame.health_score.combined_score}
                    forcedZero={frame.health_score.contributing_factors.some((f) => f.forced_zero)}
                    size={100}
                    strokeWidth={8}
                  />
                  <div className="flex flex-wrap gap-2">
                    {frame.health_score.contributing_factors.length === 0 && (
                      <span className="text-xs text-textFaint">No active penalties at this step.</span>
                    )}
                    {frame.health_score.contributing_factors.map((f, i) => (
                      <span
                        key={i}
                        className="rounded-sm border px-2.5 py-1 text-[11px] font-semibold"
                        style={{
                          color: f.source === "rul" ? "#8B7FC7" : f.source === "fault" ? "#C64F44" : f.source === "bearing" ? "#4FA8B5" : "#B08A5A",
                          borderColor: f.source === "rul" ? "#8B7FC7" : f.source === "fault" ? "#C64F44" : f.source === "bearing" ? "#4FA8B5" : "#B08A5A",
                        }}
                      >
                        {f.source.toUpperCase()} {f.forced_zero ? "forced-zero" : `−${f.penalty ?? 0}`}
                      </span>
                    ))}
                  </div>
                </div>

                <div className="flex rounded-sm border border-border bg-surface p-1">
                  {(["rpm", "cht", "egt", "oil_pressure", "oil_temp", "fuel_flow"] as const).map((key) => (
                    <div key={key} className="flex-1 p-2.5">
                      <div className="text-[10px] font-semibold uppercase tracking-wide text-textFaint">{key.replace("_", " ")}</div>
                      <div className="font-mono text-xl font-semibold">{frame.telemetry[key] ?? "—"}</div>
                    </div>
                  ))}
                </div>

                <div className="flex gap-3.5">
                  <div className="flex-1 rounded-sm border border-border bg-surface p-4">
                    <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-textFaint">RUL at this step</div>
                    {frame.rul ? (
                      <div className="font-mono text-2xl font-semibold">
                        {frame.rul.rul_cycles} <span className="text-xs text-textFaint">cycles</span>
                      </div>
                    ) : (
                      <div className="text-xs text-textFaint">— window not yet full</div>
                    )}
                  </div>
                  <div className="flex-1 rounded-sm border border-border bg-surface p-4">
                    <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-textFaint">Bearing / Vibration</div>
                    <BearingHealthVisualizer
                      reading={
                        frame.bearing
                          ? { ...frame.bearing, ts: nowIso, engine_id: engineId, model_version_id: "replay" }
                          : undefined
                      }
                      size={90}
                    />
                  </div>
                  <div className="flex-1 rounded-sm border border-border bg-surface p-4">
                    <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-textFaint">Auxiliary</div>
                    <AuxRadarChart
                      data={
                        frame.aux
                          ? { ...frame.aux, ts: nowIso, engine_id: engineId, model_version_id: "replay" }
                          : undefined
                      }
                      size={130}
                    />
                  </div>
                </div>
              </>
            )}
          </>
        )}
      </div>
    </AppShell>
  );
}
