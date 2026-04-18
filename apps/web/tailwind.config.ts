import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  darkMode: "media",
  theme: {
    extend: {
      colors: {
        // Palette from docs/UI_DESIGN.md §4.3. Restrained; accent is the
        // burnt-orange used sparingly for CTAs + approval cards.
        ink: "#0A0A0A",
        paper: "#FAFAF8",
        haze: "#F3F2EE",
        iron: "#6B6B6B",
        accent: "#E85D1A",
        success: "#2D8659",
        warning: "#B8860B",
        danger: "#A8251A",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
