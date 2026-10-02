import { NavLink, useLocation } from "react-router-dom";
import { useAuth } from "@/hooks/useAuth";
import { useTelemetryStore } from "@/store/telemetryStore";
import { useState, useRef, useEffect } from "react";

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
    to: "/twin",
    label: "3D Twin",
    icon: (
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round">
        <path d="M8 1.5l6 3.2v6.6L8 14.5l-6-3.2V4.7l6-3.2z" />
        <path d="M2 4.7l6 3.2 6-3.2M8 7.9v6.6" />
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
  const { pathname } = useLocation();
  // The twin page lives under /engines/:id/twin, so NavLink's own prefix match isn't enough.
  const onTwin = pathname === "/twin" || /^\/engines\/[^/]+\/twin$/.test(pathname);

  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  return (
    <div className="flex w-[208px] flex-shrink-0 flex-col border-r border-border bg-surface2 relative">
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
            className={({ isActive }) => {
              const active = item.to === "/twin" ? onTwin : isActive;
              return `flex items-center gap-2.5 rounded-sm border-l-2 px-3 py-2 text-[13px] font-medium ${
                active ? "border-accent bg-surface3 text-text" : "border-transparent text-textMuted hover:text-text"
              }`;
            }}
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

      {/* User Profile Popup Menu */}
      <div ref={menuRef} className="relative">
        {menuOpen && (
          <div className="absolute bottom-[calc(100%+8px)] left-2 right-2 rounded-md border border-borderStrong bg-surface p-1.5 shadow-xl shadow-black/40 z-50 animate-in slide-in-from-bottom-2 fade-in duration-200">
            <div className="px-2 py-2 mb-1 border-b border-border">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-textMuted mb-0.5">Signed In As</div>
              <div className="truncate text-xs font-medium text-text">{email}</div>
              <div className="mt-1 flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-accent"></span>
                <span className="text-[10px] uppercase tracking-wider text-accent font-semibold">{role?.replace(/_/g, " ")}</span>
              </div>
            </div>
            
            <button
              onClick={() => {
                setMenuOpen(false);
                logout();
              }}
              className="w-full flex items-center gap-2.5 rounded-sm px-2 py-2 text-left text-xs font-medium text-text hover:bg-surface3 hover:text-critical transition-colors"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path>
                <polyline points="16 17 21 12 16 7"></polyline>
                <line x1="21" y1="12" x2="9" y2="12"></line>
              </svg>
              Sign Out
            </button>
          </div>
        )}

        <button
          onClick={() => setMenuOpen((v) => !v)}
          className={`flex w-full items-center gap-2 border-t border-border px-4 py-3.5 text-left transition-colors ${menuOpen ? 'bg-surface3' : 'hover:bg-surface3'}`}
        >
          <div className="flex h-6.5 w-6.5 flex-shrink-0 items-center justify-center rounded-full border border-borderStrong bg-surface3 text-[11px] font-semibold">
            {initials}
          </div>
          <div className="min-w-0 flex-1">
            <div className="truncate text-xs font-semibold">{email}</div>
            <div className="text-[10px] text-textMuted truncate">{role?.replace(/_/g, " ")}</div>
          </div>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={`text-textMuted transition-transform duration-200 ${menuOpen ? 'rotate-180' : ''}`}>
            <polyline points="18 15 12 9 6 15"></polyline>
          </svg>
        </button>
      </div>
    </div>
  );
}
