/* ---------------------------------------------
 * AuraGen -- GlassButton
 * Premium glassmorphism button with Neural Glow
 * animation that activates when the 4GB GPU is
 * processing a generation job.
 * --------------------------------------------- */

"use client";

import { forwardRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { clsx } from "clsx";
import { Loader2 } from "lucide-react";

type GlassVariant = "default" | "primary" | "accent" | "ghost" | "danger";
type GlassSize = "sm" | "md" | "lg";

interface GlassButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: GlassVariant;
  size?: GlassSize;
  icon?: React.ReactNode;
  loading?: boolean;
  /** When true, the Neural Glow border animation activates (GPU processing). */
  gpuActive?: boolean;
  children: React.ReactNode;
}

const sizeStyles: Record<GlassSize, string> = {
  sm: "px-3 py-1.5 text-xs gap-1.5 rounded-lg",
  md: "px-5 py-2.5 text-sm gap-2 rounded-xl",
  lg: "px-7 py-3.5 text-base gap-2.5 rounded-2xl",
};

const variantStyles: Record<GlassVariant, string> = {
  default: clsx(
    "bg-white/[0.03] border-white/[0.08] text-white/90",
    "hover:bg-white/[0.06] hover:border-white/[0.14]"
  ),
  primary: clsx(
    "bg-indigo-500/90 border-indigo-400/30 text-white",
    "hover:bg-indigo-500 hover:border-indigo-400/50"
  ),
  accent: clsx(
    "bg-violet-500/20 border-violet-400/20 text-violet-200",
    "hover:bg-violet-500/30 hover:border-violet-400/30"
  ),
  ghost: clsx(
    "bg-transparent border-transparent text-white/60",
    "hover:bg-white/[0.04] hover:text-white/90"
  ),
  danger: clsx(
    "bg-rose-500/15 border-rose-400/20 text-rose-300",
    "hover:bg-rose-500/25 hover:border-rose-400/30"
  ),
};

/* Neural Glow colour keyframes for the GPU-active state */
const neuralGlowBorder = {
  borderColor: [
    "rgba(99,102,241,0.5)",
    "rgba(139,92,246,0.6)",
    "rgba(167,139,250,0.5)",
    "rgba(99,102,241,0.5)",
  ],
  boxShadow: [
    "0 0 12px rgba(99,102,241,0.25), 0 0 40px rgba(99,102,241,0.08), inset 0 0 12px rgba(99,102,241,0.04)",
    "0 0 20px rgba(139,92,246,0.30), 0 0 60px rgba(139,92,246,0.12), inset 0 0 18px rgba(139,92,246,0.06)",
    "0 0 12px rgba(99,102,241,0.25), 0 0 40px rgba(99,102,241,0.08), inset 0 0 12px rgba(99,102,241,0.04)",
  ],
};

export const GlassButton = forwardRef<HTMLButtonElement, GlassButtonProps>(
  function GlassButton(
    {
      variant = "default",
      size = "md",
      icon,
      loading = false,
      gpuActive = false,
      children,
      className,
      disabled,
      ...props
    },
    ref
  ) {
    const isDisabled = disabled || loading;
    const showGlow = gpuActive && !isDisabled;

    return (
      <motion.button
        ref={ref as React.Ref<HTMLButtonElement>}
        whileHover={isDisabled ? undefined : { scale: 1.025 }}
        whileTap={isDisabled ? undefined : { scale: 0.97 }}
        transition={{ type: "spring", stiffness: 400, damping: 25 }}
        className={clsx(
          "relative inline-flex items-center justify-center font-medium",
          "border backdrop-blur-[12px] [-webkit-backdrop-filter:blur(12px)]",
          "outline-none transition-colors duration-200 ease-out",
          "focus-visible:ring-2 focus-visible:ring-indigo-500/50 focus-visible:ring-offset-2 focus-visible:ring-offset-[#0a0a0f]",
          sizeStyles[size],
          variantStyles[variant],
          isDisabled && "opacity-40 cursor-not-allowed pointer-events-none",
          className
        )}
        disabled={isDisabled}
        {...(props as React.ComponentPropsWithoutRef<typeof motion.button>)}
      >
        {/* -- Neural Glow overlay (GPU processing state) -- */}
        <AnimatePresence>
          {showGlow && (
            <motion.span
              className="absolute inset-0 rounded-[inherit] pointer-events-none"
              initial={{ opacity: 0 }}
              animate={{
                opacity: 1,
                ...neuralGlowBorder,
              }}
              exit={{ opacity: 0 }}
              transition={{
                opacity: { duration: 0.3 },
                borderColor: { duration: 3, repeat: Infinity, ease: "easeInOut" },
                boxShadow: { duration: 3, repeat: Infinity, ease: "easeInOut" },
              }}
              style={{
                border: "1.5px solid rgba(99,102,241,0.5)",
              }}
            />
          )}
        </AnimatePresence>

        {/* -- Ambient glow background for primary variant -- */}
        {variant === "primary" && !isDisabled && (
          <motion.span
            className="absolute inset-0 rounded-[inherit] bg-indigo-500/20 blur-xl pointer-events-none -z-10"
            animate={{ opacity: [0.4, 0.7, 0.4], scale: [1, 1.08, 1] }}
            transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}
          />
        )}

        {/* -- Content -- */}
        <span className="relative z-10 inline-flex items-center justify-center gap-[inherit]">
          {loading ? (
            <Loader2
              className={clsx(
                "animate-spin",
                size === "sm" ? "w-3.5 h-3.5" : size === "lg" ? "w-5 h-5" : "w-4 h-4"
              )}
            />
          ) : icon ? (
            <span
              className={clsx(
                "flex items-center justify-center",
                size === "sm" ? "w-3.5 h-3.5" : size === "lg" ? "w-5 h-5" : "w-4 h-4"
              )}
            >
              {icon}
            </span>
          ) : null}
          {children}
        </span>
      </motion.button>
    );
  }
);
