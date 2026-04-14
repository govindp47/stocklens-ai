import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        /* Brand palette */
        brand: {
          50: "hsl(var(--brand-50))",
          100: "hsl(var(--brand-100))",
          200: "hsl(var(--brand-200))",
          500: "hsl(var(--brand-500))",
          600: "hsl(var(--brand-600))",
          700: "hsl(var(--brand-700))",
          900: "hsl(var(--brand-900))",
        },
        /* Semantic surface / text tokens — exposed as Tailwind classes */
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        surface: {
          DEFAULT: "hsl(var(--surface))",
          raised: "hsl(var(--surface-raised))",
        },
        border: "hsl(var(--border))",
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        /* Accent for subtle warm highlights */
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        /* Sentiment */
        sentiment: {
          positive: "hsl(var(--sentiment-positive))",
          neutral: "hsl(var(--sentiment-neutral))",
          negative: "hsl(var(--sentiment-negative))",
        },
      },
      fontFamily: {
        sans: ["var(--font-inter)", "system-ui", "sans-serif"],
        mono: ["var(--font-jetbrains-mono)", "monospace"],
      },
      fontSize: {
        "2xs": ["0.6875rem", { lineHeight: "1rem" }],
      },
      borderRadius: {
        "4xl": "2rem",
      },
      animation: {
        "fade-in-up": "fade-in-up 0.35s ease-out forwards",
        "fade-in": "fade-in 0.2s ease-out forwards",
        "slide-in-left": "slide-in-left 0.25s ease-out forwards",
        shimmer: "shimmer 1.6s ease-in-out infinite",
        "step-pop": "step-pop 0.3s ease-out forwards",
        "step-complete": "step-complete 0.4s ease-out forwards",
        float: "float 3s ease-in-out infinite",
        "timeline-in": "timeline-in 0.25s ease-out forwards",
      },
      keyframes: {
        "fade-in": {
          from: { opacity: "0" },
          to: { opacity: "1" },
        },
        float: {
          "0%, 100%": { transform: "translateY(0px)" },
          "50%": { transform: "translateY(-4px)" },
        },
      },
      boxShadow: {
        xs: "0 1px 2px 0 rgba(0,0,0,0.04)",
        panel: "0 1px 4px 0 rgba(0,0,0,0.06), 0 1px 2px -1px rgba(0,0,0,0.04)",
        "panel-hover":
          "0 6px 20px 0 rgba(0,0,0,0.09), 0 2px 6px -2px rgba(0,0,0,0.06)",
        card: "0 0 0 1px rgba(0,0,0,0.05), 0 2px 8px 0 rgba(0,0,0,0.06)",
        "input-focus": "0 0 0 3px hsl(var(--brand-100))",
        "glow-brand": "0 0 0 3px hsl(var(--brand-100))",
        "glow-border": "0 0 0 1px hsla(186,80%,52%,0.15)",
      },
      spacing: {
        "4.5": "1.125rem",
        "18": "4.5rem",
      },
    },
  },
  plugins: [],
};

export default config;
