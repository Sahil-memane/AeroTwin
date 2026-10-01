import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useTelemetryStore } from "@/store/telemetryStore";
import { makeFrame, makeTelemetry } from "@/test/twinFixtures";
import type { Mission, SimulationRunResponse } from "@/types";

vi.mock("@/services/resources", () => ({
  enginesApi: { get: vi.fn() },
  missionsApi: { list: vi.fn() },
  simulationApi: { runReplay: vi.fn(), get: vi.fn() },
}));

import { enginesApi, missionsApi, simulationApi } from "@/services/resources";
import { useReplayRun } from "./useReplayRun";

const E = "eng-1";
const mission = (id: string, asset: string, count: number | null): Mission => ({
  id,
  uav_asset_id: asset,
  mission_type: "endurance",
  status: "active",
  start_time: "2026-09-28T22:51:40",
  end_time: null,
  environmental_profile: null,
  reading_count: count,
});
const run = (status: SimulationRunResponse["status"], frames = 3, error: string | null = null): SimulationRunResponse => ({
  simulation_id: "sim-1",
  status,
  mode: "replay",
  error,
  results: status === "completed" ? Array.from({ length: frames }, (_, i) => makeFrame({ step: i })) : null,
  created_at: "2026-09-30T07:00:00",
  completed_at: null,
});
const POLL = { timeout: 4000 }; // the hook polls every 1.5 s

beforeEach(() => {
  vi.clearAllMocks();
  useTelemetryStore.setState({ engines: {} });
  vi.mocked(enginesApi.get).mockResolvedValue({ id: E, serial_number: "S", uav_asset_id: "asset-1", status: "active" });
  vi.mocked(missionsApi.list).mockResolvedValue([mission("other", "asset-2", 500), mission("empty", "asset-1", 0), mission("m-1", "asset-1", 100), mission("m-2", "asset-1", 50)]);
  vi.mocked(simulationApi.runReplay).mockResolvedValue({ simulation_id: "sim-1", status: "queued" });
  vi.mocked(simulationApi.get).mockResolvedValue(run("completed"));
});

describe("loading missions", () => {
  it("does nothing until replay is enabled", async () => {
    renderHook(() => useReplayRun(E, false));
    await new Promise((r) => setTimeout(r, 30));
    expect(enginesApi.get).not.toHaveBeenCalled();
    expect(missionsApi.list).not.toHaveBeenCalled();
  });

  it("loads only this engine's aircraft missions (with stats) and preselects the first that has telemetry", async () => {
    const { result } = renderHook(() => useReplayRun(E, true));
    await waitFor(() => expect(result.current.missions).toHaveLength(3));
    expect(missionsApi.list).toHaveBeenCalledWith(true);
    expect(result.current.missions.map((m) => m.id)).toEqual(["empty", "m-1", "m-2"]);
    expect(result.current.missionId).toBe("m-1"); // "empty" has 0 readings
  });

  it("loads once, even across re-renders", async () => {
    const { result, rerender } = renderHook(() => useReplayRun(E, true));
    await waitFor(() => expect(result.current.missions.length).toBeGreaterThan(0));
    rerender();
    expect(enginesApi.get).toHaveBeenCalledTimes(1);
  });

  it("reports a load failure", async () => {
    vi.mocked(missionsApi.list).mockRejectedValue(new Error("boom"));
    const { result } = renderHook(() => useReplayRun(E, true));
    await waitFor(() => expect(result.current.error).toMatch(/couldn't load missions/i));
    expect(result.current.missionId).toBe("");
  });
});

describe("running a replay", () => {
  it("start() does nothing without a mission", async () => {
    vi.mocked(missionsApi.list).mockResolvedValue([]);
    const { result } = renderHook(() => useReplayRun(E, true));
    await act(async () => {
      await result.current.start();
    });
    expect(simulationApi.runReplay).not.toHaveBeenCalled();
  });

  it("starts through the API, polls, and exposes the completed frames at index 0", async () => {
    const { result } = renderHook(() => useReplayRun(E, true));
    await waitFor(() => expect(result.current.missionId).toBe("m-1"));
    await act(async () => {
      await result.current.start();
    });
    expect(simulationApi.runReplay).toHaveBeenCalledWith(E, "m-1");
    await waitFor(() => expect(result.current.frames).toHaveLength(3), POLL);
    expect(simulationApi.get).toHaveBeenCalledWith("sim-1");
    expect(result.current.run?.status).toBe("completed");
    expect(result.current.frameIndex).toBe(0);
    expect(result.current.error).toBeNull();
  });

  it("frames stay empty while the run is still running", async () => {
    vi.mocked(simulationApi.get).mockResolvedValue(run("running"));
    const { result } = renderHook(() => useReplayRun(E, true));
    await waitFor(() => expect(result.current.missionId).toBe("m-1"));
    await act(async () => {
      await result.current.start();
    });
    await waitFor(() => expect(result.current.run?.status).toBe("running"), POLL);
    expect(result.current.frames).toEqual([]);
  });

  it("a failed run surfaces the server's error and no frames", async () => {
    vi.mocked(simulationApi.get).mockResolvedValue(run("failed", 0, "no telemetry in window"));
    const { result } = renderHook(() => useReplayRun(E, true));
    await waitFor(() => expect(result.current.missionId).toBe("m-1"));
    await act(async () => {
      await result.current.start();
    });
    await waitFor(() => expect(result.current.error).toBe("no telemetry in window"), POLL);
    expect(result.current.frames).toEqual([]);
  });

  it("a start failure is reported and starting resets", async () => {
    vi.mocked(simulationApi.runReplay).mockRejectedValue(new Error("500"));
    const { result } = renderHook(() => useReplayRun(E, true));
    await waitFor(() => expect(result.current.missionId).toBe("m-1"));
    await act(async () => {
      await result.current.start();
    });
    expect(result.current.error).toMatch(/couldn't start the replay/i);
    expect(result.current.starting).toBe(false);
  });

  it("a polling failure reports lost contact", async () => {
    vi.mocked(simulationApi.get).mockRejectedValue(new Error("net"));
    const { result } = renderHook(() => useReplayRun(E, true));
    await waitFor(() => expect(result.current.missionId).toBe("m-1"));
    await act(async () => {
      await result.current.start();
    });
    await waitFor(() => expect(result.current.error).toMatch(/lost contact/i), POLL);
  });

  it("the operator can pick another mission", async () => {
    const { result } = renderHook(() => useReplayRun(E, true));
    await waitFor(() => expect(result.current.missionId).toBe("m-1"));
    act(() => result.current.setMissionId("m-2"));
    expect(result.current.missionId).toBe("m-2");
  });
});

describe("playback", () => {
  it("auto-advances through the steps and stops at the last one", async () => {
    const { result } = renderHook(() => useReplayRun(E, true));
    await waitFor(() => expect(result.current.missionId).toBe("m-1"));
    await act(async () => {
      await result.current.start();
    });
    await waitFor(() => expect(result.current.frames).toHaveLength(3), POLL);
    act(() => result.current.setPlaying(true));
    await waitFor(() => expect(result.current.frameIndex).toBe(2), { timeout: 3000 });
    await waitFor(() => expect(result.current.playing).toBe(false));
    expect(result.current.frameIndex).toBe(2);
  });

  it("scrubbing sets the step", async () => {
    const { result } = renderHook(() => useReplayRun(E, true));
    await waitFor(() => expect(result.current.missionId).toBe("m-1"));
    await act(async () => {
      await result.current.start();
    });
    await waitFor(() => expect(result.current.frames).toHaveLength(3), POLL);
    act(() => result.current.setFrameIndex(1));
    expect(result.current.frameIndex).toBe(1);
  });

  it("starting again resets the step, run and playing state", async () => {
    const { result } = renderHook(() => useReplayRun(E, true));
    await waitFor(() => expect(result.current.missionId).toBe("m-1"));
    await act(async () => {
      await result.current.start();
    });
    await waitFor(() => expect(result.current.frames).toHaveLength(3), POLL);
    act(() => result.current.setFrameIndex(2));
    vi.mocked(simulationApi.get).mockResolvedValue(run("running"));
    await act(async () => {
      await result.current.start();
    });
    expect(result.current.frameIndex).toBe(0);
    expect(result.current.playing).toBe(false);
    expect(result.current.frames).toEqual([]);
  });
});

describe("isolation", () => {
  it("never writes to the live telemetry store", async () => {
    useTelemetryStore.setState({ engines: { [E]: { telemetry: makeTelemetry({ cht: 123 }) } } });
    const before = useTelemetryStore.getState().engines;
    const { result } = renderHook(() => useReplayRun(E, true));
    await waitFor(() => expect(result.current.missionId).toBe("m-1"));
    await act(async () => {
      await result.current.start();
    });
    await waitFor(() => expect(result.current.frames).toHaveLength(3), POLL);
    expect(useTelemetryStore.getState().engines).toBe(before);
    expect(useTelemetryStore.getState().engines[E].telemetry?.cht).toBe(123);
  });

  it("stops polling when unmounted", async () => {
    vi.mocked(simulationApi.get).mockResolvedValue(run("running"));
    const { result, unmount } = renderHook(() => useReplayRun(E, true));
    await waitFor(() => expect(result.current.missionId).toBe("m-1"));
    await act(async () => {
      await result.current.start();
    });
    const clear = vi.spyOn(globalThis, "clearInterval");
    unmount();
    expect(clear).toHaveBeenCalled();
    clear.mockRestore();
  });
});
