import type { WhatIfConfig, WhatIfParam, WhatIfResponse } from "@/types";
import { WHAT_IF_PARAMS } from "@/types";
import { PARAM_LABELS, fmtNum, fmtSigned } from "./whatIfFormat";

export interface SummaryLine {
  key: string;
  text: string;
  /** True when this model/output actually moved (drives the emphasis dot, not the wording). */
  changed: boolean;
}

/**
 * Plain-language recap built ONLY from values in the backend response
 * (no LLM, no client-side model logic): it restates what the real models
 * returned so the operator doesn't have to diff six cards by eye.
 */
export function buildSummary(r: WhatIfResponse, config: WhatIfConfig): SummaryLine[] {
  const out: SummaryLine[] = [];
  const m = r.model_results;
  const hf = r.health_fusion;
  if (!m || !hf || !r.delta) return out;

  const moved = WHAT_IF_PARAMS.filter((p: WhatIfParam) => r.delta![p] !== 0);
  out.push({
    key: "inputs",
    changed: moved.length > 0,
    text:
      moved.length === 0
        ? "Scenario equals the baseline — no parameter was changed."
        : `Scenario changes: ${moved.map((p) => `${PARAM_LABELS[p]} ${fmtSigned(r.delta![p])} ${config.parameters[p].unit}`).join(", ")}.`,
  });

  const missing = hf.scenario.missing_sources;
  if (missing.length > 0) {
    out.push({ key: "health", changed: false, text: `Health: unavailable — insufficient data from ${missing.join(", ").toUpperCase()}.` });
  } else {
    out.push({
      key: "health",
      changed: hf.score_delta !== 0,
      text: `Health: ${fmtNum(hf.baseline.score)} → ${fmtNum(hf.scenario.score)} (${fmtSigned(hf.score_delta)}).`,
    });
  }

  const rul = m.rul;
  if (rul.baseline.status === "COMPLETED" && rul.scenario.status === "COMPLETED") {
    out.push({
      key: "rul",
      changed: rul.changed,
      text: `RUL: ${fmtNum(rul.baseline.rul_cycles ?? 0)} → ${fmtNum(rul.scenario.rul_cycles ?? 0)} cycles${
        rul.delta_cycles !== null ? ` (${fmtSigned(rul.delta_cycles)})` : ""
      }.`,
    });
  } else {
    out.push({ key: "rul", changed: false, text: `RUL: ${rul.scenario.status === "INSUFFICIENT_DATA" ? "insufficient data" : rul.scenario.status.toLowerCase().replace("_", " ")}.` });
  }

  const f = m.fault;
  if (f.scenario.status === "COMPLETED" && f.baseline.status === "COMPLETED") {
    const label = (x: typeof f.baseline) => `${x.fault_class} · ${x.state}`;
    out.push({
      key: "fault",
      changed: f.changed,
      text:
        (f.changed ? `Fault: ${label(f.baseline)} → ${label(f.scenario)}` : `Fault: unchanged (${label(f.scenario)})`) +
        (f.scenario.reliable === false ? " — advisory, not scored." : "."),
    });
  } else {
    out.push({ key: "fault", changed: false, text: `Fault: ${f.scenario.status === "INSUFFICIENT_DATA" ? "insufficient data" : f.scenario.status.toLowerCase().replace("_", " ")}.` });
  }

  const b = m.bearing;
  out.push({
    key: "bearing",
    changed: b.changed,
    text: b.changed
      ? `Bearing: ${b.baseline.class_label} → ${b.scenario.class_label} (driven by RPM only).`
      : `Bearing: unchanged — ${b.input_changed ? "RPM changed but the model output did not" : "the scenario did not modify its inputs"}.`,
  });

  const a = m.auxiliary;
  if (a.baseline.status === "COMPLETED" && a.scenario.status === "COMPLETED") {
    out.push({
      key: "aux",
      changed: a.changed,
      text: a.changed
        ? `Auxiliary: ${a.baseline.risk_level} ${fmtNum(a.baseline.failure_probability_pct ?? 0)}% → ${a.scenario.risk_level} ${fmtNum(a.scenario.failure_probability_pct ?? 0)}%.`
        : `Auxiliary: unchanged (${a.scenario.risk_level} ${fmtNum(a.scenario.failure_probability_pct ?? 0)}%).`,
    });
  } else {
    out.push({ key: "aux", changed: false, text: `Auxiliary: ${a.scenario.status.toLowerCase().replace("_", " ")}.` });
  }

  if (r.alerts) {
    const al = r.alerts;
    out.push({
      key: "alerts",
      changed: al.change !== "NONE" && al.change !== "UNCHANGED",
      text:
        al.change === "NONE"
          ? "Simulated alerts: none would fire."
          : `Simulated alert (${al.change.toLowerCase()}): ${al.scenario ? al.scenario.severity.toUpperCase() : "cleared"}.`,
    });
  }
  return out;
}
