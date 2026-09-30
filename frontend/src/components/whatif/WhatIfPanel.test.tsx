import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, ApiTimeoutError } from "@/services/apiClient";
import { CONFIG, CURRENT, TELEMETRY, makeInsufficientResponse, makeResponse } from "@/test/whatIfFixtures";
import type { WhatIfResponse } from "@/types";

vi.mock("@/services/resources", () => ({
  enginesApi: {
    telemetryLatest: vi.fn(),
    // Any of these being called would mean the What-If panel touched live engine data.
    get: vi.fn(),
    faultsLatest: vi.fn(),
    createMaintenanceLog: vi.fn(),
    // read-only helpers the baseline picker uses
    healthScore: vi.fn(),
    telemetryAt: vi.fn(),
  },
  simulationApi: {
    whatIfConfig: vi.fn(),
    runParameterWhatIf: vi.fn(),
    runReplay: vi.fn(),
    runWhatIf: vi.fn(),
    get: vi.fn(),
  },
  alertsApi: { acknowledge: vi.fn(), list: vi.fn() },
}));

import { alertsApi, enginesApi, simulationApi } from "@/services/resources";
import { WhatIfPanel, buildBaselineOptions } from "./WhatIfPanel";
import { parseBackendTs } from "./whatIfFormat";

const telemetryLatest = vi.mocked(enginesApi.telemetryLatest);
const whatIfConfig = vi.mocked(simulationApi.whatIfConfig);
const runParameterWhatIf = vi.mocked(simulationApi.runParameterWhatIf);

const PARAMS = ["rpm", "cht", "egt", "oil_pressure", "oil_temperature", "fuel_flow"] as const;

async function renderPanel() {
  render(<WhatIfPanel engineId="eng-1" />);
  await screen.findByTestId("whatif-controls");
}

function slider(label: string) {
  return screen.getByLabelText(`${label} scenario`) as HTMLInputElement;
}
function scenarioInput(param: string) {
  return screen.getByTestId(`whatif-scenario-${param}`) as HTMLInputElement;
}

async function runAndWait(response: WhatIfResponse = makeResponse()) {
  runParameterWhatIf.mockResolvedValueOnce(response);
  fireEvent.click(screen.getByTestId("whatif-run"));
  await screen.findByTestId("whatif-results");
}

beforeEach(() => {
  vi.clearAllMocks();
  telemetryLatest.mockResolvedValue(TELEMETRY);
  whatIfConfig.mockResolvedValue(CONFIG);
  vi.mocked(enginesApi.healthScore).mockResolvedValue({ history: [] } as never);
});

describe("What-If controls", () => {
  it("opens with the actual current telemetry (scenario == current, delta 0)", async () => {
    await renderPanel();
    expect(telemetryLatest).toHaveBeenCalledWith("eng-1");
    for (const p of PARAMS) {
      expect(scenarioInput(p).value).toBe(String(Number(CURRENT[p].toFixed(2))));
      expect(screen.getByTestId(`whatif-current-${p}`)).toHaveTextContent(String(Number(CURRENT[p].toFixed(2))));
      expect(screen.getByTestId(`whatif-delta-${p}`)).toHaveTextContent(/^0 /);
    }
    expect(screen.getByTestId("whatif-live-badge")).toHaveTextContent("LIVE ENGINE");
    expect(screen.getByTestId("whatif-run")).toBeDisabled();
    expect(screen.getByTestId("whatif-hint")).toBeInTheDocument();
  });

  it("shows an explicit unavailable state — no substituted values — when telemetry is missing", async () => {
    telemetryLatest.mockRejectedValue(new ApiError(404, "No telemetry"));
    render(<WhatIfPanel engineId="eng-1" />);
    expect(await screen.findByTestId("whatif-unavailable")).toHaveTextContent(/unavailable/i);
    expect(screen.queryByTestId("whatif-controls")).not.toBeInTheDocument();
    expect(screen.queryByTestId("whatif-run")).not.toBeInTheDocument();
  });

  it("warns when the latest reading is old, and not when it is fresh; naive timestamps are read as UTC", async () => {
    await renderPanel(); // fixture reading is from 2026-09-30 — long past
    expect(screen.getByTestId("whatif-old-telemetry")).toHaveTextContent(/doesn.t appear to be streaming/);
    cleanup();

    const fresh = new Date(Date.now() - 20_000).toISOString().replace("Z", ""); // naive UTC, as the backend sends
    telemetryLatest.mockResolvedValue({ ...TELEMETRY, ts: fresh });
    await renderPanel();
    expect(screen.queryByTestId("whatif-old-telemetry")).not.toBeInTheDocument();
    expect(parseBackendTs("2026-09-30T08:06:33.041266").toISOString()).toBe("2026-09-30T08:06:33.041Z");
    expect(parseBackendTs("2026-09-30T08:06:33Z").toISOString()).toBe("2026-09-30T08:06:33.000Z");
  });

  it("represents all six parameters with labels, units and config-driven slider ranges", async () => {
    await renderPanel();
    const expected = {
      rpm: ["RPM", "RPM"],
      cht: ["CHT", "°C"],
      egt: ["EGT", "°C"],
      oil_pressure: ["Oil Pressure", "psi"],
      oil_temperature: ["Oil Temperature", "°C"],
      fuel_flow: ["Fuel Flow", "GPH"],
    } as const;
    for (const p of PARAMS) {
      const row = screen.getByTestId(`whatif-row-${p}`);
      expect(row).toHaveTextContent(expected[p][0]);
      expect(row).toHaveTextContent(expected[p][1]);
      const s = slider(expected[p][0]);
      // Ranges/steps come from /simulation/what-if/config, not the component.
      expect(s.min).toBe(String(CONFIG.parameters[p].min));
      expect(s.max).toBe(String(CONFIG.parameters[p].max));
      expect(s.step).toBe(String(CONFIG.parameters[p].step));
    }
  });

  it("slider changes update the scenario value and show the delta", async () => {
    await renderPanel();
    fireEvent.change(slider("RPM"), { target: { value: "5300" } });
    expect(scenarioInput("rpm").value).toBe("5300");
    expect(screen.getByTestId("whatif-delta-rpm")).toHaveTextContent("+391.3 RPM");
    fireEvent.change(slider("Oil Pressure"), { target: { value: "82" } });
    expect(screen.getByTestId("whatif-delta-oil_pressure")).toHaveTextContent("-11.07 psi");
    // current stays untouched
    expect(screen.getByTestId("whatif-current-rpm")).toHaveTextContent("4908.7 RPM");
    expect(screen.getByTestId("whatif-run")).toBeEnabled();
  });

  it("clamps typed values into the configured range", async () => {
    await renderPanel();
    fireEvent.change(scenarioInput("rpm"), { target: { value: "999999" } });
    expect(scenarioInput("rpm").value).toBe(String(CONFIG.parameters.rpm.max));
  });
});

describe("Running a What-If", () => {
  it("sends only the changed parameters, the engine id and the pinned baseline timestamp", async () => {
    await renderPanel();
    fireEvent.change(slider("RPM"), { target: { value: "5300" } });
    fireEvent.change(slider("EGT"), { target: { value: "880" } });
    await runAndWait();
    expect(runParameterWhatIf).toHaveBeenCalledTimes(1);
    expect(runParameterWhatIf).toHaveBeenCalledWith("eng-1", { rpm: 5300, egt: 880 }, TELEMETRY.ts, 60_000);
  });

  it("shows CALCULATING… and disables Run while the request is in flight", async () => {
    await renderPanel();
    fireEvent.change(slider("CHT"), { target: { value: "170" } });
    let resolve!: (r: WhatIfResponse) => void;
    runParameterWhatIf.mockReturnValueOnce(new Promise<WhatIfResponse>((r) => (resolve = r)));
    fireEvent.click(screen.getByTestId("whatif-run"));

    const btn = await screen.findByText("CALCULATING…");
    expect(btn).toBeDisabled();
    expect(screen.getByTestId("whatif-calculating")).toBeInTheDocument();
    fireEvent.click(btn); // double-click guard
    expect(runParameterWhatIf).toHaveBeenCalledTimes(1);

    resolve(makeResponse());
    await screen.findByTestId("whatif-results");
    expect(screen.queryByTestId("whatif-calculating")).not.toBeInTheDocument();
    expect(screen.getByTestId("whatif-run")).toHaveTextContent("RUN WHAT-IF");
  });

  it("renders a successful result entirely from the backend response", async () => {
    await renderPanel();
    fireEvent.change(slider("RPM"), { target: { value: "5300" } });
    await runAndWait();

    expect(screen.getByTestId("whatif-badge")).toHaveTextContent("WHAT-IF SIMULATION");
    expect(screen.getByTestId("whatif-health-baseline")).toHaveTextContent("65");
    expect(screen.getByTestId("whatif-health-scenario")).toHaveTextContent("54");
    expect(screen.getByTestId("whatif-health-delta")).toHaveTextContent("-11");
    expect(screen.getByTestId("whatif-rul")).toHaveTextContent("126 cycles");
    expect(screen.getByTestId("whatif-rul")).toHaveTextContent("91 cycles");
    expect(screen.getByTestId("whatif-rul-delta")).toHaveTextContent("-35 cycles");
    expect(screen.getByTestId("whatif-fault")).toHaveTextContent("No Failure · NORMAL");
    expect(screen.getByTestId("whatif-fault")).toHaveTextContent("Compass Failure · ANOMALY_DETECTED");
    expect(screen.getByTestId("whatif-fault")).toHaveTextContent("CHANGED");
    expect(screen.getByTestId("whatif-bearing")).toHaveTextContent("OR_021 · Outer Race");
    expect(screen.getByTestId("whatif-aux")).toHaveTextContent("MODERATE · 30.8%");

    // Health Fusion: all four sources, zero shown explicitly.
    for (const s of ["rul", "fault", "bearing", "aux"]) expect(screen.getByTestId(`whatif-fusion-${s}`)).toBeInTheDocument();
    const faultRow = screen.getByTestId("whatif-fusion-fault");
    expect(within(faultRow).getAllByText("0").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByTestId("whatif-fusion-rul")).toHaveTextContent("+13");

    // Physics: 5 channels, no RPM.
    for (const p of ["cht", "egt", "oil_pressure", "oil_temperature", "fuel_flow"]) {
      expect(screen.getByTestId(`whatif-physics-${p}`)).toBeInTheDocument();
    }
    expect(screen.queryByTestId("whatif-physics-rpm")).not.toBeInTheDocument();
    expect(screen.getByTestId("whatif-physics-egt")).toHaveTextContent("REVIEW");
    expect(screen.getByTestId("whatif-physics-egt")).toHaveTextContent("(was CONSISTENT)");

    // Current vs scenario table with backend units.
    expect(screen.getByTestId("whatif-compare-rpm")).toHaveTextContent("4908.7 RPM");
    expect(screen.getByTestId("whatif-compare-rpm")).toHaveTextContent("5300 RPM");
    expect(screen.getByTestId("whatif-compare-rpm")).toHaveTextContent("+391.3 RPM");
    expect(screen.getByTestId("whatif-compare-fuel_flow")).toHaveTextContent("GPH");

    // Methodology transparency.
    expect(screen.getByTestId("whatif-method")).toHaveTextContent("Baseline: recent engine telemetry window");
    expect(screen.getByTestId("whatif-perturbed")).toHaveTextContent("Perturbed readings: 10 / 89 loaded");
    expect(screen.getByTestId("whatif-method")).toHaveTextContent("PARAMETER PERTURBATION");
    expect(screen.getByText(/last persisted LIVE score/)).toBeInTheDocument();
  });

  it("displays the backend's bearing/aux input_changed flags and notes verbatim", async () => {
    await renderPanel();
    fireEvent.change(slider("CHT"), { target: { value: "170" } });
    await runAndWait();
    const r = makeResponse();
    expect(screen.getByTestId("whatif-bearing-note")).toHaveTextContent(r.model_results!.bearing.note);
    expect(screen.getByTestId("whatif-bearing-input")).toHaveTextContent("Scenario modifies bearing inputs: no");
    expect(screen.getByTestId("whatif-bearing")).toHaveTextContent("UNCHANGED");
    expect(screen.getByTestId("whatif-aux-input")).toHaveTextContent("Scenario modifies auxiliary inputs: yes");
    expect(screen.queryByTestId("whatif-aux-note")).not.toBeInTheDocument(); // note is null -> nothing invented
  });

  it("shows the RPM-driven bearing note and the aux 'unchanged' note when the backend sends them", async () => {
    await renderPanel();
    fireEvent.change(slider("RPM"), { target: { value: "5300" } });
    const r = makeResponse();
    r.model_results!.bearing = { ...r.model_results!.bearing, input_changed: true, changed: true, note: "Bearing output changed; RPM only." };
    r.model_results!.auxiliary = { ...r.model_results!.auxiliary, input_changed: false, note: "Auxiliary prediction unchanged: inputs untouched." };
    await runAndWait(r);
    expect(screen.getByTestId("whatif-bearing-note")).toHaveTextContent("Bearing output changed; RPM only.");
    expect(screen.getByTestId("whatif-bearing-input")).toHaveTextContent("yes (RPM)");
    expect(screen.getByTestId("whatif-aux-note")).toHaveTextContent("Auxiliary prediction unchanged");
  });

  it("marks simulation alerts as SIMULATION and never presents them as live", async () => {
    await renderPanel();
    fireEvent.change(slider("EGT"), { target: { value: "880" } });
    await runAndWait();
    const box = screen.getByTestId("whatif-alerts");
    expect(within(box).getByTestId("whatif-alerts-badge")).toHaveTextContent("SIMULATION");
    expect(box).toHaveTextContent(/never created or broadcast as live alerts/i);
    expect(screen.getByTestId("whatif-alerts-change")).toHaveTextContent("NEW");
    expect(screen.getByTestId("whatif-alert-scenario")).toHaveTextContent("RUL: 91 cycles remaining");
    // the page's live-alert plumbing is never touched
    expect(vi.mocked(alertsApi.acknowledge)).not.toHaveBeenCalled();
    expect(vi.mocked(alertsApi.list)).not.toHaveBeenCalled();
  });

  it("says so when no simulated alert would fire (no fabricated alert)", async () => {
    await renderPanel();
    fireEvent.change(slider("CHT"), { target: { value: "160" } });
    const r = makeResponse();
    r.alerts = { simulation: true, baseline: null, scenario: null, change: "NONE" };
    await runAndWait(r);
    expect(screen.getByTestId("whatif-alert-none")).toBeInTheDocument();
    expect(screen.queryByTestId("whatif-alert-scenario")).not.toBeInTheDocument();
  });

  it("renders INSUFFICIENT_DATA as unavailable — not RUL 0, not Normal, not healthy", async () => {
    await renderPanel();
    fireEvent.change(slider("CHT"), { target: { value: "170" } });
    await runAndWait(makeInsufficientResponse());

    expect(screen.getByTestId("whatif-status")).toHaveTextContent("INSUFFICIENT_DATA");
    expect(screen.getByTestId("whatif-insufficient")).toHaveTextContent("20 readings available");
    expect(screen.getByTestId("whatif-health-unavailable")).toHaveTextContent(/Unavailable/);
    expect(screen.queryByTestId("whatif-health-scenario")).not.toBeInTheDocument();

    const rul = screen.getByTestId("whatif-rul");
    expect(rul).toHaveTextContent("Insufficient data");
    expect(rul).not.toHaveTextContent("0 cycles");
    expect(screen.getByTestId("whatif-rul-delta")).toHaveTextContent("—");
    const fault = screen.getByTestId("whatif-fault");
    expect(fault).toHaveTextContent("Insufficient data");
    expect(fault).not.toHaveTextContent("Normal");
    expect(fault).not.toHaveTextContent("No Failure");
    // contributors that had no output are n/a, not a healthy-looking 0
    expect(screen.getByTestId("whatif-fusion-rul")).toHaveTextContent("n/a");
    expect(screen.getByTestId("whatif-fusion-fault")).toHaveTextContent("n/a");
  });

  it("handles an engine with no telemetry at all", async () => {
    await renderPanel();
    fireEvent.change(slider("CHT"), { target: { value: "170" } });
    const r = makeResponse({
      simulation_status: "INSUFFICIENT_DATA",
      baseline: null, scenario: null, delta: null, model_results: null, health_fusion: null,
      physics_consistency: null, alerts: null, baseline_timestamp: null,
      message: "No telemetry recorded for this engine — current engine data unavailable.",
    });
    await runAndWait(r);
    expect(screen.getByTestId("whatif-no-telemetry")).toHaveTextContent(/unavailable/i);
    expect(screen.queryByTestId("whatif-health")).not.toBeInTheDocument();
  });

  it.each([
    ["MODEL_UNAVAILABLE", "whatif-model-unavailable", /unavailable on the server/i],
    ["ERROR", "whatif-model-error", /model failed/i],
  ] as const)("shows a concise banner for %s", async (status, testId, text) => {
    await renderPanel();
    fireEvent.change(slider("CHT"), { target: { value: "170" } });
    const r = makeResponse({ simulation_status: status });
    r.model_results!.bearing.scenario = { status: status === "ERROR" ? "ERROR" : "MODEL_UNAVAILABLE", message: "Bearing CNN failed to load" };
    await runAndWait(r);
    expect(screen.getByTestId(testId)).toHaveTextContent(text);
    expect(screen.getByTestId("whatif-bearing")).toHaveTextContent("Bearing CNN failed to load");
  });

  it("tells the user when values were clamped, without touching their sliders", async () => {
    await renderPanel();
    fireEvent.change(slider("EGT"), { target: { value: "990" } });
    const r = makeResponse();
    r.window.clamped_values = 3;
    await runAndWait(r);
    expect(screen.getByTestId("whatif-clamped")).toHaveTextContent(/clamped/i);
    expect(scenarioInput("egt").value).toBe("990");
  });

  it("flags results as stale when sliders move after a run", async () => {
    await renderPanel();
    fireEvent.change(slider("RPM"), { target: { value: "5300" } });
    await runAndWait();
    expect(screen.queryByTestId("whatif-stale")).not.toBeInTheDocument();
    fireEvent.change(slider("RPM"), { target: { value: "5400" } });
    expect(screen.getByTestId("whatif-stale")).toBeInTheDocument();
  });
});

describe("Errors", () => {
  it.each([
    [new ApiError(400, { simulation_status: "INVALID_INPUT", errors: ["'rpm'=999 outside configured range [0, 6500] RPM"] }), /Invalid input: 'rpm'=999 outside/],
    [new ApiError(403, "Forbidden"), /don't have permission/],
    [new ApiError(404, "Engine not found"), /Engine not found/],
    [new ApiTimeoutError(60000), /timed out/i],
    [new TypeError("Failed to fetch"), /Couldn't reach the server/],
    [new ApiError(500, "Traceback (most recent call last): secret stack"), /server hit an error/],
  ])("shows a concise message for %#", async (err, text) => {
    await renderPanel();
    fireEvent.change(slider("CHT"), { target: { value: "170" } });
    runParameterWhatIf.mockRejectedValueOnce(err);
    fireEvent.click(screen.getByTestId("whatif-run"));
    const alert = await screen.findByTestId("whatif-error");
    expect(alert).toHaveTextContent(text);
    expect(alert).not.toHaveTextContent(/Traceback|secret stack/);
    expect(screen.queryByTestId("whatif-results")).not.toBeInTheDocument();
    expect(screen.getByTestId("whatif-run")).toBeEnabled(); // can retry
  });
});

describe("Reset & isolation from live state", () => {
  it("RESET TO CURRENT restores every slider, clears results, and doesn't modify live state", async () => {
    await renderPanel();
    for (const [label, v] of [["RPM", "5300"], ["CHT", "170"], ["EGT", "880"], ["Oil Pressure", "82"], ["Oil Temperature", "108"], ["Fuel Flow", "4.2"]]) {
      fireEvent.change(slider(label), { target: { value: v } });
    }
    await runAndWait();
    telemetryLatest.mockClear();

    fireEvent.click(screen.getByTestId("whatif-reset"));

    for (const p of PARAMS) {
      expect(scenarioInput(p).value).toBe(String(Number(CURRENT[p].toFixed(2))));
      expect(screen.getByTestId(`whatif-delta-${p}`)).toHaveTextContent(/^0 /);
    }
    expect(screen.queryByTestId("whatif-results")).not.toBeInTheDocument();
    expect(screen.getByTestId("whatif-run")).toBeDisabled();
    expect(telemetryLatest).not.toHaveBeenCalled(); // reset is purely local
  });

  it("Refresh current re-reads telemetry and discards results computed against the old baseline", async () => {
    await renderPanel();
    fireEvent.change(slider("RPM"), { target: { value: "5300" } });
    await runAndWait();
    telemetryLatest.mockResolvedValueOnce({ ...TELEMETRY, ts: "2026-09-30T08:00:00", rpm: 3000 });
    fireEvent.click(screen.getByTestId("whatif-refresh"));
    await waitFor(() => expect(screen.getByTestId("whatif-current-rpm")).toHaveTextContent("3000 RPM"));
    expect(screen.queryByTestId("whatif-results")).not.toBeInTheDocument();
    expect((screen.getByTestId("whatif-scenario-rpm") as HTMLInputElement).value).toBe("3000");
  });

  it("ignores a response that arrives after Reset", async () => {
    await renderPanel();
    fireEvent.change(slider("CHT"), { target: { value: "170" } });
    let resolve!: (r: WhatIfResponse) => void;
    runParameterWhatIf.mockReturnValueOnce(new Promise<WhatIfResponse>((r) => (resolve = r)));
    fireEvent.click(screen.getByTestId("whatif-run"));
    await screen.findByTestId("whatif-calculating");
    fireEvent.click(screen.getByTestId("whatif-reset"));
    resolve(makeResponse());
    await waitFor(() => expect(screen.queryByTestId("whatif-calculating")).not.toBeInTheDocument());
    expect(screen.queryByTestId("whatif-results")).not.toBeInTheDocument();
  });

  it("running a scenario leaves live telemetry display and live APIs untouched", async () => {
    await renderPanel();
    fireEvent.change(slider("RPM"), { target: { value: "5300" } });
    await runAndWait();

    // LIVE and WHAT-IF are visibly distinct labelled regions
    expect(within(screen.getByTestId("whatif-live")).getByText("LIVE ENGINE")).toBeInTheDocument();
    expect(screen.getByTestId("whatif-badge")).toHaveTextContent("WHAT-IF SIMULATION");
    expect(screen.getByTestId("whatif-live")).not.toHaveTextContent("5300");
    // "Current" is still the real reading
    expect(screen.getByTestId("whatif-current-rpm")).toHaveTextContent("4908.7 RPM");
    // only the read-only what-if endpoint was used; no live-engine writes/reads beyond the initial fetch
    expect(telemetryLatest).toHaveBeenCalledTimes(1);
    expect(vi.mocked(enginesApi.createMaintenanceLog)).not.toHaveBeenCalled();
    expect(vi.mocked(enginesApi.faultsLatest)).not.toHaveBeenCalled();
    // the only extra read is the one-time health-history fetch for the baseline picker
    expect(vi.mocked(enginesApi.healthScore)).toHaveBeenCalledTimes(1);
    expect(vi.mocked(enginesApi.telemetryAt)).not.toHaveBeenCalled();
    expect(vi.mocked(simulationApi.runReplay)).not.toHaveBeenCalled();
    expect(vi.mocked(simulationApi.runWhatIf)).not.toHaveBeenCalled();
  });
});


describe("Baseline picker", () => {
  const HISTORY = Array.from({ length: 60 }, (_, i) => ({
    ts: `2026-09-30T07:${String(10 + Math.floor(i / 6)).padStart(2, "0")}:${String((i % 6) * 10).padStart(2, "0")}`,
    combined_score: i === 20 ? 72 : 0,
  }));

  it("buildBaselineOptions: newest first, includes the best-scoring moment, is bounded", () => {
    const opts = buildBaselineOptions(HISTORY);
    expect(opts.length).toBeGreaterThan(1);
    expect(opts.length).toBeLessThanOrEqual(15);
    const sorted = [...opts].map((o) => o.value).sort().reverse();
    expect(opts.map((o) => o.value)).toEqual(sorted);
    expect(opts.some((o) => o.value === HISTORY[20].ts && /health 72/.test(o.label) && /best recent/.test(o.label))).toBe(true);
    expect(buildBaselineOptions([])).toEqual([]);
  });

  it("choosing a past moment loads that reading as the baseline, labels it HISTORICAL, and pins baseline_timestamp", async () => {
    vi.mocked(enginesApi.healthScore).mockResolvedValue({ history: HISTORY } as never);
    const past = { ...TELEMETRY, ts: HISTORY[20].ts, rpm: 2222, cht: 101 };
    vi.mocked(enginesApi.telemetryAt).mockResolvedValue(past);
    await renderPanel();
    await waitFor(() => expect(screen.getByTestId("whatif-baseline-select").querySelectorAll("option").length).toBeGreaterThan(1));

    fireEvent.change(screen.getByTestId("whatif-baseline-select"), { target: { value: HISTORY[20].ts } });
    await waitFor(() => expect(screen.getByTestId("whatif-current-rpm")).toHaveTextContent("2222 RPM"));
    expect(enginesApi.telemetryAt).toHaveBeenCalledWith("eng-1", HISTORY[20].ts);
    expect(screen.getByTestId("whatif-live-badge")).toHaveTextContent("HISTORICAL BASELINE");
    expect(screen.queryByTestId("whatif-old-telemetry")).not.toBeInTheDocument(); // only warns for the latest reading
    expect((screen.getByTestId("whatif-scenario-rpm") as HTMLInputElement).value).toBe("2222");

    fireEvent.change(slider("CHT"), { target: { value: "160" } });
    await runAndWait();
    expect(runParameterWhatIf).toHaveBeenCalledWith("eng-1", { cht: 160 }, HISTORY[20].ts, 60_000);
  });

  it("switching baseline discards results computed against the previous one", async () => {
    vi.mocked(enginesApi.healthScore).mockResolvedValue({ history: HISTORY } as never);
    vi.mocked(enginesApi.telemetryAt).mockResolvedValue({ ...TELEMETRY, ts: HISTORY[20].ts });
    await renderPanel();
    await waitFor(() => expect(screen.getByTestId("whatif-baseline-select").querySelectorAll("option").length).toBeGreaterThan(1));
    fireEvent.change(slider("RPM"), { target: { value: "5300" } });
    await runAndWait();
    fireEvent.change(screen.getByTestId("whatif-baseline-select"), { target: { value: HISTORY[20].ts } });
    await waitFor(() => expect(screen.queryByTestId("whatif-results")).not.toBeInTheDocument());
  });

  it("still works when the health history can't be loaded", async () => {
    vi.mocked(enginesApi.healthScore).mockRejectedValue(new Error("boom"));
    await renderPanel();
    expect(screen.getByTestId("whatif-baseline-select").querySelectorAll("option")).toHaveLength(1);
  });
});

describe("Parameter cards", () => {
  it("shows which models each parameter feeds, from the backend's feature mapping", async () => {
    await renderPanel();
    const rpm = screen.getByTestId("whatif-row-rpm");
    expect(rpm).toHaveTextContent("Feeds");
    for (const m of ["RUL", "Fault", "Bearing", "Aux"]) expect(rpm).toHaveTextContent(m);
    const egt = screen.getByTestId("whatif-row-egt");
    expect(egt).toHaveTextContent("RUL");
    expect(egt).toHaveTextContent("Fault");
    expect(egt).not.toHaveTextContent("Bearing"); // EGT does not reach the bearing model
    expect(egt).not.toHaveTextContent("Aux");
  });

  it("per-parameter reset restores only that parameter", async () => {
    await renderPanel();
    fireEvent.change(slider("RPM"), { target: { value: "5300" } });
    fireEvent.change(slider("CHT"), { target: { value: "170" } });
    fireEvent.click(within(screen.getByTestId("whatif-row-rpm")).getByLabelText("Reset RPM"));
    expect(scenarioInput("rpm").value).toBe("4908.7");
    expect(scenarioInput("cht").value).toBe("170");
    expect(within(screen.getByTestId("whatif-row-cht")).getByLabelText("Reset CHT")).toBeInTheDocument();
    expect(within(screen.getByTestId("whatif-row-rpm")).queryByLabelText("Reset RPM")).not.toBeInTheDocument();
  });
});

describe("Result summary", () => {
  it("restates the backend result in plain language, only from response values", async () => {
    await renderPanel();
    fireEvent.change(slider("RPM"), { target: { value: "5300" } });
    await runAndWait();
    const list = screen.getByTestId("whatif-summary");
    expect(list).toHaveTextContent("Scenario changes: RPM +391.3 RPM, EGT +38.81 °C");
    expect(list).toHaveTextContent("Health: 65 → 54 (-11)");
    expect(list).toHaveTextContent("RUL: 126 → 91 cycles (-35)");
    expect(list).toHaveTextContent("Fault: No Failure · NORMAL → Compass Failure · ANOMALY_DETECTED");
    expect(list).toHaveTextContent("Bearing: unchanged — the scenario did not modify its inputs");
    expect(list).toHaveTextContent("Auxiliary: unchanged (MODERATE 30.8%)");
    expect(list).toHaveTextContent("Simulated alert (new): WARNING");
  });

  it("says health is unavailable (not a number) when sources are missing", async () => {
    await renderPanel();
    fireEvent.change(slider("CHT"), { target: { value: "170" } });
    await runAndWait(makeInsufficientResponse());
    const list = screen.getByTestId("whatif-summary");
    expect(list).toHaveTextContent("Health: unavailable — insufficient data from RUL, FAULT.");
    expect(list).toHaveTextContent("RUL: insufficient data.");
    expect(list).toHaveTextContent("Fault: insufficient data.");
    expect(list).not.toHaveTextContent(/RUL: 0/);
  });

  it("fusion contributor bars: every source has a row; unavailable sources are marked, not zero-filled", async () => {
    await renderPanel();
    fireEvent.change(slider("CHT"), { target: { value: "170" } });
    await runAndWait(makeInsufficientResponse());
    expect(screen.getByTestId("whatif-fusion-rul")).toHaveTextContent("n/a (no model output)");
    expect(screen.getByTestId("whatif-fusion-bearing")).not.toHaveTextContent("n/a");
  });
});

describe("Advisory fault (input coverage too low)", () => {
  function withExcludedFault(): WhatIfResponse {
    const r = makeResponse();
    for (const side of [r.health_fusion!.baseline, r.health_fusion!.scenario, r.health_fusion!]) {
      side.sources.fault = { penalty: 0, active: false, forced_zero: false, available: true, excluded: true };
      side.excluded_sources = ["fault"];
    }
    r.model_results!.fault.baseline = { ...r.model_results!.fault.baseline, reliable: false, input_coverage: 0.46875 };
    r.model_results!.fault.scenario = { ...r.model_results!.fault.scenario, reliable: false, input_coverage: 0.46875 };
    return r;
  }

  it("shows the fault result as ADVISORY, marks it excluded in Health Fusion, and still shows a real health score", async () => {
    await renderPanel();
    fireEvent.change(slider("RPM"), { target: { value: "5300" } });
    await runAndWait(withExcludedFault());

    const advisory = screen.getByTestId("whatif-fault-advisory");
    expect(advisory).toHaveTextContent("ADVISORY — not scored in Health Fusion");
    expect(advisory).toHaveTextContent("only 47% of the model's input channels are measured");
    expect(screen.getByTestId("whatif-fault")).toHaveTextContent("Compass Failure"); // the result is still displayed
    expect(screen.getByTestId("whatif-fusion-fault")).toHaveTextContent("excluded (advisory — low input coverage)");
    expect(screen.getByTestId("whatif-fusion-fault")).not.toHaveTextContent("n/a"); // set aside, not "missing"
    // health is a real assessment of the other three sources — not "unavailable"
    expect(screen.queryByTestId("whatif-health-unavailable")).not.toBeInTheDocument();
    expect(screen.getByTestId("whatif-health-scenario")).toHaveTextContent("54");
    expect(screen.getByTestId("whatif-excluded-note")).toHaveTextContent("Health excludes Fault");
    expect(screen.getByTestId("whatif-summary")).toHaveTextContent("advisory, not scored");
  });

  it("no advisory chrome when the fault result is reliable", async () => {
    await renderPanel();
    fireEvent.change(slider("RPM"), { target: { value: "5300" } });
    await runAndWait(makeResponse());
    expect(screen.queryByTestId("whatif-fault-advisory")).not.toBeInTheDocument();
    expect(screen.queryByTestId("whatif-excluded-note")).not.toBeInTheDocument();
  });
});

