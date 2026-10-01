import { useCallback, useEffect, useRef, useState } from "react";
import { enginesApi, missionsApi, simulationApi } from "@/services/resources";
import type { Mission, SimulationRunResponse } from "@/types";

/**
 * Replay of a recorded mission for the 3D twin: lists the engine's missions (with how much telemetry
 * each has), starts a replay run through the real models, polls it, and exposes the step the
 * operator is on. Mirrors the Simulation page's flow; it never touches live state.
 */
export function useReplayRun(engineId: string, enabled: boolean) {
  const [missions, setMissions] = useState<Mission[]>([]);
  const [missionId, setMissionId] = useState("");
  const [run, setRun] = useState<SimulationRunResponse | null>(null);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [frameIndex, setFrameIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const poll = useRef<ReturnType<typeof setInterval> | null>(null);

  // Load missions for this engine's aircraft the first time replay is opened.
  const loaded = useRef(false);
  useEffect(() => {
    if (!enabled || loaded.current || !engineId) return;
    loaded.current = true;
    Promise.all([enginesApi.get(engineId), missionsApi.list(true)])
      .then(([engine, all]) => {
        const mine = all.filter((m) => m.uav_asset_id === engine.uav_asset_id);
        setMissions(mine);
        const runnable = mine.find((m) => (m.reading_count ?? 0) > 0);
        if (runnable) setMissionId(runnable.id);
      })
      .catch(() => setError("Couldn't load missions for this engine."));
  }, [enabled, engineId]);

  useEffect(
    () => () => {
      if (poll.current) clearInterval(poll.current);
    },
    [],
  );

  const start = useCallback(async () => {
    if (!missionId) return;
    setStarting(true);
    setError(null);
    setRun(null);
    setFrameIndex(0);
    setPlaying(false);
    try {
      const created = await simulationApi.runReplay(engineId, missionId);
      if (poll.current) clearInterval(poll.current);
      poll.current = setInterval(async () => {
        try {
          const polled = await simulationApi.get(created.simulation_id);
          setRun(polled);
          if (polled.status === "completed" || polled.status === "failed") {
            if (poll.current) clearInterval(poll.current);
            if (polled.status === "failed") setError(polled.error ?? "Replay failed.");
          }
        } catch {
          if (poll.current) clearInterval(poll.current);
          setError("Lost contact with the server while replaying.");
        }
      }, 1500);
    } catch {
      setError("Couldn't start the replay.");
    } finally {
      setStarting(false);
    }
  }, [engineId, missionId]);

  const frames = run?.status === "completed" ? (run.results ?? []) : [];

  // Auto-advance while playing.
  useEffect(() => {
    if (!playing || frames.length === 0) return;
    const id = setInterval(() => {
      setFrameIndex((i) => {
        if (i >= frames.length - 1) {
          setPlaying(false);
          return i;
        }
        return i + 1;
      });
    }, 250);
    return () => clearInterval(id);
  }, [playing, frames.length]);

  return { missions, missionId, setMissionId, run, frames, starting, error, frameIndex, setFrameIndex, playing, setPlaying, start };
}
