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
          bg: "#050608",
          panel: "rgba(11,16,24,0.62)",
          border: "rgba(93,130,168,0.28)",
          text: "#eaf4ff",
          secondary: "#a9b9cb",
          muted: "#6f8196",
          buy: "#39ff9a",
          sell: "#ff5c77",
          blocked: "#ffbf3c",
          neutral: "#37d9ff",
        },
      },
      boxShadow: {
        panel: "0 0 0 1px rgba(78,121,163,0.22), 0 14px 34px rgba(2,8,16,0.55), inset 0 1px 0 rgba(120,180,255,0.08)",
        neon: "0 0 24px rgba(55,217,255,0.28)",
        neonSoft: "0 0 12px rgba(55,217,255,0.2)",
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
