import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: {
          0: "#080b10",
          1: "#0c1017",
          2: "#11161e",
          3: "#151c26",
          4: "#1a2332",
        },
        border: {
          DEFAULT: "#1e2736",
          subtle: "#151c26",
        },
        text: {
          0: "#edf2f7",
          1: "#b8c4d0",
          2: "#6b7a8d",
          3: "#5a6b80",
        },
        accent: {
          DEFAULT: "#4a90f7",
          dim: "rgba(74,144,247,0.12)",
          glow: "rgba(74,144,247,0.06)",
        },
        green: {
          DEFAULT: "#34d399",
          dim: "rgba(52,211,153,0.10)",
        },
        red: {
          DEFAULT: "#f87171",
          dim: "rgba(248,113,113,0.10)",
        },
        amber: {
          DEFAULT: "#fbbf24",
          dim: "rgba(251,191,36,0.10)",
        },
      },
      fontFamily: {
        sans: [
          "Inter",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "sans-serif",
        ],
        mono: [
          "JetBrains Mono",
          "Consolas",
          "Courier New",
          "monospace",
        ],
      },
      fontSize: {
        "2xs": "0.75rem",
        xs: "0.72rem",
        sm: "0.78rem",
        base: "0.82rem",
        lg: "1.0rem",
        xl: "1.2rem",
      },
      keyframes: {
        "slide-in-left": {
          from: { transform: "translateX(-100%)" },
          to: { transform: "translateX(0)" },
        },
      },
      animation: {
        "slide-in-left": "slide-in-left 200ms ease-out",
      },
    },
  },
  plugins: [],
};

export default config;
