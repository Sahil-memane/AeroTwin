import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Backend timestamps are naive UTC (e.g. "2026-09-30T08:06:33.04", no zone
 * suffix). `new Date()` would read those as LOCAL time and show them offset
 * by the viewer's UTC difference, so every backend timestamp goes through
 * here. Strings that already carry a zone (Z / +05:30) are left untouched. */
export function parseBackendTs(ts: string): Date {
  return new Date(/([zZ]|[+-]\d{2}:?\d{2})$/.test(ts) ? ts : `${ts}Z`);
}

export function fmtDateTime(ts: string): string {
  return parseBackendTs(ts).toLocaleString();
}

export function fmtTime(ts: string): string {
  return parseBackendTs(ts).toLocaleTimeString();
}

/** "8 min", "2 h 4 min" */
export function fmtAge(ms: number): string {
  const min = Math.max(0, Math.round(ms / 60_000));
  if (min < 60) return `${min} min`;
  return `${Math.floor(min / 60)} h ${min % 60} min`;
}
