import type { ReactNode } from "react";
import { useEffect, useState } from "react";

interface TopbarProps {
  breadcrumb: string[];
  headerRight?: ReactNode;
}

export function Topbar({ breadcrumb, headerRight }: TopbarProps) {
  const [now, setNow] = useState(new Date());

  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  const formatted = now.toISOString().slice(0, 19).replace("T", " ") + " UTC";

  return (
    <div className="flex h-14 flex-shrink-0 items-center gap-4 border-b border-border bg-surface px-6">
      <div className="text-xs text-textMuted">
        {breadcrumb.map((part, i) => (
          <span key={i}>
            {i > 0 && <span className="mx-1.5 text-textFaint">/</span>}
            <span className={i === breadcrumb.length - 1 ? "text-text" : ""}>{part}</span>
          </span>
        ))}
      </div>
      <div className="flex-grow" />
      {/* Right-side slot: simulator controls (Dashboard) or nothing (other pages) */}
      {headerRight && <div className="flex items-center gap-3">{headerRight}</div>}
      <div className="flex items-center gap-1.5 text-[11px] font-semibold text-textMuted">
        <span className="h-1.5 w-1.5 rounded-full bg-healthy" />
        LIVE
      </div>
      <div className="font-mono text-xs text-textMuted">{formatted}</div>
    </div>
  );
}
