import { describe, expect, it } from "vitest";
import type { Mission } from "@/types";
import { MAX_REPLAY_STEPS, fmtDuration, hasRecordedData, missionLabel, missionTypeLabel, recordedSpanMs, replayPlan } from "./missionInfo";

const M: Mission = {
  id: "abcdef12-0000-0000-0000-000000000000",
  uav_asset_id: "a",
  mission_type: "endurance",
  start_time: "2026-09-28T22:51:40",
  end_time: null,
  environmental_profile: null,
  status: "active",
};

describe("missionInfo helpers", () => {
  it("humanises mission types", () => {
    expect(missionTypeLabel("endurance")).toBe("Endurance");
    expect(missionTypeLabel("high_altitude_patrol")).toBe("High altitude patrol");
    expect(missionTypeLabel("test-flight")).toBe("Test flight");
  });

  it("formats durations at the right scale", () => {
    expect(fmtDuration(42_000)).toBe("42 s");
    expect(fmtDuration(17 * 60_000)).toBe("17 min");
    expect(fmtDuration((3 * 60 + 5) * 60_000)).toBe("3 h 05 min");
    expect(fmtDuration((37) * 3600_000)).toBe("1 d 13 h");
    expect(fmtDuration(-5)).toBe("0 s");
  });

  it("treats unknown stats as 'may have data' but 0 as empty", () => {
    expect(hasRecordedData(M)).toBe(true);
    expect(hasRecordedData({ ...M, reading_count: null })).toBe(true);
    expect(hasRecordedData({ ...M, reading_count: 0 })).toBe(false);
    expect(hasRecordedData({ ...M, reading_count: 1 })).toBe(true);
  });

  it("computes the recorded span from naive-UTC timestamps", () => {
    expect(recordedSpanMs(M)).toBeNull();
    expect(recordedSpanMs({ ...M, first_ts: "2026-09-30T08:00:00", last_ts: "2026-09-30T08:10:00" })).toBe(10 * 60_000);
  });

  it("states honestly what replay will do with the readings", () => {
    expect(replayPlan(M)).toBeNull(); // stats not loaded -> say nothing rather than guess
    expect(replayPlan({ ...M, reading_count: 0 })).toMatch(/nothing to run/);
    expect(replayPlan({ ...M, reading_count: 120 })).toBe("Replay will use all 120 readings.");
    expect(replayPlan({ ...M, reading_count: MAX_REPLAY_STEPS })).toMatch(/use all/);
    expect(replayPlan({ ...M, reading_count: MAX_REPLAY_STEPS + 1 })).toMatch(/sample 300 of the 301 readings/);
  });

  it("builds the option label, omitting what isn't known", () => {
    expect(missionLabel({ ...M, reading_count: 92166 }, "N123AB")).toMatch(/^N123AB · Endurance · .+ · Active · 92,166 readings$/);
    expect(missionLabel({ ...M, reading_count: 0, status: "scheduled" })).toMatch(/^Endurance · .+ · Scheduled · no telemetry$/);
    expect(missionLabel(M, "N1")).toMatch(/^N1 · Endurance · .+ · Active$/); // no stats -> no data suffix
  });
});
