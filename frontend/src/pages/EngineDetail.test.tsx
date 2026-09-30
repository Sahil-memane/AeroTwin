import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useTelemetryStore } from "@/store/telemetryStore";
import { TELEMETRY } from "@/test/whatIfFixtures";
import type { HealthScoreResponse } from "@/types";

vi.mock("@/components/layout/AppShell", () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
vi.mock("@/hooks/useEngineWebSocket", () => ({ useEngineWebSocket: () => undefined }));

vi.mock("@/services/resources", () => ({
  enginesApi: {
    get: vi.fn(),
    healthScore: vi.fn(),
    telemetryLatest: vi.fn(),
    rul: vi.fn(),
    rulStatus: vi.fn(),
    faultsLatest: vi.fn(),
    bearingHealth: vi.fn(),
    auxLatest: vi.fn(),
    maintenanceLogs: vi.fn(),
    physicsConsistency: vi.fn(),
    createMaintenanceLog: vi.fn(),
  },
  alertsApi: { list: vi.fn(), acknowledge: vi.fn() },
}));

import { enginesApi } from "@/services/resources";
import { EngineDetail } from "./EngineDetail";

const ENGINE = "eng-1";

function health(over: Partial<HealthScoreResponse> = {}): HealthScoreResponse {
  return {
    engine_id: ENGINE,
    combined_score: 72,
    contributing_factors: [],
    primary_concern: null,
    status: "healthy",
    last_updated: "2026-09-30T08:00:00",
    age_seconds: 30,
    stale: false,
    history: [],
    ...over,
  };
}

function renderPage() {
  render(
    <MemoryRouter initialEntries={[`/engines/${ENGINE}`]}>
      <Routes>
        <Route path="/engines/:engineId" element={<EngineDetail />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  useTelemetryStore.setState({ engines: {} });
  vi.mocked(enginesApi.get).mockResolvedValue({ id: ENGINE, serial_number: "SIM-ENGINE-01", status: "operational" } as never);
  vi.mocked(enginesApi.telemetryLatest).mockResolvedValue(TELEMETRY);
  vi.mocked(enginesApi.rul).mockResolvedValue([]);
  vi.mocked(enginesApi.rulStatus).mockResolvedValue({ status: "INSUFFICIENT_DATA", samples_collected: 3, samples_required: 30 } as never);
  vi.mocked(enginesApi.faultsLatest).mockRejectedValue(new Error("none"));
  vi.mocked(enginesApi.bearingHealth).mockRejectedValue(new Error("none"));
  vi.mocked(enginesApi.auxLatest).mockRejectedValue(new Error("none"));
  vi.mocked(enginesApi.maintenanceLogs).mockResolvedValue([]);
  vi.mocked(enginesApi.physicsConsistency).mockResolvedValue({ engine_id: ENGINE, parameters: [] });
});

describe("EngineDetail health freshness", () => {
  it("flags a stale persisted score (flagged, not hidden) with its age", async () => {
    const twoHoursFourMinAgo = new Date(Date.now() - (2 * 60 + 4) * 60_000).toISOString().replace("Z", "");
    vi.mocked(enginesApi.healthScore).mockResolvedValue(health({ stale: true, age_seconds: 7440, last_updated: twoHoursFourMinAgo }));
    renderPage();
    const badge = await screen.findByTestId("score-stale");
    expect(badge).toHaveTextContent(/STALE/);
    expect(badge).toHaveTextContent("2 h 4 min");
    expect(badge).toHaveTextContent(/not streaming/);
  });

  it("shows no stale badge for a fresh score", async () => {
    const justNow = new Date(Date.now() - 10_000).toISOString().replace("Z", "");
    vi.mocked(enginesApi.healthScore).mockResolvedValue(health({ last_updated: justNow, age_seconds: 10 }));
    renderPage();
    await waitFor(() => expect(enginesApi.healthScore).toHaveBeenCalled());
    await screen.findByText("SIM-ENGINE-01");
    expect(screen.queryByTestId("score-stale")).not.toBeInTheDocument();
  });

  it("a live WebSocket score supersedes the REST stale flag", async () => {
    const old = new Date(Date.now() - 3 * 3600_000).toISOString().replace("Z", "");
    vi.mocked(enginesApi.healthScore).mockResolvedValue(health({ stale: true, age_seconds: 10800, last_updated: old }));
    renderPage();
    await screen.findByTestId("score-stale");
    useTelemetryStore.getState().setHealthScore(ENGINE, {
      combined_score: 64, contributing_factors: [], primary_concern: null, ts: new Date().toISOString().replace("Z", ""),
    });
    await waitFor(() => expect(screen.queryByTestId("score-stale")).not.toBeInTheDocument());
  });

  it("announces a partial assessment and names the sources with no fresh output", async () => {
    vi.mocked(enginesApi.healthScore).mockResolvedValue(health());
    renderPage();
    await screen.findByText("SIM-ENGINE-01");
    useTelemetryStore.getState().setHealthScore(ENGINE, {
      combined_score: 100, contributing_factors: [], primary_concern: null, missing_sources: ["rul", "fault"], ts: "2026-09-30T13:00:00",
    });
    const note = await screen.findByTestId("score-partial");
    expect(note).toHaveTextContent("Partial assessment");
    expect(note).toHaveTextContent("RUL, Fault");
  });

  it("no partial-assessment note when every source reported", async () => {
    vi.mocked(enginesApi.healthScore).mockResolvedValue(health());
    renderPage();
    await screen.findByText("SIM-ENGINE-01");
    useTelemetryStore.getState().setHealthScore(ENGINE, {
      combined_score: 80, contributing_factors: [], primary_concern: null, missing_sources: [], ts: "2026-09-30T13:00:00",
    });
    await waitFor(() => expect(screen.queryByTestId("score-partial")).not.toBeInTheDocument());
  });
});

describe("EngineDetail fault banner", () => {
  const naive = (msAgo: number) => new Date(Date.now() - msAgo).toISOString().replace("Z", "");
  const fault = (over: object = {}) => ({
    ts: naive(5_000), engine_id: ENGINE, model_version_id: "m", class_id: 5, fault_class: "Compass Failure",
    confidence: 0.999, probabilities: [], state: "FAULT_CONFIRMED" as const, ...over,
  });

  it("an advisory fault (model fed mostly placeholder channels) is labelled and noted in the header — not a red alert", async () => {
    vi.mocked(enginesApi.healthScore).mockResolvedValue(health({ last_updated: naive(5_000) }));
    renderPage();
    await screen.findByText("SIM-ENGINE-01");
    useTelemetryStore.getState().setFault(ENGINE, fault({ reliable: false, input_coverage: 0.46875 }) as never);
    const banner = await screen.findByTestId("fault-banner");
    expect(banner).toHaveAttribute("data-variant", "advisory");
    expect(screen.getByTestId("fault-banner-title")).toHaveTextContent("ADVISORY");
    expect(screen.getByTestId("score-fault-advisory")).toHaveTextContent(/not included in this score/);
  });

  it("a reliable fault stays a red alert and adds no advisory note", async () => {
    vi.mocked(enginesApi.healthScore).mockResolvedValue(health({ last_updated: naive(5_000) }));
    renderPage();
    await screen.findByText("SIM-ENGINE-01");
    useTelemetryStore.getState().setFault(ENGINE, fault({ reliable: true, input_coverage: 0.95 }) as never);
    expect(await screen.findByTestId("fault-banner")).toHaveAttribute("data-variant", "alert");
    expect(screen.queryByTestId("score-fault-advisory")).not.toBeInTheDocument();
  });

  it("an old fault prediction is dated as stale instead of shown as a current condition", async () => {
    vi.mocked(enginesApi.healthScore).mockResolvedValue(health({ last_updated: naive(5_000) }));
    renderPage();
    await screen.findByText("SIM-ENGINE-01");
    useTelemetryStore.getState().setFault(ENGINE, fault({ ts: naive(65 * 60_000), reliable: true }) as never);
    const stale = await screen.findByTestId("fault-banner-stale");
    expect(stale).toHaveTextContent("Last prediction 1 h 5 min ago");
  });
});

