import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import { missionsApi, uavAssetsApi } from "@/services/resources";
import type { Mission, UAVAsset } from "@/types";
import { fmtDateTime } from "@/lib/utils";

// "active" is what every mission actually created by this app uses for
// "currently underway" (missions.py's own conflict check agrees) — kept
// alongside "in_progress" for display only in case older data used it.
const STATUS_LABEL: Record<string, string> = {
  scheduled: "SCHEDULED",
  active: "ACTIVE",
  in_progress: "IN PROGRESS",
  completed: "COMPLETED",
  cancelled: "CANCELLED",
};

export function Missions() {
  const navigate = useNavigate();
  const [missions, setMissions] = useState<Mission[]>([]);
  const [assets, setAssets] = useState<UAVAsset[]>([]);
  const [filter, setFilter] = useState<string>("all");
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ uav_asset_id: "", mission_type: "", start_time: "" });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([missionsApi.list(), uavAssetsApi.list()]).then(([m, a]) => {
      setMissions(m);
      setAssets(a);
    });
  }, []);

  function assetTail(id: string) {
    return assets.find((a) => a.id === id)?.tail_number ?? id.slice(0, 8);
  }

  const visible = filter === "all" ? missions : missions.filter((m) => m.status === filter);

  async function createMission(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!form.uav_asset_id || !form.mission_type || !form.start_time) return;
    setSubmitting(true);
    try {
      const created = await missionsApi.create({
        uav_asset_id: form.uav_asset_id,
        mission_type: form.mission_type,
        start_time: new Date(form.start_time).toISOString(),
      });
      setMissions((prev) => [created, ...prev]);
      setShowForm(false);
      setForm({ uav_asset_id: "", mission_type: "", start_time: "" });
    } catch {
      setError("Could not create mission — check the start time is in the future.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AppShell breadcrumb={["Fleet", "Missions"]}>
      <div className="flex flex-col gap-4 p-5">
        <div className="flex items-center gap-2.5">
          <div className="text-[15px] font-semibold">Missions</div>
          <div className="flex-grow" />
          {["all", "scheduled", "active", "completed"].map((s) => (
            <button
              key={s}
              onClick={() => setFilter(s)}
              className={`rounded-full border px-2.5 py-0.5 text-[11px] font-semibold ${
                filter === s ? "border-accent text-accent" : "border-borderStrong text-textMuted"
              }`}
            >
              {s === "all" ? "All" : STATUS_LABEL[s]}
            </button>
          ))}
          <button
            onClick={() => setShowForm((v) => !v)}
            className="ml-2 rounded-sm bg-accent px-3 py-1.5 text-xs font-semibold text-bg"
          >
            + New Mission
          </button>
        </div>

        {showForm && (
          <form onSubmit={createMission} className="flex items-end gap-2.5 rounded-sm border border-border bg-surface p-3.5">
            <div className="flex flex-col gap-1">
              <label className="text-[10px] font-semibold uppercase text-textFaint">UAV Asset</label>
              <select
                value={form.uav_asset_id}
                onChange={(e) => setForm((f) => ({ ...f, uav_asset_id: e.target.value }))}
                className="rounded-sm border border-borderStrong bg-surface2 px-2 py-1.5 text-xs"
              >
                <option value="">Select…</option>
                {assets.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.tail_number}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-[10px] font-semibold uppercase text-textFaint">Mission Type</label>
              <input
                value={form.mission_type}
                onChange={(e) => setForm((f) => ({ ...f, mission_type: e.target.value }))}
                placeholder="Endurance Patrol"
                className="rounded-sm border border-borderStrong bg-surface2 px-2 py-1.5 text-xs"
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-[10px] font-semibold uppercase text-textFaint">Start Time</label>
              <input
                type="datetime-local"
                value={form.start_time}
                onChange={(e) => setForm((f) => ({ ...f, start_time: e.target.value }))}
                className="rounded-sm border border-borderStrong bg-surface2 px-2 py-1.5 text-xs"
              />
            </div>
            <button type="submit" disabled={submitting} className="rounded-sm bg-accent px-3 py-1.5 text-xs font-semibold text-bg">
              Create
            </button>
            {error && <span className="text-xs text-critical">{error}</span>}
          </form>
        )}

        <div className="rounded-sm border border-border bg-surface">
          <table className="w-full border-collapse">
            <thead>
              <tr>
                {["UAV Asset", "Type", "Status", "Start"].map((h) => (
                  <th key={h} className="border-b border-border px-3 py-2 text-left text-[10px] font-semibold uppercase tracking-wide text-textFaint">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {visible.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-3 py-6 text-center text-xs text-textFaint">
                    No missions.
                  </td>
                </tr>
              )}
              {visible.map((m) => (
                <tr
                  key={m.id}
                  onClick={() => navigate(`/missions/${m.id}`)}
                  className="cursor-pointer hover:bg-surface2"
                >
                  <td className="border-b border-border px-3 py-2.5 font-mono text-xs">{assetTail(m.uav_asset_id)}</td>
                  <td className="border-b border-border px-3 py-2.5 text-xs">{m.mission_type}</td>
                  <td className="border-b border-border px-3 py-2.5">
                    <span
                      className={`rounded-sm border px-2 py-0.5 text-[11px] font-semibold ${
                        m.status === "active" || m.status === "in_progress"
                          ? "border-healthy text-healthy"
                          : "border-borderStrong text-textMuted"
                      }`}
                    >
                      {STATUS_LABEL[m.status] ?? m.status.toUpperCase()}
                    </span>
                  </td>
                  <td className="border-b border-border px-3 py-2.5 font-mono text-xs text-textMuted">
                    {fmtDateTime(m.start_time)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </AppShell>
  );
}
