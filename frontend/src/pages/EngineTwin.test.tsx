import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useTelemetryStore } from "@/store/telemetryStore";
import { makeInsufficientResponse, makeResponse } from "@/test/whatIfFixtures";
import { BEARING_OR21, makeFrame, makeSpec, makeTelemetry, minutesAgoNaive, PHYSICS } from "@/test/twinFixtures";
import type { PartId } from "@/lib/engineScene";
import type { WhatIfResponse } from "@/types";

vi.mock("@/components/layout/AppShell", () => ({ AppShell: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }));
vi.mock("@/hooks/useEngineWebSocket", () => ({ useEngineWebSocket: () => undefined }));

// WebGL isn't available in jsdom: stub the canvas, keep its contract (props in, onSelect out).
vi.mock("@/components/twin/Engine3D", () => ({
  partLabel: (p: PartId) => p.kind,
  Engine3D: (props: { spec: { spec: { num_cylinders: number } }; selected: PartId | null; onSelect: (p: PartId | null) => void; resetViewKey?: number }) => (
    <div data-testid="engine3d-stub" data-selected={props.selected?.kind ?? ""} data-reset={props.resetViewKey}>
      cylinders:{props.spec.spec.num_cylinders}
      <button onClick={() => props.onSelect({ kind: "cylinder", index: 1 })}>pick-cyl-2</button>
      <button onClick={() => props.onSelect({ kind: "bearing" })}>pick-bearing</button>
      <button onClick={() => props.onSelect({ kind: "prop" })}>pick-prop</button>
      <button onClick={() => props.onSelect({ kind: "gearbox" })}>pick-gearbox</button>
      <button onClick={() => props.onSelect({ kind: "turbo" })}>pick-turbo</button>
      <button onClick={() => props.onSelect({ kind: "block" })}>pick-block</button>
      <button onClick={() => props.onSelect(null)}>pick-none</button>
    </div>
  ),
}));

// The What-If panel has its own tests; here it is a stub that hands the page a result.
const whatIfBus = vi.hoisted(() => ({ result: null as unknown, stale: false }));
vi.mock("@/components/whatif/WhatIfPanel", () => ({
  WhatIfPanel: ({ onResult }: { onResult?: (r: unknown, stale: boolean) => void }) => (
    <div data-testid="whatif-stub">
      <button onClick={() => onResult?.(whatIfBus.result, whatIfBus.stale)}>run-whatif</button>
    </div>
  ),
}));

vi.mock("@/services/resources", () => ({
  enginesApi: {
    get: vi.fn(),
    twin: vi.fn(),
    telemetryLatest: vi.fn(),
    physicsConsistency: vi.fn(),
    faultsLatest: vi.fn(),
    bearingHealth: vi.fn(),
    auxLatest: vi.fn(),
    rul: vi.fn(),
    healthScore: vi.fn(),
  },
  missionsApi: { list: vi.fn() },
  simulationApi: { runReplay: vi.fn(), get: vi.fn() },
}));

import { enginesApi, missionsApi, simulationApi } from "@/services/resources";
import { EngineTwin } from "./EngineTwin";

const E = "eng-1";
const api = vi.mocked(enginesApi);
const POLL = { timeout: 4000 };

function renderPage() {
  render(
    <MemoryRouter initialEntries={[`/engines/${E}/twin`]}>
      <Routes>
        <Route path="/engines/:engineId/twin" element={<EngineTwin />} />
      </Routes>
    </MemoryRouter>,
  );
}

const sensorValue = (k: string) => screen.getByTestId(`twin-sensor-${k}-value`);
const waitLive = () => waitFor(() => expect(sensorValue("cht")).toHaveTextContent("200 °C"));
const chipText = () => screen.getByTestId("twin-state");

beforeEach(() => {
  vi.clearAllMocks();
  whatIfBus.result = null;
  whatIfBus.stale = false;
  useTelemetryStore.setState({ engines: {}, liveAlerts: [] });
  api.twin.mockResolvedValue(makeSpec());
  api.get.mockResolvedValue({ id: E, serial_number: "S", uav_asset_id: "asset-1", status: "active" });
  api.telemetryLatest.mockResolvedValue(makeTelemetry());
  api.physicsConsistency.mockResolvedValue({ engine_id: E, parameters: PHYSICS });
  api.faultsLatest.mockRejectedValue(new Error("none"));
  api.bearingHealth.mockRejectedValue(new Error("none"));
  api.auxLatest.mockRejectedValue(new Error("none"));
  api.rul.mockResolvedValue([]);
  api.healthScore.mockResolvedValue({ combined_score: 64, contributing_factors: [], primary_concern: null, last_updated: null, history: [] } as never);
  vi.mocked(missionsApi.list).mockResolvedValue([
    { id: "m-1", uav_asset_id: "asset-1", mission_type: "endurance", status: "active", start_time: "2026-09-28T22:51:40", end_time: null, environmental_profile: null, reading_count: 100, first_ts: "2026-09-28T22:51:57", last_ts: "2026-09-30T08:06:33" },
  ]);
  vi.mocked(simulationApi.runReplay).mockResolvedValue({ simulation_id: "sim-1", status: "queued" });
  vi.mocked(simulationApi.get).mockResolvedValue({
    simulation_id: "sim-1",
    status: "completed",
    mode: "replay",
    error: null,
    created_at: "t",
    completed_at: "t",
    results: [
      makeFrame({ step: 0, telemetry: { rpm: 2000, cht: 120, egt: 700, oil_pressure: 70, oil_temp: 90, fuel_flow: 5, vibration_x: 0.3, vibration_y: 0.4, vibration_z: 0 } }),
      makeFrame({ step: 1, telemetry: { rpm: 2500, cht: 150, egt: 710, oil_pressure: 71, oil_temp: 91, fuel_flow: 6, vibration_x: 0.3, vibration_y: 0.4, vibration_z: 0 } }),
      makeFrame({ step: 2, telemetry: { rpm: 2900, cht: 180, egt: 720, oil_pressure: 72, oil_temp: 92, fuel_flow: 7, vibration_x: 0.3, vibration_y: 0.4, vibration_z: 0 } }),
    ],
  });
});

describe("page: data comes from the API and the live store", () => {
  it("builds the model from the spec the API returns (not built-in numbers)", async () => {
    api.twin.mockResolvedValue(makeSpec({ num_cylinders: 6, displacement_cc: 4321, rated_power_kw: 99.9 }));
    renderPage();
    expect(await screen.findByTestId("engine3d-stub")).toHaveTextContent("cylinders:6");
    const line = screen.getByTestId("twin-spec-line");
    expect(line).toHaveTextContent("6 cylinders");
    expect(line).toHaveTextContent("4321 cc");
    expect(line).toHaveTextContent("99.9 kW");
    expect(line).toHaveTextContent("test/specs.py");
    expect(screen.getByText(/TEST-ENGINE-9/)).toBeInTheDocument();
  });

  it("shows the real sensor values with physics status; RPM is an input", async () => {
    renderPage();
    await waitLive();
    expect(sensorValue("rpm")).toHaveTextContent("3000 rpm");
    expect(sensorValue("oil_pressure")).toHaveTextContent("75 psi");
    expect(screen.getByTestId("twin-sensor-cht")).toHaveTextContent("REVIEW");
    expect(screen.getByTestId("twin-sensor-fuel_flow")).toHaveTextContent("ANOMALY");
    expect(screen.getByTestId("twin-sensor-rpm")).toHaveTextContent("input");
  });

  it("a live WebSocket update changes what the twin shows", async () => {
    renderPage();
    await waitLive();
    act(() => useTelemetryStore.getState().setTelemetry(E, makeTelemetry({ cht: 333, rpm: 4400 })));
    await waitFor(() => expect(sensorValue("cht")).toHaveTextContent("333 °C"));
    expect(sensorValue("rpm")).toHaveTextContent("4400 rpm");
    expect(chipText()).toHaveTextContent("LIVE");
    expect(screen.queryByTestId("twin-stale-banner")).not.toBeInTheDocument();
  });

  it("the header and overlay both carry the source chip", async () => {
    renderPage();
    await waitLive();
    expect(chipText()).toHaveTextContent("LIVE");
    expect(within(screen.getByTestId("twin-overlay")).getByText("LIVE")).toBeInTheDocument();
  });
});

describe("the health figure is the backend's", () => {
  it("summary health is the REST score", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByTestId("summary-health")).toHaveTextContent("64"));
    expect(screen.getByTestId("summary-health")).toHaveTextContent("Health Fusion");
  });

  it("when the backend has no score, health is Unavailable even with model outputs present", async () => {
    api.healthScore.mockRejectedValue(new Error("404"));
    api.bearingHealth.mockResolvedValue(BEARING_OR21);
    renderPage();
    await waitFor(() => expect(screen.getByTestId("summary-bearing")).toHaveTextContent("OR_021"));
    expect(screen.getByTestId("summary-health")).toHaveTextContent("Unavailable");
    expect(screen.getByTestId("summary-health")).toHaveAttribute("data-unavailable", "true");
  });

  it("a live health score from the stream replaces the REST one", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByTestId("summary-health")).toHaveTextContent("64"));
    act(() => useTelemetryStore.getState().setHealthScore(E, { combined_score: 22.5, contributing_factors: [], ts: "t" }));
    expect(screen.getByTestId("summary-health")).toHaveTextContent("22.5");
  });

  it("no prediction is 'Unavailable', never a made-up value", async () => {
    renderPage();
    await waitLive();
    expect(screen.getByTestId("summary-fault")).toHaveTextContent("Unavailable");
    expect(screen.getByTestId("summary-rul")).toHaveTextContent("Unavailable");
    expect(screen.getByTestId("summary-aux")).toHaveTextContent("Unavailable");
  });

  it("an advisory fault is labelled advisory / not scored", async () => {
    api.faultsLatest.mockResolvedValue({
      ts: "t", engine_id: E, model_version_id: "m", class_id: 5, fault_class: "Compass Failure", confidence: 0.99, probabilities: [], state: "FAULT_CONFIRMED", input_coverage: 0.47, reliable: false,
    });
    renderPage();
    await waitFor(() => expect(screen.getByTestId("summary-fault")).toHaveTextContent("Compass Failure"));
    expect(screen.getByTestId("summary-fault")).toHaveTextContent("advisory — not scored");
  });
});

describe("live vs stale vs no data", () => {
  it("telemetry older than 5 minutes is STALE with its age and a not-a-live-view banner", async () => {
    api.telemetryLatest.mockResolvedValue(makeTelemetry({ ts: minutesAgoNaive(104) }));
    renderPage();
    expect(await screen.findByTestId("twin-stale-banner")).toHaveTextContent(/not streaming/i);
    expect(chipText()).toHaveTextContent("STALE");
    expect(screen.getByTestId("twin-age")).toHaveTextContent("last data 1 h 44 min ago");
    expect(screen.getByTestId("summary-source")).toHaveTextContent("STALE");
  });

  it("4 minutes old is still LIVE; 6 minutes old is STALE", async () => {
    api.telemetryLatest.mockResolvedValue(makeTelemetry({ ts: minutesAgoNaive(4) }));
    renderPage();
    await waitLive();
    expect(chipText()).toHaveTextContent("LIVE");
    act(() => useTelemetryStore.getState().setTelemetry(E, makeTelemetry({ ts: minutesAgoNaive(6) })));
    await waitFor(() => expect(chipText()).toHaveTextContent("STALE"));
  });

  it("no telemetry => NO DATA and dashes instead of invented values", async () => {
    api.telemetryLatest.mockRejectedValue(new Error("404"));
    renderPage();
    await screen.findByTestId("engine3d-stub");
    expect(chipText()).toHaveTextContent("NO DATA");
    expect(screen.getByTestId("twin-age")).toHaveTextContent("no telemetry received");
    expect(sensorValue("cht")).toHaveTextContent("—");
    expect(sensorValue("rpm")).toHaveTextContent("—");
  });

  it("without the engine configuration it refuses to guess a cylinder count", async () => {
    api.twin.mockRejectedValue(new Error("500"));
    renderPage();
    expect(await screen.findByTestId("twin-no-spec")).toHaveTextContent(/no cylinder count is assumed/i);
    expect(screen.queryByTestId("engine3d-stub")).not.toBeInTheDocument();
    await waitLive(); // live readings are still shown
  });
});

describe("view modes", () => {
  it("starts on Health and switches the side panel per mode", async () => {
    renderPage();
    await waitLive();
    expect(screen.getByTestId("mode-tab-health")).toHaveAttribute("aria-selected", "true");
    expect(screen.getByTestId("mode-panel")).toHaveAttribute("data-mode", "health");
    for (const m of ["thermal", "fault", "bearing", "physics", "vibration"]) {
      fireEvent.click(screen.getByTestId(`mode-tab-${m}`));
      expect(screen.getByTestId("mode-panel")).toHaveAttribute("data-mode", m);
      expect(screen.getByTestId(`mode-tab-${m}`)).toHaveAttribute("aria-selected", "true");
    }
    expect(screen.getByTestId("mode-tab-health")).toHaveAttribute("aria-selected", "false");
  });

  it("thermal mode states the temperatures are engine-level", async () => {
    renderPage();
    await waitLive();
    fireEvent.click(screen.getByTestId("mode-tab-thermal"));
    expect(screen.getAllByTestId("mode-note").map((n) => n.textContent).join(" ")).toMatch(/not a per-cylinder measurement/i);
  });

  it("physics mode shows the measured-vs-expected table from the API", async () => {
    renderPage();
    await waitLive();
    fireEvent.click(screen.getByTestId("mode-tab-physics"));
    expect(screen.getByTestId("physics-row-cht")).toHaveTextContent("150");
    expect(screen.getByTestId("physics-row-cht")).toHaveTextContent("REVIEW");
  });

  it("vibration RMS is Unavailable until 10 live readings have been seen", async () => {
    renderPage();
    await waitLive();
    fireEvent.click(screen.getByTestId("mode-tab-vibration"));
    const rmsRow = () => screen.getByText(/^Vibration RMS/).closest("[data-testid='inspect-row']")!;
    expect(rmsRow()).toHaveAttribute("data-unavailable", "true");
    for (let i = 0; i < 12; i++) act(() => useTelemetryStore.getState().setTelemetry(E, makeTelemetry({ vibration_x: 0.3 + i * 0.001 })));
    await waitFor(() => expect(rmsRow()).not.toHaveAttribute("data-unavailable"));
    expect(rmsRow()).toHaveTextContent(/last \d+ readings/);
  });

  it("the legend and reset button are present; reset bumps the camera key", async () => {
    renderPage();
    await screen.findByTestId("engine3d-stub");
    expect(screen.getByTestId("twin-legend")).toHaveTextContent(/placeholder/i);
    const before = screen.getByTestId("engine3d-stub").getAttribute("data-reset");
    fireEvent.click(screen.getByRole("button", { name: "Reset view" }));
    expect(screen.getByTestId("engine3d-stub").getAttribute("data-reset")).not.toBe(before);
  });
});

describe("component inspector is honest", () => {
  it("a cylinder shows per-cylinder CHT/EGT as Unavailable and engine-level values labelled as such", async () => {
    renderPage();
    await waitLive();
    fireEvent.click(screen.getByText("pick-cyl-2"));
    expect(screen.getByTestId("inspector-title")).toHaveTextContent("Cylinder 2 · bank B");
    const own = screen.getByText("CHT — this cylinder").closest("[data-testid='inspect-row']")!;
    expect(own).toHaveTextContent("Unavailable");
    expect(own).toHaveAttribute("data-unavailable", "true");
    expect(screen.getByText("EGT — this cylinder").closest("[data-testid='inspect-row']")).toHaveTextContent("Unavailable");
    expect(screen.getByText("CHT — engine-level").closest("[data-testid='inspect-row']")).toHaveTextContent("200 °C");
    expect(screen.getByTestId("inspector-note")).toHaveTextContent(/not a per-cylinder measurement/i);
    expect(screen.getByTestId("twin-sensor-note")).toHaveTextContent(/per-cylinder temperatures are not measured/i);
  });

  it("gearbox and propeller open separate inspections", async () => {
    renderPage();
    await waitLive();
    fireEvent.click(screen.getByText("pick-gearbox"));
    expect(screen.getByTestId("inspector-title")).toHaveTextContent("Propeller gearbox");
    expect(screen.getByTestId("engine3d-stub")).toHaveAttribute("data-selected", "gearbox");
    fireEvent.click(screen.getByText("pick-prop"));
    expect(screen.getByTestId("inspector-title")).toHaveTextContent(/^Propeller$/);
    expect(screen.getByText("Gear ratio").closest("[data-testid='inspect-row']")).toHaveAttribute("data-unavailable", "true");
  });

  it("the turbo is a placeholder with an unknown fitment", async () => {
    renderPage();
    await waitLive();
    fireEvent.click(screen.getByText("pick-turbo"));
    expect(screen.getByText("Installed").closest("[data-testid='inspect-row']")).toHaveTextContent("Unknown");
    expect(screen.getByText("Boost pressure").closest("[data-testid='inspect-row']")).toHaveAttribute("data-unavailable", "true");
  });

  it("the bearing shows the model output and says the bearing ID is unavailable", async () => {
    api.bearingHealth.mockResolvedValue({ ...BEARING_OR21, class_label: "OR_014", severity_inches: 0.014, confidence: 0.93 });
    renderPage();
    await waitFor(() => expect(screen.getByTestId("summary-bearing")).toHaveTextContent("OR_014"));
    fireEvent.click(screen.getByText("pick-bearing"));
    expect(screen.getByText("Model class").closest("[data-testid='inspect-row']")).toHaveTextContent("OR_014");
    expect(screen.getByText("Severity").closest("[data-testid='inspect-row']")).toHaveTextContent("0.014 in");
    expect(screen.getByText("Confidence").closest("[data-testid='inspect-row']")).toHaveTextContent("93%");
    expect(screen.getByText("Bearing ID").closest("[data-testid='inspect-row']")).toHaveAttribute("data-unavailable", "true");
  });

  it("clear closes the inspection; selecting nothing from the canvas also clears it", async () => {
    renderPage();
    await waitLive();
    fireEvent.click(screen.getByText("pick-block"));
    expect(screen.getByTestId("inspector-title")).toHaveTextContent("Engine block");
    fireEvent.click(screen.getByRole("button", { name: "clear" }));
    expect(screen.queryByTestId("inspector-title")).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("pick-block"));
    fireEvent.click(screen.getByText("pick-none"));
    expect(screen.queryByTestId("inspector-title")).not.toBeInTheDocument();
  });

  it("a spec that reports per-cylinder sensors changes the note", async () => {
    api.twin.mockResolvedValue(makeSpec({}, true));
    renderPage();
    await screen.findByTestId("engine3d-stub");
    expect(screen.getByTestId("twin-sensor-note")).toHaveTextContent(/per-cylinder temperature sensors are available/i);
  });
});

describe("REPLAY source", () => {
  async function openReplayAndRun() {
    fireEvent.click(screen.getByTestId("source-tab-replay"));
    expect(await screen.findByTestId("twin-replay-banner")).toHaveTextContent(/not live data/i);
    await waitFor(() => expect(screen.getByTestId("replay-mission")).toHaveValue("m-1"));
    fireEvent.click(screen.getByTestId("replay-run"));
    await screen.findByTestId("replay-scrubber", undefined, POLL);
  }

  it("shows the replay banner and controls, and no frame until a run completes", async () => {
    renderPage();
    await waitLive();
    fireEvent.click(screen.getByTestId("source-tab-replay"));
    expect(screen.getByTestId("replay-controls")).toBeInTheDocument();
    expect(chipText()).toHaveTextContent("NO DATA"); // nothing replayed yet: not LIVE, not invented
    expect(sensorValue("cht")).toHaveTextContent("—");
  });

  it("shows the recorded step with a REPLAY chip and step label, and scrubbing changes the values", async () => {
    renderPage();
    await waitLive();
    await openReplayAndRun();
    expect(chipText()).toHaveTextContent("REPLAY");
    expect(screen.getByTestId("twin-age")).toHaveTextContent("Step 1 / 3");
    expect(screen.getByTestId("replay-step")).toHaveTextContent("Step 1 / 3");
    expect(sensorValue("cht")).toHaveTextContent("120 °C");
    expect(within(screen.getByTestId("twin-overlay")).getByText("REPLAY")).toBeInTheDocument();
    fireEvent.change(screen.getByTestId("replay-scrubber"), { target: { value: "2" } });
    expect(sensorValue("cht")).toHaveTextContent("180 °C");
    expect(sensorValue("rpm")).toHaveTextContent("2900 rpm");
    expect(screen.getByTestId("twin-age")).toHaveTextContent("Step 3 / 3");
    expect(screen.getByTestId("summary-health")).toHaveTextContent("77"); // the frame's backend score
  });

  it("replay never modifies the live store, and LIVE shows the live values again afterwards", async () => {
    renderPage();
    await waitLive();
    const before = useTelemetryStore.getState().engines;
    await openReplayAndRun();
    expect(sensorValue("cht")).toHaveTextContent("120 °C");
    expect(useTelemetryStore.getState().engines).toBe(before);
    expect(useTelemetryStore.getState().engines[E].telemetry?.cht).toBe(200);
    fireEvent.click(screen.getByTestId("source-tab-live"));
    expect(sensorValue("cht")).toHaveTextContent("200 °C");
    expect(chipText()).toHaveTextContent("LIVE");
  });

  it("an old recording is REPLAY, not STALE, and there is no stale banner", async () => {
    renderPage();
    await waitLive();
    await openReplayAndRun(); // frames are dated 2026-09-30
    expect(chipText()).toHaveTextContent("REPLAY");
    expect(screen.queryByTestId("twin-stale-banner")).not.toBeInTheDocument();
  });

  it("a stale live engine shows STALE on the LIVE tab but REPLAY on the replay tab", async () => {
    api.telemetryLatest.mockResolvedValue(makeTelemetry({ ts: minutesAgoNaive(90) }));
    renderPage();
    await screen.findByTestId("twin-stale-banner");
    await openReplayAndRun();
    expect(chipText()).toHaveTextContent("REPLAY");
    fireEvent.click(screen.getByTestId("source-tab-live"));
    expect(chipText()).toHaveTextContent("STALE");
  });

  it("a failed replay shows the error", async () => {
    vi.mocked(simulationApi.runReplay).mockRejectedValue(new Error("500"));
    renderPage();
    await waitLive();
    fireEvent.click(screen.getByTestId("source-tab-replay"));
    await waitFor(() => expect(screen.getByTestId("replay-mission")).toHaveValue("m-1"));
    fireEvent.click(screen.getByTestId("replay-run"));
    expect(await screen.findByTestId("replay-error")).toHaveTextContent(/couldn't start the replay/i);
  });
});

describe("WHAT-IF source", () => {
  const runWhatIf = async (result: WhatIfResponse | null, stale = false) => {
    whatIfBus.result = result;
    whatIfBus.stale = stale;
    fireEvent.click(screen.getByText("run-whatif"));
  };

  it("before any result the twin keeps showing the LIVE engine and says so", async () => {
    renderPage();
    await waitLive();
    fireEvent.click(screen.getByTestId("source-tab-whatif"));
    expect(screen.getByTestId("twin-whatif-banner")).toHaveTextContent(/until then the twin shows the LIVE engine/i);
    expect(chipText()).toHaveTextContent("LIVE");
    expect(sensorValue("cht")).toHaveTextContent("200 °C");
    expect(screen.queryByTestId("twin-compare")).not.toBeInTheDocument();
  });

  it("a result is shown as a WHAT-IF SIMULATION with scenario values, backend health, and a comparison", async () => {
    renderPage();
    await waitLive();
    fireEvent.click(screen.getByTestId("source-tab-whatif"));
    await runWhatIf(makeResponse());
    expect(chipText()).toHaveTextContent("WHAT-IF SIMULATION");
    expect(screen.getByTestId("twin-whatif-banner")).toHaveTextContent(/The live engine is unchanged/i);
    expect(sensorValue("rpm")).toHaveTextContent("5300 rpm"); // scenario, not live 3000
    expect(sensorValue("egt")).toHaveTextContent("880 °C");
    expect(screen.getByTestId("summary-health")).toHaveTextContent("54"); // backend scenario score
    expect(screen.getByTestId("twin-compare")).toBeInTheDocument();
    expect(screen.getByTestId("compare-health")).toHaveTextContent("65");
    expect(screen.getByTestId("twin-age")).toHaveTextContent(/Scenario/);
    // What-If doesn't change vibration: no vibration magnitude is invented
    fireEvent.click(screen.getByTestId("mode-tab-vibration"));
    expect(screen.getByText("Vibration magnitude").closest("[data-testid='inspect-row']")).toHaveAttribute("data-unavailable", "true");
  });

  it("the live engine is untouched, and can be shown instead of the scenario", async () => {
    renderPage();
    await waitLive();
    const before = useTelemetryStore.getState().engines;
    fireEvent.click(screen.getByTestId("source-tab-whatif"));
    await runWhatIf(makeResponse());
    expect(useTelemetryStore.getState().engines).toBe(before);
    fireEvent.click(screen.getByTestId("whatif-show-live"));
    expect(chipText()).toHaveTextContent("LIVE");
    expect(sensorValue("rpm")).toHaveTextContent("3000 rpm");
    expect(screen.getByTestId("twin-whatif-banner")).toHaveTextContent(/Showing the LIVE engine/i);
    fireEvent.click(screen.getByTestId("whatif-show-scenario"));
    expect(sensorValue("rpm")).toHaveTextContent("5300 rpm");
  });

  it("with sources missing the scenario health is Unavailable (partial), never the backend's misleading number", async () => {
    renderPage();
    await waitLive();
    fireEvent.click(screen.getByTestId("source-tab-whatif"));
    await runWhatIf(makeInsufficientResponse());
    const h = screen.getByTestId("summary-health");
    expect(h).toHaveTextContent("Unavailable");
    expect(h).not.toHaveTextContent("100");
    expect(screen.getByTestId("summary-rul")).toHaveTextContent("Unavailable");
    expect(screen.getByTestId("summary-fault")).toHaveTextContent("Unavailable");
    expect(screen.getByTestId("compare-rul")).toHaveTextContent("Insufficient data");
  });

  it("a stale scenario flag reaches the comparison card", async () => {
    renderPage();
    await waitLive();
    fireEvent.click(screen.getByTestId("source-tab-whatif"));
    await runWhatIf(makeResponse(), true);
    expect(screen.getByTestId("twin-compare-stale")).toBeInTheDocument();
  });

  it("the comparison is only shown on the What-If tab", async () => {
    renderPage();
    await waitLive();
    fireEvent.click(screen.getByTestId("source-tab-whatif"));
    await runWhatIf(makeResponse());
    expect(screen.getByTestId("twin-compare")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("source-tab-live"));
    expect(screen.queryByTestId("twin-compare")).not.toBeInTheDocument();
    expect(chipText()).toHaveTextContent("LIVE");
  });
});
