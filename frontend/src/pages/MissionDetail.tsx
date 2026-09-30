import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import { enginesApi, missionsApi, uavAssetsApi } from "@/services/resources";
import type { Engine, MissionDetail as MissionDetailType, UAVAsset } from "@/types";
import { fmtDateTime, fmtTime } from "@/lib/utils";

type NumericSummaryKey = "rpm_avg" | "rpm_max" | "cht_avg" | "cht_max" | "egt_avg" | "egt_max" | "oil_pressure_min" | "fuel_flow_avg";

const STAT_ROWS: { key: NumericSummaryKey; label: string; unit: string }[] = [
  { key: "rpm_avg", label: "RPM (avg)", unit: "" },
  { key: "rpm_max", label: "RPM (max)", unit: "" },
  { key: "cht_avg", label: "CHT (avg)", unit: "°C" },
  { key: "cht_max", label: "CHT (max)", unit: "°C" },
  { key: "egt_avg", label: "EGT (avg)", unit: "°C" },
  { key: "egt_max", label: "EGT (max)", unit: "°C" },
  { key: "oil_pressure_min", label: "Oil Pressure (min)", unit: "psi" },
  { key: "fuel_flow_avg", label: "Fuel Flow (avg)", unit: "gph" },
];

export function MissionDetail() {
  const { missionId = "" } = useParams();
  const [mission, setMission] = useState<MissionDetailType | null>(null);
  const [asset, setAsset] = useState<UAVAsset | null>(null);
  const [linkedEngine, setLinkedEngine] = useState<Engine | null>(null);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    if (!missionId) return;
    let cancelled = false;

    async function load() {
      try {
        const m = await missionsApi.get(missionId);
        if (cancelled) return;
        setMission(m);

        const [assets, engines] = await Promise.all([uavAssetsApi.list(), enginesApi.list()]);
        if (cancelled) return;
        setAsset(assets.find((a) => a.id === m.uav_asset_id) ?? null);
        setLinkedEngine(engines.find((e) => e.uav_asset_id === m.uav_asset_id) ?? null);
      } catch {
        if (!cancelled) setNotFound(true);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [missionId]);

  if (notFound) {
    return (
      <AppShell breadcrumb={["Fleet", "Missions", "Not found"]}>
        <div className="p-5 text-xs text-textFaint">Mission not found.</div>
      </AppShell>
    );
  }

  const summary = mission?.telemetry_summary ?? null;

  return (
    <AppShell breadcrumb={["Fleet", "Missions", asset?.tail_number ?? missionId.slice(0, 8)]}>
      <div className="flex flex-col gap-4 p-5">
        <div className="rounded-sm border border-border bg-surface p-4.5">
          <div className="flex items-start justify-between">
            <div>
              <div className="text-[15px] font-semibold">{asset?.tail_number ?? "…"}</div>
              <div className="mt-0.5 text-[11px] text-textMuted">{mission?.mission_type}</div>
            </div>
            {linkedEngine ? (
              <Link
                to={`/engines/${linkedEngine.id}/simulation?mission=${missionId}`}
                className="rounded-sm border border-borderStrong bg-surface2 px-3 py-1.5 text-xs font-semibold hover:border-accent hover:text-accent hover:no-underline"
              >
                Replay this mission →
              </Link>
            ) : (
              <span className="text-[11px] text-textFaint">No engine linked to this asset — replay unavailable.</span>
            )}
          </div>

          <div className="mt-3 flex flex-wrap gap-x-6 gap-y-1.5 text-[11px] text-textMuted">
            <span>
              Status: <span className="font-semibold text-text">{mission?.status.toUpperCase()}</span>
            </span>
            <span>
              Start: <span className="font-mono text-text">{mission ? fmtDateTime(mission.start_time) : "—"}</span>
            </span>
            <span>
              End:{" "}
              <span className="font-mono text-text">
                {mission?.end_time ? fmtDateTime(mission.end_time) : "—"}
              </span>
            </span>
          </div>

          {mission?.environmental_profile && Object.keys(mission.environmental_profile).length > 0 && (
            <div className="mt-3 border-t border-border pt-3">
              <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-textFaint">
                Environmental Profile
              </div>
              <div className="flex flex-wrap gap-x-5 gap-y-1 font-mono text-[11px] text-textMuted">
                {Object.entries(mission.environmental_profile).map(([k, v]) => (
                  <span key={k}>
                    {k}: <span className="text-text">{String(v)}</span>
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="rounded-sm border border-border bg-surface p-4.5">
          <div className="mb-3 text-[11px] font-semibold uppercase tracking-wide text-textFaint">Telemetry Summary</div>
          {!summary ? (
            <div className="text-xs text-textFaint">No telemetry recorded for this mission yet.</div>
          ) : (
            <>
              <div className="mb-3 text-[11px] text-textMuted">
                {summary.reading_count} reading(s)
                {summary.first_ts && summary.last_ts && (
                  <>
                    {" "}
                    · {fmtTime(summary.first_ts)} – {fmtTime(summary.last_ts)}
                  </>
                )}
              </div>
              <div className="grid grid-cols-4 gap-3.5">
                {STAT_ROWS.map(({ key, label, unit }) => {
                  const value = summary[key];
                  return (
                    <div key={key}>
                      <div className="text-[10px] font-semibold uppercase tracking-wide text-textFaint">{label}</div>
                      <div className="font-mono text-lg font-semibold">
                        {value == null ? "—" : value.toFixed(1)}
                        {value != null && unit && <span className="ml-0.5 text-[10px] text-textFaint">{unit}</span>}
                      </div>
                    </div>
                  );
                })}
              </div>
            </>
          )}
        </div>
      </div>
    </AppShell>
  );
}
