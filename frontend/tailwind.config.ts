import type { Config } from "tailwindcss";
import typography from "@tailwindcss/typography";

export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        border: "hsl(var(--border))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        muted: { DEFAULT: "hsl(var(--muted))", foreground: "hsl(var(--muted-foreground))" },
        primary: { DEFAULT: "hsl(var(--primary))", foreground: "hsl(var(--primary-foreground))" },
        destructive: { DEFAULT: "hsl(var(--destructive))", foreground: "hsl(var(--destructive-foreground))" },
        card: { DEFAULT: "hsl(var(--card))", foreground: "hsl(var(--card-foreground))" },
        success: "hsl(var(--success))",
        danger: "hsl(var(--danger))",
        warning: "hsl(var(--warning))",
        info: "hsl(var(--info))",
        // Wise & Pinterest-inspired design tokens - Light mode
        "near-black": "#0e0f0c",
        "semantier-green": "#9fe870",
        "dark-green": "#163300",
        "light-mint": "#e2f6d5",
        "pastel-green": "#cdffad",
        "warm-dark": "#454745",
        "warm-gray": "#868685",
        "light-surface": "#e8ebe6",
        "focus-blue": "#435ee5",
        // Wise & Pinterest-inspired design tokens - Dark mode (warm dark)
        "warm-white": "#f5f5f0",
        "dark-surface": "#1a1a16",
        "dark-surface-2": "#22221e",
        "dark-border": "#2d2d28",
        "dark-muted": "#91918c",
      },
      fontFamily: {
        sans: ["Autaut Grotesk", "-apple-system", "system-ui", "Segoe UI", "Roboto", "Oxygen-Sans", "Ubuntu", "Cantarell", "Fira Sans", "Droid Sans", "Helvetica Neue", "Helvetica", "Hiragino Kaku Gothic Pro W3", "Meiryo", "MS PGothic", "Arial", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 4px)",
        sm: "calc(var(--radius) - 8px)",
        button: "16px",
        card: "20px",
        comfortable: "20px",
        section: "32px",
        hero: "40px",
      },
    },
  },
  plugins: [typography],
} satisfies Config;
