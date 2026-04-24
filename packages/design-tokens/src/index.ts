// Helm design tokens — the source of truth for every surface.
//
// The warm-paper palette (oklch) flows through Tailwind on web, StyleSheet
// on mobile, and plain CSS on desktop. We keep the values here so a palette
// shift propagates everywhere without per-app edits.
//
// Values duplicate what lives in `apps/web/app/globals.css` and
// `apps/web/tailwind.config.ts`. When you change a token here, also update
// those two so Tailwind's generated utilities and runtime CSS match. A
// future session can collapse the duplication with a Tailwind plugin.

export const COLORS = {
  paper: "oklch(0.985 0.008 85)",
  paper2: "oklch(0.965 0.012 82)",
  sand: "oklch(0.935 0.018 80)",
  sand2: "oklch(0.895 0.022 78)",
  rule: "oklch(0.86 0.02 78)",
  ink: "oklch(0.26 0.02 60)",
  ink2: "oklch(0.42 0.02 65)",
  ink3: "oklch(0.58 0.018 70)",
  terracotta: "oklch(0.64 0.09 45)",
  terracotta2: "oklch(0.55 0.1 42)",
  terracottaSoft: "oklch(0.92 0.03 55)",
  sage: "oklch(0.66 0.055 145)",
  sage2: "oklch(0.5 0.06 145)",
  sageSoft: "oklch(0.93 0.025 140)",
  amber: "oklch(0.78 0.09 80)",
  amber2: "oklch(0.5 0.08 70)",
  amberSoft: "oklch(0.94 0.04 85)",
  rose: "oklch(0.7 0.07 25)",
  rose2: "oklch(0.5 0.08 25)",
  roseSoft: "oklch(0.94 0.03 25)",
} as const;

// Native-safe fallbacks (hex approximations of the oklch values). React
// Native's StyleSheet doesn't accept oklch(), so mobile uses these.
// Generated from the oklch values above; update together.
export const COLORS_HEX = {
  paper: "#FAF7ED",
  paper2: "#F2EDDF",
  sand: "#E8DFC9",
  sand2: "#D8CCB0",
  rule: "#C9BEA3",
  ink: "#38302A",
  ink2: "#5E554B",
  ink3: "#857C70",
  terracotta: "#C27854",
  terracotta2: "#A85F3C",
  terracottaSoft: "#EFDFD0",
  sage: "#88A88A",
  sage2: "#5F8364",
  sageSoft: "#DEE9DB",
  amber: "#D5B36D",
  amber2: "#87683A",
  amberSoft: "#EEE1BF",
  rose: "#CB8776",
  rose2: "#8F493C",
  roseSoft: "#F0DCD6",
} as const;

export const RADII = {
  sm: 8,
  md: 12,
  lg: 18,
  xl: 24,
} as const;

export const FONTS = {
  sans: "DM Sans",
  serif: "Instrument Serif",
  mono: "JetBrains Mono",
} as const;

export const SPACING = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  "2xl": 32,
  "3xl": 48,
} as const;

export const SHADOWS = {
  sm: "0 1px 0 oklch(0.86 0.02 78 / .6)",
  md: "0 1px 2px oklch(0.5 0.02 70 / .06), 0 4px 16px oklch(0.5 0.02 70 / .06)",
  lg: "0 2px 4px oklch(0.5 0.02 70 / .06), 0 12px 32px oklch(0.5 0.02 70 / .1)",
} as const;

export type ColorToken = keyof typeof COLORS;
export type HexColorToken = keyof typeof COLORS_HEX;
export type RadiiToken = keyof typeof RADII;
export type SpacingToken = keyof typeof SPACING;
