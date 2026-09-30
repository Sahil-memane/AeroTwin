import { NavLink } from "react-router-dom";
import { useAuth } from "@/hooks/useAuth";
import { useTelemetryStore } from "@/store/telemetryStore";

const NAV_ITEMS = [
  {
    to: "/dashboard",
    label: "Dashboard",
    icon: (
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4">
        <rect x="1.5" y="1.5" width="6" height="6" rx="0.5" />
        <rect x="8.5" y="1.5" width="6" height="6" rx="0.5" />
        <rect x="1.5" y="8.5" width="6" height="6" rx="0.5" />
        <rect x="8.5" y="8.5" width="6" height="6" rx="0.5" />
      </svg>
    ),
  },
  {
    to: "/missions",
    label: "Missions",
    icon: (
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round">
        <path d="M14.5 1.5L1.5 7.2l4.6 1.7 1.7 4.6L14.5 1.5z" />
      </svg>
    ),
  },
  {
    to: "/assets",
    label: "Assets",
    icon: (
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round">
        <rect x="1.5" y="3.5" width="13" height="9" rx="0.8" />
        <path d="M1.5 6.5h13" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    to: "/alerts",
    label: "Alerts",
    icon: (
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round">
        <path d="M8 2L14.5 13.5H1.5L8 2z" />
        <path d="M8 6.5v3.2" strokeLinecap="round" />
        <circle cx="8" cy="11.6" r="0.6" fill="currentColor" stroke="none" />
      </svg>
    ),
  },
];

export function Sidebar() {
  const { email, role, logout } = useAuth();
  const openAlertsCount = useTelemetryStore((s) => s.liveAlerts.filter((a) => !a.is_acknowledged).length);
  const initials = (email ?? "?").slice(0, 2).toUpperCase();

  return (
    <div className="flex w-[208px] flex-shrink-0 flex-col border-r border-border bg-surface2">
      <div className="border-b border-border px-5 pb-4 pt-5">
        <div className="text-[15px] font-bold tracking-wide">
          AERO<span className="text-accent">TWIN</span>
        </div>
        <div className="mt-0.5 text-[10px] tracking-wider text-textFaint">DIGITAL TWIN OPS</div>
      </div>

      <div className="flex flex-col gap-0.5 p-2">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              `flex items-center gap-2.5 rounded-sm border-l-2 px-3 py-2 text-[13px] font-medium ${
                isActive ? "border-accent bg-surface3 text-text" : "border-transparent text-textMuted hover:text-text"
              }`
            }
          >
            {item.icon}
            {item.label}
            {item.to === "/alerts" && openAlertsCount > 0 && (
              <span className="ml-auto rounded-full bg-critical px-1.5 py-0.5 text-[10px] font-bold text-white">
                {openAlertsCount}
              </span>
            )}
          </NavLink>
        ))}
      </div>

      <div className="flex-grow" />

      <button
        onClick={logout}
        className="flex items-center gap-2 border-t border-border px-4 py-3.5 text-left hover:bg-surface3"
      >
        <div className="flex h-6.5 w-6.5 flex-shrink-0 items-center justify-center rounded-full border border-borderStrong bg-surface3 text-[11px] font-semibold">
          {initials}
        </div>
        <div className="min-w-0">
          <div className="truncate text-xs font-semibold">{email}</div>
          <div className="text-[10px] text-textMuted">{role?.replace(/_/g, " ")}</div>
        </div>
      </button>
    </div>
  );
}
