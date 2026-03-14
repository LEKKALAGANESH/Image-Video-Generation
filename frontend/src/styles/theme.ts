/* ─────────────────────────────────────────────
 * AuraGen — Design Token System
 * Liquid Glassmorphism Theme Configuration
 * ───────────────────────────────────────────── */

export const theme = {
  /* ── Color Palette ───────────────────────────── */
  colors: {
    /* Dark backgrounds */
    dark: "#0a0a0f",
    surface: "#12121a",
    elevated: "#1a1a28",

    /* Glass alphas */
    "glass-light": "rgba(255, 255, 255, 0.03)",
    "glass-medium": "rgba(255, 255, 255, 0.06)",
    "glass-heavy": "rgba(255, 255, 255, 0.12)",

    /* Accents */
    primary: "#6366f1",
    "primary-light": "#818cf8",
    "primary-dark": "#4f46e5",
    secondary: "#8b5cf6",
    "secondary-light": "#a78bfa",
    "secondary-dark": "#7c3aed",
    success: "#10b981",
    "success-light": "#34d399",
    "success-dark": "#059669",
    warning: "#f59e0b",
    "warning-light": "#fbbf24",
    "warning-dark": "#d97706",
    error: "#f43f5e",
    "error-light": "#fb7185",
    "error-dark": "#e11d48",

    /* Text hierarchy */
    text: {
      primary: "rgba(255, 255, 255, 0.92)",
      secondary: "rgba(255, 255, 255, 0.56)",
      tertiary: "rgba(255, 255, 255, 0.32)",
      disabled: "rgba(255, 255, 255, 0.16)",
    },
  },

  /* ── Glass Effect Presets ────────────────────── */
  glass: {
    subtle: {
      background: "rgba(255, 255, 255, 0.02)",
      backdropFilter: "blur(12px)",
      border: "1px solid rgba(255, 255, 255, 0.04)",
      shadow: "0 4px 16px rgba(0, 0, 0, 0.2), inset 0 1px 0 rgba(255, 255, 255, 0.03)",
    },
    medium: {
      background: "rgba(255, 255, 255, 0.03)",
      backdropFilter: "blur(20px)",
      border: "1px solid rgba(255, 255, 255, 0.06)",
      shadow: "0 8px 32px rgba(0, 0, 0, 0.4), inset 0 1px 0 rgba(255, 255, 255, 0.05)",
    },
    heavy: {
      background: "rgba(255, 255, 255, 0.06)",
      backdropFilter: "blur(30px) saturate(150%)",
      border: "1px solid rgba(255, 255, 255, 0.1)",
      shadow: "0 12px 48px rgba(0, 0, 0, 0.5), inset 0 1px 0 rgba(255, 255, 255, 0.08)",
    },
    frosted: {
      background: "rgba(255, 255, 255, 0.01)",
      backdropFilter: "blur(40px) saturate(180%)",
      border: "1px solid rgba(255, 255, 255, 0.04)",
      shadow: "0 16px 64px rgba(0, 0, 0, 0.5), inset 0 1px 0 rgba(255, 255, 255, 0.06)",
    },
    tinted: {
      background: "rgba(99, 102, 241, 0.06)",
      backdropFilter: "blur(24px) saturate(150%)",
      border: "1px solid rgba(99, 102, 241, 0.12)",
      shadow: "0 8px 32px rgba(99, 102, 241, 0.08), inset 0 1px 0 rgba(255, 255, 255, 0.05)",
    },
  },

  /* ── Shadow Presets ──────────────────────────── */
  shadows: {
    /* Depth-based shadows */
    depth: {
      0: "none",
      1: "0 2px 8px rgba(0, 0, 0, 0.2), 0 1px 3px rgba(0, 0, 0, 0.15)",
      2: "0 4px 16px rgba(0, 0, 0, 0.25), 0 2px 6px rgba(0, 0, 0, 0.2)",
      3: "0 8px 32px rgba(0, 0, 0, 0.35), 0 4px 12px rgba(0, 0, 0, 0.25)",
      4: "0 16px 48px rgba(0, 0, 0, 0.45), 0 8px 24px rgba(0, 0, 0, 0.3)",
      5: "0 24px 64px rgba(0, 0, 0, 0.55), 0 12px 32px rgba(0, 0, 0, 0.35)",
    },

    /* Glow sizes */
    glow: {
      sm: "0 0 8px rgba(99, 102, 241, 0.4), 0 0 24px rgba(99, 102, 241, 0.15)",
      md: "0 0 16px rgba(99, 102, 241, 0.4), 0 0 48px rgba(99, 102, 241, 0.15)",
      lg: "0 0 24px rgba(99, 102, 241, 0.5), 0 0 80px rgba(99, 102, 241, 0.2)",
      xl: "0 0 40px rgba(99, 102, 241, 0.5), 0 0 120px rgba(99, 102, 241, 0.25), 0 0 200px rgba(99, 102, 241, 0.1)",
    },

    /* Colored glows for each accent */
    coloredGlow: {
      primary: "0 0 20px rgba(99, 102, 241, 0.4), 0 0 60px rgba(99, 102, 241, 0.15)",
      secondary: "0 0 20px rgba(139, 92, 246, 0.4), 0 0 60px rgba(139, 92, 246, 0.15)",
      success: "0 0 20px rgba(16, 185, 129, 0.4), 0 0 60px rgba(16, 185, 129, 0.15)",
      warning: "0 0 20px rgba(245, 158, 11, 0.4), 0 0 60px rgba(245, 158, 11, 0.15)",
      error: "0 0 20px rgba(244, 63, 94, 0.4), 0 0 60px rgba(244, 63, 94, 0.15)",
    },
  },

  /* ── Animation Presets ───────────────────────── */
  animations: {
    /* Duration presets */
    duration: {
      fast: "150ms",
      normal: "300ms",
      slow: "500ms",
      glacial: "1000ms",
    },

    /* Easing curves */
    easing: {
      spring: "cubic-bezier(0.34, 1.56, 0.64, 1)",
      bounce: "cubic-bezier(0.68, -0.55, 0.265, 1.55)",
      smooth: "cubic-bezier(0.4, 0, 0.2, 1)",
      sharp: "cubic-bezier(0.4, 0, 0.6, 1)",
    },

    /* Keyframe references */
    keyframes: {
      neuralPulse: "neural-pulse 3s ease-in-out infinite",
      glassShimmer: "glass-shimmer 8s ease-in-out infinite",
      float: "float 6s ease-in-out infinite",
      glowBreathe: "glow-breathe 4s ease-in-out infinite",
      morphShape: "morph-shape 8s ease-in-out infinite",
      hologramFlicker: "hologram-flicker 3s ease-in-out infinite",
      prismaticRotate: "prismatic-rotate 8s linear infinite",
      dataStreamScroll: "data-stream-scroll 20s linear infinite",
      shimmer: "shimmer 2s ease-in-out infinite",
      pulseGlow: "pulse-glow 2s ease-in-out infinite",
      morphingBorder: "morphing-border 8s ease-in-out infinite",
      dataScroll: "data-scroll 15s linear infinite",
      hologram: "hologram 3s ease-in-out infinite",
      scanLine: "scan-line 4s linear infinite",
    },
  },

  /* ── Spacing Scale (4px-based) ─────────────── */
  spacing: {
    0: "0px",
    0.5: "2px",
    1: "4px",
    1.5: "6px",
    2: "8px",
    2.5: "10px",
    3: "12px",
    3.5: "14px",
    4: "16px",
    5: "20px",
    6: "24px",
    7: "28px",
    8: "32px",
    9: "36px",
    10: "40px",
    11: "44px",
    12: "48px",
    14: "56px",
    16: "64px",
    20: "80px",
    24: "96px",
    28: "112px",
    32: "128px",
    36: "144px",
    40: "160px",
    44: "176px",
    48: "192px",
    52: "208px",
    56: "224px",
    60: "240px",
    64: "256px",
    72: "288px",
    80: "320px",
    96: "384px",
  } as Record<number | string, string>,

  /* ── Typography ────────────────────────────── */
  typography: {
    display: {
      fontSize: "3.5rem",
      lineHeight: "1.1",
      letterSpacing: "-0.02em",
      fontWeight: 700,
    },
    heading: {
      fontSize: "2rem",
      lineHeight: "1.2",
      letterSpacing: "-0.015em",
      fontWeight: 600,
    },
    subheading: {
      fontSize: "1.25rem",
      lineHeight: "1.4",
      letterSpacing: "-0.01em",
      fontWeight: 500,
    },
    body: {
      fontSize: "1rem",
      lineHeight: "1.6",
      letterSpacing: "0em",
      fontWeight: 400,
    },
    caption: {
      fontSize: "0.875rem",
      lineHeight: "1.5",
      letterSpacing: "0.01em",
      fontWeight: 400,
    },
    micro: {
      fontSize: "0.75rem",
      lineHeight: "1.4",
      letterSpacing: "0.02em",
      fontWeight: 400,
    },
  },

  /* ── Depth Level Configs ────────────────────── */
  depths: {
    0: { scale: 1, blur: 0, opacity: 1, shadow: "none", zIndex: 0 },
    1: {
      scale: 1.01,
      blur: 0,
      opacity: 1,
      shadow: "0 2px 8px rgba(0, 0, 0, 0.2), 0 1px 3px rgba(0, 0, 0, 0.15)",
      zIndex: 10,
    },
    2: {
      scale: 1.02,
      blur: 0,
      opacity: 0.98,
      shadow: "0 4px 16px rgba(0, 0, 0, 0.25), 0 2px 6px rgba(0, 0, 0, 0.2)",
      zIndex: 20,
    },
    3: {
      scale: 1.04,
      blur: 0.5,
      opacity: 0.96,
      shadow: "0 8px 32px rgba(0, 0, 0, 0.35), 0 4px 12px rgba(0, 0, 0, 0.25)",
      zIndex: 30,
    },
    4: {
      scale: 1.06,
      blur: 1,
      opacity: 0.94,
      shadow: "0 16px 48px rgba(0, 0, 0, 0.45), 0 8px 24px rgba(0, 0, 0, 0.3)",
      zIndex: 40,
    },
    5: {
      scale: 1.08,
      blur: 1.5,
      opacity: 0.92,
      shadow: "0 24px 64px rgba(0, 0, 0, 0.55), 0 12px 32px rgba(0, 0, 0, 0.35)",
      zIndex: 50,
    },
  } as Record<number, { scale: number; blur: number; opacity: number; shadow: string; zIndex: number }>,

  /* ── Breakpoints ───────────────────────────── */
  breakpoints: {
    sm: 640,
    md: 768,
    lg: 1024,
    xl: 1280,
    "2xl": 1536,
  },
} as const;

/* ── Utility Functions ───────────────────────── */

/**
 * Returns a CSS-in-JS style object for a glass variant.
 */
export function glassStyle(
  variant: keyof typeof theme.glass
): {
  background: string;
  backdropFilter: string;
  WebkitBackdropFilter: string;
  border: string;
  boxShadow: string;
} {
  const glass = theme.glass[variant];
  return {
    background: glass.background,
    backdropFilter: glass.backdropFilter,
    WebkitBackdropFilter: glass.backdropFilter,
    border: glass.border,
    boxShadow: glass.shadow,
  };
}

/**
 * Returns transform + filter + opacity styles for a given depth level.
 */
export function depthStyle(level: number): {
  transform: string;
  filter: string;
  opacity: number;
  boxShadow: string;
  zIndex: number;
} {
  const clampedLevel = Math.max(0, Math.min(5, Math.round(level)));
  const depth = theme.depths[clampedLevel];
  return {
    transform: `scale(${depth.scale})`,
    filter: depth.blur > 0 ? `blur(${depth.blur}px)` : "none",
    opacity: depth.opacity,
    boxShadow: depth.shadow,
    zIndex: depth.zIndex,
  };
}

/**
 * Returns a box-shadow string for a colored glow.
 */
export function glowColor(
  color: string,
  intensity: "sm" | "md" | "lg" | "xl" = "md"
): string {
  const intensityMap = {
    sm: { inner: 0.3, mid: 8, outer: 24, outerOpacity: 0.1 },
    md: { inner: 0.4, mid: 16, outer: 48, outerOpacity: 0.15 },
    lg: { inner: 0.5, mid: 24, outer: 80, outerOpacity: 0.2 },
    xl: { inner: 0.6, mid: 40, outer: 120, outerOpacity: 0.25 },
  };

  const config = intensityMap[intensity];

  /* Parse hex color to rgb components */
  const hexToRgb = (hex: string): { r: number; g: number; b: number } | null => {
    const shorthand = /^#?([a-f\d])([a-f\d])([a-f\d])$/i;
    const fullHex = hex.replace(shorthand, (_, r, g, b) => r + r + g + g + b + b);
    const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(fullHex);
    return result
      ? { r: parseInt(result[1], 16), g: parseInt(result[2], 16), b: parseInt(result[3], 16) }
      : null;
  };

  const rgb = hexToRgb(color);
  if (!rgb) {
    /* Fallback: treat color as-is (could be rgb string or named color) */
    return `0 0 ${config.mid}px ${color}, 0 0 ${config.outer}px ${color}`;
  }

  const { r, g, b } = rgb;
  return `0 0 ${config.mid}px rgba(${r}, ${g}, ${b}, ${config.inner}), 0 0 ${config.outer}px rgba(${r}, ${g}, ${b}, ${config.outerOpacity})`;
}

export type ThemeType = typeof theme;
export default theme;
