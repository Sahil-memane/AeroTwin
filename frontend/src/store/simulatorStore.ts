/**
 * Global simulator store — persists across ALL page navigation.
 *
 * Responsibilities:
 *  1. Track which engines have an active simulation (running / stopped / connecting)
 *  2. Send a heartbeat ping every 60 s per running engine (keeps the backend
 *     safety-net watchdog from auto-stopping after 24 h of silence)
 *  3. On logout or window/tab close → call POST /simulator/stop-all so the
 *     Docker container is always cleaned up, even if the user never clicks Stop
 */
import { create } from "zustand";
import { simulatorApi } from "@/services/resources";

export type SimState = "stopped" | "loading" | "connecting" | "running" | "error";

interface SimulatorStore {
  /** engine_id → current state */
  states: Record<string, SimState>;

  /** Set state for one engine */
  setState: (engineId: string, s: SimState) => void;

  /** Called by Dashboard when first packet arrives — promotes connecting → running */
  promoteToRunning: (engineId: string) => void;

  /** Returns true if any engine is running or connecting */
  anyActive: () => boolean;

  /** Start global lifecycle effects (heartbeat + window-close). Call once in App. */
  mount: () => () => void;
}

export const useSimulatorStore = create<SimulatorStore>((set, get) => ({
  states: {},

  setState: (engineId, s) =>
    set((prev) => ({ states: { ...prev.states, [engineId]: s } })),

  promoteToRunning: (engineId) =>
    set((prev) => {
      if (prev.states[engineId] === "connecting") {
        return { states: { ...prev.states, [engineId]: "running" } };
      }
      return prev;
    }),

  anyActive: () =>
    Object.values(get().states).some((s) => s === "running" || s === "connecting"),

  mount: () => {
    // ── Heartbeat: ping every 60 s for each running engine ───────────
    const heartbeatInterval = setInterval(() => {
      const running = Object.entries(get().states)
        .filter(([, s]) => s === "running")
        .map(([id]) => id);
      running.forEach((engineId) => {
        simulatorApi.heartbeat(engineId).catch(() => {/* silent */});
      });
    }, 60_000);

    // ── Window close / tab close / refresh → stop all ───────────────
    const handleBeforeUnload = () => {
      if (!get().anyActive()) return;
      // sendBeacon is fire-and-forget; guaranteed to be sent even on page close
      const token = localStorage.getItem("access_token") ?? sessionStorage.getItem("access_token");
      if (token) {
        navigator.sendBeacon(
          "/api/v1/simulator/stop-all",
          new Blob(
            [JSON.stringify({})],
            { type: "application/json" }
          )
        );
      }
    };
    window.addEventListener("beforeunload", handleBeforeUnload);

    return () => {
      clearInterval(heartbeatInterval);
      window.removeEventListener("beforeunload", handleBeforeUnload);
    };
  },
}));
