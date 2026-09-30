import type { ReactNode } from "react";
import type { WhatIfConfig, WhatIfFusionSource, WhatIfFusionSourceView, WhatIfModelStatus, WhatIfParam, WhatIfResponse } from "@/types";
import { WHAT_IF_PARAMS } from "@/types";
import { PARAM_LABELS, fmtNum, fmtPct, fmtSigned } from "./whatIfFormat";
import { buildSummary } from "./whatIfSummary";

interface WhatIfResultsProps {
  result: WhatIfResponse;
  config: WhatIfConfig;
  /** Scenario sliders moved since this result was computed. */
  stale: boolean;
}

const SIM = "#C9962F";

const STATUS_TEXT: Record<WhatIfModelStatus, string> = {
  COMPLETED: "Completed",
  INSUFFICIENT_DATA: "Insufficient data",
  MODEL_UNAVAILABLE: "Model unavailable",
  ERROR: "Error",
};

const FUSION_LABELS: Record<WhatIfFusionSource, string> = { rul: "RUL", fault: "Fault", bearing: "Bearing", aux: "Auxiliary" };
const FUSION_COLORS: Record<WhatIfFusionSource, string> = { rul: "#8B7FC7", fault: "#6C8EBF", bearing: "#4FA8B5", aux: "#B08A5A" };
const FUSION_ORDER: WhatIfFusionSource[] = ["rul", "fault", "bearing", "aux"];
// Largest single-source penalty in Health Fusion (fault = 40) — only sets bar width.
const BAR_FULL_SCALE = 40;

const PHYSICS_ORDER = ["cht", "egt", "oil_pressure", "oil_temperature", "fuel_flow"] as const;
const PHYSICS_COLOR: Record<string, string> = { CONSISTENT: "#4C9A6A", ELEVATED: "#C9962F", REVIEW: "#C9962F", ANOMALY: "#C64F44" };

const scoreColor = (s: number, forced = false) => (forced || s < 20 ? "#C64F44" : s < 50 ? "#C9962F" : "#4C9A6A");

function Section({ title, children, testId, aside }: { title: string; children: ReactNode; testId?: string; aside?: ReactNode }) {
  return (
    <section className="min-w-0 rounded-sm border border-border bg-surface p-4" data-testid={testId}>
      <div className="mb-3 flex items-center gap-2">
        <h3 className="text-[11px] font-semibold uppercase tracking-wide text-textFaint">{title}</h3>
        <span className="flex-grow" />
        {aside}
      </div>
      {children}
    </section>
  );
}

function Banner({ tone, children, testId }: { tone: "warn" | "crit" | "info"; children: ReactNode; testId: string }) {
  const cls =
    tone === "crit"
      ? "border-critical bg-criticalBg text-critical"
      : tone === "warn"
        ? "border-warning bg-warningBg text-warning"
        : "border-borderStrong bg-surface2 text-textMuted";
  return (
    <div role={tone === "crit" ? "alert" : undefined} className={`rounded-sm border px-3 py-2 text-xs ${cls}`} data-testid={testId}>
      {children}
    </div>
  );
}

function ChangedBadge({ changed }: { changed: boolean }) {
  return (
    <span
      className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${changed ? "border-accent text-accent" : "border-borderStrong text-textMuted"}`}
    >
      {changed ? "CHANGED" : "UNCHANGED"}
    </span>
  );
}

/** Deterministic score ring (number is real DOM text, so it is readable and testable). */
function MiniRing({ score, forced, label, testId }: { score: number; forced?: boolean; label: string; testId: string }) {
  const r = 34;
  const c = 2 * Math.PI * r;
  const color = scoreColor(score, forced);
  return (
    <div className="flex flex-col items-center gap-1">
      <div className="relative h-[84px] w-[84px]">
        <svg width={84} height={84} viewBox="0 0 84 84" aria-hidden>
          <circle cx="42" cy="42" r={r} fill="none" stroke="#262D38" strokeWidth="7" />
          <circle
            cx="42"
            cy="42"
            r={r}
            fill="none"
            stroke={color}
            strokeWidth="7"
            strokeLinecap="round"
            strokeDasharray={c}
            strokeDashoffset={c * (1 - Math.max(0, Math.min(100, score)) / 100)}
            transform="rotate(-90 42 42)"
          />
        </svg>
        <span className="absolute inset-0 flex items-center justify-center font-mono text-2xl font-semibold" style={{ color }} data-testid={testId}>
          {fmtNum(score)}
        </span>
      </div>
      <span className="text-[10px] font-semibold uppercase tracking-wide text-textFaint">{label}</span>
    </div>
  );
}

function ModelValue({ status, message, children }: { status: WhatIfModelStatus; message?: string; children: ReactNode }) {
  if (status !== "COMPLETED") {
    return (
      <span className="font-sans text-xs text-textMuted" title={message}>
        {STATUS_TEXT[status]}
        {message ? <span className="block text-[10px] text-textFaint">{message}</span> : null}
      </span>
    );
  }
  return <>{children}</>;
}

function ModelCard({
  title,
  testId,
  changed,
  before,
  after,
  footer,
}: {
  title: string;
  testId: string;
  changed: boolean;
  before: ReactNode;
  after: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <div className="flex min-w-0 flex-col gap-2 rounded-sm border border-border bg-surface p-4" data-testid={testId}>
      <div className="flex items-center gap-2">
        <h3 className="text-[11px] font-semibold uppercase tracking-wide text-textFaint">{title}</h3>
        <span className="flex-grow" />
        <ChangedBadge changed={changed} />
      </div>
      <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 text-xs">
        <span className="pt-0.5 text-[10px] font-semibold uppercase text-textFaint">Baseline</span>
        <span className="min-w-0 break-words font-mono text-text">{before}</span>
        <span className="pt-0.5 text-[10px] font-semibold uppercase text-textFaint">What-If</span>
        <span className="min-w-0 break-words font-mono font-semibold text-text">{after}</span>
      </div>
      {footer}
    </div>
  );
}

function PenaltyBar({ view, color, muted }: { view: WhatIfFusionSourceView; color: string; muted?: boolean }) {
  if (view.excluded) return <div className="h-2 rounded-sm border border-dashed border-borderStrong" title="advisory — not scored" />;
  if (!view.available) return <div className="h-2 rounded-sm border border-dashed border-borderStrong" title="no model output" />;
  const pct = view.forced_zero ? 100 : Math.min(100, ((view.penalty ?? 0) / BAR_FULL_SCALE) * 100);
  return (
    <div className="h-2 overflow-hidden rounded-sm bg-surface3">
      <div
        className="h-full rounded-sm"
        style={{ width: `${pct}%`, backgroundColor: view.forced_zero ? "#E8564A" : color, opacity: muted ? 0.45 : 1 }}
      />
    </div>
  );
}

export function WhatIfResults({ result, config, stale }: WhatIfResultsProps) {
  const { model_results: models, health_fusion: fusion, physics_consistency: physics, alerts, window: win } = result;

  const noTelemetry = result.baseline === null || models === null || fusion === null;
  const missing = fusion?.scenario.missing_sources ?? [];
  const healthUnavailable = missing.length > 0;
  const summary = noTelemetry ? [] : buildSummary(result, config);

  return (
    <div className="flex min-w-0 flex-col gap-3.5 rounded-sm border border-dashed p-4" style={{ borderColor: SIM }} data-testid="whatif-results">
      {/* Header */}
      <div className="flex flex-wrap items-center gap-2.5">
        <span className="rounded-sm border px-2 py-0.5 text-[10px] font-bold tracking-wider" style={{ borderColor: SIM, color: SIM }} data-testid="whatif-badge">
          WHAT-IF SIMULATION
        </span>
        <span className="text-[11px] text-textMuted">Computed by the real models on a modified copy of recent telemetry — not live data</span>
        <span className="flex-grow" />
        <span className="font-mono text-[11px] text-textMuted" data-testid="whatif-status">
          {result.simulation_status}
        </span>
      </div>

      {stale && (
        <Banner tone="warn" testId="whatif-stale">
          Scenario values changed since this result was computed — press RUN WHAT-IF to update.
        </Banner>
      )}
      {noTelemetry && (
        <Banner tone="info" testId="whatif-no-telemetry">
          {result.message ?? "No telemetry recorded for this engine — current engine data unavailable."}
        </Banner>
      )}
      {result.simulation_status === "INSUFFICIENT_DATA" && !noTelemetry && (
        <Banner tone="info" testId="whatif-insufficient">
          Insufficient telemetry history: {win.total_readings} readings available (RUL needs {win.required_readings.rul}, Fault needs{" "}
          {win.required_readings.fault}). Models without enough history are shown as unavailable — they are not treated as zero or normal.
        </Banner>
      )}
      {result.simulation_status === "MODEL_UNAVAILABLE" && (
        <Banner tone="crit" testId="whatif-model-unavailable">
          One or more models are unavailable on the server. Affected results are marked below.
        </Banner>
      )}
      {result.simulation_status === "ERROR" && (
        <Banner tone="crit" testId="whatif-model-error">
          A model failed while computing this scenario. Affected results are marked below.
        </Banner>
      )}
      {(win.clamped_values ?? 0) > 0 && (
        <Banner tone="warn" testId="whatif-clamped">
          The requested shift pushed {win.clamped_values} perturbed reading(s) beyond the configured sensor bounds; those readings were clamped to the
          bound. Your slider values were not changed.
        </Banner>
      )}

      {!noTelemetry && models && fusion && (
        <>
          {/* Hero: health + what changed */}
          <div className="grid min-w-0 gap-3.5 lg:grid-cols-[minmax(0,auto)_minmax(0,1fr)]" data-testid="whatif-health">
            <div className="flex min-w-[300px] items-center justify-center gap-5 rounded-sm border border-border bg-surface p-4">
              {healthUnavailable ? (
                <div className="max-w-[280px] text-xs text-textMuted" data-testid="whatif-health-unavailable">
                  <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-textFaint">Engine health</div>
                  <span className="font-semibold text-text">Unavailable — insufficient data.</span> Health Fusion has no output from{" "}
                  {missing.map((m) => FUSION_LABELS[m]).join(", ")}, so a combined score would not be a full assessment.
                </div>
              ) : (
                <>
                  <MiniRing score={fusion.baseline.score} forced={fusion.baseline.forced_zero} label="Baseline" testId="whatif-health-baseline" />
                  <div className="flex flex-col items-center gap-1">
                    <span aria-hidden className="text-xl text-textFaint">→</span>
                    <span
                      className="rounded-full border px-2.5 py-0.5 font-mono text-xs font-semibold"
                      style={{
                        borderColor: fusion.score_delta === 0 ? "#333D4A" : fusion.score_delta > 0 ? "#4C9A6A" : "#C64F44",
                        color: fusion.score_delta === 0 ? "#8B93A1" : fusion.score_delta > 0 ? "#4C9A6A" : "#C64F44",
                      }}
                      data-testid="whatif-health-delta"
                    >
                      {fmtSigned(fusion.score_delta)}
                    </span>
                  </div>
                  <MiniRing score={fusion.scenario.score} forced={fusion.scenario.forced_zero} label="What-If" testId="whatif-health-scenario" />
                </>
              )}
            </div>

            <div className="min-w-0 rounded-sm border border-border bg-surface p-4">
              <div className="mb-2 flex items-center gap-2">
                <h3 className="text-[11px] font-semibold uppercase tracking-wide text-textFaint">What changed</h3>
                <span className="flex-grow" />
                {result.live_reference && (
                  <span className="text-[10px] text-textFaint">
                    last persisted LIVE score <span className="font-mono">{fmtNum(result.live_reference.combined_score)}</span> · baseline is recomputed from the window
                  </span>
                )}
              </div>
              <ul className="flex flex-col gap-1.5 text-xs" data-testid="whatif-summary">
                {summary.map((l) => (
                  <li key={l.key} className="flex items-start gap-2">
                    <span
                      aria-hidden
                      className="mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full"
                      style={{ backgroundColor: l.changed ? "#5B8FD6" : "#4A515C" }}
                    />
                    <span className={l.changed ? "text-text" : "text-textMuted"}>{l.text}</span>
                  </li>
                ))}
              </ul>
              {!healthUnavailable && fusion.scenario.excluded_sources.length > 0 && (
                <div className="mb-2 text-[11px] text-textMuted" data-testid="whatif-excluded-note">
                  Health excludes {fusion.scenario.excluded_sources.map((m) => FUSION_LABELS[m]).join(", ")} (advisory — too few measured input channels).
                </div>
              )}
              {!healthUnavailable && fusion.scenario.primary_concern && (
                <div className="mt-2.5 border-t border-border pt-2 text-xs text-textMuted">
                  <span className="text-textFaint">Primary concern (what-if):</span> {fusion.scenario.primary_concern}
                </div>
              )}
            </div>
          </div>

          {/* Model cards */}
          <div className="grid grid-cols-1 gap-3.5 md:grid-cols-2 2xl:grid-cols-4">
            <ModelCard
              title="RUL"
              testId="whatif-rul"
              changed={models.rul.changed}
              before={
                <ModelValue status={models.rul.baseline.status} message={models.rul.baseline.message}>
                  {fmtNum(models.rul.baseline.rul_cycles ?? 0)} cycles
                </ModelValue>
              }
              after={
                <ModelValue status={models.rul.scenario.status} message={models.rul.scenario.message}>
                  {fmtNum(models.rul.scenario.rul_cycles ?? 0)} cycles
                </ModelValue>
              }
              footer={
                <div className="text-[11px] text-textMuted" data-testid="whatif-rul-delta">
                  Delta: {models.rul.delta_cycles === null ? "—" : `${fmtSigned(models.rul.delta_cycles)} cycles`}
                </div>
              }
            />
            <ModelCard
              title="Fault"
              testId="whatif-fault"
              changed={models.fault.changed}
              footer={
                models.fault.scenario.reliable === false ? (
                  <span className="rounded-sm border border-borderStrong bg-surface2 px-2 py-1 text-[11px] leading-snug text-textMuted" data-testid="whatif-fault-advisory">
                    ADVISORY — not scored in Health Fusion
                    {models.fault.scenario.input_coverage !== undefined && ` (only ${Math.round(models.fault.scenario.input_coverage * 100)}% of the model's input channels are measured)`}
                  </span>
                ) : undefined
              }
              before={
                <ModelValue status={models.fault.baseline.status} message={models.fault.baseline.message}>
                  {models.fault.baseline.fault_class} · {models.fault.baseline.state}
                  {models.fault.baseline.confidence !== undefined && <span className="text-textFaint"> · {fmtPct(models.fault.baseline.confidence)}</span>}
                </ModelValue>
              }
              after={
                <ModelValue status={models.fault.scenario.status} message={models.fault.scenario.message}>
                  {models.fault.scenario.fault_class} · {models.fault.scenario.state}
                  {models.fault.scenario.confidence !== undefined && <span className="text-textFaint"> · {fmtPct(models.fault.scenario.confidence)}</span>}
                </ModelValue>
              }
            />
            <ModelCard
              title="Bearing / Vibration"
              testId="whatif-bearing"
              changed={models.bearing.changed}
              before={
                <ModelValue status={models.bearing.baseline.status} message={models.bearing.baseline.message}>
                  {models.bearing.baseline.class_label} · {models.bearing.baseline.fault_location}
                  {models.bearing.baseline.severity_inches != null && <span className="text-textFaint"> · {models.bearing.baseline.severity_inches} in</span>}
                  {models.bearing.baseline.confidence !== undefined && <span className="text-textFaint"> · {fmtPct(models.bearing.baseline.confidence)}</span>}
                </ModelValue>
              }
              after={
                <ModelValue status={models.bearing.scenario.status} message={models.bearing.scenario.message}>
                  {models.bearing.scenario.class_label} · {models.bearing.scenario.fault_location}
                  {models.bearing.scenario.severity_inches != null && <span className="text-textFaint"> · {models.bearing.scenario.severity_inches} in</span>}
                  {models.bearing.scenario.confidence !== undefined && <span className="text-textFaint"> · {fmtPct(models.bearing.scenario.confidence)}</span>}
                </ModelValue>
              }
              footer={
                <div className="flex flex-col gap-1">
                  <span className="text-[10px] text-textFaint" data-testid="whatif-bearing-input">
                    Scenario modifies bearing inputs: {models.bearing.input_changed ? "yes (RPM)" : "no"}
                  </span>
                  <span className="text-[11px] leading-snug text-textMuted" data-testid="whatif-bearing-note">{models.bearing.note}</span>
                </div>
              }
            />
            <ModelCard
              title="Auxiliary"
              testId="whatif-aux"
              changed={models.auxiliary.changed}
              before={
                <ModelValue status={models.auxiliary.baseline.status} message={models.auxiliary.baseline.message}>
                  {models.auxiliary.baseline.risk_level} · {fmtNum(models.auxiliary.baseline.failure_probability_pct ?? 0)}%
                  {models.auxiliary.baseline.primary_failure_cause && <span className="text-textFaint"> · {models.auxiliary.baseline.primary_failure_cause}</span>}
                </ModelValue>
              }
              after={
                <ModelValue status={models.auxiliary.scenario.status} message={models.auxiliary.scenario.message}>
                  {models.auxiliary.scenario.risk_level} · {fmtNum(models.auxiliary.scenario.failure_probability_pct ?? 0)}%
                  {models.auxiliary.scenario.primary_failure_cause && <span className="text-textFaint"> · {models.auxiliary.scenario.primary_failure_cause}</span>}
                </ModelValue>
              }
              footer={
                <div className="flex flex-col gap-1">
                  <span className="text-[10px] text-textFaint" data-testid="whatif-aux-input">
                    Scenario modifies auxiliary inputs: {models.auxiliary.input_changed ? "yes (RPM/CHT)" : "no"}
                  </span>
                  {models.auxiliary.scenario.status === "COMPLETED" && models.auxiliary.scenario.recommended_action && (
                    <span className="text-[11px] leading-snug text-textMuted" data-testid="whatif-aux-action">
                      Model recommendation (what-if): {models.auxiliary.scenario.recommended_action}
                    </span>
                  )}
                  {models.auxiliary.note && (
                    <span className="text-[11px] leading-snug text-textMuted" data-testid="whatif-aux-note">{models.auxiliary.note}</span>
                  )}
                </div>
              }
            />
          </div>

          {/* Health Fusion contributors */}
          <Section title="Health Fusion contributors" testId="whatif-fusion" aside={<span className="text-[10px] text-textFaint">penalty points · bar full scale = {BAR_FULL_SCALE}</span>}>
            <div className="grid grid-cols-[80px_minmax(0,1fr)_minmax(0,1fr)_64px] items-center gap-x-4 gap-y-2.5 text-xs">
              <span className="text-[10px] font-semibold uppercase text-textFaint">Source</span>
              <span className="text-[10px] font-semibold uppercase text-textFaint">Baseline</span>
              <span className="text-[10px] font-semibold uppercase text-textFaint">What-If</span>
              <span className="text-right text-[10px] font-semibold uppercase text-textFaint">Delta</span>
              {FUSION_ORDER.map((src) => {
                const b = fusion.baseline.sources[src];
                const s = fusion.scenario.sources[src];
                const cell = (v: WhatIfFusionSourceView) =>
                  v.excluded ? "excluded (advisory — low input coverage)" : !v.available ? "n/a (no model output)" : v.forced_zero ? "FORCED TO 0" : fmtNum(v.penalty ?? 0);
                const delta = b.available && s.available && !b.excluded && !s.excluded && b.penalty !== null && s.penalty !== null ? fmtSigned(s.penalty - b.penalty) : "—";
                return (
                  <div key={src} className="contents" data-testid={`whatif-fusion-${src}`}>
                    <span className="flex items-center gap-1.5 font-semibold text-textMuted">
                      <span aria-hidden className="h-2 w-2 rounded-full" style={{ backgroundColor: FUSION_COLORS[src] }} />
                      {FUSION_LABELS[src]}
                    </span>
                    <div className="flex min-w-0 flex-col gap-1">
                      <PenaltyBar view={b} color={FUSION_COLORS[src]} muted />
                      <span className="font-mono text-[11px] text-textMuted">{cell(b)}</span>
                    </div>
                    <div className="flex min-w-0 flex-col gap-1">
                      <PenaltyBar view={s} color={FUSION_COLORS[src]} />
                      <span className="font-mono text-[11px]">{cell(s)}</span>
                    </div>
                    <span className="text-right font-mono text-[11px]">{delta}</span>
                  </div>
                );
              })}
            </div>
          </Section>
        </>
      )}

      {/* Physics + inputs */}
      {(physics || (result.baseline && result.scenario && result.delta)) && (
        <div className="grid min-w-0 grid-cols-1 gap-3.5 2xl:grid-cols-2">
          {physics && (
            <Section title="Physics consistency" testId="whatif-physics" aside={<span className="text-[10px] text-textFaint">scenario vs Otto-cycle expectation</span>}>
              <table className="w-full table-fixed text-xs">
                <thead>
                  <tr className="text-left text-[10px] uppercase text-textFaint">
                    <th className="w-[28%] pb-1.5 font-semibold">Parameter</th>
                    <th className="pb-1.5 text-right font-semibold">Expected</th>
                    <th className="pb-1.5 text-right font-semibold">Scenario</th>
                    <th className="pb-1.5 text-right font-semibold">Residual</th>
                    <th className="w-[26%] pb-1.5 text-right font-semibold">Status</th>
                  </tr>
                </thead>
                <tbody className="font-mono">
                  {PHYSICS_ORDER.map((p) => {
                    const row = physics.parameters[p];
                    if (!row) return null;
                    return (
                      <tr key={p} className="border-t border-border" data-testid={`whatif-physics-${p}`}>
                        <td className="py-1.5 font-sans font-semibold text-textMuted">{PARAM_LABELS[p]}</td>
                        <td className="py-1.5 text-right">{fmtNum(row.expected)}</td>
                        <td className="py-1.5 text-right">{fmtNum(row.measured)}</td>
                        <td className="py-1.5 text-right">{fmtSigned(row.residual)}</td>
                        <td className="py-1.5 text-right font-sans text-[10px] font-semibold" style={{ color: PHYSICS_COLOR[row.status] }}>
                          {row.status}
                          {row.baseline_status !== row.status && <span className="block font-normal text-textFaint">(was {row.baseline_status})</span>}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              <div className="mt-2 text-[10px] text-textFaint">
                RPM is an input to the physics model, not a checked channel. Deviation score: {fmtNum(physics.deviation_score.baseline)} →{" "}
                {fmtNum(physics.deviation_score.scenario)}
              </div>
            </Section>
          )}

          {result.baseline && result.scenario && result.delta && (
            <Section title="Current vs scenario telemetry" testId="whatif-compare">
              <table className="w-full table-fixed text-xs">
                <thead>
                  <tr className="text-left text-[10px] uppercase text-textFaint">
                    <th className="w-[30%] pb-1.5 font-semibold">Parameter</th>
                    <th className="pb-1.5 text-right font-semibold">Current</th>
                    <th className="pb-1.5 text-right font-semibold">Scenario</th>
                    <th className="pb-1.5 text-right font-semibold">Delta</th>
                  </tr>
                </thead>
                <tbody className="font-mono">
                  {WHAT_IF_PARAMS.map((p: WhatIfParam) => (
                    <tr key={p} className="border-t border-border" data-testid={`whatif-compare-${p}`}>
                      <td className="py-1.5 font-sans font-semibold text-textMuted">{PARAM_LABELS[p]}</td>
                      <td className="py-1.5 text-right">{fmtNum(result.baseline![p])} {config.parameters[p].unit}</td>
                      <td className="py-1.5 text-right">{fmtNum(result.scenario![p])} {config.parameters[p].unit}</td>
                      <td className={`py-1.5 text-right ${result.delta![p] === 0 ? "text-textFaint" : "font-semibold text-accent"}`}>
                        {fmtSigned(result.delta![p])} {config.parameters[p].unit}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Section>
          )}
        </div>
      )}

      {/* Simulation alerts */}
      {alerts && (
        <div className="rounded-sm border border-dashed p-4" style={{ borderColor: SIM }} data-testid="whatif-alerts">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <span className="rounded-sm border px-2 py-0.5 text-[10px] font-bold tracking-wider" style={{ borderColor: SIM, color: SIM }} data-testid="whatif-alerts-badge">
              SIMULATION
            </span>
            <span className="text-[11px] font-semibold uppercase tracking-wide text-textFaint">Simulated alerts</span>
            <span className="text-[10px] text-textFaint">— never created or broadcast as live alerts</span>
            <span className="flex-grow" />
            <span className="font-mono text-[11px] text-textMuted" data-testid="whatif-alerts-change">{alerts.change}</span>
          </div>
          {alerts.scenario ? (
            <div className="text-xs" data-testid="whatif-alert-scenario">
              <span className="font-semibold uppercase">{alerts.scenario.severity}</span>: {alerts.scenario.message}
            </div>
          ) : (
            <div className="text-xs text-textMuted" data-testid="whatif-alert-none">No alert would fire under this scenario.</div>
          )}
          {alerts.baseline && <div className="mt-1 text-[11px] text-textFaint">Baseline would raise: {alerts.baseline.severity.toUpperCase()}</div>}
        </div>
      )}

      {/* Methodology */}
      <div className="flex flex-col gap-1 text-[11px] text-textFaint" data-testid="whatif-method">
        <div className="flex flex-wrap gap-x-4 gap-y-1">
          <span>Baseline: recent engine telemetry window</span>
          <span data-testid="whatif-perturbed">
            Perturbed readings: {win.perturbed_readings} / {win.total_readings} loaded · fault model needs {win.required_readings.fault}, RUL needs{" "}
            {win.required_readings.rul}
          </span>
        </div>
        <div>Scenario type: PARAMETER PERTURBATION — parameters are shifted independently; no cross-parameter engine physics is simulated.</div>
        {result.model_versions && (
          <div>
            Model versions:{" "}
            {Object.entries(result.model_versions)
              .map(([k, v]) => `${k} ${v}`)
              .join(" · ")}
          </div>
        )}
        {result.assumptions && result.assumptions.length > 0 && (
          <details className="mt-0.5">
            <summary className="cursor-pointer">Assumptions &amp; limitations</summary>
            <ul className="ml-4 list-disc">
              {result.assumptions.map((a) => (
                <li key={a}>{a}</li>
              ))}
            </ul>
          </details>
        )}
      </div>
    </div>
  );
}
