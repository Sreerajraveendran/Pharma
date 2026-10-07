/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        "primary": "#003d9b",
        "primary-container": "#0052cc",
        "secondary": "#006c47",
        "secondary-container": "#82f9be",
        "tertiary": "#5e3c00",
        "error": "#ba1a1a",
        "error-container": "#ffdad6",
        "background": "#f8f9fb",
        "on-background": "#191c1e",
        "surface": "#f8f9fb",
        "surface-bright": "#f8f9fb",
        "surface-container": "#edeef0",
        "surface-container-low": "#f3f4f6",
        "surface-container-high": "#e7e8ea",
        "surface-container-highest": "#e1e2e4",
        "surface-container-lowest": "#ffffff",
        "surface-dim": "#d9dadc",
        "outline-variant": "#c3c6d6",
        "outline": "#737685",
        "on-surface-variant": "#434654",
        "on-surface": "#191c1e",
        "inverse-surface": "#2e3132",
        "inverse-on-surface": "#f0f1f3",
      },
      borderRadius: {
        "DEFAULT": "0.25rem",
        "sm": "0.125rem",
        "md": "0.375rem",
        "lg": "0.5rem",
        "xl": "0.75rem",
        "full": "9999px",
      },
      fontFamily: {
        sans: ["Inter", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      }
    },
  },
  plugins: [],
}
