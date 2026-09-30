import { useMemo } from "react";
import type { RulPrediction } from "@/types";

interface RulTrendChartProps {
  data: RulPrediction[];
  width?: number;
  height?: number;
  className?: string;
  // Accuracy-First Phase 2: when there are zero predictions, distinguish
  // "still collecting the sliding window" from "nothing at all yet" —
  // shown only when the caller has real progress to report (from
  // GET /rul/status), never fabricated.
  collecting?: { samplesCollected: number; samplesRequired: number } | null;
}

const RUL_CAP = 125;
const THRESHOLD = 50;

export function RulTrendChart({ data, width = 500, height = 170, className, collecting }: RulTrendChartProps) {
  const { points, latest, bandPath } = useMemo(() => {
    if (data.length === 0) return { points: "", latest: null, bandPath: "" };
    const ordered = [...data].reverse(); // oldest -> newest, left to right
    const plotW = width - 20;
    const plotH = height - 30;
    const step = ordered.length > 1 ? plotW / (ordered.length - 1) : 0;
    const yFor = (v: number) => 10 + plotH * (1 - Math.max(0, Math.min(RUL_CAP, v)) / RUL_CAP);
    const pts = ordered.map((d, i) => `${(10 + i * step).toFixed(1)},${yFor(d.rul_cycles).toFixed(1)}`);

    // Real split-conformal interval (Accuracy-First Phase 2) — only
    // drawn where actually present (pre-Phase-2 rows have neither
    // bound), never interpolated/invented for rows that lack it.
    const withBand = ordered.filter((d) => d.rul_lower != null && d.rul_upper != null);
    let bandPath = "";
    if (withBand.length > 1) {
      const upperPts = withBand.map((d) => {
        const i = ordered.indexOf(d);
        return `${(10 + i * step).toFixed(1)},${yFor(d.rul_upper!).toFixed(1)}`;
      });
      const lowerPts = withBand
        .map((d) => {
          const i = ordered.indexOf(d);
          return `${(10 + i * step).toFixed(1)},${yFor(d.rul_lower!).toFixed(1)}`;
        })
        .reverse();
      bandPath = `M ${upperPts.join(" L ")} L ${lowerPts.join(" L ")} Z`;
    }

    return { points: pts.join(" "), latest: ordered[ordered.length - 1], bandPath };
  }, [data, width, height]);

  const thresholdY = 10 + (height - 30) * (1 - THRESHOLD / RUL_CAP);
  const isImminent = latest && latest.rul_cycles < THRESHOLD;

  if (data.length === 0) {
    return (
      <div
        className="flex flex-col items-center justify-center gap-1 rounded border border-dashed border-borderStrong text-textFaint text-xs"
        style={{ width, height }}
      >
        {collecting ? (
          <>
            <span>Collecting history — {collecting.samplesCollected}/{collecting.samplesRequired} samples</span>
            <span className="text-[10px] text-textFaint/70">RUL prediction unavailable until the window fills</span>
          </>
        ) : (
          "— no RUL predictions yet"
        )}
      </div>
    );
  }

  return (
    <svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`} className={className}>
      {isImminent && (
        <rect x={width * 0.7} y={10} width={width * 0.3 - 10} height={height - 30} fill="#C64F44" opacity={0.08} />
      )}
      <line x1={0} y1={thresholdY} x2={width} y2={thresholdY} stroke="#C9962F" strokeWidth={1} strokeDasharray="4 3" />
      <text x={4} y={thresholdY - 4} fontSize={9} fill="#C9962F" fontFamily="IBM Plex Mono, monospace">
        {THRESHOLD} cyc — warning threshold
      </text>
      {bandPath && <path d={bandPath} fill="#5B8FD6" opacity={0.12} stroke="none" />}
      <polyline points={points} fill="none" stroke="#5B8FD6" strokeWidth={2} />
      {latest && (
        <circle
          cx={Number(points.split(" ").at(-1)?.split(",")[0])}
          cy={Number(points.split(" ").at(-1)?.split(",")[1])}
          r={4}
          fill={latest.rul_cycles < 20 ? "#E8564A" : latest.rul_cycles < 50 ? "#C9962F" : "#4C9A6A"}
        />
      )}
    </svg>
  );
}
