import { useEffect, useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { alertsApi } from "@/services/resources";
import type { Alert, AlertSeverity } from "@/types";
import { fmtDateTime, fmtTime } from "@/lib/utils";

type Filter = "all" | AlertSeverity | "acknowledged";

export function Alerts() {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [filter, setFilter] = useState<Filter>("all");
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    const params =
      filter === "acknowledged"
        ? { is_acknowledged: true }
        : filter === "warning" || filter === "critical"
          ? { severity: filter as AlertSeverity, is_acknowledged: false }
          : {};
    const data = await alertsApi.list(params);
    setAlerts(data);
    setLoading(false);
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filter]);

  async function acknowledge(id: string) {
    await alertsApi.acknowledge(id);
    setAlerts((prev) =>
      prev.map((a) => (a.id === id ? { ...a, is_acknowledged: true, acknowledged_at: new Date().toISOString() } : a)),
    );
  }

  return (
    <AppShell breadcrumb={["Fleet", "Alerts"]}>
      <div className="flex flex-col gap-4 p-5">
        <div className="flex items-center gap-2.5">
          <div className="text-[15px] font-semibold">Alerts</div>
          <div className="flex-grow" />
          {(["all", "critical", "warning", "acknowledged"] as Filter[]).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`rounded-full border px-2.5 py-0.5 text-[11px] font-semibold capitalize ${
                filter === f ? "border-accent text-accent" : "border-borderStrong text-textMuted"
              }`}
            >
              {f}
            </button>
          ))}
        </div>

        <div className="rounded-sm border border-border bg-surface">
          {loading && <div className="p-6 text-center text-xs text-textFaint">Loading alerts…</div>}
          {!loading && alerts.length === 0 && <div className="p-6 text-center text-xs text-textFaint">No alerts.</div>}
          {alerts.map((alert) => (
            <div
              key={alert.id}
              className={`flex gap-3.5 border-b border-border px-4 py-3.5 last:border-b-0 ${alert.is_acknowledged ? "opacity-55" : ""}`}
              style={{ borderLeft: `3px solid ${alert.is_acknowledged ? "#333D4A" : alert.severity === "critical" ? "#E8564A" : "#C9962F"}` }}
            >
              <div className="w-[90px] flex-shrink-0">
                <span className={`text-[11px] font-bold ${alert.is_acknowledged ? "text-textMuted" : alert.severity === "critical" ? "text-forcedZero" : "text-warning"}`}>
                  {alert.severity.toUpperCase()}
                </span>
              </div>
              <div className="flex-grow">
                <div className="mb-1 flex items-center gap-2">
                  <span className="text-sm font-semibold">{alert.engine_id.slice(0, 8)}</span>
                  <span
                    className="rounded-sm border px-1.5 py-0.5 text-[10px] font-semibold"
                    style={{ color: "#5B8FD6", borderColor: "#5B8FD6" }}
                  >
                    {alert.source}
                  </span>
                </div>
                <div className="text-xs leading-relaxed">{alert.message}</div>
                {alert.is_acknowledged && alert.acknowledged_at && (
                  <div className="mt-1 text-[10px] text-textFaint">Acknowledged at {fmtDateTime(alert.acknowledged_at)}</div>
                )}
              </div>
              <div className="w-[120px] flex-shrink-0 text-right">
                <div className="mb-1.5 font-mono text-[11px] text-textFaint">{fmtTime(alert.created_at)}</div>
                {!alert.is_acknowledged && (
                  <button
                    onClick={() => acknowledge(alert.id)}
                    className="rounded-sm border border-borderStrong px-2.5 py-1 text-[10px] font-semibold hover:border-accent hover:text-accent"
                  >
                    Acknowledge
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </AppShell>
  );
}
