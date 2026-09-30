import type { ReactNode } from "react";

interface LiveTickerProps {
  items: ReactNode[];
}

/**
 * Adapted from Magic UI's "Marquee" (registry: marquee) — duplicated
 * track + CSS keyframe translate, paused on hover. Used as an ops-center
 * style live status strip rather than a decorative scroller.
 */
export function LiveTicker({ items }: LiveTickerProps) {
  if (items.length === 0) return null;

  return (
    <div className="group overflow-hidden border-y border-border bg-surface2 py-1.5">
      <div className="flex w-max animate-ticker-scroll gap-12 group-hover:[animation-play-state:paused]">
        {[0, 1].map((rep) => (
          <div key={rep} className="flex gap-12">
            {items.map((item, i) => (
              <div key={`${rep}-${i}`} className="flex items-center gap-2 whitespace-nowrap font-mono text-[11px]">
                {item}
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
