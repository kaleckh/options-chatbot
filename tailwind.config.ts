import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: {
          0: "#060708",
          1: "#0b0d0f",
          2: "#111417",
          3: "#181c20",
          4: "#20262b",
        },
        border: {
          DEFAULT: "#2a3036",
          subtle: "#20262b",
        },
        text: {
          0: "#f2f5f7",
          1: "#c5ced8",
          2: "#9aa7b4",
          3: "#8a96a3",
        },
        accent: {
          DEFAULT: "#27c7d8",
          dim: "rgba(39,199,216,0.12)",
          glow: "rgba(39,199,216,0.08)",
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
        xs: "0.78rem",
        sm: "0.86rem",
        base: "0.92rem",
        lg: "1.05rem",
        xl: "1.25rem",
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
