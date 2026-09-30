import type { BearingHealthReading } from "@/types";

interface BearingHealthVisualizerProps {
  reading?: BearingHealthReading;
  size?: number;
}

function severityColor(inches: number | null): string {
  if (!inches) return "#4C9A6A";
  if (inches >= 0.021) return "#C64F44";
  if (inches >= 0.014) return "#C9962F";
  return "#C9962F";
}

export function BearingHealthVisualizer({ reading, size = 120 }: BearingHealthVisualizerProps) {
  const isNormal = !reading || reading.class_label === "Normal" || !reading.severity_inches;
  const color = isNormal ? "#4C9A6A" : severityColor(reading!.severity_inches);

  return (
    <div className="flex items-center gap-4">
      <svg width={size} height={size} viewBox="0 0 120 120">
        <circle cx="60" cy="60" r="46" fill="none" stroke="#333D4A" strokeWidth="10" />
        {!isNormal && (
          <circle
            cx="60"
            cy="60"
            r="46"
            fill="none"
            stroke={color}
            strokeWidth="10"
            strokeDasharray="18 271"
            strokeDashoffset="-5"
            transform="rotate(-90 60 60)"
          />
        )}
        <circle cx="60" cy="60" r="26" fill="none" stroke="#333D4A" strokeWidth="8" />
        <circle cx="60" cy="60" r="10" fill="#1D2330" stroke="#333D4A" strokeWidth="1.5" />
        {[[60, 14], [93, 37], [93, 83], [60, 106], [27, 83], [27, 37]].map(([x, y], i) => (
          <circle key={i} cx={x} cy={y} r="4.5" fill="#4A515C" />
        ))}
      </svg>
      <div>
        {reading ? (
          <>
            <div className="font-mono text-base font-bold" style={{ color }}>
              {reading.class_label}
            </div>
            <div className="text-xs text-textMuted mt-0.5">{reading.fault_location}</div>
            {reading.severity_inches != null && (
              <div className="text-xs text-textMuted">Severity {reading.severity_inches}in</div>
            )}
            <div className="text-xs text-textFaint">{(reading.confidence * 100).toFixed(0)}% confidence</div>
          </>
        ) : (
          <div className="text-xs text-textFaint border border-dashed border-borderStrong rounded px-3 py-2">
            — no bearing reading yet
          </div>
        )}
      </div>
    </div>
  );
}
