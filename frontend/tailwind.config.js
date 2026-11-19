/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          900: "#0B1220",
          800: "#131C2E",
          700: "#1F2937",
          600: "#374151",
          500: "#4B5563",
          400: "#6B7280",
        },
        primary: {
          50: "#EFF6FF",
          100: "#DBEAFE",
          200: "#BFDBFE",
          500: "#3B82F6",
          600: "#2563EB",
          700: "#1D4ED8",
        },
        success: { 50: "#ECFDF5", 100: "#D1FAE5", 600: "#059669", 700: "#047857" },
        warn: { 50: "#FFFBEB", 100: "#FEF3C7", 600: "#D97706", 700: "#B45309" },
        danger: { 50: "#FEF2F2", 100: "#FEE2E2", 600: "#DC2626", 700: "#B91C1C" },
        info: { 50: "#F0F9FF", 100: "#E0F2FE", 600: "#0284C7" },
      },
      fontFamily: {
        sans: [
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
      },
      borderRadius: { md: "6px", lg: "10px", xl: "14px" },
      fontSize: { "2xs": ["11px", "16px"] },
      boxShadow: {
        card: "0 1px 2px rgba(15, 23, 42, 0.04), 0 1px 3px rgba(15, 23, 42, 0.06)",
        pop: "0 10px 30px rgba(15, 23, 42, 0.12)",
      },
      keyframes: {
        "fade-in": { from: { opacity: "0" }, to: { opacity: "1" } },
        pulseSoft: { "0%,100%": { opacity: "1" }, "50%": { opacity: "0.45" } },
      },
      animation: {
        "fade-in": "fade-in 140ms ease-out",
        "pulse-soft": "pulseSoft 1.6s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
