import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CONFIG, makeResponse } from "@/test/whatIfFixtures";
import real from "@/test/fixtures/real-what-if-responses.json";
import type { WhatIfResponse } from "@/types";
import { WhatIfResults } from "./WhatIfResults";

/**
 * Contract test against payloads captured from the REAL backend
 * (backend/app/services/what_if_scenario.run_scenario, serialised as the
 * API returns it) — guards against the hand-written fixtures and the
 * TypeScript types drifting from what the server actually sends.
 * Regenerate the JSON by re-running the capture script from the Phase C
 * notes if the backend response shape changes.
 */

function shape(value: unknown): unknown {
  if (Array.isArray(value)) return value.length ? [shape(value[0])] : [];
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value as Record<string, unknown>).map(([k, v]) => [k, shape(v)]));
  }
  return value === null ? "null" : typeof value;
}

function keyPaths(value: unknown, prefix = ""): string[] {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return Object.entries(value as Record<string, unknown>).flatMap(([k, v]) => [
      `${prefix}${k}`,
      ...(k === "feature_mapping" || k === "model_versions" ? [] : keyPaths(v, `${prefix}${k}.`)),
    ]);
  }
  return [];
}

const full = real.full as unknown as WhatIfResponse;
const short = real.short as unknown as WhatIfResponse;
const empty = real.empty as unknown as WhatIfResponse;

describe("What-If contract with the real backend payload", () => {
  it("the backend sends no undeclared top-level/structural fields (extras are only optional model-output detail)", () => {
    const fixtureKeys = new Set(keyPaths(makeResponse()));
    // Optional model-output detail the types declare as optional (class ids,
    // probabilities, wear seed, aux detail, ...). Anything OUTSIDE these
    // prefixes that isn't in the fixture means the API grew a field the
    // types don't know about — update types/index.ts and the fixture.
    const optionalDetail = /^(window\.aux_|model_results\.(rul|fault|bearing|auxiliary)\.(baseline|scenario)\.|alerts\.(baseline|scenario)\.)/;
    const unknown = keyPaths(full).filter((k) => !fixtureKeys.has(k) && !k.startsWith("feature_mapping") && !optionalDetail.test(k));
    expect(unknown).toEqual([]);
  });

  it("every key the UI relies on exists in the real payload", () => {
    const realKeys = new Set(keyPaths(full));
    const required = keyPaths(makeResponse()).filter(
      // optional/nullable-by-design in a real run
      (k) =>
        !["message", "live_reference", "assumptions"].includes(k) &&
        !k.startsWith("model_versions") &&
        !k.startsWith("live_reference") &&
        !/^alerts\.(baseline|scenario)\./.test(k), // null when no alert fires
    );
    const absent = required.filter((k) => !realKeys.has(k));
    expect(absent).toEqual([]);
  });

  it("primitive types match at shared paths", () => {
    const a = shape(full) as Record<string, unknown>;
    const b = shape(makeResponse()) as Record<string, unknown>;
    for (const k of ["simulation_status", "mode", "scenario_type", "perturbation_count", "baseline_timestamp"]) {
      expect(typeof a[k]).toBe(typeof b[k]);
    }
    expect(shape(full.health_fusion!.scenario.sources)).toEqual(shape(makeResponse().health_fusion!.scenario.sources));
    expect(shape(full.alerts)).toMatchObject({ simulation: "boolean", change: "string" });
  });

  it("renders a real COMPLETED payload", () => {
    render(<WhatIfResults result={full} config={CONFIG} stale={false} />);
    expect(screen.getByTestId("whatif-badge")).toHaveTextContent("WHAT-IF SIMULATION");
    expect(screen.getByTestId("whatif-status")).toHaveTextContent("COMPLETED");
    for (const s of ["rul", "fault", "bearing", "aux"]) expect(screen.getByTestId(`whatif-fusion-${s}`)).toBeInTheDocument();
    for (const p of ["cht", "egt", "oil_pressure", "oil_temperature", "fuel_flow"]) {
      expect(screen.getByTestId(`whatif-physics-${p}`)).toBeInTheDocument();
    }
    expect(screen.getByTestId("whatif-alerts-badge")).toHaveTextContent("SIMULATION");
    expect(screen.getByTestId("whatif-bearing-note")).toHaveTextContent(full.model_results!.bearing.note);
    expect(screen.getByTestId("whatif-perturbed")).toHaveTextContent(
      `Perturbed readings: ${full.window.perturbed_readings} / ${full.window.total_readings} loaded`,
    );
    expect(screen.getByTestId("whatif-compare-rpm")).toHaveTextContent("+400 RPM");
  });

  it("renders a real INSUFFICIENT_DATA payload without RUL 0 / Normal / a health number", () => {
    render(<WhatIfResults result={short} config={CONFIG} stale={false} />);
    expect(screen.getByTestId("whatif-insufficient")).toBeInTheDocument();
    expect(screen.getByTestId("whatif-health-unavailable")).toBeInTheDocument();
    expect(screen.getByTestId("whatif-rul")).toHaveTextContent("Insufficient data");
    expect(screen.getByTestId("whatif-rul")).not.toHaveTextContent("0 cycles");
    expect(screen.getByTestId("whatif-fault")).toHaveTextContent("Insufficient data");
    expect(screen.getByTestId("whatif-fusion-rul")).toHaveTextContent("n/a");
  });

  it("renders the real no-telemetry payload as unavailable", () => {
    render(<WhatIfResults result={empty} config={CONFIG} stale={false} />);
    expect(screen.getByTestId("whatif-no-telemetry")).toHaveTextContent(/unavailable/i);
    expect(screen.queryByTestId("whatif-health")).not.toBeInTheDocument();
    expect(screen.queryByTestId("whatif-compare")).not.toBeInTheDocument();
  });
});
