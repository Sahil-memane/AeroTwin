import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/components/layout/AppShell", () => ({ AppShell: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }));
vi.mock("@/services/resources", () => ({ enginesApi: { list: vi.fn() } }));

import { enginesApi } from "@/services/resources";
import { TwinIndex } from "./TwinIndex";

const engine = (id: string, serial: string, status = "active") => ({ id, serial_number: serial, uav_asset_id: null, status });

function Where() {
  return <div data-testid="where">{useLocation().pathname}</div>;
}

function renderPage() {
  render(
    <MemoryRouter initialEntries={["/twin"]}>
      <Routes>
        <Route path="/twin" element={<TwinIndex />} />
        <Route path="/engines/:id/twin" element={<Where />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => vi.clearAllMocks());

describe("TwinIndex", () => {
  it("shows a loading state first", () => {
    vi.mocked(enginesApi.list).mockReturnValue(new Promise(() => undefined));
    renderPage();
    expect(screen.getByText(/loading engines/i)).toBeInTheDocument();
  });

  it("one engine => redirects straight to its twin", async () => {
    vi.mocked(enginesApi.list).mockResolvedValue([engine("eng-1", "SN-1")]);
    renderPage();
    await waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent("/engines/eng-1/twin"));
    expect(screen.queryByTestId("twin-index")).not.toBeInTheDocument();
  });

  it("several engines => a picker linking each to its own twin, with serial and status", async () => {
    vi.mocked(enginesApi.list).mockResolvedValue([engine("a", "SN-A", "active"), engine("b", "SN-B", "maintenance")]);
    renderPage();
    const a = await screen.findByTestId("twin-pick-a");
    expect(a).toHaveAttribute("href", "/engines/a/twin");
    expect(a).toHaveTextContent("SN-A");
    expect(screen.getByTestId("twin-pick-b")).toHaveAttribute("href", "/engines/b/twin");
    expect(screen.getByTestId("twin-pick-b")).toHaveTextContent("maintenance");
  });

  it("no engines => says so, no picker", async () => {
    vi.mocked(enginesApi.list).mockResolvedValue([]);
    renderPage();
    expect(await screen.findByText(/no engines are registered yet/i)).toBeInTheDocument();
    expect(screen.queryByText(/loading engines/i)).not.toBeInTheDocument();
  });

  it("a failed load shows an alert, not an empty fleet", async () => {
    vi.mocked(enginesApi.list).mockRejectedValue(new Error("500"));
    renderPage();
    expect(await screen.findByRole("alert")).toHaveTextContent(/couldn't load the engine list/i);
    expect(screen.queryByText(/no engines are registered yet/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/loading engines/i)).not.toBeInTheDocument();
  });
});
