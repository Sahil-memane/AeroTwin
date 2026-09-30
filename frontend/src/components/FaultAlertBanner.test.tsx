import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { FaultPrediction } from "@/types";
import { FaultAlertBanner } from "./FaultAlertBanner";

const fault = (over: Partial<FaultPrediction> = {}): FaultPrediction => ({
  ts: "2026-09-30T12:57:43",
  engine_id: "e",
  model_version_id: "m",
  class_id: 5,
  fault_class: "Compass Failure",
  confidence: 0.999,
  probabilities: [],
  state: "FAULT_CONFIRMED",
  ...over,
});

describe("FaultAlertBanner", () => {
  it.each([
    ["no fault", undefined],
    ["No Failure", fault({ fault_class: "No Failure" })],
    ["abstained", fault({ fault_class: "Unknown / insufficient evidence" })],
    ["recovered", fault({ state: "RECOVERED" })],
  ])("renders nothing for %s", (_n, f) => {
    const { container } = render(<FaultAlertBanner fault={f} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("a reliable confirmed fault is a red alert that says health is forced to 0, with Acknowledge", () => {
    const onAck = vi.fn();
    render(<FaultAlertBanner fault={fault({ reliable: true, input_coverage: 0.9 })} onAcknowledge={onAck} />);
    expect(screen.getByTestId("fault-banner")).toHaveAttribute("data-variant", "alert");
    expect(screen.getByTestId("fault-banner-title")).toHaveTextContent("FAULT DETECTED — COMPASS FAILURE");
    expect(screen.getByTestId("fault-banner-detail")).toHaveTextContent("health score forced to 0");
    fireEvent.click(screen.getByRole("button", { name: "Acknowledge" }));
    expect(onAck).toHaveBeenCalled();
  });

  it("a legacy row (no reliability info) keeps the original alert behaviour", () => {
    render(<FaultAlertBanner fault={fault()} onAcknowledge={() => undefined} />);
    expect(screen.getByTestId("fault-banner")).toHaveAttribute("data-variant", "alert");
    expect(screen.getByTestId("fault-banner-detail")).toHaveTextContent("health score forced to 0");
  });

  it("an advisory result is shown neutrally, labelled not scored, and never claims to force health to 0", () => {
    render(<FaultAlertBanner fault={fault({ reliable: false, input_coverage: 0.46875 })} onAcknowledge={() => undefined} />);
    expect(screen.getByTestId("fault-banner")).toHaveAttribute("data-variant", "advisory");
    expect(screen.getByTestId("fault-banner-title")).toHaveTextContent("FAULT MODEL ADVISORY — COMPASS FAILURE (not scored)");
    const detail = screen.getByTestId("fault-banner-detail");
    expect(detail).toHaveTextContent("99.9% model confidence");
    expect(detail).toHaveTextContent("only 47% of the model's input channels are measured");
    expect(detail).toHaveTextContent("not used in the health score or alerts");
    expect(detail).not.toHaveTextContent("forced to 0");
    expect(screen.queryByRole("button", { name: "Acknowledge" })).not.toBeInTheDocument(); // nothing to acknowledge
  });

  it("an advisory result without a coverage figure still explains itself", () => {
    render(<FaultAlertBanner fault={fault({ reliable: false })} />);
    expect(screen.getByTestId("fault-banner-detail")).toHaveTextContent("low input coverage");
  });

  it("a stale prediction is dated and dimmed, and can't be acknowledged as if it were current", () => {
    render(<FaultAlertBanner fault={fault({ reliable: true })} onAcknowledge={() => undefined} ageMs={3_600_000} />);
    expect(screen.getByTestId("fault-banner-stale")).toHaveTextContent("Last prediction 1 h 00 min ago — engine not streaming".replace("1 h 00", "1 h 0"));
    expect(screen.getByTestId("fault-banner")).toHaveClass("opacity-70");
    expect(screen.queryByRole("button", { name: "Acknowledge" })).not.toBeInTheDocument();
  });

  it("a fresh prediction shows no stale line", () => {
    render(<FaultAlertBanner fault={fault({ reliable: true })} onAcknowledge={() => undefined} ageMs={30_000} />);
    expect(screen.queryByTestId("fault-banner-stale")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Acknowledge" })).toBeInTheDocument();
  });
});
