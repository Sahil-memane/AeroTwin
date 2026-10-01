import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { makeInsufficientResponse, makeResponse } from "@/test/whatIfFixtures";
import { BEARING_OR21, makeSpec, makeTelemetry, makeVm, minutesAgoNaive } from "@/test/twinFixtures";
import type { HealthInput } from "@/lib/engineTwin";
import { modeStyles, type TwinMode } from "@/lib/twinModes";
import { modePanel } from "@/lib/twinModePanel";
import { inspect, UNAVAILABLE } from "@/lib/twinInspect";
import { InspectorView, ModePanelView, SourceChip, SummaryBar, TwinCompare, compareRows, sourceAge, sourceChip } from "./TwinPanels";

const health = (over: Partial<HealthInput> = {}): HealthInput => ({ score: 64, factors: [], missing: [], excluded: [], primaryConcern: null, ...over });
const view = (vm: ReturnType<typeof makeVm>, mode: TwinMode) => render(<ModePanelView data={modePanel(vm, mode, modeStyles(vm, mode))} />);
const unavailableOf = (id: string) => screen.getByTestId(id).getAttribute("data-unavailable") === "true";

describe("source chip and age", () => {
  it("LIVE / STALE / NO DATA / REPLAY / WHAT-IF SIMULATION", () => {
    expect(sourceChip(makeVm()).text).toBe("LIVE");
    expect(sourceChip(makeVm({ telemetry: makeTelemetry({ ts: minutesAgoNaive(60) }) })).text).toBe("STALE");
    expect(sourceChip(makeVm({ telemetry: undefined })).text).toBe("NO DATA");
    expect(sourceChip(makeVm({ kind: "replay" })).text).toBe("REPLAY");
    expect(sourceChip(makeVm({ kind: "whatif" })).text).toBe("WHAT-IF SIMULATION");
  });
  it("renders the chip with a test id", () => {
    render(<SourceChip vm={makeVm({ telemetry: makeTelemetry({ ts: minutesAgoNaive(60) }) })} />);
    expect(screen.getByTestId("twin-state")).toHaveTextContent("STALE");
  });
  it("age text: updated / last data / no telemetry / step label", () => {
    expect(sourceAge(makeVm())).toMatch(/^updated \d+ s ago$/);
    expect(sourceAge(makeVm({ telemetry: makeTelemetry({ ts: minutesAgoNaive(65) }) }))).toMatch(/^last data 1 h 5 min ago/);
    expect(sourceAge(makeVm({ telemetry: undefined }))).toBe("no telemetry received");
    expect(sourceAge(makeVm({ kind: "replay", sourceLabel: "Step 2 / 9" }))).toBe("Step 2 / 9");
  });
});

describe("SummaryBar", () => {
  it("nothing available => every stat is 'Unavailable' (no invented numbers), health included", () => {
    render(<SummaryBar vm={makeVm({ telemetry: undefined })} />);
    for (const id of ["summary-health", "summary-rul", "summary-fault", "summary-bearing", "summary-aux", "summary-quality"]) {
      expect(screen.getByTestId(id)).toHaveTextContent(UNAVAILABLE);
      expect(unavailableOf(id)).toBe(true);
    }
    expect(screen.getByTestId("summary-source")).toHaveTextContent("NO DATA");
  });

  it("health is only ever the backend score: other model outputs without a score leave it Unavailable", () => {
    render(<SummaryBar vm={makeVm({ fault: { fault_class: "Compass Failure", confidence: 1, state: "FAULT_CONFIRMED" }, bearing: BEARING_OR21, rul: { rul_cycles: 2 } })} />);
    expect(screen.getByTestId("summary-health")).toHaveTextContent(UNAVAILABLE);
    expect(screen.getByTestId("summary-health")).toHaveTextContent("no score for this source");
  });

  it("a null backend score is Unavailable, not 0", () => {
    render(<SummaryBar vm={makeVm({ health: health({ score: null }) })} />);
    expect(screen.getByTestId("summary-health")).toHaveTextContent(UNAVAILABLE);
    expect(unavailableOf("summary-health")).toBe(true);
  });

  it("shows the real values when present", () => {
    render(
      <SummaryBar
        vm={makeVm({
          health: health({ score: 64.25, missing: ["aux"] }),
          rul: { rul_cycles: 120 },
          fault: { fault_class: "Compass Failure", confidence: 0.91, reliable: false },
          bearing: BEARING_OR21,
          aux: { risk_level: "HIGH", failure_probability_pct: 71, primary_failure_cause: null },
          quality: "VALID",
        })}
      />,
    );
    expect(screen.getByTestId("summary-health")).toHaveTextContent("64.3");
    expect(screen.getByTestId("summary-health")).toHaveTextContent("partial — no aux");
    expect(screen.getByTestId("summary-rul")).toHaveTextContent("120 cyc");
    expect(screen.getByTestId("summary-fault")).toHaveTextContent("Compass Failure");
    expect(screen.getByTestId("summary-fault")).toHaveTextContent("advisory — not scored");
    expect(screen.getByTestId("summary-bearing")).toHaveTextContent("OR_021");
    expect(screen.getByTestId("summary-bearing")).toHaveTextContent("0.021 in");
    expect(screen.getByTestId("summary-aux")).toHaveTextContent("HIGH");
    expect(screen.getByTestId("summary-aux")).toHaveTextContent("71% failure probability");
    expect(screen.getByTestId("summary-quality")).toHaveTextContent("VALID");
    expect(screen.getByTestId("summary-source")).toHaveTextContent("LIVE");
  });

  it("forced-zero health says so", () => {
    render(<SummaryBar vm={makeVm({ health: health({ score: 0, factors: [{ source: "bearing", forced_zero: true }] }) })} />);
    expect(screen.getByTestId("summary-health")).toHaveTextContent("forced to 0");
  });
});

describe("ModePanelView", () => {
  it("health mode: headline is the backend score; fusion rows show penalty / forced / excluded / missing", () => {
    const vm = makeVm({
      health: health({
        score: 40,
        factors: [{ source: "rul", penalty: 12 }, { source: "bearing", forced_zero: true }],
        missing: ["aux"],
        excluded: ["fault"],
      }),
    });
    view(vm, "health");
    expect(screen.getByTestId("mode-panel")).toHaveAttribute("data-mode", "health");
    expect(screen.getByTestId("mode-headline")).toHaveTextContent("40");
    expect(screen.getByTestId("fusion-row-rul")).toHaveAttribute("data-state", "penalty");
    expect(screen.getByTestId("fusion-row-rul")).toHaveTextContent("−12 pts");
    expect(screen.getByTestId("fusion-row-bearing")).toHaveAttribute("data-state", "forced");
    expect(screen.getByTestId("fusion-row-fault")).toHaveAttribute("data-state", "excluded");
    expect(screen.getByTestId("fusion-row-aux")).toHaveAttribute("data-state", "missing");
  });

  it("health mode without a score shows the headline as Unavailable with a reason", () => {
    view(makeVm(), "health");
    expect(screen.getByTestId("mode-headline")).toHaveTextContent(UNAVAILABLE);
    expect(screen.getByTestId("mode-headline")).toHaveTextContent(/no health score/i);
  });

  it("physics mode: table with measured/expected/residual/status; RPM is 'input'; missing cells Unavailable", () => {
    view(makeVm(), "physics");
    const cht = screen.getByTestId("physics-row-cht");
    expect(cht).toHaveTextContent("200");
    expect(cht).toHaveTextContent("150");
    expect(cht).toHaveTextContent("+50");
    expect(cht).toHaveTextContent("REVIEW");
    const rpm = screen.getByTestId("physics-row-rpm");
    expect(rpm).toHaveTextContent("input");
    expect(rpm).toHaveTextContent(UNAVAILABLE);
  });

  it("physics mode with no data: every cell is Unavailable", () => {
    view(makeVm({ telemetry: undefined, physics: [] }), "physics");
    const cht = screen.getByTestId("physics-row-cht");
    expect(within(cht).getAllByText(UNAVAILABLE).length).toBeGreaterThanOrEqual(3);
  });

  it("thermal mode: flags engine-level CHT, no per-cylinder values", () => {
    view(makeVm(), "thermal");
    expect(screen.getAllByTestId("mode-note").map((n) => n.textContent).join(" ")).toMatch(/not a per-cylinder measurement/i);
    expect(screen.queryByText(/cylinder 1/i)).not.toBeInTheDocument();
  });

  it("unavailable rows are flagged and carry their reason", () => {
    view(makeVm(), "fault");
    const flagged = screen.getAllByTestId("inspect-row").filter((r) => r.getAttribute("data-unavailable") === "true");
    expect(flagged.length).toBeGreaterThanOrEqual(6);
    expect(screen.getAllByText(/does not localise a fault to a component/i).length).toBeGreaterThan(0);
  });

  it("vibration mode: RMS unavailable below 10 samples, numeric from 10", () => {
    const { unmount } = view(makeVm({ vibrationHistory: [0.5, 0.5] }), "vibration");
    const row = screen.getByText("Vibration RMS").closest("[data-testid='inspect-row']")!;
    expect(row).toHaveAttribute("data-unavailable", "true");
    expect(row).toHaveTextContent(UNAVAILABLE);
    unmount();
    view(makeVm({ vibrationHistory: Array(10).fill(0.5) }), "vibration");
    const ok = screen.getByText(/Vibration RMS \(last 10 readings\)/).closest("[data-testid='inspect-row']")!;
    expect(ok).not.toHaveAttribute("data-unavailable");
    expect(ok).toHaveTextContent("0.5");
  });
});

describe("InspectorView", () => {
  it("empty: prompts to click a part", () => {
    render(<InspectorView inspection={null} onClear={() => undefined} />);
    expect(screen.getByTestId("inspector")).toHaveTextContent(/click any part/i);
    expect(screen.queryByTestId("inspector-title")).not.toBeInTheDocument();
  });

  it("cylinder: per-cylinder CHT/EGT are Unavailable with a reason; engine-level values are labelled", () => {
    const vm = makeVm();
    render(<InspectorView inspection={inspect({ kind: "cylinder", index: 1 }, vm, makeSpec())} onClear={() => undefined} />);
    expect(screen.getByTestId("inspector-title")).toHaveTextContent("Cylinder 2 · bank B");
    const own = screen.getByText("CHT — this cylinder").closest("[data-testid='inspect-row']")!;
    expect(own).toHaveTextContent(UNAVAILABLE);
    expect(own).toHaveAttribute("data-unavailable", "true");
    expect(own).toHaveTextContent(/one CHT \/ EGT sensor shared by all cylinders/);
    expect(screen.getByText("CHT — engine-level").closest("[data-testid='inspect-row']")).toHaveTextContent("200 °C");
    expect(screen.getByTestId("inspector-note")).toHaveTextContent(/not a per-cylinder measurement/i);
  });

  it("clear button calls onClear", () => {
    const onClear = vi.fn();
    render(<InspectorView inspection={inspect({ kind: "prop" }, makeVm(), makeSpec())} onClear={onClear} />);
    fireEvent.click(screen.getByRole("button", { name: "clear" }));
    expect(onClear).toHaveBeenCalledTimes(1);
  });
});

describe("TwinCompare", () => {
  it("renders current vs scenario from the response, marking what changed", () => {
    render(<TwinCompare result={makeResponse()} stale={false} />);
    expect(screen.getByTestId("twin-compare")).toHaveTextContent("WHAT-IF SIMULATION");
    const h = screen.getByTestId("compare-health");
    expect(h).toHaveTextContent("65");
    expect(h).toHaveTextContent("54");
    expect(h).toHaveAttribute("data-changed", "true");
    expect(screen.getByTestId("compare-rul")).toHaveTextContent("126 cyc");
    expect(screen.getByTestId("compare-rul")).toHaveTextContent("91 cyc");
    expect(screen.getByTestId("compare-fault")).toHaveTextContent("Compass Failure");
    expect(screen.getByTestId("compare-bearing")).not.toHaveAttribute("data-changed");
    expect(screen.getByTestId("compare-t-rpm")).toHaveAttribute("data-changed", "true");
    expect(screen.getByTestId("compare-t-cht")).not.toHaveAttribute("data-changed");
    const egt = screen.getByTestId("compare-p-egt");
    expect(egt).toHaveTextContent("CONSISTENT");
    expect(egt).toHaveTextContent("REVIEW");
    expect(screen.queryByTestId("twin-compare-stale")).not.toBeInTheDocument();
  });

  it("shows the stale-scenario banner when asked", () => {
    render(<TwinCompare result={makeResponse()} stale />);
    expect(screen.getByTestId("twin-compare-stale")).toHaveTextContent(/run again/i);
  });

  it("insufficient data: health 'Unavailable (partial)', unavailable models say so; no invented numbers", () => {
    render(<TwinCompare result={makeInsufficientResponse()} stale={false} />);
    expect(screen.getByTestId("compare-health")).toHaveTextContent(`${UNAVAILABLE} (partial)`);
    expect(screen.getByTestId("compare-health")).not.toHaveTextContent("100");
    expect(screen.getByTestId("compare-rul")).toHaveTextContent("Insufficient data");
    expect(screen.getByTestId("compare-fault")).toHaveTextContent("Insufficient data");
  });

  it("renders nothing when the response has no model results", () => {
    const { container } = render(<TwinCompare result={{ ...makeResponse(), model_results: undefined } as never} stale={false} />);
    expect(container).toBeEmptyDOMElement();
    expect(compareRows({ ...makeResponse(), baseline: undefined } as never)).toEqual([]);
  });
});
