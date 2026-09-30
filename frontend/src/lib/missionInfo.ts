import type { Mission } from "@/types";
import { fmtDateTime, parseBackendTs } from "@/lib/utils";

/** Mirrors backend MAX_REPLAY_READINGS (simulation.py): replay samples down to this many steps. */
export const MAX_REPLAY_STEPS = 300;

/** "endurance" → "Endurance", "high_altitude_patrol" → "High altitude patrol". */
export function missionTypeLabel(type: string): string {
  const spaced = type.replace(/[_-]+/g, " ").trim();
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

export function missionStatusLabel(status: string): string {
  return status.charAt(0).toUpperCase() + status.slice(1);
}

/** Whole-unit duration: "42 s", "17 min", "3 h 05 min", "1 d 13 h". */
export function fmtDuration(ms: number): string {
  const s = Math.max(0, Math.round(ms / 1000));
  if (s < 60) return `${s} s`;
  const min = Math.round(s / 60);
  if (min < 60) return `${min} min`;
  const h = Math.floor(min / 60);
  if (h < 24) return `${h} h ${String(min % 60).padStart(2, "0")} min`;
  return `${Math.floor(h / 24)} d ${h % 24} h`;
}

/** Unknown (stats not loaded) is treated as "may have data" so a missing stat never blocks the picker. */
export function hasRecordedData(m: Mission): boolean {
  return m.reading_count === undefined || m.reading_count === null ? true : m.reading_count > 0;
}

/** Recorded time span of the mission's telemetry, or null when not known / empty. */
export function recordedSpanMs(m: Mission): number | null {
  if (!m.first_ts || !m.last_ts) return null;
  return parseBackendTs(m.last_ts).getTime() - parseBackendTs(m.first_ts).getTime();
}

/** One-line description for a <select> option: which aircraft, what kind of mission, when, and how much data. */
export function missionLabel(m: Mission, tailNumber?: string): string {
  const parts = [tailNumber, missionTypeLabel(m.mission_type), fmtDateTime(m.start_time), missionStatusLabel(m.status)].filter(Boolean);
  if (m.reading_count !== undefined && m.reading_count !== null) {
    parts.push(m.reading_count > 0 ? `${m.reading_count.toLocaleString()} readings` : "no telemetry");
  }
  return parts.join(" · ");
}

/** What Replay will actually do with this mission's telemetry. */
export function replayPlan(m: Mission): string | null {
  const n = m.reading_count;
  if (n === undefined || n === null) return null;
  if (n === 0) return "No telemetry is stored for this mission, so Replay has nothing to run.";
  if (n > MAX_REPLAY_STEPS) return `Replay will sample ${MAX_REPLAY_STEPS} of the ${n.toLocaleString()} readings, evenly across the whole mission.`;
  return `Replay will use all ${n.toLocaleString()} readings.`;
}
