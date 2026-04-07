import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["class"],
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        terminal: {
          bg: "#0b0f14",
          panel: "#121821",
          border: "#1f2933",
          text: "#f5f7fa",
          secondary: "#a7b1bd",
          muted: "#6b7480",
          buy: "#1db954",
          sell: "#f04438",
          blocked: "#f59e0b",
          neutral: "#3b82f6",
        },
      },
      boxShadow: {
        panel: "0 0 0 1px rgba(31,41,51,0.8), 0 10px 28px rgba(0,0,0,0.35)",
      },
      borderRadius: {
        xl2: "1rem",
      },
      keyframes: {
        pulseBorder: {
          "0%, 100%": { boxShadow: "0 0 0 1px rgba(31,41,51,0.9)" },
          "50%": { boxShadow: "0 0 0 1px rgba(59,130,246,0.85)" },
        },
      },
      animation: {
        pulseBorder: "pulseBorder 1.6s ease-in-out",
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular"],
      },
    },
  },
  plugins: [],
};

export default config;
