import type { Config } from "tailwindcss";

/**
 * AeroTwin design tokens — approved in the Phase 5A design review
 * (docs/design/ui-design-system.md has the full rationale). Aerospace
 * ops-console theme: near-black surfaces, hairline borders, desaturated
 * status colors, monospace telemetry. No gradients/glow tokens on purpose.
 */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        bg: "#0B0E13",
        surface: "#12161D",
        surface2: "#171C24",
        surface3: "#1D2330",
        border: "#262D38",
        borderStrong: "#333D4A",
        text: "#E8EAED",
        textMuted: "#A0A8B5",
        textFaint: "#8C94A3",

        healthy: "#4C9A6A",
        healthyBg: "rgba(76,154,106,0.14)",
        warning: "#C9962F",
        warningBg: "rgba(201,150,47,0.14)",
        critical: "#C64F44",
        criticalBg: "rgba(198,79,68,0.14)",
        forcedZero: "#E8564A",
        forcedZeroBg: "#3A1512",

        srcFault: "#6C8EBF",
        srcFaultBg: "rgba(108,142,191,0.14)",
        srcRul: "#8B7FC7",
        srcRulBg: "rgba(139,127,199,0.14)",
        srcBearing: "#4FA8B5",
        srcBearingBg: "rgba(79,168,181,0.14)",
        srcAux: "#B08A5A",
        srcAuxBg: "rgba(176,138,90,0.14)",

        accent: "#5B8FD6",
      },
      fontFamily: {
        sans: ["IBM Plex Sans", "system-ui", "sans-serif"],
        mono: ["IBM Plex Mono", "SF Mono", "Consolas", "monospace"],
      },
      keyframes: {
        "ticker-scroll": {
          from: { transform: "translateX(0)" },
          to: { transform: "translateX(-50%)" },
        },
        "blink-cursor": {
          "0%, 49%": { opacity: "1" },
          "50%, 100%": { opacity: "0" },
        },
      },
      animation: {
        "ticker-scroll": "ticker-scroll 28s linear infinite",
        "blink-cursor": "blink-cursor 1s step-end infinite",
      },
    },
  },
  plugins: [],
} satisfies Config;
