import { useMemo } from "react";
import { cn } from "@/lib/utils";
import type { HealthStatus } from "@/types";

interface HealthScoreRingProps {
  // `null` means "no health score has ever been computed for this
  // engine yet" (Accuracy-First Phase 2) — distinct from a real score
  // of 0, which is a genuine critical assessment. Never pass a
  // fabricated 100/0 to paper over missing data; pass null instead.
  score: number | null;
  forcedZero?: boolean;
  size?: number;
  strokeWidth?: number;
  showLabel?: boolean;
  className?: string;
}

const STATUS_COLOR: Record<HealthStatus, string> = {
  healthy: "#4C9A6A",
  warning: "#C9962F",
  critical: "#C64F44",
};

function statusFor(score: number, forcedZero?: boolean): HealthStatus {
  if (forcedZero || score < 20) return "critical";
  if (score < 50) return "warning";
  return "healthy";
}

/**
 * Animated circular gauge — technique adapted from Magic UI's
 * "Animated Circular Progress Bar" (stroke-dasharray transition on a
 * fixed-radius circle), parameterized for the 3 sizes AeroTwin needs
 * (dashboard mini row, engine-detail hero, style-guide sample).
 */
export function HealthScoreRing({
  score,
  forcedZero = false,
  size = 100,
  strokeWidth = 8,
  showLabel = true,
  className,
}: HealthScoreRingProps) {
  const hasData = score !== null;
  const status = forcedZero ? "critical" : hasData ? statusFor(score, forcedZero) : null;
  const color = forcedZero ? "#E8564A" : status ? STATUS_COLOR[status] : "#4A5568";

  const { radius, circumference, offset } = useMemo(() => {
    const r = size / 2 - strokeWidth;
    const c = 2 * Math.PI * r;
    if (!hasData) return { radius: r, circumference: c, offset: c }; // 0 visible arc
    // Visual floor so a score of exactly 0 still shows a sliver of arc —
    // the number itself (rendered below) stays the accurate source of truth.
    const clamped = Math.max(0, Math.min(100, score));
    const visualPercent = clamped === 0 ? 4 : clamped;
    return { radius: r, circumference: c, offset: c * (1 - visualPercent / 100) };
  }, [score, hasData, size, strokeWidth]);

  return (
    <div className={cn("relative inline-flex items-center justify-center", className)} style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="#262D38"
          strokeWidth={strokeWidth}
          strokeDasharray={hasData ? undefined : "4 4"}
        />
        {hasData && (
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke={color}
            strokeWidth={strokeWidth}
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            transform={`rotate(-90 ${size / 2} ${size / 2})`}
            style={{ transition: "stroke-dashoffset 0.8s ease" }}
          />
        )}
      </svg>
      {showLabel && (
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="font-mono font-bold" style={{ color, fontSize: size * 0.24 }}>
            {hasData ? Math.round(score) : "—"}
          </span>
          {size >= 80 && (
            <span className="text-[9px] font-bold tracking-wider" style={{ color }}>
              {hasData ? status!.toUpperCase() : "NO DATA"}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
