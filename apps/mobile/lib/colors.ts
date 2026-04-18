/**
 * Palette mirrors apps/web/tailwind.config.ts colors. When we extract
 * shared design tokens into packages/design-tokens (Phase 4 polish), both
 * surfaces read from the same JSON. Until then, keep these in sync by hand
 * when the web palette changes.
 */
export const colors = {
  ink: "#0A0A0A",
  paper: "#FAFAF8",
  haze: "#F3F2EE",
  iron: "#6B6B6B",
  accent: "#E85D1A",
  success: "#2D8659",
  warning: "#B8860B",
  danger: "#A8251A",
} as const;

export type ColorName = keyof typeof colors;
