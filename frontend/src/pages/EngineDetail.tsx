import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import { HealthScoreRing } from "@/components/HealthScoreRing";
import { RulTrendChart } from "@/components/RulTrendChart";
import { FaultAlertBanner } from "@/components/FaultAlertBanner";
import { BearingHealthVisualizer } from "@/components/BearingHealthVisualizer";
import { AuxRadarChart } from "@/components/AuxRadarChart";
import { PhysicsConsistencyPanel } from "@/components/PhysicsConsistencyPanel";
import { useEngineWebSocket } from "@/hooks/useEngineWebSocket";
import { useTelemetryStore } from "@/store/telemetryStore";
import { alertsApi, enginesApi } from "@/services/resources";
import type { Engine, MaintenanceLog, RulPrediction, RulStatus } from "@/types";
import { fmtAge, fmtDateTime, parseBackendTs } from "@/lib/utils";

// Mirrors backend HEALTH_SCORE_STALE_AFTER_SECONDS (default 300 s).
const STALE_SCORE_MS = 5 * 60_000;

const INSTRUMENTS: { key: "rpm" | "cht" | "egt" | "oil_pressure" | "oil_temp" | "fuel_flow"; label: string; unit: string }[] = [
  { key: "rpm", label: "RPM", unit: "" },
  { key: "cht", label: "CHT", unit: "°C" },
  { key: "egt", label: "EGT", unit: "°C" },
  { key: "oil_pressure", label: "Oil Press", unit: "psi" },
  { key: "oil_temp", label: "Oil Temp", unit: "°C" },
  { key: "fuel_flow", label: "Fuel Flow", unit: "gph" },
];

export function EngineDetail() {
  const { engineId = "" } = useParams();
  useEngineWebSocket(engineId);

  const live = useTelemetryStore((s) => s.engines[engineId]);
  const [engine, setEngine] = useState<Engine | null>(null);
  const [rulHistory, setRulHistory] = useState<RulPrediction[]>([]);
  const [rulStatus, setRulStatus] = useState<RulStatus | null>(null);
  const [logs, setLogs] = useState<MaintenanceLog[]>([]);
  const [currentScore, setCurrentScore] = useState<{ score: number | null; status: string; primaryConcern?: string | null } | null>(null);
  // Re-evaluated periodically so a score goes STALE on screen even when nothing else re-renders the page.
  const [nowMs, setNowMs] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNowMs(Date.now()), 30_000);
    return () => clearInterval(id);
  }, []);
  const [logForm, setLogForm] = useState({ action_taken: "", notes: "" });
  const [logSubmitting, setLogSubmitting] = useState(false);

  const setTelemetry = useTelemetryStore((s) => s.setTelemetry);
  const setFault = useTelemetryStore((s) => s.setFault);
  const setBearing = useTelemetryStore((s) => s.setBearing);
  const setAux = useTelemetryStore((s) => s.setAux);
  const setHealthScore = useTelemetryStore((s) => s.setHealthScore);
  const setPhysicsConsistency = useTelemetryStore((s) => s.setPhysicsConsistency);

  useEffect(() => {
    if (!engineId) return;
    let cancelled = false;

    async function load() {
      const [engineRes, healthRes, telemetryRes, rulRes, rulStatusRes, faultRes, bearingRes, auxRes, logsRes, physicsRes] = await Promise.allSettled([
        enginesApi.get(engineId),
        enginesApi.healthScore(engineId, 30),
        enginesApi.telemetryLatest(engineId),
        enginesApi.rul(engineId, 30),
        enginesApi.rulStatus(engineId),
        enginesApi.faultsLatest(engineId),
        enginesApi.bearingHealth(engineId),
        enginesApi.auxLatest(engineId),
        enginesApi.maintenanceLogs(engineId),
        enginesApi.physicsConsistency(engineId),
      ]);
      if (cancelled) return;

      if (engineRes.status === "fulfilled") setEngine(engineRes.value);
      if (healthRes.status === "fulfilled") {
        setCurrentScore({
          score: healthRes.value.combined_score,
          status: healthRes.value.status,
          primaryConcern: healthRes.value.primary_concern,
        });
        setHealthScore(engineId, {
          combined_score: healthRes.value.combined_score,
          contributing_factors: healthRes.value.contributing_factors,
          primary_concern: healthRes.value.primary_concern,
          ts: healthRes.value.last_updated ?? new Date().toISOString(),
        });
      }
      if (telemetryRes.status === "fulfilled") setTelemetry(engineId, telemetryRes.value);
      if (rulRes.status === "fulfilled") setRulHistory(rulRes.value);
      if (rulStatusRes.status === "fulfilled") setRulStatus(rulStatusRes.value);
      if (faultRes.status === "fulfilled") setFault(engineId, faultRes.value);
      if (bearingRes.status === "fulfilled") setBearing(engineId, bearingRes.value);
      if (auxRes.status === "fulfilled") setAux(engineId, auxRes.value);
      if (logsRes.status === "fulfilled") setLogs(logsRes.value);
      if (physicsRes.status === "fulfilled") setPhysicsConsistency(engineId, physicsRes.value.parameters);
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [engineId, setTelemetry, setFault, setBearing, setAux, setHealthScore, setPhysicsConsistency]);

  // Prepend live RUL pushes onto the history array used by the trend chart.
  useEffect(() => {
    if (live?.rul) {
      setRulHistory((prev) => (prev[0]?.ts === live.rul!.ts ? prev : [live.rul!, ...prev].slice(0, 30)));
    }
  }, [live?.rul]);

  // No `?? 100` fallback (Accuracy-First Phase 2) — `null` means "no
  // health score exists yet," and HealthScoreRing renders that
  // honestly (a dashed ring + "NO DATA") instead of a fabricated value.
  const displayScore = live?.healthScore?.combined_score ?? currentScore?.score ?? null;
  const factors = live?.healthScore?.contributing_factors ?? [];
  const primaryConcern = live?.healthScore?.primary_concern ?? currentScore?.primaryConcern ?? null;
  // Both the REST load and WebSocket pushes land in the same store slice, each
  // stamped with the time of the score it carries — so freshness is judged from
  // that stamp's age (a score older than STALE_SCORE_MS means the engine has
  // stopped streaming), not from where the score came from.
  const scoreTs = live?.healthScore?.ts;
  const scoreAgeMs = scoreTs ? nowMs - parseBackendTs(scoreTs).getTime() : null;
  const scoreStale = scoreAgeMs !== null && scoreAgeMs > STALE_SCORE_MS && displayScore !== null;
  const missingSources = live?.healthScore?.missing_sources ?? [];
  // Fault result present but advisory-only (model fed mostly placeholder channels): not part of the score.
  const faultAdvisory = live?.fault?.reliable === false;
  const faultAgeMs = live?.fault?.ts ? nowMs - parseBackendTs(live.fault.ts).getTime() : null;
  const SOURCE_LABEL: Record<string, string> = { rul: "RUL", fault: "Fault", bearing: "Bearing", aux: "Auxiliary" };

  async function acknowledgeFaultAlert() {
    try {
      const alerts = await alertsApi.list({ engine_id: engineId, is_acknowledged: false });
      if (alerts.length > 0) await alertsApi.acknowledge(alerts[0].id);
    } catch {
      /* best-effort — banner stays visible either way until the fault clears */
    }
  }

  async function submitMaintenanceLog(e: React.FormEvent) {
    e.preventDefault();
    if (!logForm.action_taken.trim()) return;
    setLogSubmitting(true);
    try {
      const created = await enginesApi.createMaintenanceLog(engineId, logForm.action_taken, logForm.notes || undefined);
      setLogs((prev) => [created, ...prev]);
      setLogForm({ action_taken: "", notes: "" });
    } finally {
      setLogSubmitting(false);
    }
  }

  const card = "min-w-0 rounded-sm border border-border bg-surface p-4";
  const cardTitle = "mb-2.5 text-[11px] font-semibold uppercase tracking-wide text-textFaint";

  return (
    <AppShell
      breadcrumb={["Fleet", "Dashboard", engine?.serial_number ?? engineId.slice(0, 8)]}
      copilotEngineId={engineId}
      copilotEngineSerial={engine?.serial_number}
      copilotExpanded
    >
      <div className="flex min-w-0 flex-col gap-3.5 p-5">
        <FaultAlertBanner fault={live?.fault} onAcknowledge={acknowledgeFaultAlert} ageMs={faultAgeMs} />

        {/* Header */}
        <div className="flex min-w-0 flex-wrap items-center gap-x-6 gap-y-3 rounded-sm border border-border bg-surface p-4">
          <div className="min-w-[140px]">
            <div className="text-[17px] font-bold">{engine?.serial_number ?? "…"}</div>
            <div className="mt-0.5 text-[11px] text-textMuted">{engine?.status}</div>
          </div>
          <HealthScoreRing score={displayScore} forcedZero={factors.some((f) => f.forced_zero)} size={110} strokeWidth={9} />
          <div className="flex min-w-[220px] flex-1 flex-col gap-1.5">
            {primaryConcern && (
              <div className="text-xs font-semibold text-textMuted">
                <span className="text-textFaint">Primary concern:</span> {primaryConcern}
              </div>
            )}
            <div className="flex flex-wrap gap-2">
              {factors.length === 0 && <span className="text-xs text-textFaint">No active penalties — nominal.</span>}
              {factors.map((f, i) => (
                <span
                  key={i}
                  className="rounded-sm border px-2.5 py-1 text-[11px] font-semibold"
                  style={{
                    color: f.source === "rul" ? "#8B7FC7" : f.source === "fault" ? "#C64F44" : f.source === "bearing" ? "#4FA8B5" : "#B08A5A",
                    borderColor: f.source === "rul" ? "#8B7FC7" : f.source === "fault" ? "#C64F44" : f.source === "bearing" ? "#4FA8B5" : "#B08A5A",
                  }}
                  title={f.correlated_with ? `Double-counting mitigated with ${f.correlated_with}` : undefined}
                >
                  {f.source.toUpperCase()} {f.forced_zero ? "forced-zero" : `−${f.penalty ?? 0}`}
                  {f.correlated_with ? " *" : ""}
                </span>
              ))}
            </div>
            {scoreStale && (
              <div className="w-fit rounded-sm border border-warning bg-warningBg px-2.5 py-1 text-[11px] font-semibold text-warning" data-testid="score-stale">
                STALE · last score {scoreAgeMs !== null ? fmtAge(scoreAgeMs) : ""} ago — engine not streaming
              </div>
            )}
            {faultAdvisory && (
              <div className="w-fit rounded-sm border border-borderStrong bg-surface2 px-2.5 py-1 text-[11px] text-textMuted" data-testid="score-fault-advisory">
                Fault model is advisory here — not included in this score (too few measured input channels)
              </div>
            )}
            {missingSources.length > 0 && (
              <div className="w-fit rounded-sm border border-borderStrong bg-surface2 px-2.5 py-1 text-[11px] text-textMuted" data-testid="score-partial">
                Partial assessment — no fresh output from {missingSources.map((m) => SOURCE_LABEL[m] ?? m).join(", ")} yet
              </div>
            )}
          </div>
          <Link
            to={`/engines/${engineId}/simulation`}
            className="flex-shrink-0 rounded-sm border border-borderStrong bg-surface2 px-3 py-1.5 text-xs font-semibold hover:border-accent hover:text-accent hover:no-underline"
          >
            Replay / What-If →
          </Link>
        </div>

        {/* Telemetry strip */}
        <div className="grid grid-cols-2 gap-px overflow-hidden rounded-sm border border-border bg-border sm:grid-cols-3 xl:grid-cols-6">
          {INSTRUMENTS.map(({ key, label, unit }) => (
            <div key={key} className="min-w-0 bg-surface p-3">
              <div className="text-[10px] font-semibold uppercase tracking-wide text-textFaint">{label}</div>
              <div className="truncate font-mono text-xl font-semibold">
                {live?.telemetry ? live.telemetry[key].toFixed(0) : "—"}
                {unit && <span className="ml-0.5 text-[10px] text-textFaint">{unit}</span>}
              </div>
            </div>
          ))}
        </div>

        {/* RUL + Bearing */}
        <div className="grid grid-cols-1 gap-3.5 xl:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
          <div className={card}>
            <div className={cardTitle}>RUL Trend</div>
            <RulTrendChart
              data={rulHistory}
              collecting={
                rulStatus && rulStatus.status === "INSUFFICIENT_DATA"
                  ? { samplesCollected: rulStatus.samples_collected, samplesRequired: rulStatus.samples_required }
                  : null
              }
            />
          </div>
          <div className={card}>
            <div className={cardTitle}>Bearing / Vibration Health</div>
            <BearingHealthVisualizer reading={live?.bearing} />
          </div>
        </div>

        {/* Aux + Physics */}
        <div className="grid grid-cols-1 gap-3.5 lg:grid-cols-[minmax(0,280px)_minmax(0,1fr)]">
          <div className={card}>
            <div className={cardTitle}>Auxiliary Failure Modes</div>
            <div className="flex justify-center">
              <AuxRadarChart data={live?.aux} />
            </div>
          </div>
          <div className={card}>
            <div className={cardTitle}>Physics ↔ AI Consistency</div>
            <PhysicsConsistencyPanel parameters={live?.physicsConsistency} />
          </div>
        </div>

        {/* Maintenance */}
        <div className="min-w-0 rounded-sm border border-border bg-surface">
          <div className="border-b border-border px-4 py-3 text-[11px] font-semibold uppercase tracking-wide text-textFaint">
            Maintenance Log
          </div>
          <form onSubmit={submitMaintenanceLog} className="flex flex-wrap gap-2 border-b border-border p-3">
            <input
              value={logForm.action_taken}
              onChange={(e) => setLogForm((f) => ({ ...f, action_taken: e.target.value }))}
              placeholder="Action taken…"
              maxLength={120}
              className="min-w-[180px] flex-1 rounded-sm border border-borderStrong bg-surface2 px-2.5 py-1.5 text-xs outline-none focus:border-accent"
            />
            <input
              value={logForm.notes}
              onChange={(e) => setLogForm((f) => ({ ...f, notes: e.target.value }))}
              placeholder="Notes (optional)…"
              className="min-w-[180px] flex-1 rounded-sm border border-borderStrong bg-surface2 px-2.5 py-1.5 text-xs outline-none focus:border-accent"
            />
            <button type="submit" disabled={logSubmitting} className="rounded-sm bg-accent px-4 py-1.5 text-xs font-semibold text-bg disabled:opacity-50">
              Log
            </button>
          </form>
          <table className="w-full table-fixed border-collapse">
            <thead>
              <tr>
                {[
                  ["Date", "w-[26%]"],
                  ["Action Taken", "w-[40%]"],
                  ["Notes", "w-[34%]"],
                ].map(([h, w]) => (
                  <th key={h} className={`${w} border-b border-border px-3 py-2 text-left text-[10px] font-semibold uppercase tracking-wide text-textFaint`}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {logs.length === 0 && (
                <tr>
                  <td colSpan={3} className="px-3 py-4 text-center text-xs text-textFaint">
                    No maintenance logged yet.
                  </td>
                </tr>
              )}
              {logs.map((log) => (
                <tr key={log.id}>
                  <td className="border-b border-border px-3 py-2 font-mono text-xs text-textMuted">{fmtDateTime(log.logged_at)}</td>
                  <td className="break-words border-b border-border px-3 py-2 text-xs">{log.action_taken}</td>
                  <td className="break-words border-b border-border px-3 py-2 text-xs text-textMuted">{log.notes ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </AppShell>
  );
}
