import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CONFIG, TELEMETRY } from "@/test/whatIfFixtures";
import type { SimulationRunResponse } from "@/types";

vi.mock("@/components/layout/AppShell", () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock("@/services/resources", () => ({
  enginesApi: {
    get: vi.fn(),
    telemetryLatest: vi.fn(),
    telemetryAt: vi.fn(),
    healthScore: vi.fn(),
  },
  missionsApi: { list: vi.fn() },
  uavAssetsApi: { list: vi.fn() },
  simulationApi: {
    runReplay: vi.fn(),
    runWhatIf: vi.fn(),
    get: vi.fn(),
    whatIfConfig: vi.fn(),
    runParameterWhatIf: vi.fn(),
  },
}));

import { enginesApi, missionsApi, simulationApi, uavAssetsApi } from "@/services/resources";
import { SimulationReplay } from "./SimulationReplay";

const STEP = {
  step: 0,
  ts: "2026-09-30T07:00:00",
  telemetry: { rpm: 3000, cht: 120, egt: 700, oil_pressure: 70, oil_temp: 90, fuel_flow: 5 },
  rul: null,
  fault: null,
  bearing: null,
  aux: null,
  health_score: { combined_score: 77, contributing_factors: [] },
};

function run(mode: "replay" | "what_if"): SimulationRunResponse {
  return {
    simulation_id: `sim-${mode}`,
    status: "completed",
    mode,
    error: null,
    results: [STEP],
    created_at: "2026-09-30T07:00:00",
    completed_at: "2026-09-30T07:00:01",
  };
}

const MISSION_DATA = {
  id: "m-1", uav_asset_id: "asset-1", mission_type: "endurance", status: "active",
  start_time: "2026-09-28T22:51:40", end_time: null, environmental_profile: null,
  reading_count: 92166, first_ts: "2026-09-28T22:51:57", last_ts: "2026-09-30T08:06:33",
};
const MISSION_EMPTY = {
  id: "m-0", uav_asset_id: "asset-1", mission_type: "endurance", status: "scheduled",
  start_time: "2026-09-30T10:00:00", end_time: null, environmental_profile: null,
  reading_count: 0, first_ts: null, last_ts: null,
};

function renderPage(url = "/engines/eng-1/simulation") {
  render(
    <MemoryRouter initialEntries={[url]}>
      <Routes>
        <Route path="/engines/:engineId/simulation" element={<SimulationReplay />} />
      </Routes>
    </MemoryRouter>,
  );
}

const POLL_WAIT = { timeout: 4000 }; // page polls every 1.5 s

async function startReplay() {
  await screen.findByTestId("mission-info"); // newest mission with telemetry (m-1) is auto-selected
  fireEvent.click(screen.getByRole("button", { name: "Run Simulation" }));
  await screen.findByText(/Step 1 \/ 1/, undefined, POLL_WAIT);
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(enginesApi.get).mockResolvedValue({ id: "eng-1", serial_number: "SIM-ENGINE-01", uav_asset_id: "asset-1" } as never);
  vi.mocked(enginesApi.telemetryLatest).mockResolvedValue(TELEMETRY);
  vi.mocked(enginesApi.healthScore).mockResolvedValue({ history: [] } as never);
  vi.mocked(uavAssetsApi.list).mockResolvedValue([{ id: "asset-1", tail_number: "N123AB", status: "active" }] as never);
  // newest first, as the API returns them: a scheduled mission with no data, then the recorded one
  vi.mocked(missionsApi.list).mockResolvedValue([MISSION_EMPTY, MISSION_DATA] as never);
  vi.mocked(simulationApi.whatIfConfig).mockResolvedValue(CONFIG);
  vi.mocked(simulationApi.runReplay).mockResolvedValue({ simulation_id: "sim-replay", status: "queued" });
  vi.mocked(simulationApi.runWhatIf).mockResolvedValue({ simulation_id: "sim-what_if", status: "queued" });
  vi.mocked(simulationApi.get).mockImplementation(async (id: string) => run(id === "sim-replay" ? "replay" : "what_if"));
});

describe("SimulationReplay page — mode isolation", () => {
  it("Replay works exactly as before and shows no What-If UI", async () => {
    renderPage();
    await startReplay();
    expect(simulationApi.runReplay).toHaveBeenCalledWith("eng-1", "m-1");
    expect(screen.getByRole("button", { name: "Run Simulation" })).toBeInTheDocument();
    expect(screen.queryByTestId("whatif-panel")).not.toBeInTheDocument();
    expect(screen.queryByTestId("preset-section-label")).not.toBeInTheDocument();
    expect(simulationApi.whatIfConfig).not.toHaveBeenCalled(); // What-If never even loads in Replay
  });

  it("Replay → What-If: replay results don't leak into What-If, and back", async () => {
    renderPage();
    await startReplay();

    fireEvent.click(screen.getByRole("button", { name: "What-If" }));
    await screen.findByTestId("whatif-controls");
    expect(screen.queryByText(/Step 1 \/ 1/)).not.toBeInTheDocument(); // replay frames hidden
    expect(screen.getByTestId("whatif-panel")).toBeInTheDocument();
    // What-If opens on the parameter tool; the preset envelope controls are one tab away
    expect(screen.queryByTestId("preset-section-label")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Preset mission" }));
    expect(screen.getByTestId("preset-section-label")).toHaveTextContent(/Preset mission envelope/);

    fireEvent.click(screen.getByRole("button", { name: "Replay" }));
    expect(await screen.findByText(/Step 1 \/ 1/)).toBeInTheDocument(); // replay result intact
    expect(screen.queryByTestId("whatif-panel")).not.toBeInTheDocument();
  });

  it("parameter scenario edits don't reach Replay or the preset run, and don't survive a mode switch", async () => {
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: "What-If" }));
    await screen.findByTestId("whatif-controls");
    fireEvent.change(screen.getByLabelText("RPM scenario"), { target: { value: "5300" } });
    expect((screen.getByTestId("whatif-scenario-rpm") as HTMLInputElement).value).toBe("5300");

    fireEvent.click(screen.getByRole("button", { name: "Replay" }));
    expect(screen.queryByTestId("whatif-panel")).not.toBeInTheDocument();
    expect(simulationApi.runParameterWhatIf).not.toHaveBeenCalled();

    // returning re-initialises from current telemetry — no stale scenario carried over
    fireEvent.click(screen.getByRole("button", { name: "What-If" }));
    await screen.findByTestId("whatif-controls");
    expect((screen.getByTestId("whatif-scenario-rpm") as HTMLInputElement).value).toBe("4908.7");
  });

  it("the existing preset What-If run still works, is labelled synthetic, and is hidden in Replay", async () => {
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: "What-If" }));
    await screen.findByTestId("whatif-controls");
    fireEvent.click(screen.getByRole("tab", { name: "Preset mission" }));

    fireEvent.change(screen.getByDisplayValue("Nominal Cruise"), { target: { value: "hot_weather_endurance" } });
    fireEvent.click(screen.getByRole("button", { name: "Run Preset Simulation" }));
    expect(simulationApi.runWhatIf).toHaveBeenCalledWith("eng-1", { preset: "hot_weather_endurance" });
    expect(simulationApi.runParameterWhatIf).not.toHaveBeenCalled(); // presets don't go through the parameter endpoint

    expect(await screen.findByTestId("preset-results-label", undefined, POLL_WAIT)).toHaveTextContent(/not live data/i);
    expect(screen.getByText(/Step 1 \/ 1/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Replay" }));
    await waitFor(() => expect(screen.queryByTestId("preset-results-label")).not.toBeInTheDocument());
    expect(screen.queryByText(/Step 1 \/ 1/)).not.toBeInTheDocument();
  });

  it("What-If tabs: parameter tool is the default, the preset tab swaps controls, and slider edits survive a tab flip", async () => {
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: "What-If" }));
    await screen.findByTestId("whatif-controls");
    expect(screen.getByRole("tab", { name: "Parameter What-If" })).toHaveAttribute("aria-selected", "true");
    expect(screen.queryByRole("button", { name: "Run Preset Simulation" })).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("RPM scenario"), { target: { value: "5300" } });
    fireEvent.click(screen.getByRole("tab", { name: "Preset mission" }));
    expect(screen.getByRole("button", { name: "Run Preset Simulation" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "Parameter What-If" }));
    expect((screen.getByTestId("whatif-scenario-rpm") as HTMLInputElement).value).toBe("5300");
  });

  describe("Replay mission picker", () => {
    it("asks the API for per-mission stats", async () => {
      renderPage();
      await screen.findByTestId("mission-info");
      expect(missionsApi.list).toHaveBeenCalledWith(true);
    });

    it("describes each mission (aircraft · type · start · status · data) and disables one with no telemetry", async () => {
      renderPage();
      await screen.findByTestId("mission-info");
      const options = screen.getAllByRole("option") as HTMLOptionElement[];
      const data = options.find((o) => o.value === "m-1")!;
      const empty = options.find((o) => o.value === "m-0")!;

      expect(data.textContent).toMatch(/^N123AB · Endurance · .+ · Active · 92,166 readings$/);
      expect(data.disabled).toBe(false);
      expect(empty.textContent).toMatch(/^N123AB · Endurance · .+ · Scheduled · no telemetry$/);
      expect(empty.disabled).toBe(true); // nothing to replay, so it can't be picked
      // the bare word "endurance" is no longer the whole label
      expect(data.textContent).not.toBe("endurance");
    });

    it("opens on the newest mission that has data and shows its info card", async () => {
      renderPage();
      const card = await screen.findByTestId("mission-info");
      expect((screen.getByDisplayValue(/N123AB · Endurance/) as HTMLSelectElement).value).toBe("m-1");
      expect(screen.getByTestId("mission-info-title")).toHaveTextContent("Endurance mission");
      expect(screen.getByTestId("mission-info-status")).toHaveTextContent("ACTIVE");
      expect(card).toHaveTextContent("N123AB");
      expect(card).toHaveTextContent("not ended yet");
      expect(screen.getByTestId("mission-info-readings")).toHaveTextContent("92,166");
      expect(screen.getByTestId("mission-info-window")).toHaveTextContent(/1 d 9 h/); // 09-28 22:51 → 09-30 08:06
      expect(screen.getByTestId("mission-info-plan")).toHaveTextContent("Replay will sample 300 of the 92,166 readings");
    });

    it("a mission with no telemetry (opened via ?mission=) warns and blocks Run", async () => {
      renderPage("/engines/eng-1/simulation?mission=m-0");
      const plan = await screen.findByTestId("mission-info-plan");
      expect(plan).toHaveTextContent("No telemetry is stored for this mission");
      expect(screen.getByTestId("mission-info-readings")).toHaveTextContent("0");
      expect(screen.getByRole("button", { name: "Run Simulation" })).toBeDisabled();
      expect(simulationApi.runReplay).not.toHaveBeenCalled();
    });

    it("shows a hint (and no card) when there is no mission to describe", async () => {
      vi.mocked(missionsApi.list).mockResolvedValue([]);
      renderPage();
      expect(await screen.findByTestId("mission-info-hint")).toHaveTextContent("No missions are recorded for this aircraft yet");
      expect(screen.queryByTestId("mission-info")).not.toBeInTheDocument();
    });

    it("still works if the aircraft list can't be loaded (label just omits the tail number)", async () => {
      vi.mocked(uavAssetsApi.list).mockRejectedValue(new Error("boom"));
      renderPage();
      await screen.findByTestId("mission-info");
      const data = (screen.getAllByRole("option") as HTMLOptionElement[]).find((o) => o.value === "m-1")!;
      expect(data.textContent).toMatch(/^Endurance · .+ · Active · 92,166 readings$/);
    });
  });
});

