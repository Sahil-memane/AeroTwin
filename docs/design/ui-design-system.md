# AeroTwin — UI Design System

Approved direction (Phase 5A): aerospace/defense-grade operator console —
dense, information-first, no gradients/glow/decorative chrome. Values on
screen are either real backend data or explicitly marked unavailable.

Source of truth for the actual token values is `frontend/tailwind.config.ts`
— this doc explains the rationale and where each token is used.

## Color tokens

| Token | Hex | Use |
|---|---|---|
| `bg` | `#0B0E13` | Page background |
| `surface` / `surface2` / `surface3` | `#12161D` / `#171C24` / `#1D2330` | Panel, elevated panel, hover/active surface |
| `border` / `borderStrong` | `#262D38` / `#333D4A` | Hairline dividers, input/button borders |
| `text` / `textMuted` / `textFaint` | `#E4E7EB` / `#8B93A1` / `#4A515C` | Primary / secondary / disabled-unavailable text |
| `healthy` | `#4C9A6A` | Health score ≥ 50 |
| `warning` | `#C9962F` | Health score 20–49 |
| `critical` | `#C64F44` | Health score < 20 |
| `forcedZero` | `#E8564A` (fill `#3A1512`) | Fault confidence > 90% forces score to 0 — visually distinct from plain "critical" |
| `srcFault` / `srcRul` / `srcBearing` / `srcAux` | `#6C8EBF` / `#8B7FC7` / `#4FA8B5` / `#B08A5A` | Per-model badge colors, distinct hue family from the health bands to avoid confusion |
| `accent` | `#5B8FD6` | Links, primary buttons, focus rings |

All status colors are intentionally desaturated (not neon) per the brief.

## Typography

IBM Plex Sans (UI chrome, labels, body) + IBM Plex Mono (all telemetry
numbers, timestamps, IDs) — loaded via Google Fonts in `index.html`.
Cross-checked against ui-ux-pro-max's dashboard-oriented font pairings
("Dashboard Data": Fira Code/Fira Sans, "Developer Mono": JetBrains
Mono/IBM Plex Sans) — Plex Sans/Mono holds up against both and was kept
rather than swapped without real benefit.

## Component → implementation mapping

| Design component | Implementation | Notes |
|---|---|---|
| HealthScoreRing | `frontend/src/components/HealthScoreRing.tsx` | Stroke-dasharray technique adapted from Magic UI's `animated-circular-progress-bar`; 4 states (healthy/warning/critical/forced-zero) |
| RulTrendChart | `frontend/src/components/RulTrendChart.tsx` | Hand-rolled SVG polyline, warning-threshold line at 50 cycles, critical shading zone |
| FaultAlertBanner | `frontend/src/components/FaultAlertBanner.tsx` | Renders only when `fault_class !== "No Failure"`; forced-zero gets a darker fill |
| BearingHealthVisualizer | `frontend/src/components/BearingHealthVisualizer.tsx` | Schematic double-ring + ball markers |
| AuxRadarChart | `frontend/src/components/AuxRadarChart.tsx` | 5-axis pentagon (TWF/HDF/PWF/OSF/RNF), computed via trig, not hardcoded points |
| CopilotPanel | `frontend/src/components/CopilotPanel.tsx` | Collapsed docked tab ↔ 380px expanded panel; response text uses a Magic UI `typing-animation`-style character reveal |
| Live ticker | `frontend/src/components/LiveTicker.tsx` | Magic UI `marquee` technique (duplicated track + CSS keyframe), used for a functional ops-feed strip, not decoration |
| KPI counters | `frontend/src/components/NumberTicker.tsx` | Adapted from Magic UI `number-ticker` (spring count-up via `motion`) |

## Deliberately not used

Magic UI's decorative/marketing components — meteors, confetti, particles,
sparkles-text, aurora-text, neon-gradient-card, warp-background, retro-grid,
light-rays, globe, icon-cloud, border-beam glow, shimmer/rainbow/shiny
buttons — all conflict with the "no gradients/glow/decoration" brief for
an operator console.

ui-ux-pro-max's top style match for "aerospace defense mission control"
was **HUD / Sci-Fi FUI** (neon glow, scanning lines) — also not used for
the same reason. The **Data-Dense Dashboard** style match (low motion
cost, no glow) was used instead to validate density/spacing.
