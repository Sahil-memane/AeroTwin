import { useEffect, useRef, useState } from "react";
import { useSimulatorStore } from "@/store/simulatorStore";
import { Link } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import { HealthScoreRing } from "@/components/HealthScoreRing";
import { NumberTicker } from "@/components/NumberTicker";
import { LiveTicker } from "@/components/LiveTicker";
import { alertsApi, dashboardApi, enginesApi, simulatorApi } from "@/services/resources";
import type { Alert, BearingHealthReading, DashboardSummary, Engine, FaultPrediction, HealthScoreResponse } from "@/types";
import { fmtAgeShort, fmtTime, parseBackendTs } from "@/lib/utils";
import { useEngineWebSocket } from "@/hooks/useEngineWebSocket";
import { useTelemetryStore } from "@/store/telemetryStore";
import { useAuthStore } from "@/store/authStore";

// Same threshold as the engine page and the 3D twin: no reading for this long => not streaming.
const STALE_AFTER_MS = 5 * 60_000;
// KPIs and the alert feed are REST data (no stream for them), so re-read them on a timer.
const REFRESH_MS = 10_000;

/** Keeps one engine's live WebSocket open while mounted; renders nothing. */
function EngineLiveFeed({ engineId }: { engineId: string }) {
  useEngineWebSocket(engineId);
  return null;
}

function statusOfScore(score: number | null | undefined): "critical" | "warning" | "healthy" | undefined {
  if (score === null || score === undefined) return undefined;
  return score < 20 ? "critical" : score < 50 ? "warning" : "healthy";
}

interface FleetRow {
  engine: Engine;
  health?: HealthScoreResponse;
  fault?: FaultPrediction;
  bearing?: BearingHealthReading;
  hasAnyData: boolean;
}

async function loadFleetRow(engine: Engine): Promise<FleetRow> {
  const [health, fault, bearing] = await Promise.allSettled([
    enginesApi.healthScore(engine.id, 1),
    enginesApi.faultsLatest(engine.id),
    enginesApi.bearingHealth(engine.id),
  ]);
  const hasHealth = health.status === "fulfilled";
  const hasFault = fault.status === "fulfilled";
  const hasBearing = bearing.status === "fulfilled";
  return {
    engine,
    health: hasHealth ? health.value : undefined,
    fault: hasFault ? fault.value : undefined,
    bearing: hasBearing ? bearing.value : undefined,
    hasAnyData: hasHealth || hasFault || hasBearing,
  };
}

function statusColor(status?: string) {
  if (status === "critical") return "text-critical";
  if (status === "warning") return "text-warning";
  return "text-healthy";
}

export function Dashboard() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [rows, setRows] = useState<FleetRow[]>([]);
  const [recentAlerts, setRecentAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);
  const liveEngines = useTelemetryStore((s) => s.engines);
  const [nowMs, setNowMs] = useState(() => Date.now());

  // ── Simulator state (GLOBAL — persists across all page navigation) ───────
  const simState         = useSimulatorStore((s) => s.states) as Record<string, "running" | "stopped" | "loading" | "connecting" | "error">;
  const setSimGlobal     = useSimulatorStore((s) => s.setState);
  const promoteToRunning = useSimulatorStore((s) => s.promoteToRunning);
  // Per-engine packet counter (increments on each WS telemetry frame while sim is running)
  const packetCount = useRef<Record<string, number>>({});
  const [packetTick, setPacketTick] = useState(0);
  // Previous telemetry timestamps — used to detect new incoming packets
  const prevTsRef = useRef<Record<string, string>>({});


  useEffect(() => {
    const id = setInterval(() => setNowMs(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  // Periodic KPI/alert refresh. Heartbeat is now handled globally in App via simulatorStore.
  useEffect(() => {
    const id = setInterval(() => {
      Promise.all([dashboardApi.summary(), alertsApi.list({ is_acknowledged: false })])
        .then(([s, a]) => {
          setSummary(s);
          setRecentAlerts(a.slice(0, 4));
        })
        .catch(() => undefined);
    }, REFRESH_MS);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      const [summaryRes, engines, alerts] = await Promise.all([
        dashboardApi.summary(),
        enginesApi.list(),
        alertsApi.list({ is_acknowledged: false }),
      ]);
      if (cancelled) return;
      setSummary(summaryRes);
      setRecentAlerts(alerts.slice(0, 4));
      const fleetRows = await Promise.all(engines.map(loadFleetRow));
      if (!cancelled) {
        setRows(fleetRows);
        setLoading(false);
        // Sync simulator status from backend on first load (in case sim was already running)
        Promise.allSettled(fleetRows.map((r) => simulatorApi.status(r.engine.id)))
          .then((results) => {
            results.forEach((res, i) => {
              if (res.status === "fulfilled") {
                const s = res.value.status === "running" ? "running" : "stopped";
                setSimGlobal(fleetRows[i].engine.id, s);
              }
            });
          })
          .catch(() => undefined);
      }
    }
    load().catch(() => setLoading(false));
    return () => { cancelled = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // NOTE: No unmount stop here — the global simulatorStore handles lifecycle.
  // Navigating away does NOT stop the simulator.


  async function acknowledge(alertId: string) {
    await alertsApi.acknowledge(alertId);
    setRecentAlerts((prev) => prev.filter((a) => a.id !== alertId));
  }

  /** Toggle simulator on/off for a single engine. */
  async function toggleSimulator(engineId: string) {
    const current = simState[engineId] ?? "stopped";
    if (current === "loading" || current === "connecting") return;
    setSimGlobal(engineId, "loading");
    try {
      if (current === "running") {
        await simulatorApi.stop(engineId);
        packetCount.current[engineId] = 0;
        prevTsRef.current[engineId] = "";
        setPacketTick((n) => n + 1);
        setSimGlobal(engineId, "stopped");
      } else {
        await simulatorApi.start(engineId);
        packetCount.current[engineId] = 0;
        prevTsRef.current[engineId] = "";
        // Container started — wait for first telemetry packet before going "running"
        setSimGlobal(engineId, "connecting");
        // Safety fallback: if no telemetry after 30s, promote to running anyway
        setTimeout(() => promoteToRunning(engineId), 30_000);
      }
    } catch {
      setSimGlobal(engineId, "error");
      setTimeout(() => setSimGlobal(engineId, current === "running" ? "running" : "stopped"), 3000);
    }
  }

  // When telemetry arrives for an engine in "connecting" state, promote it to "running".
  // Also count packets for already-running engines.
  useEffect(() => {
    const entries = Object.entries(simState).filter(
      ([, s]) => s === "running" || s === "connecting"
    );
    if (entries.length === 0) return;

    entries.forEach(([engineId, s]) => {
      const currentTs = liveEngines[engineId]?.telemetry?.ts;
      if (currentTs && currentTs !== prevTsRef.current[engineId]) {
        prevTsRef.current[engineId] = currentTs;
        if (s === "connecting") {
          // First packet received — promote to running in global store
          promoteToRunning(engineId);
        }
        packetCount.current[engineId] = (packetCount.current[engineId] ?? 0) + 1;
        setPacketTick((n) => n + 1);
      }
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [liveEngines, simState]);

  /** Inline simulator toggle button — used in the header bar. */
  function SimButton(engineId: string, label?: string) {
    const s = simState[engineId] ?? "stopped";
    const isRunning    = s === "running";
    const isLoading    = s === "loading";
    const isConnecting = s === "connecting";
    const isError      = s === "error";
    const isBusy = isLoading || isConnecting;
    const pktCnt = packetCount.current[engineId] ?? 0;
    return (
      <button
        key={engineId}
        id={`sim-toggle-${engineId}`}
        onClick={() => toggleSimulator(engineId)}
        disabled={isBusy}
        title={
          isConnecting
            ? `Connecting simulator for ${label ?? engineId}…`
            : isRunning
              ? `Stop simulation for ${label ?? engineId}`
              : `Start simulation for ${label ?? engineId}`
        }
        className={[
          "flex items-center gap-1.5 rounded border px-3 py-1 text-[10px] font-bold tracking-widest transition-all duration-200",
          isBusy
            ? "cursor-wait border-accent/40 text-accent/70 opacity-80"
            : isError
              ? "border-critical/70 bg-critical/10 text-critical"
              : isRunning
                ? "border-healthy/50 bg-healthy/10 text-healthy shadow-[0_0_8px_rgba(74,222,128,0.15)] hover:border-critical/60 hover:bg-critical/10 hover:text-critical"
                : "border-borderStrong bg-surface2 text-textMuted hover:border-accent hover:text-accent",
        ].join(" ")}
      >
        {/* Leading indicator */}
        {isLoading ? (
          <span className="inline-block h-2 w-2 animate-spin rounded-full border border-current border-t-transparent" />
        ) : isConnecting ? (
          // Pulsing ring during connecting phase
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent opacity-60" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-accent/80" />
          </span>
        ) : isRunning ? (
          <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-healthy" />
        ) : (
          <svg width="7" height="8" viewBox="0 0 7 8" fill="currentColor" className="opacity-60">
            <path d="M0 0l7 4-7 4V0z" />
          </svg>
        )}
        {/* Label */}
        <span>{label ?? engineId.slice(0, 8)}</span>
        {/* State tag */}
        <span className={isRunning ? "opacity-80" : "opacity-40"}>
          {isLoading ? "STARTING…" : isConnecting ? "CONNECTING…" : isError ? "ERR" : isRunning ? "ON" : "START"}
        </span>
        {/* Live packet count */}
        {isRunning && pktCnt > 0 && (
          <span className="ml-0.5 rounded bg-healthy/20 px-1 font-mono text-[9px] text-healthy">
            {pktCnt < 1000 ? pktCnt : `${(pktCnt/1000).toFixed(1)}k`} pkts
          </span>
        )}
      </button>
    );
  }

  /** Animated packet counter shown while the simulator is running. */
  function PacketCounter({ count }: { engineId: string; count: number }) {
    // Show a brief flash on the dot when count changes
    return (
      <span className="flex items-center gap-1 font-mono text-[10px] text-textFaint">
        <span
          key={count}  // key change triggers CSS re-animation
          className="inline-block h-1.5 w-1.5 rounded-full bg-healthy"
          style={{ animation: "simPing 0.4s ease-out" }}
        />
        <span>
          {count < 1000
            ? `${count} pkts`
            : `${(count / 1000).toFixed(1)}k pkts`}
        </span>
      </span>
    );
  }

  // Inject the ping keyframe once into the document
  useEffect(() => {
    const id = "sim-ping-style";
    if (!document.getElementById(id)) {
      const style = document.createElement("style");
      style.id = id;
      style.textContent = `
        @keyframes simPing {
          0%   { transform: scale(1.8); opacity: 1; }
          100% { transform: scale(1);   opacity: 0.7; }
        }
      `;
      document.head.appendChild(style);
    }
  }, []);

  // suppress unused warning — packetTick is only used to force re-renders
  void packetTick;


  const tickerItems = rows
    .filter((r) => r.health && (r.health.status === "warning" || r.health.status === "critical"))
    .map((r) => (
      <span key={r.engine.id} className="flex items-center gap-2">
        <span className={`h-1.5 w-1.5 rounded-full ${r.health!.status === "critical" ? "bg-critical" : "bg-warning"}`} />
        <b className={statusColor(r.health!.status)}>{r.engine.serial_number}</b>
        <span className="text-textMuted">
          {r.health!.status.toUpperCase()} · {r.fault && r.fault.fault_class !== "No Failure" ? r.fault.fault_class : "score " + (r.health!.combined_score ?? "—")}
        </span>
      </span>
    ));
  if (summary) {
    tickerItems.push(
      <span key="avg" className="text-textFaint">
        FLEET AVG HEALTH <b className="text-text">{summary.fleet_health.average_score ?? "—"}</b>
      </span>,
      <span key="missions" className="text-textFaint">
        ACTIVE MISSIONS <b className="text-text">{summary.active_missions}</b>
      </span>,
    );
  }

  return (
    <AppShell
      breadcrumb={["Fleet", "Dashboard"]}
      scrollable={false}
      copilotEngineId={rows[0]?.engine.id}
      copilotEngineSerial={rows[0]?.engine.serial_number}
      headerRight={
        rows.length > 0 ? (
          <div className="flex items-center gap-2">
            {/* Separator */}
            <span className="h-4 w-px bg-border" />
            <span className="text-[10px] font-semibold uppercase tracking-widest text-textFaint">Simulation</span>
            {rows.map((r) => SimButton(r.engine.id, r.engine.serial_number))}
          </div>
        ) : undefined
      }
    >
      {rows.map((r) => (
        <EngineLiveFeed key={r.engine.id} engineId={r.engine.id} />
      ))}
      <LiveTicker items={tickerItems} />
      <div className="scrollbar-thin flex flex-grow flex-col gap-4 overflow-auto p-5">
        {/* KPI row */}
        <div className="flex gap-3.5">
          <div className="flex-1 rounded-sm border border-border bg-surface p-4">
            <div className="text-[11px] font-semibold uppercase tracking-wide text-textFaint">Active Fleet</div>
            <div className="mt-1.5 font-mono text-[28px] font-semibold leading-none">
              <NumberTicker value={summary?.total_engines ?? 0} />
            </div>
            <div className="mt-1 text-[11px] text-textMuted">engines reporting</div>
          </div>
          <div className="flex-1 rounded-sm border border-border bg-surface p-4">
            <div className="text-[11px] font-semibold uppercase tracking-wide text-textFaint">Open Alerts</div>
            <div className="mt-1.5 font-mono text-[28px] font-semibold leading-none text-critical">
              <NumberTicker value={summary?.open_alerts ?? 0} />
            </div>
            <div className="mt-1 text-[11px] text-textMuted">unacknowledged</div>
          </div>
          <div className="flex-1 rounded-sm border border-border bg-surface p-4">
            <div className="text-[11px] font-semibold uppercase tracking-wide text-textFaint">Active Missions</div>
            <div className="mt-1.5 font-mono text-[28px] font-semibold leading-none">
              <NumberTicker value={summary?.active_missions ?? 0} />
            </div>
            <div className="mt-1 text-[11px] text-textMuted">in progress</div>
          </div>
          <div className="flex flex-1 items-center gap-3.5 rounded-sm border border-border bg-surface p-4">
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-wide text-textFaint">Fleet Avg Health</div>
              <div
                className={`mt-1.5 font-mono text-[28px] font-semibold leading-none ${
                  summary && summary.fleet_health.average_score != null
                    ? statusColor(
                        summary.fleet_health.average_score < 20
                          ? "critical"
                          : summary.fleet_health.average_score < 50
                            ? "warning"
                            : "healthy",
                      )
                    : "text-textFaint"
                }`}
              >
                {summary?.fleet_health.average_score ?? "—"}
              </div>
            </div>
            <div className="ml-auto">
              <HealthScoreRing score={summary?.fleet_health.average_score ?? null} size={44} strokeWidth={5} showLabel={false} />
            </div>
          </div>
        </div>

        {/* Fleet table + alerts feed */}
        <div className="flex flex-grow gap-3.5 min-h-0">
          <div className="flex-grow rounded-sm border border-border bg-surface">
            <div className="border-b border-border px-3.5 py-3 text-[11px] font-semibold uppercase tracking-wide text-textFaint">
              Fleet Status
            </div>
            <table className="w-full border-collapse">
              <thead>
                <tr>
                  {["Engine", "Health", "RUL", "Fault", "Bearing", "Aux Risk", "Live Data"].map((h) => (
                    <th key={h} className="border-b border-border px-3 py-2 text-left text-[10px] font-semibold uppercase tracking-wide text-textFaint">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {loading && (
                  <tr>
                    <td colSpan={7} className="px-3 py-6 text-center text-xs text-textFaint">
                      Loading fleet…
                    </td>
                  </tr>
                )}
                {!loading && rows.length === 0 && (
                  <tr>
                    <td colSpan={7} className="px-3 py-6 text-center text-xs text-textFaint">
                      No engines registered yet.
                    </td>
                  </tr>
                )}
                {rows.map((row) => {
                  // Live values (WebSocket) win over the REST snapshot loaded at page open.
                  const live = liveEngines[row.engine.id];
                  const score = live?.healthScore ? live.healthScore.combined_score : (row.health?.combined_score ?? null);
                  const status = live?.healthScore ? statusOfScore(score) : row.health?.status;
                  const factors = live?.healthScore?.contributing_factors ?? row.health?.contributing_factors ?? [];
                  const fault = live?.fault ?? row.fault;
                  const bearing = live?.bearing ?? row.bearing;
                  const rulFactor = factors.find((f) => f.source === "rul");
                  const auxFactor = factors.find((f) => f.source === "aux");
                  const t = live?.telemetry;
                  const ageMs = t ? nowMs - parseBackendTs(t.ts).getTime() : null;
                  const dataState = !t ? "none" : ageMs !== null && ageMs > STALE_AFTER_MS ? "stale" : "live";
                  const hasAnyData = row.hasAnyData || !!live;
                  return (
                    <tr key={row.engine.id} className="hover:bg-surface2" data-testid={`fleet-row-${row.engine.id}`}>
                      <td className="border-b border-border px-3 py-2.5">
                        <Link to={`/engines/${row.engine.id}`} className="font-semibold text-text hover:text-accent hover:no-underline">
                          {row.engine.serial_number}
                        </Link>
                      </td>
                      <td className="border-b border-border px-3 py-2.5">
                        {score !== null && status ? (
                          <div className="flex items-center gap-2">
                            <HealthScoreRing score={score} size={30} strokeWidth={3.4} showLabel={false} />
                            <span className={`font-mono font-semibold ${statusColor(status)}`} data-testid={`fleet-health-${row.engine.id}`}>
                              {score} · {status.toUpperCase()}
                            </span>
                          </div>
                        ) : (
                          <span className="text-xs text-textFaint">— no data</span>
                        )}
                      </td>
                      <td className="border-b border-border px-3 py-2.5 font-mono text-xs">
                        {rulFactor ? `${(rulFactor as { rul_cycles?: number }).rul_cycles ?? "—"} cyc` : hasAnyData ? "nominal" : "—"}
                      </td>
                      <td className="border-b border-border px-3 py-2.5">
                        {fault ? (
                          <span
                            className="whitespace-nowrap rounded-sm border px-2 py-0.5 text-[11px] font-semibold"
                            style={{ color: "#6C8EBF", borderColor: "#6C8EBF", backgroundColor: "rgba(108,142,191,0.14)" }}
                            title={fault.reliable === false ? "Advisory: too few measured input channels — not used in the health score" : undefined}
                          >
                            {fault.fault_class} {fault.fault_class !== "No Failure" ? `${(fault.confidence * 100).toFixed(0)}%` : ""}
                            {fault.reliable === false ? " · advisory" : ""}
                          </span>
                        ) : (
                          <span className="text-xs text-textFaint">—</span>
                        )}
                      </td>
                      <td className="border-b border-border px-3 py-2.5">
                        {bearing ? (
                          <span
                            className="rounded-sm border px-2 py-0.5 text-[11px] font-semibold"
                            style={{ color: "#4FA8B5", borderColor: "#4FA8B5", backgroundColor: "rgba(79,168,181,0.14)" }}
                          >
                            {bearing.class_label}
                          </span>
                        ) : (
                          <span className="text-xs text-textFaint">—</span>
                        )}
                      </td>
                      <td className="border-b border-border px-3 py-2.5 font-mono text-xs">
                        {live?.aux
                          ? `${live.aux.failure_probability_pct.toFixed(0)}%`
                          : auxFactor
                            ? `${(auxFactor as { failure_probability_pct?: number }).failure_probability_pct ?? "—"}%`
                            : hasAnyData
                              ? "low"
                              : "—"}
                      </td>
                      <td className="border-b border-border px-3 py-2.5" data-testid={`fleet-live-${row.engine.id}`}>
                        {/* ── Live data block ────────────────────────────────────────── */}
                        <div className="flex flex-col gap-0.5">
                          {t ? (
                            <>
                              <div className="flex items-center gap-2">
                                <span
                                  className={`rounded-sm border px-1.5 py-0.5 text-[9px] font-bold tracking-wider ${
                                    dataState === "live" ? "border-healthy text-healthy" : "border-warning text-warning"
                                  }`}
                                  data-testid={`fleet-chip-${row.engine.id}`}
                                >
                                  {dataState === "live" ? "LIVE" : "STALE"}
                                </span>
                                <span className="font-mono text-[10px] text-textMuted">
                                  {dataState === "live" ? `${fmtAgeShort(ageMs ?? 0)} ago` : `last ${fmtAgeShort(ageMs ?? 0)} ago`}
                                </span>
                                {/* Packet counter while sim is running */}
                                {simState[row.engine.id] === "running" && (
                                  <PacketCounter engineId={row.engine.id} count={packetCount.current[row.engine.id] ?? 0} />
                                )}
                              </div>
                              <div className="font-mono text-[11px] text-textMuted">
                                RPM {t.rpm.toFixed(0)} · CHT {t.cht.toFixed(0)}° · EGT {t.egt.toFixed(0)}°
                              </div>
                            </>
                          ) : row.health?.last_updated ? (
                            <span className="font-mono text-xs text-textMuted">connecting… last score {fmtTime(row.health.last_updated)}</span>
                          ) : hasAnyData ? (
                            <span className="font-mono text-xs text-textMuted">—</span>
                          ) : (
                            <span className="font-mono text-xs text-textMuted">no telemetry</span>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Alerts feed */}
          <div className="w-[336px] flex-shrink-0 rounded-sm border border-border bg-surface">
            <div className="flex items-center border-b border-border px-3.5 py-3">
              <div className="text-[11px] font-semibold uppercase tracking-wide text-textFaint">Recent Alerts</div>
              <Link to="/alerts" className="ml-auto text-[11px]">
                View all →
              </Link>
            </div>
            {recentAlerts.length === 0 && <div className="p-4 text-xs text-textFaint">No open alerts.</div>}
            {recentAlerts.map((alert) => (
              <div
                key={alert.id}
                className="flex flex-col gap-1 border-b border-border px-3.5 py-2.5"
                style={{ borderLeft: `3px solid ${alert.severity === "critical" ? "#E8564A" : "#C9962F"}` }}
              >
                <div className="flex items-baseline justify-between">
                  <span className={`text-[11px] font-bold ${alert.severity === "critical" ? "text-forcedZero" : "text-warning"}`}>
                    {alert.severity.toUpperCase()}
                  </span>
                  <span className="text-[10px] text-textFaint">{fmtTime(alert.created_at)}</span>
                </div>
                <div className="text-xs">{alert.message}</div>
                <button
                  onClick={() => acknowledge(alert.id)}
                  className="self-start rounded-sm border border-borderStrong px-2.5 py-0.5 text-[10px] font-semibold hover:border-accent hover:text-accent"
                >
                  Acknowledge
                </button>
              </div>
            ))}
          </div>
        </div>
      </div>
    </AppShell>
  );
}
