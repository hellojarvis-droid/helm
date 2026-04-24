import type { Config } from "tailwindcss";

// Warm paper palette (from the Helm cockpit design handoff). Colors are
// inlined as oklch literals with Tailwind's `<alpha-value>` hook so every
// class supports opacity modifiers (`bg-paper/40`, `text-iron/60`).
// The same values are duplicated as CSS vars in globals.css for arbitrary
// style attrs (charts, inline backgrounds) — keep the two in sync.

const oklchVar = (l: number, c: number, h: number) =>
  `oklch(${l} ${c} ${h} / <alpha-value>)`;

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        paper: oklchVar(0.985, 0.008, 85),
        "paper-2": oklchVar(0.965, 0.012, 82),
        sand: oklchVar(0.935, 0.018, 80),
        "sand-2": oklchVar(0.895, 0.022, 78),
        rule: oklchVar(0.86, 0.02, 78),
        ink: oklchVar(0.26, 0.02, 60),
        "ink-2": oklchVar(0.42, 0.02, 65),
        "ink-3": oklchVar(0.58, 0.018, 70),
        terracotta: oklchVar(0.64, 0.09, 45),
        "terracotta-2": oklchVar(0.55, 0.1, 42),
        "terracotta-soft": oklchVar(0.92, 0.03, 55),
        sage: oklchVar(0.66, 0.055, 145),
        "sage-2": oklchVar(0.5, 0.06, 145),
        "sage-soft": oklchVar(0.93, 0.025, 140),
        amber: oklchVar(0.78, 0.09, 80),
        "amber-2": oklchVar(0.5, 0.08, 70),
        "amber-soft": oklchVar(0.94, 0.04, 85),
        rose: oklchVar(0.7, 0.07, 25),
        "rose-2": oklchVar(0.5, 0.08, 25),
        "rose-soft": oklchVar(0.94, 0.03, 25),
        // Legacy aliases — existing pages using `bg-haze`, `text-iron`,
        // `text-accent`, `text-success/warning/danger` keep rendering under
        // the new palette without class rewrites.
        haze: oklchVar(0.965, 0.012, 82),
        iron: oklchVar(0.58, 0.018, 70),
        accent: oklchVar(0.64, 0.09, 45),
        success: oklchVar(0.5, 0.06, 145),
        warning: oklchVar(0.5, 0.08, 70),
        danger: oklchVar(0.5, 0.08, 25),
      },
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        serif: ["var(--font-serif)", "Iowan Old Style", "Georgia", "serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
      borderRadius: {
        sm: "8px",
        md: "12px",
        lg: "18px",
        xl: "24px",
      },
      boxShadow: {
        sm: "0 1px 0 oklch(0.86 0.02 78 / .6)",
        DEFAULT:
          "0 1px 2px oklch(0.5 0.02 70 / .06), 0 4px 16px oklch(0.5 0.02 70 / .06)",
        lg: "0 2px 4px oklch(0.5 0.02 70 / .06), 0 12px 32px oklch(0.5 0.02 70 / .1)",
      },
      letterSpacing: {
        tightest: "-0.02em",
      },
    },
  },
  plugins: [],
};

export default config;
