import type { ReactNode } from "react";
import type { WhatIfResponse } from "@/types";
import { fmtAgeShort, fmtDateTime } from "@/lib/utils";
import type { TwinViewModel } from "@/lib/engineTwin";
import type { Inspection, InspectRow } from "@/lib/twinInspect";
import { UNAVAILABLE, num } from "@/lib/twinInspect";
import type { ModePanelData } from "@/lib/twinModePanel";

const SIM = "#C9962F";
const REPLAY = "#6C8EBF";

const card = "min-w-0 rounded-sm border border-border bg-surface p-4";
const cardTitle = "mb-2 text-[11px] font-semibold uppercase tracking-wide text-textFaint";

// ── source chip (LIVE / STALE / NO DATA / REPLAY / WHAT-IF SIMULATION) ─────────────

export function sourceChip(vm: TwinViewModel): { text: string; color: string } {
  switch (vm.state) {
    case "live":
      return { text: "LIVE", color: "#4C9A6A" };
    case "stale":
      return { text: "STALE", color: "#C9962F" };
    case "replay":
      return { text: "REPLAY", color: REPLAY };
    case "whatif":
      return { text: "WHAT-IF SIMULATION", color: SIM };
    default:
      return { text: "NO DATA", color: "#8B93A1" };
  }
}

export function SourceChip({ vm, testId = "twin-state" }: { vm: TwinViewModel; testId?: string }) {
  const c = sourceChip(vm);
  return (
    <span className="rounded-sm border px-2 py-0.5 text-[10px] font-bold tracking-wider" style={{ borderColor: c.color, color: c.color }} data-testid={testId}>
      {c.text}
    </span>
  );
}

/** "updated 3 s ago" / "last data 1 h 4 min ago" / replay step label / scenario label. */
export function sourceAge(vm: TwinViewModel): string {
  if (vm.state === "replay" || vm.state === "whatif") return vm.sourceLabel ?? "";
  if (!vm.timestamp) return "no telemetry received";
  return vm.state === "stale" ? `last data ${fmtAgeShort(vm.ageMs ?? 0)} ago (${fmtDateTime(vm.timestamp)})` : `updated ${fmtAgeShort(vm.ageMs ?? 0)} ago`;
}

// ── engine summary ────────────────────────────────────────────────────

function Stat({ label, value, sub, color, testId, unavailable }: { label: string; value: ReactNode; sub?: ReactNode; color?: string; testId: string; unavailable?: boolean }) {
  return (
    <div className="min-w-0 bg-surface px-3 py-2.5" data-testid={testId} data-unavailable={unavailable ? "true" : undefined}>
      <div className="text-[10px] font-semibold uppercase tracking-wide text-textFaint">{label}</div>
      <div className={`truncate font-mono text-[15px] font-semibold ${unavailable ? "text-textMuted" : ""}`} style={color ? { color } : undefined}>
        {value}
      </div>
      {sub && <div className="truncate text-[10px] text-textFaint">{sub}</div>}
    </div>
  );
}

export function SummaryBar({ vm }: { vm: TwinViewModel }) {
  const h = vm.health;
  const chip = sourceChip(vm);
  return (
    <div className="grid grid-cols-2 gap-px overflow-hidden rounded-sm border border-border bg-border sm:grid-cols-4 xl:grid-cols-7" data-testid="twin-summary">
      <Stat
        testId="summary-health"
        label="Engine health"
        unavailable={!h || h.score === null}
        value={h && h.score !== null ? num(h.score) : UNAVAILABLE}
        sub={h && h.score !== null ? (h.missing.length > 0 ? `partial — no ${h.missing.join(", ")}` : h.forcedZero ? "forced to 0" : "Health Fusion") : "no score for this source"}
      />
      <Stat testId="summary-rul" label="RUL" unavailable={!vm.rul} value={vm.rul ? `${num(vm.rul.cycles)} cyc` : UNAVAILABLE} sub={vm.rul ? undefined : "no prediction"} />
      <Stat
        testId="summary-fault"
        label="Fault status"
        unavailable={!vm.fault}
        value={vm.fault ? vm.fault.label : UNAVAILABLE}
        sub={vm.fault ? (vm.fault.advisory ? "advisory — not scored" : vm.fault.confidence !== null ? `${num(vm.fault.confidence * 100, 0)}% confidence` : undefined) : "no prediction"}
      />
      <Stat
        testId="summary-bearing"
        label="Bearing status"
        unavailable={!vm.bearing.present}
        value={vm.bearing.present ? (vm.bearing.label ?? UNAVAILABLE) : UNAVAILABLE}
        color={vm.bearing.present ? vm.bearing.color : undefined}
        sub={vm.bearing.present ? (vm.bearing.severity ? `${num(vm.bearing.severity, 3)} in` : "no severity") : "no prediction"}
      />
      <Stat
        testId="summary-aux"
        label="Auxiliary risk"
        unavailable={!vm.aux}
        value={vm.aux ? `${vm.aux.risk}` : UNAVAILABLE}
        sub={vm.aux ? `${num(vm.aux.probabilityPct)}% failure probability` : "no prediction"}
      />
      <Stat
        testId="summary-quality"
        label="Telemetry quality"
        unavailable={!vm.quality}
        value={vm.quality ?? UNAVAILABLE}
        sub={vm.quality ? "validation result" : "not recorded for this source"}
        color={vm.quality === "VALID" ? "#4C9A6A" : vm.quality ? "#C9962F" : undefined}
      />
      <Stat testId="summary-source" label="Data source" value={chip.text} color={chip.color} sub={sourceAge(vm)} />
    </div>
  );
}

// ── mode panel ────────────────────────────────────────────────────────

function RowView({ r }: { r: InspectRow }) {
  return (
    <div className="contents" data-testid="inspect-row" data-unavailable={r.unavailable ? "true" : undefined}>
      <dt className="text-textFaint">{r.label}</dt>
      <dd className="text-right font-mono" style={r.color ? { color: r.color } : undefined}>
        <span className={r.unavailable ? "italic text-textMuted" : ""}>{r.value}</span>
        {r.reason && <span className="block font-sans text-[10px] not-italic leading-snug text-textFaint">{r.reason}</span>}
      </dd>
    </div>
  );
}

export function Rows({ rows }: { rows: InspectRow[] }) {
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-xs">
      {rows.map((r, i) => (
        <RowView key={`${r.label}-${i}`} r={r} />
      ))}
    </dl>
  );
}

const FUSION_STATE_COLOR = { ok: "#4C9A6A", penalty: "#C9962F", forced: "#C64F44", excluded: "#6C8EBF", missing: "#8B93A1" } as const;

export function ModePanelView({ data }: { data: ModePanelData }) {
  return (
    <div className={card} data-testid="mode-panel" data-mode={data.mode}>
      <div className="mb-0.5 text-[13px] font-semibold">{data.title} view</div>
      <div className="mb-2.5 text-[11px] text-textMuted">{data.blurb}</div>

      {data.headline && (
        <div className="mb-2.5 rounded-sm border border-border bg-surface2 px-3 py-2" data-testid="mode-headline">
          <div className="text-[10px] uppercase text-textFaint">{data.headline.label}</div>
          <div className={`font-mono text-2xl font-semibold ${data.headline.unavailable ? "text-textMuted" : ""}`}>{data.headline.value}</div>
          {data.headline.reason && <div className="text-[10px] text-textFaint">{data.headline.reason}</div>}
        </div>
      )}

      {data.fusion && (
        <div className="mb-2.5" data-testid="fusion-list">
          <div className={cardTitle}>Health Fusion contributors</div>
          <div className="flex flex-col divide-y divide-border rounded-sm border border-border">
            {data.fusion.map((f) => (
              <div key={f.source} className="flex items-center gap-2 px-2.5 py-1.5 text-xs" data-testid={`fusion-row-${f.source}`} data-state={f.state}>
                <span className="h-2 w-2 flex-shrink-0 rounded-full" style={{ backgroundColor: FUSION_STATE_COLOR[f.state] }} />
                <span className="font-semibold text-textMuted">{f.label}</span>
                <span className="flex-grow" />
                <span className="font-mono">{f.text}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {data.physicsTable && (
        <table className="mb-2.5 w-full table-fixed text-xs" data-testid="physics-table">
          <thead>
            <tr className="text-left text-[10px] uppercase text-textFaint">
              <th className="w-[27%] pb-1 font-semibold">Channel</th>
              <th className="pb-1 text-right font-semibold">Measured</th>
              <th className="pb-1 text-right font-semibold">Expected</th>
              <th className="pb-1 text-right font-semibold">Residual</th>
              <th className="w-[24%] pb-1 text-right font-semibold">Status</th>
            </tr>
          </thead>
          <tbody className="font-mono">
            {data.physicsTable.map((r) => (
              <tr key={r.key} className="border-t border-border" data-testid={`physics-row-${r.key}`}>
                <td className="py-1.5 font-sans font-semibold text-textMuted">
                  {r.label}
                  <span className="text-textFaint"> {r.unit}</span>
                </td>
                <td className="py-1.5 text-right">{r.measured}</td>
                <td className={`py-1.5 text-right ${r.expected === UNAVAILABLE ? "italic text-textMuted" : ""}`} title={r.note}>
                  {r.expected}
                </td>
                <td className={`py-1.5 text-right ${r.residual === UNAVAILABLE ? "italic text-textMuted" : ""}`}>{r.residual}</td>
                <td className="py-1.5 text-right font-sans text-[10px] font-semibold" style={{ color: r.statusColor }}>
                  {r.status ?? (r.note ? "input" : UNAVAILABLE)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {data.sections.map((s) => (
        <div key={s.title} className="mb-2.5">
          <div className={cardTitle}>{s.title}</div>
          <Rows rows={s.rows} />
        </div>
      ))}

      {data.notes.map((n) => (
        <div key={n} className="mt-1.5 rounded-sm border border-border bg-surface2 px-2.5 py-2 text-[11px] leading-snug text-textMuted" data-testid="mode-note">
          {n}
        </div>
      ))}
    </div>
  );
}

// ── component inspector ───────────────────────────────────────────────

export function InspectorView({ inspection, onClear }: { inspection: Inspection | null; onClear: () => void }) {
  return (
    <div className={card} data-testid="inspector">
      <div className={cardTitle}>Component inspection</div>
      {!inspection ? (
        <div className="text-xs text-textMuted">Click any part of the engine — block, a cylinder, turbo, bearing, gearbox, propeller, exhaust, oil or fuel — to see the information AeroTwin actually has for it.</div>
      ) : (
        <>
          <div className="mb-2 flex items-center gap-2">
            <span className="text-[13px] font-semibold" data-testid="inspector-title">
              {inspection.title}
            </span>
            <span className="flex-grow" />
            <button onClick={onClear} className="text-[11px] text-accent hover:underline">
              clear
            </button>
          </div>
          {inspection.sections.map((s) => (
            <div key={s.title} className="mb-2.5">
              <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-textFaint">{s.title}</div>
              <Rows rows={s.rows} />
            </div>
          ))}
          {inspection.notes.map((n) => (
            <div key={n} className="mt-1 rounded-sm border border-border bg-surface2 px-2.5 py-2 text-[11px] leading-snug text-textMuted" data-testid="inspector-note">
              {n}
            </div>
          ))}
        </>
      )}
    </div>
  );
}

// ── current vs what-if (compact; every value comes from the What-If response) ─────────

export interface CompareRow {
  key: string;
  label: string;
  current: string;
  scenario: string;
  changed: boolean;
}

const dash = UNAVAILABLE;
function modelText<T extends { status: string }>(blk: T, f: (b: T) => string): string {
  return blk.status === "COMPLETED" ? f(blk) : blk.status === "INSUFFICIENT_DATA" ? "Insufficient data" : UNAVAILABLE;
}

export function compareRows(r: WhatIfResponse): CompareRow[] {
  if (!r.model_results || !r.health_fusion || !r.baseline || !r.scenario) return [];
  const m = r.model_results;
  const hf = r.health_fusion;
  const health = (side: typeof hf.baseline) => (side.missing_sources.length > 0 ? `${dash} (partial)` : num(side.score));
  const rows: CompareRow[] = [
    { key: "health", label: "Health", current: health(hf.baseline), scenario: health(hf.scenario), changed: hf.score_delta !== 0 },
    {
      key: "rul",
      label: "RUL",
      current: modelText(m.rul.baseline, (b) => `${num(b.rul_cycles)} cyc`),
      scenario: modelText(m.rul.scenario, (b) => `${num(b.rul_cycles)} cyc`),
      changed: m.rul.changed,
    },
    {
      key: "fault",
      label: "Fault",
      current: modelText(m.fault.baseline, (b) => `${b.fault_class ?? UNAVAILABLE}${b.reliable === false ? " (advisory)" : ""}`),
      scenario: modelText(m.fault.scenario, (b) => `${b.fault_class ?? UNAVAILABLE}${b.reliable === false ? " (advisory)" : ""}`),
      changed: m.fault.changed,
    },
    {
      key: "bearing",
      label: "Bearing",
      current: modelText(m.bearing.baseline, (b) => b.class_label ?? UNAVAILABLE),
      scenario: modelText(m.bearing.scenario, (b) => b.class_label ?? UNAVAILABLE),
      changed: m.bearing.changed,
    },
    {
      key: "aux",
      label: "Auxiliary",
      current: modelText(m.auxiliary.baseline, (b) => `${b.risk_level ?? UNAVAILABLE} ${num(b.failure_probability_pct)}%`),
      scenario: modelText(m.auxiliary.scenario, (b) => `${b.risk_level ?? UNAVAILABLE} ${num(b.failure_probability_pct)}%`),
      changed: m.auxiliary.changed,
    },
  ];
  const labels: Record<string, string> = { rpm: "RPM", cht: "CHT", egt: "EGT", oil_pressure: "Oil pressure", oil_temperature: "Oil temperature", fuel_flow: "Fuel flow" };
  for (const k of Object.keys(labels) as (keyof typeof r.baseline)[]) {
    rows.push({ key: `t-${k}`, label: labels[k], current: num(r.baseline[k]), scenario: num(r.scenario[k]), changed: r.delta ? r.delta[k] !== 0 : false });
  }
  if (r.physics_consistency) {
    const names: Record<string, string> = { cht: "CHT", egt: "EGT", oil_pressure: "Oil pressure", oil_temperature: "Oil temperature", fuel_flow: "Fuel flow" };
    for (const [k, p] of Object.entries(r.physics_consistency.parameters)) {
      if (!p) continue;
      rows.push({ key: `p-${k}`, label: `Physics · ${names[k] ?? k}`, current: p.baseline_status, scenario: p.status, changed: p.baseline_status !== p.status });
    }
  }
  return rows;
}

export function TwinCompare({ result, stale }: { result: WhatIfResponse; stale: boolean }) {
  const rows = compareRows(result);
  if (rows.length === 0) return null;
  return (
    <div className={card} style={{ borderColor: SIM, borderStyle: "dashed" }} data-testid="twin-compare">
      <div className="mb-2 flex items-center gap-2">
        <span className="rounded-sm border px-2 py-0.5 text-[10px] font-bold tracking-wider" style={{ borderColor: SIM, color: SIM }}>
          WHAT-IF SIMULATION
        </span>
        <span className="text-[11px] font-semibold uppercase tracking-wide text-textFaint">Current vs scenario</span>
      </div>
      {stale && (
        <div className="mb-2 rounded-sm border border-warning bg-warningBg px-2 py-1 text-[11px] text-warning" data-testid="twin-compare-stale">
          Scenario values changed since this result — run again to update.
        </div>
      )}
      <table className="w-full table-fixed text-xs">
        <thead>
          <tr className="text-left text-[10px] uppercase text-textFaint">
            <th className="w-[36%] pb-1 font-semibold">Item</th>
            <th className="pb-1 text-right font-semibold">Current</th>
            <th className="pb-1 text-right font-semibold">Scenario</th>
          </tr>
        </thead>
        <tbody className="font-mono">
          {rows.map((r) => (
            <tr key={r.key} className="border-t border-border" data-testid={`compare-${r.key}`} data-changed={r.changed ? "true" : undefined}>
              <td className="py-1 font-sans font-semibold text-textMuted">{r.label}</td>
              <td className="py-1 text-right">{r.current}</td>
              <td className={`py-1 text-right ${r.changed ? "font-semibold text-accent" : ""}`}>
                {r.changed && <span aria-hidden>▸ </span>}
                {r.scenario}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="mt-1.5 text-[10px] text-textFaint">“Current” is the recomputed baseline window the backend used for this scenario.</div>
    </div>
  );
}
