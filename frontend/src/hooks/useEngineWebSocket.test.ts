import { describe, expect, it } from "vitest";
import { resolveWsBase } from "@/hooks/useEngineWebSocket";

describe("resolveWsBase", () => {
  it("leaves an absolute URL untouched", () => {
    expect(resolveWsBase("ws://localhost:8000/api/v1", { protocol: "http:", host: "x" })).toBe("ws://localhost:8000/api/v1");
  });
  it("resolves a same-origin path to wss on https pages", () => {
    expect(resolveWsBase("/api/v1", { protocol: "https:", host: "twin.example.com" })).toBe("wss://twin.example.com/api/v1");
  });
  it("resolves a same-origin path to ws on http pages", () => {
    expect(resolveWsBase("/api/v1", { protocol: "http:", host: "localhost:8080" })).toBe("ws://localhost:8080/api/v1");
  });
});
