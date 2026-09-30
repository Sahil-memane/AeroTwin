import { useMemo } from "react";
import type { AuxPrediction } from "@/types";

interface AuxRadarChartProps {
  data?: AuxPrediction;
  size?: number;
}

const AXES = ["TWF", "HDF", "PWF", "OSF", "RNF"] as const;
const CX = 90;
const CY = 90;
const R = 70;

function vertex(index: number, radiusFraction: number) {
  const angle = (-90 + index * 72) * (Math.PI / 180);
  return { x: CX + R * radiusFraction * Math.cos(angle), y: CY + R * radiusFraction * Math.sin(angle) };
}

export function AuxRadarChart({ data, size = 180 }: AuxRadarChartProps) {
  const { dataPoints, primaryCause, dominant } = useMemo(() => {
    const byCode: Record<string, number> = { TWF: 0, HDF: 0, PWF: 0, OSF: 0, RNF: 0 };
    for (const f of data?.detected_failure_types ?? []) {
      if (f.code in byCode) byCode[f.code] = f.probability * 100;
    }
    const pts = AXES.map((code, i) => vertex(i, Math.min(1, byCode[code] / 100)));
    const maxCode = AXES.reduce((a, b) => (byCode[a] >= byCode[b] ? a : b));
    return {
      dataPoints: pts.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" "),
      primaryCause: data?.primary_failure_cause,
      dominant: byCode[maxCode] > 0 ? { code: maxCode, value: byCode[maxCode] } : null,
    };
  }, [data]);

  const outer = AXES.map((_, i) => vertex(i, 1));
  const mid = AXES.map((_, i) => vertex(i, 0.67));
  const inner = AXES.map((_, i) => vertex(i, 0.33));
  const poly = (pts: { x: number; y: number }[]) => pts.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");

  return (
    <div>
      <svg width={size} height={size} viewBox="-16 0 212 180">
        <polygon points={poly(outer)} fill="none" stroke="#333D4A" strokeWidth={1} />
        <polygon points={poly(mid)} fill="none" stroke="#262D38" strokeWidth={1} />
        <polygon points={poly(inner)} fill="none" stroke="#262D38" strokeWidth={1} />
        {outer.map((p, i) => (
          <line key={i} x1={CX} y1={CY} x2={p.x} y2={p.y} stroke="#262D38" strokeWidth={1} />
        ))}
        {data && <polygon points={dataPoints} fill="#B08A5A" fillOpacity={0.32} stroke="#B08A5A" strokeWidth={1.5} />}
        {AXES.map((label, i) => {
          const p = vertex(i, 1.14);
          const anchor = i === 0 ? "middle" : i === 1 ? "start" : i === 2 ? "start" : i === 3 ? "end" : "end";
          return (
            <text key={label} x={p.x} y={p.y} textAnchor={anchor} fontSize={9} fill="#8B93A1">
              {label}
              {dominant?.code === label && dominant.value > 0 ? ` ${dominant.value.toFixed(0)}%` : ""}
            </text>
          );
        })}
      </svg>
      {primaryCause && (
        <div className="text-xs text-textMuted mt-1">
          Primary cause: <span className="font-semibold" style={{ color: "#C9962F" }}>{primaryCause}</span>
        </div>
      )}
      {!data && <div className="text-xs text-textFaint mt-1">— no auxiliary prediction yet</div>}
    </div>
  );
}
