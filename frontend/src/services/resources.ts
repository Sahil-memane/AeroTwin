import { api } from "@/services/apiClient";
import type {
  Alert,
  AlertSeverity,
  AuxPrediction,
  BearingHealthReading,
  DashboardSummary,
  Engine,
  FaultPrediction,
  HealthScoreResponse,
  MaintenanceLog,
  Mission,
  MissionDetail,
  PhysicsConsistencyResponse,
  RulPrediction,
  RulStatus,
  SimulationRunResponse,
  TelemetryReading,
  TokenResponse,
  UAVAsset,
  EngineTwinSpec,
  WhatIfConfig,
  WhatIfParam,
  WhatIfResponse,
} from "@/types";

// ── Auth ──────────────────────────────────────────────────────────────
export const authApi = {
  login: (email: string, password: string) =>
    api.post<TokenResponse>("/auth/login", { email, password }, { anonymous: true }),
  register: (payload: { email: string; password: string; full_name: string; role: string }) =>
    api.post<TokenResponse>("/auth/register", payload, { anonymous: true }),
};

// ── Engines ───────────────────────────────────────────────────────────
export const enginesApi = {
  list: () => api.get<Engine[]>("/engines"),
  get: (engineId: string) => api.get<Engine>(`/engines/${engineId}`),
  healthScore: (engineId: string, historyLimit = 50) =>
    api.get<HealthScoreResponse>(`/engines/${engineId}/health-score`, { history_limit: historyLimit }),
  // Static description the 3D twin is built from (real engine config, sensor ranges, which sensors exist).
  twin: (engineId: string) => api.get<EngineTwinSpec>(`/engines/${engineId}/twin`),
  telemetryLatest: (engineId: string) => api.get<TelemetryReading>(`/engines/${engineId}/telemetry/latest`),
  // Newest stored reading at or before `ts` (What-If historical baseline picker).
  telemetryAt: (engineId: string, ts: string) =>
    api.get<TelemetryReading[]>(`/engines/${engineId}/telemetry`, { to: ts, limit: 1 }).then((rows) => rows[0] ?? null),
  telemetryRange: (engineId: string, limit = 200) =>
    api.get<TelemetryReading[]>(`/engines/${engineId}/telemetry`, { limit }),
  rul: (engineId: string, limit = 30) => api.get<RulPrediction[]>(`/engines/${engineId}/rul`, { limit }),
  rulStatus: (engineId: string) => api.get<RulStatus>(`/engines/${engineId}/rul/status`),
  physicsConsistency: (engineId: string) =>
    api.get<PhysicsConsistencyResponse>(`/engines/${engineId}/physics-consistency`),
  faultsLatest: (engineId: string) => api.get<FaultPrediction>(`/engines/${engineId}/faults/latest`),
  bearingHealth: (engineId: string) => api.get<BearingHealthReading>(`/engines/${engineId}/bearing-health`),
  auxLatest: (engineId: string) => api.get<AuxPrediction>(`/engines/${engineId}/aux-latest`),
  maintenanceLogs: (engineId: string) => api.get<MaintenanceLog[]>(`/engines/${engineId}/maintenance-logs`),
  createMaintenanceLog: (engineId: string, actionTaken: string, notes?: string) =>
    api.post<MaintenanceLog>(`/engines/${engineId}/maintenance-logs`, { action_taken: actionTaken, notes }),
};

// ── UAV Assets ────────────────────────────────────────────────────────
export const uavAssetsApi = {
  list: () => api.get<UAVAsset[]>("/uav-assets"),
  create: (input: { tail_number: string; status?: string }) => api.post<UAVAsset>("/uav-assets", input),
  update: (assetId: string, input: { tail_number?: string; status?: string }) =>
    api.put<UAVAsset>(`/uav-assets/${assetId}`, input),
};

// ── Missions ──────────────────────────────────────────────────────────
export const missionsApi = {
  // `includeStats` adds reading_count / first_ts / last_ts per mission (one grouped query server-side).
  list: (includeStats = false) => api.get<Mission[]>("/missions", includeStats ? { include_stats: true } : undefined),
  get: (missionId: string) => api.get<MissionDetail>(`/missions/${missionId}`),
  create: (input: {
    uav_asset_id: string;
    mission_type: string;
    start_time: string;
    environmental_profile?: Record<string, unknown>;
  }) => api.post<Mission>("/missions", input),
};

// ── Alerts ────────────────────────────────────────────────────────────
export const alertsApi = {
  list: (filters?: { engine_id?: string; severity?: AlertSeverity; is_acknowledged?: boolean }) =>
    api.get<Alert[]>("/alerts", filters),
  acknowledge: (alertId: string) => api.patch<Alert>(`/alerts/${alertId}/acknowledge`),
};

// ── Dashboard ─────────────────────────────────────────────────────────
export const dashboardApi = {
  summary: () => api.get<DashboardSummary>("/dashboard/summary"),
};

// ── Simulation (replay / what-if) ────────────────────────────────────
export const simulationApi = {
  runReplay: (engineId: string, missionId: string) =>
    api.post<{ simulation_id: string; status: string }>("/simulation/run", {
      engine_id: engineId,
      mode: "replay",
      mission_id: missionId,
    }),
  runWhatIf: (engineId: string, environmentalProfile: Record<string, unknown>) =>
    api.post<{ simulation_id: string; status: string }>("/simulation/run", {
      engine_id: engineId,
      mode: "what_if",
      environmental_profile: environmentalProfile,
    }),
  get: (simulationId: string) => api.get<SimulationRunResponse>(`/simulation/${simulationId}`),
  // Parameter What-If: slider metadata (min/max/step/unit) — never hardcoded in the UI.
  whatIfConfig: () => api.get<WhatIfConfig>("/simulation/what-if/config"),
  // Read-only on the backend (writes no telemetry/predictions/alerts). Only
  // CHANGED parameters are sent; omitted ones mean "unchanged".
  runParameterWhatIf: (
    engineId: string,
    parameters: Partial<Record<WhatIfParam, number>>,
    baselineTimestamp?: string,
    timeoutMs?: number,
  ) =>
    api.post<WhatIfResponse>(
      "/simulation/what-if",
      {
        engine_id: engineId,
        ...(baselineTimestamp ? { baseline_timestamp: baselineTimestamp } : {}),
        parameters,
      },
      { timeoutMs },
    ),
};

// ── On-demand Simulator Control ───────────────────────────────────────
// Controls the live-telemetry simulator (the MQTT publisher that drives the
// dashboard).  Distinct from simulationApi (replay / what-if scenarios).
export type SimulatorStatus = "running" | "stopped" | "already_stopped";

export interface SimulatorStatusResponse {
  engine_id: string;
  status: "running" | "stopped" | "already_stopped";
}


export const simulatorApi = {
  /** Start the simulator for engine (idempotent). */
  start: (engineId: string) =>
    api.post<SimulatorStatusResponse>(`/simulator/${engineId}/start`),
  /** Explicitly stop the simulator. */
  stop: (engineId: string) =>
    api.post<SimulatorStatusResponse>(`/simulator/${engineId}/stop`),
  /** Force-stop regardless of state (admin / emergency). */
  forceStop: (engineId: string) =>
    api.delete<SimulatorStatusResponse>(`/simulator/${engineId}`),
  /** Lightweight heartbeat ping to keep the safety-net watchdog satisfied. */
  heartbeat: (engineId: string) =>
    api.post<{ ok: boolean }>(`/simulator/${engineId}/heartbeat`),
  /** Stop ALL running simulators — called on logout and window close. */
  stopAll: () =>
    api.post<{ stopped: string[] }>(`/simulator/stop-all`),
  /** Query the current state without any side-effects. */
  status: (engineId: string) =>
    api.get<SimulatorStatusResponse>(`/simulator/${engineId}/status`),
};
