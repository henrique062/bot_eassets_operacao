import type { Config } from "tailwindcss"

const config: Config = {
  darkMode: ["class"],
  content: [
    "./pages/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./app/**/*.{ts,tsx}",
    "./src/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "#0f1117",
        card: "#1a1d27",
        border: "#2a2d3a",
        primary: {
          DEFAULT: "#6366f1",
          foreground: "#ffffff",
        },
        success: "#22c55e",
        danger: "#ef4444",
        warning: "#f59e0b",
        muted: "#6b7280",
      },
      borderColor: {
        DEFAULT: "#2a2d3a",
      },
    },
  },
  plugins: [],
}

export default config
