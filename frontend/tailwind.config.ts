import type { Config } from "tailwindcss";

/**
 * Dark, near-black base with a slight cool undertone, one signature accent,
 * and semantic colour reserved for things that carry meaning (match bands,
 * eligibility, application stages). No gradients, no decorative colour.
 */
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Neutral ramp. Not pure grey — a few points of blue keep large dark
        // areas from looking flat and muddy.
        ink: {
          950: "#0a0b0e",
          900: "#0f1115",
          850: "#14171c",
          800: "#191d23",
          750: "#1f242b",
          700: "#272d36",
          600: "#343b46",
          500: "#4a5260",
          400: "#6b7482",
          300: "#939ba8",
          200: "#bcc2cc",
          100: "#dfe3e9",
          50: "#f5f7fa",
        },
        // Signature accent: a calm azure. Interactive elements, active nav,
        // focus, progress. Used sparingly and never as decoration.
        accent: {
          700: "#2359c4",
          600: "#2f6fe0",
          500: "#4a86ef",
          400: "#6b9ff5",
          300: "#93bbfa",
          200: "#bcd5fc",
          100: "#dce8fe",
          soft: "rgba(74, 134, 239, 0.12)",
          line: "rgba(74, 134, 239, 0.32)",
        },
        // Match bands: an ORDINAL ramp, one hue stepped by lightness.
        // The previous green/lime/amber/grey set failed CVD validation — "Good"
        // and "Moderate" were ΔE 2.3 apart under deuteranopia. See
        // lib/palette.ts for the validator command and results.
        band: {
          excellent: "#cfe0fd",
          good: "#8ab4f8",
          moderate: "#4a86ef",
          low: "#2b60bd",
        },
        signal: {
          ok: "#34d399",
          warn: "#e8b23e",
          danger: "#f2777a",
          info: "#6b9ff5",
        },
        // Application-stage accents for the tracker board.
        stage: {
          interested: "#6b7482",
          applied: "#6b9ff5",
          assessment: "#e8b23e",
          interview: "#a3d948",
          offer: "#34d399",
          rejected: "#f2777a",
        },
      },
      fontFamily: {
        sans: ["var(--font-sans)", "ui-sans-serif", "system-ui", "sans-serif"],
        display: ["var(--font-display)", "var(--font-sans)", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "Menlo", "monospace"],
      },
      fontSize: {
        "2xs": ["0.6875rem", { lineHeight: "1rem", letterSpacing: "0.03em" }],
      },
      letterSpacing: {
        tightest: "-0.025em",
      },
      borderRadius: {
        DEFAULT: "4px",
        sm: "3px",
        md: "5px",
        lg: "7px",
      },
      maxWidth: {
        shell: "78rem",
        prose: "46rem",
      },
      boxShadow: {
        // A hairline top highlight reads as a raised surface without a blur
        // halo, which keeps the UI crisp on dark backgrounds.
        edge: "inset 0 1px 0 0 rgba(255,255,255,0.04)",
        focus: "0 0 0 3px rgba(74, 134, 239, 0.22)",
      },
      keyframes: {
        "fade-in": {
          from: { opacity: "0", transform: "translateY(3px)" },
          to: { opacity: "1", transform: "none" },
        },
        shimmer: { "100%": { transform: "translateX(100%)" } },
      },
      animation: {
        "fade-in": "fade-in 160ms ease-out",
        shimmer: "shimmer 1.4s infinite",
      },
    },
  },
  plugins: [],
};

export default config;
