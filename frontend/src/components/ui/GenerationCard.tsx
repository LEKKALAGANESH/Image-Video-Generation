/* ---------------------------------------------
 * AuraGen -- GenerationCard
 * Glass card displaying a generation job with
 * live progress, Neural Glow on GPU activity,
 * and result preview.
 * --------------------------------------------- */

"use client";

import { motion, AnimatePresence } from "framer-motion";
import { clsx } from "clsx";
import { X, Download, Maximize2, Clock, AlertCircle, AlertTriangle } from "lucide-react";
import { NeuralPulse } from "@/components/animations/NeuralPulse";
import { AdaptiveMedia } from "@/components/ui/AdaptiveMedia";
import { ThreePhaseProgress } from "@/components/ui/ThreePhaseProgress";
import { useImageIntegrity } from "@/hooks/useImageIntegrity";
import { useAutoDownload } from "@/hooks/useAutoDownload";
import { getNetworkTier } from "@/lib/api";
import type { GenerationJob, GenerationMode, NetworkTier } from "@/types";

interface GenerationCardProps {
  job: GenerationJob;
  /** Current network tier — if omitted, reads from API client singleton. */
  networkTier?: NetworkTier;
  onRemove?: (jobId: string) => void;
  onExpand?: (jobId: string) => void;
  className?: string;
}

const modeLabels: Record<GenerationMode, string> = {
  image: "Image",
  video: "Video",
  pose: "Pose",
};

const statusConfig = {
  queued: {
    label: "Queued",
    color: "rgba(245, 158, 11, 0.8)",
    bgClass: "bg-amber-500/10",
  },
  processing: {
    label: "Generating",
    color: "rgba(99, 102, 241, 0.9)",
    bgClass: "bg-indigo-500/10",
  },
  completed: {
    label: "Complete",
    color: "rgba(16, 185, 129, 0.9)",
    bgClass: "bg-emerald-500/10",
  },
  failed: {
    label: "Failed",
    color: "rgba(244, 63, 94, 0.9)",
    bgClass: "bg-rose-500/10",
  },
  cancelled: {
    label: "Cancelled",
    color: "rgba(255, 255, 255, 0.4)",
    bgClass: "bg-white/5",
  },
} as const;

export function GenerationCard({
  job,
  networkTier,
  onRemove,
  onExpand,
  className,
}: GenerationCardProps) {
  const tier = networkTier ?? getNetworkTier();
  const isProcessing = job.status === "processing";
  const isComplete = job.status === "completed";
  const isFailed = job.status === "failed";
  const status = statusConfig[job.status];

  // Auto-download completed outputs to OPFS for local-first gallery
  const { phase: dlPhase, percent: dlPercent, localUrl } = useAutoDownload(job);

  // Use local OPFS URL when available, fall back to backend URL
  const displayUrl = localUrl ?? job.result_url;

  // Image integrity check — detect blank/solid-color outputs
  const { status: integrity, dominantColor } = useImageIntegrity(
    isComplete ? displayUrl : null,
  );
  const isBlankOutput = integrity === "blank";

  // Show three-phase progress during processing or active download
  const showPhaseProgress =
    isProcessing || (isComplete && dlPhase !== "ready" && dlPhase !== "idle");

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 20, scale: 0.95 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, scale: 0.9, y: -10 }}
      transition={{ type: "spring", stiffness: 300, damping: 30 }}
      className={clsx(
        "group relative overflow-hidden rounded-2xl",
        "border border-white/[0.08]",
        "backdrop-blur-[20px] [-webkit-backdrop-filter:blur(20px)]",
        "transition-all duration-300 ease-out",
        className
      )}
      style={{
        background: "rgba(255, 255, 255, 0.02)",
        boxShadow: [
          "0 4px 16px rgba(0,0,0,0.2)",
          "inset 0 1px 0 rgba(255,255,255,0.03)",
          isProcessing
            ? "0 0 40px rgba(99,102,241,0.12), 0 0 80px rgba(99,102,241,0.06)"
            : "",
        ]
          .filter(Boolean)
          .join(", "),
      }}
    >
      {/* -- Neural Glow: pulsing border when GPU is processing -- */}
      <AnimatePresence>
        {isProcessing && (
          <motion.div
            className="absolute inset-0 rounded-2xl pointer-events-none z-0"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.4 }}
            style={{
              background:
                "linear-gradient(135deg, rgba(99,102,241,0.08), rgba(139,92,246,0.04), transparent)",
            }}
          >
            {/* Animated glow border overlay */}
            <motion.div
              className="absolute inset-0 rounded-2xl"
              style={{
                border: "1px solid rgba(99,102,241,0.3)",
                boxShadow:
                  "inset 0 0 20px rgba(99,102,241,0.05), 0 0 20px rgba(99,102,241,0.1)",
              }}
              animate={{
                borderColor: [
                  "rgba(99,102,241,0.3)",
                  "rgba(139,92,246,0.4)",
                  "rgba(99,102,241,0.3)",
                ],
                boxShadow: [
                  "inset 0 0 20px rgba(99,102,241,0.05), 0 0 20px rgba(99,102,241,0.1)",
                  "inset 0 0 30px rgba(99,102,241,0.08), 0 0 40px rgba(99,102,241,0.15)",
                  "inset 0 0 20px rgba(99,102,241,0.05), 0 0 20px rgba(99,102,241,0.1)",
                ],
              }}
              transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}
            />
          </motion.div>
        )}
      </AnimatePresence>

      {/* -- Preview Area -- */}
      <div className="relative aspect-square bg-white/[0.01] overflow-hidden">
        {isComplete && displayUrl ? (
          <>
            <AdaptiveMedia
              src={displayUrl}
              previewSrc={job.thumbnail_url}
              tier={tier}
              alt={job.prompt}
              className="w-full h-full"
              mediaType={job.mode === "video" ? "video/mp4" : "image/png"}
            />
            {/* Optimization Warning — blank/solid-color output detected */}
            <AnimatePresence>
              {isBlankOutput && (
                <motion.div
                  className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-black/70 backdrop-blur-sm z-20"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.3 }}
                >
                  <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-amber-500/15 border border-amber-500/25">
                    <AlertTriangle className="w-5 h-5 text-amber-400" />
                  </div>
                  <span className="text-xs font-medium text-amber-300/90">
                    Optimization Warning
                  </span>
                  <p className="text-[10px] text-white/50 text-center max-w-[85%] leading-relaxed">
                    Blank output detected{dominantColor ? ` (${dominantColor})` : ""}.
                    This may indicate a dtype mismatch or insufficient VRAM.
                    Try reducing resolution or enabling 4-bit quantization.
                  </p>
                </motion.div>
              )}
            </AnimatePresence>
          </>
        ) : isProcessing ? (
          <div className="absolute inset-0 flex items-center justify-center">
            <NeuralPulse progress={job.progress} visible size="md" />
          </div>
        ) : isFailed ? (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-rose-400/80">
            <AlertCircle className="w-8 h-8" />
            <span className="text-xs max-w-[80%] text-center truncate">
              {job.error || "Generation failed"}
            </span>
          </div>
        ) : (
          <div className="absolute inset-0 flex items-center justify-center">
            <Clock className="w-6 h-6 text-white/20" />
          </div>
        )}

        {/* -- Hover action buttons -- */}
        <div
          className={clsx(
            "absolute top-2 right-2 flex gap-1.5",
            "opacity-0 group-hover:opacity-100 transition-opacity duration-200"
          )}
        >
          {isComplete && displayUrl && (
            <a
              href={displayUrl}
              download
              className="p-1.5 rounded-lg bg-black/40 backdrop-blur-sm border border-white/10 text-white/70 hover:text-white hover:bg-black/60 transition-colors"
            >
              <Download className="w-3.5 h-3.5" />
            </a>
          )}
          {onExpand && (
            <button
              onClick={() => onExpand(job.job_id)}
              className="p-1.5 rounded-lg bg-black/40 backdrop-blur-sm border border-white/10 text-white/70 hover:text-white hover:bg-black/60 transition-colors"
            >
              <Maximize2 className="w-3.5 h-3.5" />
            </button>
          )}
          {onRemove && (
            <button
              onClick={() => onRemove(job.job_id)}
              className="p-1.5 rounded-lg bg-black/40 backdrop-blur-sm border border-white/10 text-white/70 hover:text-rose-400 hover:bg-black/60 transition-colors"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        {/* -- Mode badge -- */}
        <div className="absolute top-2 left-2">
          <span className="px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider rounded-full bg-black/40 backdrop-blur-sm border border-white/10 text-white/60">
            {modeLabels[job.mode]}
          </span>
        </div>
      </div>

      {/* -- Info Footer -- */}
      <div className="relative z-10 p-3 space-y-2">
        {/* Prompt */}
        <p className="text-xs text-white/70 line-clamp-2 leading-relaxed">
          {job.prompt}
        </p>

        {/* Status + Progress row */}
        <div className="flex items-center justify-between gap-2">
          <span
            className={clsx(
              "inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-medium",
              status.bgClass
            )}
            style={{ color: status.color }}
          >
            {isProcessing && (
              <motion.span
                className="w-1.5 h-1.5 rounded-full"
                style={{ background: status.color }}
                animate={{ opacity: [1, 0.3, 1] }}
                transition={{ duration: 1.5, repeat: Infinity }}
              />
            )}
            {status.label}
          </span>

          {(isProcessing || job.status === "queued") && (
            <span className="text-[10px] text-white/40 font-mono tabular-nums">
              {job.progress}%
            </span>
          )}
        </div>

        {/* Three-Phase Progress: GPU → Stream → Ready */}
        {showPhaseProgress && (
          <ThreePhaseProgress
            jobStatus={job.status}
            jobProgress={job.progress}
            downloadPhase={dlPhase}
            downloadPercent={dlPercent}
          />
        )}
      </div>
    </motion.div>
  );
}
