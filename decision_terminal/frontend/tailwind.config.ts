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
          bg: "#020617", // Aurelius Obsidian
          panel: "rgba(10, 15, 25, 0.45)",
          "panel-glass": "rgba(8, 12, 18, 0.45)",
          border: "rgba(119, 162, 249, 0.12)",
          "border-bright": "rgba(119, 162, 249, 0.25)",
          text: "#f1f5f9", // Aurelius Text
          secondary: "#cbd5e1",
          muted: "#64748b",
          buy: "hsl(145, 100%, 65%)", // Aurelius Emerald
          sell: "hsl(350, 100%, 65%)", // Aurelius Magenta
          blocked: "hsl(35, 100%, 65%)", // Aurelius Amber
          neutral: "hsl(190, 100%, 65%)", // Aurelius Neural
          accent: "hsl(260, 80%, 65%)",
        },
      },
      boxShadow: {
        panel: "0 8px 32px 0 rgba(0, 0, 0, 0.5), inset 0 1px 1px rgba(255, 255, 255, 0.05)",
        neon: "0 0 15px hsla(190, 100%, 65%, 0.15)",
        neonBuy: "0 0 15px hsla(145, 100%, 65%, 0.2)",
        neonSell: "0 0 15px hsla(350, 100%, 65%, 0.2)",
        neonSoft: "0 0 12px hsla(190, 100%, 65%, 0.1)",
      },
      borderRadius: {
        xl2: "1rem",
      },
      keyframes: {
        pulseBorder: {
          "0%, 100%": { boxShadow: "0 0 0 1px rgba(78,121,163,0.28), 0 12px 28px rgba(2,8,16,0.5)" },
          "50%": { boxShadow: "0 0 0 1px rgba(55,217,255,0.55), 0 0 18px rgba(55,217,255,0.25), 0 12px 28px rgba(2,8,16,0.5)" },
        },
        shimmer: {
          "0%": { transform: "translateX(-120%)" },
          "100%": { transform: "translateX(220%)" },
        },
        softPulse: {
          "0%, 100%": { opacity: "0.65" },
          "50%": { opacity: "1" },
        },
        floatIn: {
          "0%": { opacity: "0", transform: "translateY(8px) scale(0.995)" },
          "100%": { opacity: "1", transform: "translateY(0) scale(1)" },
        },
      },
      animation: {
        pulseBorder: "pulseBorder 1.6s ease-in-out",
        shimmer: "shimmer 2.6s linear infinite",
        softPulse: "softPulse 1.8s ease-in-out infinite",
        floatIn: "floatIn 380ms cubic-bezier(0.22, 1, 0.36, 1)",
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
