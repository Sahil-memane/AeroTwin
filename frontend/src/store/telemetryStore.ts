import { create } from "zustand";
import type {
  Alert,
  AuxPrediction,
  BearingHealthReading,
  ContributingFactor,
  FaultPrediction,
  HealthStatus,
  PhysicsConsistencyParameter,
  RulPrediction,
  TelemetryReading,
} from "@/types";

export interface EngineLiveState {
  telemetry?: TelemetryReading;
  rul?: RulPrediction;
  fault?: FaultPrediction;
  bearing?: BearingHealthReading;
  aux?: AuxPrediction;
  healthScore?: {
    combined_score: number | null;
    contributing_factors: ContributingFactor[];
    primary_concern?: string | null;
    /** Sources with no fresh prediction — the score excludes them (partial assessment). */
    missing_sources?: string[];
    /** Sources that reported but are advisory-only and not scored (e.g. "fault": low input coverage). */
    excluded_sources?: string[];
    ts: string;
  };
  physicsConsistency?: PhysicsConsistencyParameter[];
}

function statusFor(score: number): HealthStatus {
  if (score < 20) return "critical";
  if (score < 50) return "warning";
  return "healthy";
}

interface TelemetryState {
  engines: Record<string, EngineLiveState>;
  liveAlerts: Alert[];
  setTelemetry: (engineId: string, data: TelemetryReading) => void;
  setRul: (engineId: string, data: RulPrediction) => void;
  setFault: (engineId: string, data: FaultPrediction) => void;
  setBearing: (engineId: string, data: BearingHealthReading) => void;
  setAux: (engineId: string, data: AuxPrediction) => void;
  setHealthScore: (
    engineId: string,
    data: {
      combined_score: number | null;
      contributing_factors: ContributingFactor[];
      primary_concern?: string | null;
      missing_sources?: string[];
      excluded_sources?: string[];
      ts: string;
    },
  ) => void;
  setPhysicsConsistency: (engineId: string, data: PhysicsConsistencyParameter[]) => void;
  pushLiveAlert: (alert: Alert) => void;
  ackAlertLocally: (alertId: string) => void;
}

export const useTelemetryStore = create<TelemetryState>((set) => ({
  engines: {},
  liveAlerts: [],
  setTelemetry: (engineId, data) =>
    set((s) => ({ engines: { ...s.engines, [engineId]: { ...s.engines[engineId], telemetry: data } } })),
  setRul: (engineId, data) =>
    set((s) => ({ engines: { ...s.engines, [engineId]: { ...s.engines[engineId], rul: data } } })),
  setFault: (engineId, data) =>
    set((s) => ({ engines: { ...s.engines, [engineId]: { ...s.engines[engineId], fault: data } } })),
  setBearing: (engineId, data) =>
    set((s) => ({ engines: { ...s.engines, [engineId]: { ...s.engines[engineId], bearing: data } } })),
  setAux: (engineId, data) =>
    set((s) => ({ engines: { ...s.engines, [engineId]: { ...s.engines[engineId], aux: data } } })),
  setHealthScore: (engineId, data) =>
    set((s) => ({ engines: { ...s.engines, [engineId]: { ...s.engines[engineId], healthScore: data } } })),
  setPhysicsConsistency: (engineId, data) =>
    set((s) => ({ engines: { ...s.engines, [engineId]: { ...s.engines[engineId], physicsConsistency: data } } })),
  pushLiveAlert: (alert) => set((s) => ({ liveAlerts: [alert, ...s.liveAlerts].slice(0, 20) })),
  ackAlertLocally: (alertId) =>
    set((s) => ({
      liveAlerts: s.liveAlerts.map((a) => (a.id === alertId ? { ...a, is_acknowledged: true } : a)),
    })),
}));

export { statusFor };
