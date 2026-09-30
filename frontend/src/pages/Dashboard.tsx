import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import { HealthScoreRing } from "@/components/HealthScoreRing";
import { NumberTicker } from "@/components/NumberTicker";
import { LiveTicker } from "@/components/LiveTicker";
import { alertsApi, dashboardApi, enginesApi } from "@/services/resources";
import type { Alert, BearingHealthReading, DashboardSummary, Engine, FaultPrediction, HealthScoreResponse } from "@/types";
import { fmtTime } from "@/lib/utils";

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
      }
    }
    load().catch(() => setLoading(false));
    return () => {
      cancelled = true;
    };
  }, []);

  async function acknowledge(alertId: string) {
    await alertsApi.acknowledge(alertId);
    setRecentAlerts((prev) => prev.filter((a) => a.id !== alertId));
  }

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
    <AppShell breadcrumb={["Fleet", "Dashboard"]} scrollable={false}>
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
                  {["Engine", "Health", "RUL", "Fault", "Bearing", "Aux Risk", "Last Telemetry"].map((h) => (
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
                  const rulFactor = row.health?.contributing_factors.find((f) => f.source === "rul");
                  const auxFactor = row.health?.contributing_factors.find((f) => f.source === "aux");
                  return (
                    <tr key={row.engine.id} className="hover:bg-surface2">
                      <td className="border-b border-border px-3 py-2.5">
                        <Link to={`/engines/${row.engine.id}`} className="font-semibold text-text hover:text-accent hover:no-underline">
                          {row.engine.serial_number}
                        </Link>
                      </td>
                      <td className="border-b border-border px-3 py-2.5">
                        {row.health && row.health.combined_score !== null ? (
                          <div className="flex items-center gap-2">
                            <HealthScoreRing score={row.health.combined_score} size={30} strokeWidth={3.4} showLabel={false} />
                            <span className={`font-mono font-semibold ${statusColor(row.health.status)}`}>
                              {row.health.combined_score} · {row.health.status.toUpperCase()}
                            </span>
                          </div>
                        ) : (
                          <span className="text-xs text-textFaint">— no data</span>
                        )}
                      </td>
                      <td className="border-b border-border px-3 py-2.5 font-mono text-xs">
                        {rulFactor ? `${(rulFactor as { rul_cycles?: number }).rul_cycles ?? "—"} cyc` : row.hasAnyData ? "nominal" : "—"}
                      </td>
                      <td className="border-b border-border px-3 py-2.5">
                        {row.fault ? (
                          <span
                            className="whitespace-nowrap rounded-sm border px-2 py-0.5 text-[11px] font-semibold"
                            style={{ color: "#6C8EBF", borderColor: "#6C8EBF", backgroundColor: "rgba(108,142,191,0.14)" }}
                          >
                            {row.fault.fault_class} {row.fault.fault_class !== "No Failure" ? `${(row.fault.confidence * 100).toFixed(0)}%` : ""}
                          </span>
                        ) : (
                          <span className="text-xs text-textFaint">—</span>
                        )}
                      </td>
                      <td className="border-b border-border px-3 py-2.5">
                        {row.bearing ? (
                          <span
                            className="rounded-sm border px-2 py-0.5 text-[11px] font-semibold"
                            style={{ color: "#4FA8B5", borderColor: "#4FA8B5", backgroundColor: "rgba(79,168,181,0.14)" }}
                          >
                            {row.bearing.class_label}
                          </span>
                        ) : (
                          <span className="text-xs text-textFaint">—</span>
                        )}
                      </td>
                      <td className="border-b border-border px-3 py-2.5 font-mono text-xs">
                        {auxFactor ? `${(auxFactor as { failure_probability_pct?: number }).failure_probability_pct ?? "—"}%` : row.hasAnyData ? "low" : "—"}
                      </td>
                      <td className="border-b border-border px-3 py-2.5 font-mono text-xs text-textMuted">
                        {row.health?.last_updated ? fmtTime(row.health.last_updated) : row.hasAnyData ? "—" : "no telemetry"}
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
