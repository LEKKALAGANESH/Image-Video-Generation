/* ─────────────────────────────────────────────
 * AuraGen — GlassPanel
 * Reusable liquid-glass container component
 * with optional glow and hover effects.
 * ───────────────────────────────────────────── */

"use client";

import { motion, type HTMLMotionProps } from "framer-motion";
import { clsx } from "clsx";
import { forwardRef } from "react";

interface GlassPanelProps extends HTMLMotionProps<"div"> {
  glow?: boolean;
  hoverable?: boolean;
  children: React.ReactNode;
  className?: string;
}

export const GlassPanel = forwardRef<HTMLDivElement, GlassPanelProps>(
  function GlassPanel({ glow = false, hoverable = false, children, className, ...props }, ref) {
    return (
      <motion.div
        ref={ref}
        className={clsx(
          "rounded-2xl",
          hoverable ? "glass-panel-hover" : "glass-panel",
          glow && "animate-glow-breathe",
          className
        )}
        whileHover={
          hoverable
            ? {
                scale: 1.005,
                transition: { duration: 0.2 },
              }
            : undefined
        }
        {...props}
      >
        {/* Shimmer overlay for glow variant */}
        {glow && (
          <div className="pointer-events-none absolute inset-0 rounded-2xl overflow-hidden">
            <div className="glass-shimmer absolute inset-0" />
          </div>
        )}
        {children}
      </motion.div>
    );
  }
);
