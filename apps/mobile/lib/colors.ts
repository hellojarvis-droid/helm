// Warm-paper palette — mirrors packages/design-tokens + web's tailwind
// config. React Native doesn't parse oklch() in StyleSheet values, so we
// use the hex approximations from COLORS_HEX. Legacy names (accent,
// success, warning, danger, haze, iron) keep existing screens working
// with the updated palette without file-by-file rewrites.

import { COLORS_HEX } from "@helm/design-tokens";

export const colors = {
  // Design-token semantic names
  paper: COLORS_HEX.paper,
  paper2: COLORS_HEX.paper2,
  sand: COLORS_HEX.sand,
  sand2: COLORS_HEX.sand2,
  rule: COLORS_HEX.rule,
  ink: COLORS_HEX.ink,
  ink2: COLORS_HEX.ink2,
  ink3: COLORS_HEX.ink3,
  terracotta: COLORS_HEX.terracotta,
  terracotta2: COLORS_HEX.terracotta2,
  terracottaSoft: COLORS_HEX.terracottaSoft,
  sage: COLORS_HEX.sage,
  sage2: COLORS_HEX.sage2,
  sageSoft: COLORS_HEX.sageSoft,
  amber: COLORS_HEX.amber,
  amber2: COLORS_HEX.amber2,
  amberSoft: COLORS_HEX.amberSoft,
  rose: COLORS_HEX.rose,
  rose2: COLORS_HEX.rose2,
  roseSoft: COLORS_HEX.roseSoft,
  // Legacy aliases — keep existing screens working after the palette swap.
  //   accent  → terracotta
  //   haze    → paper2
  //   iron    → ink3
  //   success → sage2
  //   warning → amber2
  //   danger  → rose2
  accent: COLORS_HEX.terracotta,
  haze: COLORS_HEX.paper2,
  iron: COLORS_HEX.ink3,
  success: COLORS_HEX.sage2,
  warning: COLORS_HEX.amber2,
  danger: COLORS_HEX.rose2,
} as const;

export type ColorName = keyof typeof colors;
