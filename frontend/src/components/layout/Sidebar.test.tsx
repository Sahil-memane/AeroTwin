import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";
import { useAuthStore } from "@/store/authStore";
import { useTelemetryStore } from "@/store/telemetryStore";
import { Sidebar } from "./Sidebar";

function renderAt(path: string) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <Sidebar />
      <Routes>
        <Route path="*" element={<div data-testid="page" />} />
      </Routes>
    </MemoryRouter>,
  );
}

const link = (name: string) => screen.getByRole("link", { name: new RegExp(name) });
const active = (name: string) => link(name).className.includes("border-accent");

beforeEach(() => {
  useAuthStore.setState({ email: "ops@example.com", role: "operator" as never, isAuthenticated: true });
  useTelemetryStore.setState({ engines: {}, liveAlerts: [] });
});

describe("Sidebar: 3D Twin nav item", () => {
  it("is present, links to /twin, and sits right after Dashboard", () => {
    renderAt("/dashboard");
    expect(link("3D Twin")).toHaveAttribute("href", "/twin");
    const labels = screen.getAllByRole("link").map((a) => a.textContent);
    expect(labels).toEqual(["Dashboard", "3D Twin", "Missions", "Assets", "Alerts"]);
  });

  it("is active on /twin and Dashboard is not", () => {
    renderAt("/twin");
    expect(active("3D Twin")).toBe(true);
    expect(active("Dashboard")).toBe(false);
  });

  it("stays active on a per-engine twin page /engines/:id/twin", () => {
    renderAt("/engines/abc-123/twin");
    expect(active("3D Twin")).toBe(true);
    expect(active("Dashboard")).toBe(false);
  });

  it.each(["/dashboard", "/engines/abc-123", "/engines/abc-123/simulation", "/missions", "/alerts"])("is not active on %s", (path) => {
    renderAt(path);
    expect(active("3D Twin")).toBe(false);
  });

  it("other items keep their own active state", () => {
    renderAt("/dashboard");
    expect(active("Dashboard")).toBe(true);
    expect(active("Missions")).toBe(false);
  });

  it("clicking it navigates to /twin and makes it active", () => {
    renderAt("/dashboard");
    fireEvent.click(link("3D Twin"));
    expect(active("3D Twin")).toBe(true);
    expect(active("Dashboard")).toBe(false);
  });
});

describe("Sidebar: account and alert badge", () => {
  it("shows the signed-in email and initials", () => {
    renderAt("/dashboard");
    expect(screen.getByText("ops@example.com")).toBeInTheDocument();
    expect(screen.getByText("OP")).toBeInTheDocument();
  });

  it("the Alerts badge counts only unacknowledged live alerts", () => {
    const a = (id: string, ack: boolean) => ({ id, engine_id: "e", source: "s", severity: "warning" as const, message: "m", created_at: "t", is_acknowledged: ack, acknowledged_by: null, acknowledged_at: null });
    useTelemetryStore.setState({ liveAlerts: [a("1", false), a("2", false), a("3", true)] });
    renderAt("/dashboard");
    expect(link("Alerts")).toHaveTextContent("2");
  });

  it("no badge without open alerts", () => {
    renderAt("/dashboard");
    expect(link("Alerts").textContent).toBe("Alerts");
  });
});
