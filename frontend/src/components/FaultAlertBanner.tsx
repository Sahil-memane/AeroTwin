import type { FaultPrediction } from "@/types";
import { fmtAge } from "@/lib/utils";

interface FaultAlertBannerProps {
  fault?: FaultPrediction;
  onAcknowledge?: () => void;
  /** Age of `fault` (ms since its timestamp). Past STALE_AFTER_MS the banner says the engine isn't streaming. */
  ageMs?: number | null;
}

export const STALE_AFTER_MS = 5 * 60_000;

// Accuracy-First Phase 3: a single anomalous reading no longer reads as
// a confirmed fault, and the banner shouldn't either — an in-progress
// streak (ANOMALY_DETECTED/FAULT_SUSPECTED) gets a muted "investigating"
// treatment, only FAULT_CONFIRMED gets the alarming red one. An
// abstained ("insufficient evidence") reading and RECOVERED both render
// nothing — there's no confirmed condition to alert on. `state` is
// absent on rows written before this column existed, which falls back
// to the original confidence-only look rather than hiding real history.
//
// Two further honesty rules:
//  * ADVISORY — the fault model was fed mostly placeholder channels
//    (`reliable === false`). The result is shown, but neutrally and labelled
//    as not scored: the backend excludes it from the health score and alerts,
//    so the banner must not shout "health forced to 0".
//  * STALE — the last prediction is old (engine not streaming). It is
//    dimmed and dated rather than presented as a current condition.
export function FaultAlertBanner({ fault, onAcknowledge, ageMs }: FaultAlertBannerProps) {
  if (!fault || fault.fault_class === "No Failure" || fault.fault_class === "Unknown / insufficient evidence") {
    return null;
  }
  if (fault.state === "RECOVERED") return null;

  const advisory = fault.reliable === false;
  const stale = ageMs != null && ageMs > STALE_AFTER_MS;
  const investigating = fault.state === "ANOMALY_DETECTED" || fault.state === "FAULT_SUSPECTED";
  const forcedZero = !advisory && (fault.state ? fault.state === "FAULT_CONFIRMED" && fault.confidence > 0.9 : fault.confidence > 0.9);

  const border = advisory ? "#6C8EBF" : investigating ? "#C9962F" : forcedZero ? "#E8564A" : "#C64F44";
  const bg = advisory ? "rgba(108,142,191,0.10)" : investigating ? "rgba(201,150,47,0.12)" : forcedZero ? "#3A1512" : "rgba(198,79,68,0.14)";
  const cls = fault.fault_class.toUpperCase();
  const label = advisory
    ? `FAULT MODEL ADVISORY — ${cls} (not scored)`
    : investigating
      ? `POSSIBLE FAULT — ${cls} (${fault.state === "FAULT_SUSPECTED" ? "suspected" : "investigating"})`
      : `FAULT DETECTED — ${cls}`;
  const coverage = fault.input_coverage != null ? Math.round(fault.input_coverage * 100) : null;

  return (
    <div
      className={`flex items-center gap-3 rounded-sm border px-4 py-3 ${stale ? "opacity-70" : ""}`}
      style={{ borderColor: border, backgroundColor: bg }}
      data-testid="fault-banner"
      data-variant={advisory ? "advisory" : "alert"}
    >
      <svg width={20} height={20} viewBox="0 0 16 16" fill="none" stroke={border} strokeWidth={1.4} strokeLinejoin="round" className="flex-shrink-0">
        {advisory ? (
          <>
            <circle cx="8" cy="8" r="6.2" />
            <path d="M8 7.2v3.6" strokeLinecap="round" />
            <circle cx="8" cy="4.9" r="0.6" fill={border} stroke="none" />
          </>
        ) : (
          <>
            <path d="M8 2L14.5 13.5H1.5L8 2z" />
            <path d="M8 6.5v3.2" strokeLinecap="round" />
            <circle cx="8" cy="11.6" r="0.6" fill={border} stroke="none" />
          </>
        )}
      </svg>
      <div className="min-w-0 flex-grow">
        <div className="text-sm font-bold tracking-wide" style={{ color: border }} data-testid="fault-banner-title">
          {label}
        </div>
        <div className="mt-0.5 text-xs text-textMuted" data-testid="fault-banner-detail">
          {(fault.confidence * 100).toFixed(1)}% model confidence
          {forcedZero ? " · health score forced to 0" : ""}
          {advisory && (
            <>
              {" · "}
              {coverage !== null ? `only ${coverage}% of the model's input channels are measured` : "low input coverage"} — shown for information, not
              used in the health score or alerts
            </>
          )}
        </div>
        {stale && (
          <div className="mt-0.5 text-xs font-semibold text-warning" data-testid="fault-banner-stale">
            Last prediction {fmtAge(ageMs as number)} ago — engine not streaming
          </div>
        )}
      </div>
      {onAcknowledge && !investigating && !advisory && !stale && (
        <button
          onClick={onAcknowledge}
          className="rounded-sm border border-borderStrong bg-surface2 px-3 py-1.5 text-xs font-semibold hover:border-accent hover:text-accent"
        >
          Acknowledge
        </button>
      )}
    </div>
  );
}
