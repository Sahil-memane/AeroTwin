import { describe, expect, it } from "vitest";
import { fmtAge, fmtAgeShort, parseBackendTs } from "./utils";

describe("time helpers", () => {
  it("fmtAgeShort shows seconds under a minute, then defers to fmtAge", () => {
    expect(fmtAgeShort(0)).toBe("0 s");
    expect(fmtAgeShort(12_400)).toBe("12 s");
    expect(fmtAgeShort(59_000)).toBe("59 s");
    expect(fmtAgeShort(8 * 60_000)).toBe("8 min");
    expect(fmtAgeShort(124 * 60_000)).toBe(fmtAge(124 * 60_000));
    expect(fmtAgeShort(-500)).toBe("0 s");
  });

  it("parseBackendTs reads zone-less backend timestamps as UTC and leaves zoned ones alone", () => {
    expect(parseBackendTs("2026-09-30T08:06:33").toISOString()).toBe("2026-09-30T08:06:33.000Z");
    expect(parseBackendTs("2026-09-30T08:06:33Z").toISOString()).toBe("2026-09-30T08:06:33.000Z");
    expect(parseBackendTs("2026-09-30T13:36:33+05:30").toISOString()).toBe("2026-09-30T08:06:33.000Z");
  });
});
