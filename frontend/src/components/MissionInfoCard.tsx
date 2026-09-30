import type { Mission } from "@/types";
import { fmtDateTime } from "@/lib/utils";
import { fmtDuration, hasRecordedData, missionStatusLabel, missionTypeLabel, recordedSpanMs, replayPlan } from "@/lib/missionInfo";

const STATUS_COLOR: Record<string, string> = {
  active: "#4C9A6A",
  completed: "#5B8FD6",
  scheduled: "#C9962F",
  aborted: "#C64F44",
  cancelled: "#C64F44",
};

function Field({ label, children, testId }: { label: string; children: React.ReactNode; testId?: string }) {
  return (
    <div className="min-w-0">
      <div className="text-[10px] font-semibold uppercase tracking-wide text-textFaint">{label}</div>
      <div className="mt-0.5 break-words text-xs text-text" data-testid={testId}>
        {children}
      </div>
    </div>
  );
}

/** Everything the operator needs to know about a mission before replaying it. */
export function MissionInfoCard({ mission, tailNumber }: { mission: Mission; tailNumber?: string }) {
  const span = recordedSpanMs(mission);
  const plan = replayPlan(mission);
  const empty = !hasRecordedData(mission);
  const color = STATUS_COLOR[mission.status] ?? "#8B93A1";
  const env = mission.environmental_profile ? Object.entries(mission.environmental_profile) : [];

  return (
    <div className="mt-3 rounded-sm border border-border bg-surface2 p-3.5" data-testid="mission-info">
      <div className="mb-2.5 flex flex-wrap items-center gap-2">
        <span className="text-[13px] font-semibold" data-testid="mission-info-title">
          {missionTypeLabel(mission.mission_type)} mission
        </span>
        <span className="rounded-sm border px-2 py-0.5 text-[10px] font-bold tracking-wide" style={{ borderColor: color, color }} data-testid="mission-info-status">
          {missionStatusLabel(mission.status).toUpperCase()}
        </span>
        <span className="flex-grow" />
        <span className="font-mono text-[10px] text-textFaint" title={mission.id}>
          {mission.id.slice(0, 8)}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-x-6 gap-y-3 md:grid-cols-3 xl:grid-cols-5">
        <Field label="Aircraft">{tailNumber ?? "—"}</Field>
        <Field label="Started">{fmtDateTime(mission.start_time)}</Field>
        <Field label="Ended">{mission.end_time ? fmtDateTime(mission.end_time) : mission.status === "active" ? "not ended yet" : "—"}</Field>
        <Field label="Readings stored" testId="mission-info-readings">
          {mission.reading_count === undefined || mission.reading_count === null ? "—" : mission.reading_count.toLocaleString()}
        </Field>
        <Field label="Recorded window" testId="mission-info-window">
          {mission.first_ts && mission.last_ts ? (
            <>
              {fmtDateTime(mission.first_ts)} → {fmtDateTime(mission.last_ts)}
              {span !== null && <span className="text-textMuted"> ({fmtDuration(span)})</span>}
            </>
          ) : (
            "—"
          )}
        </Field>
      </div>

      {env.length > 0 && (
        <div className="mt-3 flex flex-wrap items-center gap-1.5" data-testid="mission-info-env">
          <span className="text-[10px] font-semibold uppercase tracking-wide text-textFaint">Planned envelope</span>
          {env.map(([k, v]) => (
            <span key={k} className="rounded-sm border border-borderStrong px-1.5 py-0.5 font-mono text-[10px] text-textMuted">
              {k.replace(/_/g, " ")}: {String(v)}
            </span>
          ))}
        </div>
      )}

      {plan && (
        <div
          className={`mt-3 rounded-sm border px-2.5 py-1.5 text-[11px] ${empty ? "border-warning bg-warningBg text-warning" : "border-border text-textMuted"}`}
          data-testid="mission-info-plan"
        >
          {plan}
        </div>
      )}
    </div>
  );
}
