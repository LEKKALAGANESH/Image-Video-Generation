/* ─────────────────────────────────────────────
 * AuraGen — GlowButton
 * Premium button with glow, hover, and tap
 * animations powered by Framer Motion.
 * ───────────────────────────────────────────── */

"use client";

import { motion } from "framer-motion";
import { clsx } from "clsx";
import { Loader2 } from "lucide-react";

type ButtonVariant = "primary" | "secondary" | "ghost";

interface GlowButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  loading?: boolean;
  icon?: React.ReactNode;
  children: React.ReactNode;
}

const variantStyles: Record<ButtonVariant, string> = {
  primary: clsx(
    "bg-aura-accent/90 text-white",
    "shadow-[0_0_20px_rgba(99,102,241,0.3),0_0_60px_rgba(99,102,241,0.1)]",
    "hover:bg-aura-accent hover:shadow-[0_0_30px_rgba(99,102,241,0.4),0_0_80px_rgba(99,102,241,0.15)]",
    "active:bg-aura-accent/80"
  ),
  secondary: clsx(
    "bg-white/[0.04] text-aura-text-primary",
    "border border-white/[0.08]",
    "hover:bg-white/[0.07] hover:border-white/[0.12]"
  ),
  ghost: clsx(
    "bg-transparent text-aura-text-secondary",
    "hover:bg-white/[0.04] hover:text-aura-text-primary"
  ),
};

export function GlowButton({
  variant = "primary",
  loading = false,
  icon,
  children,
  className,
  disabled,
  ...props
}: GlowButtonProps) {
  const isDisabled = disabled || loading;

  return (
    <motion.button
      whileHover={isDisabled ? undefined : { scale: 1.02 }}
      whileTap={isDisabled ? undefined : { scale: 0.97 }}
      transition={{ type: "spring", stiffness: 400, damping: 25 }}
      className={clsx(
        "relative inline-flex items-center justify-center gap-2",
        "rounded-xl px-5 py-2.5 text-sm font-medium",
        "transition-all duration-200 ease-out",
        "outline-none focus-visible:ring-2 focus-visible:ring-aura-accent/50 focus-visible:ring-offset-2 focus-visible:ring-offset-aura-dark",
        variantStyles[variant],
        isDisabled && "opacity-50 cursor-not-allowed pointer-events-none",
        className
      )}
      disabled={isDisabled}
      {...(props as React.ComponentPropsWithoutRef<typeof motion.button>)}
    >
      {/* Glow background layer for primary variant */}
      {variant === "primary" && !isDisabled && (
        <motion.div
          className="absolute inset-0 rounded-xl bg-aura-accent/20 blur-xl"
          animate={{
            opacity: [0.5, 0.8, 0.5],
            scale: [1, 1.05, 1],
          }}
          transition={{
            duration: 3,
            repeat: Infinity,
            ease: "easeInOut",
          }}
        />
      )}

      <span className="relative z-10 flex items-center gap-2">
        {loading ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : icon ? (
          <span className="h-4 w-4 flex items-center justify-center">
            {icon}
          </span>
        ) : null}
        {children}
      </span>
    </motion.button>
  );
}
