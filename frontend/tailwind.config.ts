import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      screens: {
        'xs': '375px',    // Mobile Medium
        'sm': '640px',    // Mobile Large / small tablet
        'md': '768px',    // Tablet
        'lg': '1024px',   // Tablet Large / small desktop
        'xl': '1280px',   // Desktop Medium
        '2xl': '1440px',  // Desktop Large
        '3xl': '1920px',  // Full HD
        '4k': '2560px',   // 4K displays
      },
      fontSize: {
        'fluid-xs': 'clamp(0.625rem, 0.5rem + 0.25vw, 0.75rem)',
        'fluid-sm': 'clamp(0.75rem, 0.625rem + 0.25vw, 0.875rem)',
        'fluid-base': 'clamp(0.875rem, 0.75rem + 0.25vw, 1rem)',
        'fluid-lg': 'clamp(1rem, 0.875rem + 0.25vw, 1.125rem)',
        'fluid-xl': 'clamp(1.125rem, 1rem + 0.25vw, 1.25rem)',
      },
      spacing: {
        'fluid-1': 'clamp(0.25rem, 0.125rem + 0.25vw, 0.5rem)',
        'fluid-2': 'clamp(0.5rem, 0.25rem + 0.5vw, 1rem)',
        'fluid-3': 'clamp(0.75rem, 0.5rem + 0.5vw, 1.5rem)',
        'fluid-4': 'clamp(1rem, 0.75rem + 0.5vw, 2rem)',
      },
      colors: {
        aura: {
          dark: "#0a0a0f",
          surface: "#12121a",
          glass: "rgba(255, 255, 255, 0.03)",
          border: "rgba(255, 255, 255, 0.08)",
          accent: "#6366f1",
          glow: "#818cf8",
          pulse: "#a78bfa",
          text: {
            primary: "rgba(255, 255, 255, 0.92)",
            secondary: "rgba(255, 255, 255, 0.56)",
            tertiary: "rgba(255, 255, 255, 0.32)",
          },
        },
      },
      backdropBlur: {
        xs: "2px",
        glass: "20px",
        heavy: "40px",
      },
      boxShadow: {
        glass:
          "0 8px 32px rgba(0, 0, 0, 0.4), inset 0 1px 0 rgba(255, 255, 255, 0.05)",
        "glass-hover":
          "0 8px 32px rgba(0, 0, 0, 0.5), inset 0 1px 0 rgba(255, 255, 255, 0.08), 0 0 0 1px rgba(99, 102, 241, 0.15)",
        glow: "0 0 20px rgba(99, 102, 241, 0.3), 0 0 60px rgba(99, 102, 241, 0.1)",
        "glow-lg":
          "0 0 30px rgba(99, 102, 241, 0.4), 0 0 80px rgba(99, 102, 241, 0.15)",
        "glow-pulse":
          "0 0 40px rgba(167, 139, 250, 0.3), 0 0 100px rgba(167, 139, 250, 0.1)",
      },
      animation: {
        "neural-pulse": "neural-pulse 3s ease-in-out infinite",
        "glass-shimmer": "glass-shimmer 8s ease-in-out infinite",
        float: "float 6s ease-in-out infinite",
        "glow-breathe": "glow-breathe 4s ease-in-out infinite",
        "spin-slow": "spin 3s linear infinite",
        shimmer: "shimmer 2s ease-in-out infinite",
        "pulse-glow": "pulse-glow 2s ease-in-out infinite",
        "morphing-border": "morphing-border 8s ease-in-out infinite",
        "data-scroll": "data-scroll 15s linear infinite",
        hologram: "hologram 3s ease-in-out infinite",
        "scan-line": "scan-line 4s linear infinite",
      },
      keyframes: {
        "neural-pulse": {
          "0%, 100%": {
            opacity: "0.4",
            transform: "scale(1)",
          },
          "50%": {
            opacity: "1",
            transform: "scale(1.05)",
          },
        },
        "glass-shimmer": {
          "0%": {
            backgroundPosition: "-200% 0",
          },
          "100%": {
            backgroundPosition: "200% 0",
          },
        },
        float: {
          "0%, 100%": {
            transform: "translateY(0px)",
          },
          "50%": {
            transform: "translateY(-10px)",
          },
        },
        "glow-breathe": {
          "0%, 100%": {
            boxShadow:
              "0 0 20px rgba(99, 102, 241, 0.2), 0 0 60px rgba(99, 102, 241, 0.05)",
          },
          "50%": {
            boxShadow:
              "0 0 30px rgba(99, 102, 241, 0.4), 0 0 80px rgba(99, 102, 241, 0.15)",
          },
        },
        shimmer: {
          "0%": {
            backgroundPosition: "-200% 0",
          },
          "100%": {
            backgroundPosition: "200% 0",
          },
        },
        "pulse-glow": {
          "0%, 100%": {
            boxShadow:
              "0 0 8px rgba(99, 102, 241, 0.3), 0 0 24px rgba(99, 102, 241, 0.1)",
          },
          "50%": {
            boxShadow:
              "0 0 24px rgba(99, 102, 241, 0.6), 0 0 80px rgba(99, 102, 241, 0.25)",
          },
        },
        "morphing-border": {
          "0%, 100%": {
            borderRadius: "60% 40% 30% 70% / 60% 30% 70% 40%",
          },
          "25%": {
            borderRadius: "30% 60% 70% 40% / 50% 60% 30% 60%",
          },
          "50%": {
            borderRadius: "50% 60% 30% 60% / 30% 50% 70% 50%",
          },
          "75%": {
            borderRadius: "40% 60% 50% 40% / 60% 40% 60% 50%",
          },
        },
        "data-scroll": {
          "0%": {
            backgroundPosition: "0 0",
          },
          "100%": {
            backgroundPosition: "0 -100%",
          },
        },
        hologram: {
          "0%": { opacity: "0.95" },
          "25%": { opacity: "1" },
          "50%": { opacity: "0.97" },
          "75%": { opacity: "1" },
          "100%": { opacity: "0.95" },
        },
        "scan-line": {
          "0%": {
            transform: "translateY(-100%)",
          },
          "100%": {
            transform: "translateY(100%)",
          },
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "Fira Code", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
