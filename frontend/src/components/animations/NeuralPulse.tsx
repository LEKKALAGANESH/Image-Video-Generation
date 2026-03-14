/* ─────────────────────────────────────────────
 * AuraGen — NeuralPulse
 * Premium loading animation with concentric
 * expanding rings, a glowing core, particles,
 * and progress indication.
 * ───────────────────────────────────────────── */

"use client";

import { motion, AnimatePresence } from "framer-motion";
import { useMemo } from "react";

interface NeuralPulseProps {
  progress?: number;  // 0–100
  visible?: boolean;
  size?: "sm" | "md" | "lg";
}

const sizes = {
  sm: { container: 80, core: 16, ring: 60, text: "text-xs" },
  md: { container: 140, core: 24, ring: 100, text: "text-sm" },
  lg: { container: 220, core: 36, ring: 160, text: "text-lg" },
};

/**
 * Computes a color that shifts from accent -> glow -> pulse as progress
 * moves from 0 -> 50 -> 100.
 */
function getProgressColor(progress: number): string {
  if (progress < 50) {
    // accent (#6366f1) -> glow (#818cf8)
    const t = progress / 50;
    const r = Math.round(99 + (129 - 99) * t);
    const g = Math.round(102 + (140 - 102) * t);
    const b = Math.round(241 + (248 - 241) * t);
    return `rgb(${r}, ${g}, ${b})`;
  }
  // glow (#818cf8) -> pulse (#a78bfa)
  const t = (progress - 50) / 50;
  const r = Math.round(129 + (167 - 129) * t);
  const g = Math.round(140 + (139 - 140) * t);
  const b = Math.round(248 + (250 - 248) * t);
  return `rgb(${r}, ${g}, ${b})`;
}

export function NeuralPulse({
  progress = 0,
  visible = true,
  size = "md",
}: NeuralPulseProps) {
  const dim = sizes[size];
  const color = getProgressColor(progress);

  // Generate stable particle positions
  const particles = useMemo(
    () =>
      Array.from({ length: 8 }, (_, i) => ({
        id: i,
        angle: (i / 8) * 360,
        delay: i * 0.35,
        drift: (Math.random() - 0.5) * 40,
        duration: 2.5 + Math.random() * 1.5,
      })),
    []
  );

  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          initial={{ opacity: 0, scale: 0.8 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 0.6 }}
          transition={{ duration: 0.4, ease: "easeOut" }}
          className="relative flex items-center justify-center"
          style={{ width: dim.container, height: dim.container }}
        >
          {/* Concentric pulse rings */}
          {[0, 1, 2].map((i) => (
            <motion.div
              key={`ring-${i}`}
              className="absolute rounded-full"
              style={{
                width: dim.ring,
                height: dim.ring,
                border: `1.5px solid ${color}`,
                opacity: 0,
              }}
              animate={{
                scale: [0.3, 2.2],
                opacity: [0.7, 0],
              }}
              transition={{
                duration: 2.5,
                repeat: Infinity,
                delay: i * 0.8,
                ease: [0.4, 0, 0.2, 1],
              }}
            />
          ))}

          {/* Outer glow halo */}
          <motion.div
            className="absolute rounded-full"
            style={{
              width: dim.core * 3,
              height: dim.core * 3,
              background: `radial-gradient(circle, ${color}20 0%, transparent 70%)`,
            }}
            animate={{
              scale: [1, 1.3, 1],
              opacity: [0.4, 0.7, 0.4],
            }}
            transition={{
              duration: 2,
              repeat: Infinity,
              ease: "easeInOut",
            }}
          />

          {/* Central core orb */}
          <motion.div
            className="absolute rounded-full z-10"
            style={{
              width: dim.core,
              height: dim.core,
              background: `radial-gradient(circle at 35% 35%, ${color}, ${color}80)`,
              boxShadow: `0 0 20px ${color}80, 0 0 60px ${color}30`,
            }}
            animate={{
              scale: [1, 1.15, 1],
              boxShadow: [
                `0 0 20px ${color}80, 0 0 60px ${color}30`,
                `0 0 30px ${color}99, 0 0 80px ${color}50`,
                `0 0 20px ${color}80, 0 0 60px ${color}30`,
              ],
            }}
            transition={{
              duration: 2,
              repeat: Infinity,
              ease: "easeInOut",
            }}
          />

          {/* Floating particles */}
          {particles.map((p) => (
            <motion.div
              key={`particle-${p.id}`}
              className="absolute rounded-full z-10"
              style={{
                width: 3,
                height: 3,
                background: color,
                boxShadow: `0 0 6px ${color}`,
                left: "50%",
                top: "50%",
                marginLeft: -1.5,
                marginTop: -1.5,
              }}
              animate={{
                y: [0, -dim.container * 0.35],
                x: [0, p.drift],
                opacity: [0, 1, 0],
                scale: [0.5, 1, 0],
              }}
              transition={{
                duration: p.duration,
                repeat: Infinity,
                delay: p.delay,
                ease: "easeOut",
              }}
            />
          ))}

          {/* Progress percentage text */}
          <motion.span
            className={`absolute z-20 font-mono font-semibold ${dim.text}`}
            style={{ color, textShadow: `0 0 10px ${color}60` }}
            animate={{ opacity: [0.7, 1, 0.7] }}
            transition={{ duration: 2, repeat: Infinity }}
          >
            {Math.round(progress)}%
          </motion.span>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
