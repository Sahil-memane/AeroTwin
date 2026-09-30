import type { PhysicsConsistencyParameter, PhysicsConsistencyStatus } from "@/types";

interface PhysicsConsistencyPanelProps {
  parameters?: PhysicsConsistencyParameter[];
}

const LABELS: Record<PhysicsConsistencyParameter["parameter"], string> = {
  cht: "CHT",
  egt: "EGT",
  oil_pressure: "Oil Press",
  oil_temp: "Oil Temp",
  fuel_flow: "Fuel Flow",
};

const STATUS_COLOR: Record<PhysicsConsistencyStatus, string> = {
  CONSISTENT: "#4C9A6A",
  ELEVATED: "#C9962F",
  REVIEW: "#C9962F",
  ANOMALY: "#C64F44",
};

const fmt = (n: number, digits = 1) => Number(n.toFixed(digits)).toString();
const signed = (n: number) => (n > 0 ? `+${fmt(n)}` : fmt(n));

// Accuracy-First Phase 4 — real, server-computed Otto-cycle physics
// expectation next to what was actually measured, for each of the 5
// channels the solver covers. Never fabricated: every number here
// traces back to a real physics_deviation_readings row.
export function PhysicsConsistencyPanel({ parameters }: PhysicsConsistencyPanelProps) {
  if (!parameters || parameters.length === 0) {
    return (
      <div className="flex items-center justify-center rounded border border-dashed border-borderStrong px-4 py-6 text-xs text-textFaint">
        — no physics-consistency data yet
      </div>
    );
  }

  return (
    <table className="w-full table-fixed border-collapse text-xs">
      <thead>
        <tr className="text-left text-[10px] uppercase tracking-wide text-textFaint">
          <th className="w-[26%] pb-1.5 font-semibold">Channel</th>
          <th className="w-[19%] pb-1.5 text-right font-semibold">Measured</th>
          <th className="w-[19%] pb-1.5 text-right font-semibold">Expected</th>
          <th className="w-[17%] pb-1.5 text-right font-semibold">Residual</th>
          <th className="w-[19%] pb-1.5 text-right font-semibold">Status</th>
        </tr>
      </thead>
      <tbody className="font-mono">
        {parameters.map((p) => (
          <tr key={p.parameter} className="border-t border-border" title={`method: ${p.method}`}>
            <td className="py-1.5 font-sans font-semibold text-textMuted">
              <span className="mr-1.5 inline-block h-1.5 w-1.5 rounded-full align-middle" style={{ backgroundColor: STATUS_COLOR[p.status] }} />
              {LABELS[p.parameter]}
            </td>
            <td className="py-1.5 text-right">{fmt(p.measured)}</td>
            <td className="py-1.5 text-right text-textMuted">{fmt(p.expected)}</td>
            <td className="py-1.5 text-right text-textMuted">{signed(p.residual)}</td>
            <td className="py-1.5 text-right font-sans text-[10px] font-semibold" style={{ color: STATUS_COLOR[p.status] }}>
              {p.status}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
