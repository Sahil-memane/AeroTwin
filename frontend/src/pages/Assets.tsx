import { useEffect, useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { enginesApi, uavAssetsApi } from "@/services/resources";
import type { Engine, UAVAsset } from "@/types";

export function Assets() {
  const [assets, setAssets] = useState<UAVAsset[]>([]);
  const [engines, setEngines] = useState<Engine[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [tailNumber, setTailNumber] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([uavAssetsApi.list(), enginesApi.list()]).then(([a, e]) => {
      setAssets(a);
      setEngines(e);
    });
  }, []);

  function engineFor(assetId: string) {
    return engines.find((e) => e.uav_asset_id === assetId);
  }

  async function createAsset(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!tailNumber.trim()) return;
    setSubmitting(true);
    try {
      const created = await uavAssetsApi.create({ tail_number: tailNumber.trim() });
      setAssets((prev) => [...prev, created].sort((a, b) => a.tail_number.localeCompare(b.tail_number)));
      setShowForm(false);
      setTailNumber("");
    } catch {
      setError("Could not create asset — tail number may already be in use.");
    } finally {
      setSubmitting(false);
    }
  }

  async function retire(asset: UAVAsset) {
    const updated = await uavAssetsApi.update(asset.id, { status: asset.status === "active" ? "retired" : "active" });
    setAssets((prev) => prev.map((a) => (a.id === updated.id ? updated : a)));
  }

  return (
    <AppShell breadcrumb={["Fleet", "Assets"]}>
      <div className="flex flex-col gap-4 p-5">
        <div className="flex items-center gap-2.5">
          <div className="text-[15px] font-semibold">UAV Assets</div>
          <div className="flex-grow" />
          <button
            onClick={() => setShowForm((v) => !v)}
            className="rounded-sm bg-accent px-3 py-1.5 text-xs font-semibold text-bg"
          >
            + New Asset
          </button>
        </div>

        {showForm && (
          <form onSubmit={createAsset} className="flex items-end gap-2.5 rounded-sm border border-border bg-surface p-3.5">
            <div className="flex flex-col gap-1">
              <label className="text-[10px] font-semibold uppercase text-textFaint">Tail Number</label>
              <input
                value={tailNumber}
                onChange={(e) => setTailNumber(e.target.value)}
                placeholder="SIM-UAV-02"
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
                {["Tail Number", "Status", "Linked Engine", ""].map((h) => (
                  <th key={h} className="border-b border-border px-3 py-2 text-left text-[10px] font-semibold uppercase tracking-wide text-textFaint">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {assets.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-3 py-6 text-center text-xs text-textFaint">
                    No UAV assets.
                  </td>
                </tr>
              )}
              {assets.map((a) => {
                const engine = engineFor(a.id);
                return (
                  <tr key={a.id}>
                    <td className="border-b border-border px-3 py-2.5 font-mono text-xs">{a.tail_number}</td>
                    <td className="border-b border-border px-3 py-2.5">
                      <span
                        className={`rounded-sm border px-2 py-0.5 text-[11px] font-semibold ${
                          a.status === "active" ? "border-healthy text-healthy" : "border-borderStrong text-textMuted"
                        }`}
                      >
                        {a.status.toUpperCase()}
                      </span>
                    </td>
                    <td className="border-b border-border px-3 py-2.5 font-mono text-xs text-textMuted">
                      {engine ? engine.serial_number : "— none —"}
                    </td>
                    <td className="border-b border-border px-3 py-2.5 text-right">
                      <button
                        onClick={() => retire(a)}
                        className="text-[11px] font-semibold text-textMuted hover:text-accent"
                      >
                        {a.status === "active" ? "Retire" : "Reactivate"}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </AppShell>
  );
}
