/* ─────────────────────────────────────────────
 * AuraGen — Three-Phase Progress Indicator
 *
 * Phase 1: Neural Pulse (GPU Processing)
 * Phase 2: Disk Pulse  (Streaming to OPFS)
 * Phase 3: Instant Access (Ready)
 * ───────────────────────────────────────────── */

"use client";

import { motion } from "framer-motion";
import { clsx } from "clsx";
import { Cpu, HardDrive, Zap } from "lucide-react";
import type { DownloadPhase } from "@/lib/download-manager";
import type { JobStatus } from "@/types";

type Phase = "generating" | "streaming" | "saving" | "ready" | "idle" | "failed";

interface ThreePhaseProgressProps {
  jobStatus: JobStatus;
  jobProgress: number;
  downloadPhase?: DownloadPhase;
  downloadPercent?: number;
  className?: string;
}

function resolvePhase(
  jobStatus: JobStatus,
  downloadPhase?: DownloadPhase,
): Phase {
  if (jobStatus === "failed") return "failed";
  if (jobStatus === "processing") return "generating";
  if (jobStatus === "completed") {
    if (downloadPhase === "streaming") return "streaming";
    if (downloadPhase === "saving") return "saving";
    if (downloadPhase === "ready") return "ready";
    return "ready";
  }
  return "idle";
}

const phaseConfig = {
  idle: {
    label: "Waiting",
    color: "rgba(255,255,255,0.3)",
    glow: "transparent",
  },
  generating: {
    label: "GPU Processing",
    color: "rgba(99, 102, 241, 0.9)",
    glow: "rgba(99, 102, 241, 0.3)",
  },
  streaming: {
    label: "Streaming to Device",
    color: "rgba(59, 130, 246, 0.9)",
    glow: "rgba(59, 130, 246, 0.3)",
  },
  saving: {
    label: "Saving to Storage",
    color: "rgba(245, 158, 11, 0.9)",
    glow: "rgba(245, 158, 11, 0.3)",
  },
  ready: {
    label: "Instant Access",
    color: "rgba(16, 185, 129, 0.9)",
    glow: "rgba(16, 185, 129, 0.3)",
  },
  failed: {
    label: "Failed",
    color: "rgba(244, 63, 94, 0.9)",
    glow: "rgba(244, 63, 94, 0.2)",
  },
} as const;

const phaseIcons = {
  idle: null,
  generating: Cpu,
  streaming: HardDrive,
  saving: HardDrive,
  ready: Zap,
  failed: null,
};

export function ThreePhaseProgress({
  jobStatus,
  jobProgress,
  downloadPhase,
  downloadPercent,
  className,
}: ThreePhaseProgressProps) {
  const phase = resolvePhase(jobStatus, downloadPhase);
  const config = phaseConfig[phase];
  const Icon = phaseIcons[phase];

  // Total progress across all phases:
  // generating = 0-70%, streaming = 70-90%, saving = 90-95%, ready = 100%
  let totalPercent = 0;
  if (phase === "generating") {
    totalPercent = Math.round(jobProgress * 0.7);
  } else if (phase === "streaming") {
    totalPercent = 70 + Math.round((downloadPercent ?? 0) * 0.2);
  } else if (phase === "saving") {
    totalPercent = 92;
  } else if (phase === "ready") {
    totalPercent = 100;
  }

  const steps: Phase[] = ["generating", "streaming", "ready"];

  return (
    <div className={clsx("space-y-2", className)}>
      {/* Phase step indicators */}
      <div className="flex items-center gap-1">
        {steps.map((step, i) => {
          const stepIndex = steps.indexOf(phase);
          const thisIndex = i;
          const isActive = step === phase || (phase === "saving" && step === "streaming");
          const isComplete =
            phase === "ready" ||
            thisIndex < stepIndex ||
            (phase === "saving" && thisIndex <= 1);

          return (
            <div key={step} className="flex items-center gap-1 flex-1">
              {/* Dot */}
              <motion.div
                className="relative w-2 h-2 rounded-full flex-shrink-0"
                style={{
                  background: isComplete
                    ? phaseConfig[step].color
                    : isActive
                      ? phaseConfig[step].color
                      : "rgba(255,255,255,0.1)",
                }}
                animate={
                  isActive && phase !== "ready"
                    ? {
                        boxShadow: [
                          `0 0 4px ${phaseConfig[step].glow}`,
                          `0 0 12px ${phaseConfig[step].glow}`,
                          `0 0 4px ${phaseConfig[step].glow}`,
                        ],
                      }
                    : undefined
                }
                transition={
                  isActive ? { duration: 1.5, repeat: Infinity, ease: "easeInOut" } : undefined
                }
              />
              {/* Connector line */}
              {i < steps.length - 1 && (
                <div className="flex-1 h-px bg-white/[0.06] relative overflow-hidden">
                  {isComplete && (
                    <motion.div
                      className="absolute inset-0"
                      style={{ background: phaseConfig[step].color }}
                      initial={{ scaleX: 0 }}
                      animate={{ scaleX: 1 }}
                      transition={{ duration: 0.4 }}
                    />
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Progress bar */}
      <div className="w-full h-1 rounded-full bg-white/[0.04] overflow-hidden">
        <motion.div
          className="h-full rounded-full"
          style={{ background: config.color }}
          animate={{
            width: `${totalPercent}%`,
            boxShadow: `0 0 8px ${config.glow}`,
          }}
          transition={{ duration: 0.3, ease: "easeOut" }}
        />
      </div>

      {/* Label */}
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-1.5 text-[10px] font-medium" style={{ color: config.color }}>
          {Icon && (
            <motion.span
              animate={
                phase === "generating" || phase === "streaming"
                  ? { opacity: [1, 0.4, 1] }
                  : undefined
              }
              transition={
                phase === "generating" || phase === "streaming"
                  ? { duration: 1.5, repeat: Infinity }
                  : undefined
              }
            >
              <Icon className="w-3 h-3" />
            </motion.span>
          )}
          {config.label}
        </span>
        <span className="text-[10px] text-white/30 font-mono tabular-nums">
          {totalPercent}%
        </span>
      </div>
    </div>
  );
}
