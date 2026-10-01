import { act, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useTelemetryStore } from "@/store/telemetryStore";
import { makeTelemetry, minutesAgoNaive } from "@/test/twinFixtures";
import type { HealthScoreResponse } from "@/types";

vi.mock("@/components/layout/AppShell", () => ({ AppShell: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }));
vi.mock("@/components/NumberTicker", () => ({ NumberTicker: ({ value }: { value: number }) => <span>{value}</span> }));
const wsOpened: string[] = [];
vi.mock("@/hooks/useEngineWebSocket", () => ({
  useEngineWebSocket: (id: string | undefined) => {
    if (id) wsOpened.push(id);
  },
}));
vi.mock("@/services/resources", () => ({
  dashboardApi: { summary: vi.fn() },
  alertsApi: { list: vi.fn(), acknowledge: vi.fn() },
  enginesApi: { list: vi.fn(), healthScore: vi.fn(), faultsLatest: vi.fn(), bearingHealth: vi.fn() },
}));

import { alertsApi, dashboardApi, enginesApi } from "@/services/resources";
import { Dashboard } from "./Dashboard";

const A = "eng-a";
const B = "eng-b";
const engines = [
  { id: A, serial_number: "SN-A", uav_asset_id: null, status: "active" },
  { id: B, serial_number: "SN-B", uav_asset_id: null, status: "active" },
];
const restHealth = (score: number | null, status: HealthScoreResponse["status"], last_updated: string | null = null): HealthScoreResponse =>
  ({ engine_id: "x", combined_score: score, contributing_factors: [], status, last_updated, history: [] }) as unknown as HealthScoreResponse;
const fault = (cls: string, conf: number, reliable?: boolean) => ({ ts: "t", engine_id: "e", model_version_id: "m", class_id: 1, fault_class: cls, confidence: conf, probabilities: [], reliable });
const bearing = (label: string) => ({ ts: "t", engine_id: "e", model_version_id: "m", class_id: 1, class_label: label, fault_location: "x", severity_inches: null, confidence: 0.9 });
const live = (id: string) => screen.getByTestId(`fleet-live-${id}`);
const row = (id: string) => screen.getByTestId(`fleet-row-${id}`);

function setup(perEngine: Record<string, { health?: HealthScoreResponse | null; fault?: ReturnType<typeof fault> | null; bearing?: ReturnType<typeof bearing> | null }> = {}) {
  vi.mocked(enginesApi.list).mockResolvedValue(engines);
  vi.mocked(enginesApi.healthScore).mockImplementation(async (id: string) => {
    const h = perEngine[id]?.health;
    if (!h) throw new Error("404");
    return h;
  });
  vi.mocked(enginesApi.faultsLatest).mockImplementation(async (id: string) => {
    const f = perEngine[id]?.fault;
    if (!f) throw new Error("404");
    return f;
  });
  vi.mocked(enginesApi.bearingHealth).mockImplementation(async (id: string) => {
    const b = perEngine[id]?.bearing;
    if (!b) throw new Error("404");
    return b;
  });
}

async function renderPage() {
  render(
    <MemoryRouter>
      <Dashboard />
    </MemoryRouter>,
  );
  await screen.findByTestId(`fleet-row-${A}`);
}

beforeEach(() => {
  vi.clearAllMocks();
  wsOpened.length = 0;
  useTelemetryStore.setState({ engines: {}, liveAlerts: [] });
  vi.mocked(dashboardApi.summary).mockResolvedValue({ total_engines: 2, total_uav_assets: 1, active_missions: 3, open_alerts: 1, fleet_health: { average_score: 61, engines_with_data: 1 } as never, recent_alerts: [] });
  vi.mocked(alertsApi.list).mockResolvedValue([]);
});

describe("Dashboard fleet rows: REST snapshot", () => {
  it("shows the REST health score and status", async () => {
    setup({ [A]: { health: restHealth(70, "healthy") }, [B]: { health: restHealth(30, "warning") } });
    await renderPage();
    expect(screen.getByTestId(`fleet-health-${A}`)).toHaveTextContent("70 · HEALTHY");
    expect(screen.getByTestId(`fleet-health-${B}`)).toHaveTextContent("30 · WARNING");
  });

  it("no health, fault, bearing or telemetry => explicit 'no data' fallbacks, never invented values", async () => {
    setup();
    await renderPage();
    const r = row(A);
    expect(r).toHaveTextContent("— no data");
    expect(screen.queryByTestId(`fleet-health-${A}`)).not.toBeInTheDocument();
    expect(live(A)).toHaveTextContent("no telemetry");
    expect(within(r).queryByTestId(`fleet-chip-${A}`)).not.toBeInTheDocument();
    const cells = within(r).getAllByRole("cell");
    expect(cells[2]).toHaveTextContent("—"); // RUL: no data at all => dash, not 'nominal'
    expect(cells[2]).not.toHaveTextContent("nominal");
    expect(cells[3]).toHaveTextContent("—"); // fault
    expect(cells[4]).toHaveTextContent("—"); // bearing
    expect(cells[5]).toHaveTextContent("—"); // aux: not 'low'
    expect(cells[5]).not.toHaveTextContent("low");
  });

  it("a null REST score (no score row yet) is 'no data', not 0", async () => {
    setup({ [A]: { health: restHealth(null, "insufficient_data") } });
    await renderPage();
    expect(row(A)).toHaveTextContent("— no data");
    expect(screen.queryByTestId(`fleet-health-${A}`)).not.toBeInTheDocument();
  });

  it("with REST data but no stream yet: 'connecting… last score', and nominal/low placeholders for RUL/aux", async () => {
    setup({ [A]: { health: restHealth(70, "healthy", "2026-09-30T07:00:00") } });
    await renderPage();
    expect(live(A)).toHaveTextContent(/connecting… last score/);
    const cells = within(row(A)).getAllByRole("cell");
    expect(cells[2]).toHaveTextContent("nominal");
    expect(cells[5]).toHaveTextContent("low");
  });

  it("shows REST fault and bearing; advisory faults are labelled", async () => {
    setup({ [A]: { health: restHealth(70, "healthy"), fault: fault("Compass Failure", 0.91, false), bearing: bearing("OR_021") } });
    await renderPage();
    const cells = within(row(A)).getAllByRole("cell");
    expect(cells[3]).toHaveTextContent("Compass Failure 91%");
    expect(cells[3]).toHaveTextContent("advisory");
    expect(cells[4]).toHaveTextContent("OR_021");
  });

  it("opens one live feed per engine", async () => {
    setup();
    await renderPage();
    await waitFor(() => expect(new Set(wsOpened)).toEqual(new Set([A, B])));
  });
});

describe("Dashboard fleet rows: live store wins over the REST row", () => {
  it("live health score and status replace the REST ones", async () => {
    setup({ [A]: { health: restHealth(70, "healthy") } });
    await renderPage();
    act(() => useTelemetryStore.getState().setHealthScore(A, { combined_score: 15, contributing_factors: [], ts: "t" }));
    expect(screen.getByTestId(`fleet-health-${A}`)).toHaveTextContent("15 · CRITICAL");
    expect(screen.getByTestId(`fleet-health-${A}`)).not.toHaveTextContent("70");
  });

  it("a live null score shows 'no data' instead of the stale REST number", async () => {
    setup({ [A]: { health: restHealth(70, "healthy") } });
    await renderPage();
    act(() => useTelemetryStore.getState().setHealthScore(A, { combined_score: null, contributing_factors: [], ts: "t" }));
    expect(screen.queryByTestId(`fleet-health-${A}`)).not.toBeInTheDocument();
    expect(row(A)).toHaveTextContent("— no data");
  });

  it("live fault, bearing and aux replace the REST ones", async () => {
    setup({ [A]: { health: restHealth(70, "healthy"), fault: fault("No Failure", 0.99), bearing: bearing("Normal") } });
    await renderPage();
    act(() => {
      const s = useTelemetryStore.getState();
      s.setFault(A, fault("Compass Failure", 0.8) as never);
      s.setBearing(A, bearing("IR_014") as never);
      s.setAux(A, { ts: "t", engine_id: A, model_version_id: "m", failure_status: "x", risk_level: "HIGH", failure_probability_pct: 62.4, detected_failure_types: [], primary_failure_cause: null, recommended_action: null });
    });
    const cells = within(row(A)).getAllByRole("cell");
    expect(cells[3]).toHaveTextContent("Compass Failure 80%");
    expect(cells[3]).not.toHaveTextContent("No Failure");
    expect(cells[4]).toHaveTextContent("IR_014");
    expect(cells[5]).toHaveTextContent("62%");
  });

  it("RUL comes from the live health factors", async () => {
    setup({ [A]: { health: restHealth(70, "healthy") } });
    await renderPage();
    act(() => useTelemetryStore.getState().setHealthScore(A, { combined_score: 60, contributing_factors: [{ source: "rul", penalty: 5, rul_cycles: 123 }], ts: "t" }));
    expect(within(row(A)).getAllByRole("cell")[2]).toHaveTextContent("123 cyc");
  });
});

describe("Dashboard live chip: LIVE / STALE from store state", () => {
  it("fresh telemetry => LIVE chip, age, and the real RPM/CHT/EGT", async () => {
    setup();
    await renderPage();
    act(() => useTelemetryStore.getState().setTelemetry(A, makeTelemetry({ rpm: 3123, cht: 201.4, egt: 505.2 })));
    const chip = screen.getByTestId(`fleet-chip-${A}`);
    expect(chip).toHaveTextContent("LIVE");
    expect(chip.className).toContain("text-healthy");
    expect(live(A)).toHaveTextContent(/\d+ s ago/);
    expect(live(A)).not.toHaveTextContent("last data");
    expect(live(A)).toHaveTextContent("RPM 3123 · CHT 201° · EGT 505°");
    expect(live(A)).not.toHaveTextContent("no telemetry");
  });

  it("telemetry older than 5 minutes => STALE chip with 'last data … ago'", async () => {
    setup();
    await renderPage();
    act(() => useTelemetryStore.getState().setTelemetry(A, makeTelemetry({ ts: minutesAgoNaive(20) })));
    const chip = screen.getByTestId(`fleet-chip-${A}`);
    expect(chip).toHaveTextContent("STALE");
    expect(chip.className).toContain("text-warning");
    expect(live(A)).toHaveTextContent(/last data 20 min ago/);
  });

  it("the 5-minute boundary: 4 min old is LIVE, 6 min old is STALE", async () => {
    setup();
    await renderPage();
    act(() => useTelemetryStore.getState().setTelemetry(A, makeTelemetry({ ts: minutesAgoNaive(4) })));
    expect(screen.getByTestId(`fleet-chip-${A}`)).toHaveTextContent("LIVE");
    act(() => useTelemetryStore.getState().setTelemetry(A, makeTelemetry({ ts: minutesAgoNaive(6) })));
    expect(screen.getByTestId(`fleet-chip-${A}`)).toHaveTextContent("STALE");
  });

  it("a new reading flips a STALE engine back to LIVE", async () => {
    setup();
    await renderPage();
    act(() => useTelemetryStore.getState().setTelemetry(A, makeTelemetry({ ts: minutesAgoNaive(30) })));
    expect(screen.getByTestId(`fleet-chip-${A}`)).toHaveTextContent("STALE");
    act(() => useTelemetryStore.getState().setTelemetry(A, makeTelemetry()));
    expect(screen.getByTestId(`fleet-chip-${A}`)).toHaveTextContent("LIVE");
  });

  it("each engine has its own chip; an engine with no store state has none", async () => {
    setup();
    await renderPage();
    act(() => useTelemetryStore.getState().setTelemetry(A, makeTelemetry()));
    expect(screen.getByTestId(`fleet-chip-${A}`)).toHaveTextContent("LIVE");
    expect(screen.queryByTestId(`fleet-chip-${B}`)).not.toBeInTheDocument();
    expect(live(B)).toHaveTextContent("no telemetry");
  });

  it("live store state alone (no REST data) turns the fallbacks into nominal/low rather than dashes", async () => {
    setup();
    await renderPage();
    act(() => useTelemetryStore.getState().setTelemetry(A, makeTelemetry()));
    const cells = within(row(A)).getAllByRole("cell");
    expect(cells[2]).toHaveTextContent("nominal");
    expect(cells[5]).toHaveTextContent("low");
    // but health stays unknown: nothing is computed from telemetry
    expect(row(A)).toHaveTextContent("— no data");
  });
});

describe("Dashboard KPIs", () => {
  it("fleet average health is the backend's number; null is a dash", async () => {
    setup();
    await renderPage();
    await waitFor(() => expect(screen.getAllByText("61").length).toBeGreaterThan(0));
    expect(screen.getByText("Fleet Avg Health")).toBeInTheDocument();
  });

  it("a null fleet average is shown as a dash, not 0", async () => {
    vi.mocked(dashboardApi.summary).mockResolvedValue({ total_engines: 2, total_uav_assets: 1, active_missions: 0, open_alerts: 0, fleet_health: { average_score: null, engines_with_data: 0 } as never, recent_alerts: [] });
    setup();
    await renderPage();
    const tile = screen.getByText("Fleet Avg Health").parentElement!;
    await waitFor(() => expect(tile).toHaveTextContent("—"));
  });

  it("no engines registered => says so", async () => {
    vi.mocked(enginesApi.list).mockResolvedValue([]);
    render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>,
    );
    expect(await screen.findByText(/no engines registered yet/i)).toBeInTheDocument();
  });
});
