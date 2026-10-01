import { useEffect, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import { enginesApi } from "@/services/resources";
import type { Engine } from "@/types";

/**
 * Entry point for the sidebar's "3D Twin" item. The twin itself is per-engine
 * (/engines/:id/twin), so: one engine => go straight to it; several => let the operator choose.
 */
export function TwinIndex() {
  const [engines, setEngines] = useState<Engine[] | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    enginesApi
      .list()
      .then(setEngines)
      .catch(() => setError(true));
  }, []);

  if (engines && engines.length === 1) return <Navigate to={`/engines/${engines[0].id}/twin`} replace />;

  return (
    <AppShell breadcrumb={["Fleet", "3D Twin"]}>
      <div className="flex flex-col gap-3.5 p-5" data-testid="twin-index">
        <div className="rounded-sm border border-border bg-surface px-4 py-3">
          <div className="text-[15px] font-semibold">3D Digital Twin</div>
          <div className="mt-0.5 text-[11px] text-textMuted">Choose an engine to open its twin.</div>
        </div>
        {error && (
          <div role="alert" className="rounded-sm border border-critical bg-criticalBg px-3 py-2 text-xs text-critical">
            Couldn&apos;t load the engine list.
          </div>
        )}
        {!engines && !error && <div className="text-xs text-textMuted">Loading engines…</div>}
        {engines && engines.length === 0 && <div className="text-xs text-textMuted">No engines are registered yet.</div>}
        {engines && engines.length > 1 && (
          <div className="grid grid-cols-1 gap-2.5 md:grid-cols-2 xl:grid-cols-3">
            {engines.map((e) => (
              <Link
                key={e.id}
                to={`/engines/${e.id}/twin`}
                className="rounded-sm border border-border bg-surface p-4 hover:border-accent hover:no-underline"
                data-testid={`twin-pick-${e.id}`}
              >
                <div className="text-[13px] font-semibold text-text">{e.serial_number}</div>
                <div className="mt-0.5 text-[11px] text-textMuted">{e.status}</div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </AppShell>
  );
}
