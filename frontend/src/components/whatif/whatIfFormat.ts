import { ApiError, ApiTimeoutError } from "@/services/apiClient";
import type { WhatIfParam, WhatIfValues } from "@/types";

export const PARAM_LABELS: Record<WhatIfParam, string> = {
  rpm: "RPM",
  cht: "CHT",
  egt: "EGT",
  oil_pressure: "Oil Pressure",
  oil_temperature: "Oil Temperature",
  fuel_flow: "Fuel Flow",
};

/** Up to 2 decimals, no trailing zeros ("4908.7", "5300"). */
export function fmtNum(value: number): string {
  return Number(value.toFixed(2)).toString();
}

/** Explicit sign so direction never depends on colour alone ("+391.3", "-11.1", "0"). */
export function fmtSigned(value: number): string {
  const rounded = Number(value.toFixed(2));
  if (rounded === 0) return "0";
  return rounded > 0 ? `+${rounded}` : `${rounded}`;
}

export function fmtPct(value: number): string {
  return `${Number((value * 100).toFixed(1))}%`;
}

/** Scenario differs from current by more than float noise. */
export function differs(a: number, b: number): boolean {
  return Math.abs(a - b) > 1e-9;
}

export function changedParameters(
  current: WhatIfValues,
  scenario: WhatIfValues,
  params: readonly WhatIfParam[],
): Partial<Record<WhatIfParam, number>> {
  const out: Partial<Record<WhatIfParam, number>> = {};
  for (const p of params) {
    if (differs(current[p], scenario[p])) out[p] = scenario[p];
  }
  return out;
}

/** Concise, user-facing message for a failed What-If request. Never exposes stack traces or raw payloads. */
export function describeWhatIfError(error: unknown): string {
  if (error instanceof ApiTimeoutError) {
    return "The simulation timed out. The models may still be loading — try again in a moment.";
  }
  if (error instanceof ApiError) {
    if (error.status === 400) {
      const detail = error.detail as { simulation_status?: string; errors?: unknown } | string | undefined;
      if (detail && typeof detail === "object" && detail.simulation_status === "INVALID_INPUT") {
        const errors = Array.isArray(detail.errors) ? detail.errors.filter((e): e is string => typeof e === "string") : [];
        return errors.length > 0 ? `Invalid input: ${errors.join("; ")}` : "Invalid input — check the scenario values.";
      }
      return "The request was rejected as invalid.";
    }
    if (error.status === 403) return "You don't have permission to run What-If simulations (maintenance engineer, program manager or admin required).";
    if (error.status === 404) return "Engine not found.";
    if (error.status === 401) return "Your session has expired — sign in again.";
    if (error.status >= 500) return "The server hit an error running the simulation. Try again; if it persists, contact support.";
    return `Request failed (${error.status}).`;
  }
  return "Couldn't reach the server. Check your connection and try again.";
}

export { parseBackendTs, fmtAge } from "@/lib/utils";

export const STALE_AFTER_MS = 5 * 60_000;
