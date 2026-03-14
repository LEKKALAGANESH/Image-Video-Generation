/* ─────────────────────────────────────────────
 * AuraGen — GPU Recovery Mode Banner
 * Shown when the backend detects nvcuda.dll or
 * driver errors. Displays actionable diagnostics.
 * ───────────────────────────────────────────── */

"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { AlertTriangle, ChevronDown, RefreshCw, X } from "lucide-react";
import { clsx } from "clsx";
import type { GPUHealth, GPUStatus } from "@/hooks/useGPUHealth";

interface GPURecoveryBannerProps {
  status: GPUStatus;
  gpu: GPUHealth | null;
  error: string | null;
  onRetry: () => void;
}

export function GPURecoveryBanner({
  status,
  gpu,
  error,
  onRetry,
}: GPURecoveryBannerProps) {
  const [expanded, setExpanded] = useState(false);
  const [dismissed, setDismissed] = useState(false);

  // Only show for degraded/offline states
  if (status === "healthy" || status === "loading" || dismissed) return null;

  const isOffline = status === "offline";
  const isDirectML = gpu?.backend === "directml";
  const isCPU = gpu?.backend === "cpu";
  const hasCudaError = !!(gpu?.cudaError);
  const isDriverMissing = hasCudaError && (
    gpu!.cudaError.includes("nvcuda") ||
    gpu!.cudaError.includes("driver") ||
    gpu!.cudaError.includes("CUDA") ||
    !gpu!.driverInstalled
  );

  const title = isOffline
    ? "Backend Offline"
    : isDriverMissing
      ? "GPU Driver Update Required"
      : isDirectML
        ? "Running on DirectML (Fallback)"
        : isCPU
          ? "CPU-Only Mode"
          : "GPU Degraded";

  const description = isOffline
    ? "Cannot reach the AuraGen backend. Your gallery is still available offline."
    : isDriverMissing
      ? "NVIDIA CUDA drivers are missing or outdated. Generation speed will be significantly reduced."
      : isDirectML
        ? "Using Windows DirectML as a fallback. Install NVIDIA drivers for full CUDA acceleration."
        : "Running without GPU acceleration. Generation will be very slow.";

  const borderColor = isOffline
    ? "border-red-500/20"
    : "border-amber-500/20";
  const bgColor = isOffline
    ? "bg-red-500/[0.04]"
    : "bg-amber-500/[0.04]";
  const iconColor = isOffline ? "text-red-400" : "text-amber-400";

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -20 }}
        className={clsx(
          "mx-4 mt-2 rounded-xl border backdrop-blur-sm overflow-hidden",
          borderColor,
          bgColor,
        )}
      >
        {/* Header */}
        <div className="flex items-center gap-3 px-4 py-3">
          <motion.div
            animate={{
              boxShadow: [
                `0 0 4px ${isOffline ? "rgba(248,113,113,0.2)" : "rgba(245,158,11,0.2)"}`,
                `0 0 12px ${isOffline ? "rgba(248,113,113,0.4)" : "rgba(245,158,11,0.4)"}`,
                `0 0 4px ${isOffline ? "rgba(248,113,113,0.2)" : "rgba(245,158,11,0.2)"}`,
              ],
            }}
            transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
            className={clsx(
              "flex items-center justify-center w-8 h-8 rounded-lg flex-shrink-0",
              isOffline ? "bg-red-500/10" : "bg-amber-500/10",
            )}
          >
            <AlertTriangle className={clsx("w-4 h-4", iconColor)} />
          </motion.div>

          <div className="flex-1 min-w-0">
            <h3 className={clsx("text-xs font-semibold", iconColor)}>
              {title}
            </h3>
            <p className="text-[10px] text-white/40 leading-relaxed mt-0.5">
              {description}
            </p>
          </div>

          <div className="flex items-center gap-1.5 flex-shrink-0">
            <button
              onClick={onRetry}
              className="p-1.5 rounded-lg bg-white/[0.04] border border-white/[0.08] text-white/50 hover:text-white/80 hover:bg-white/[0.08] transition-colors"
              title="Retry detection"
            >
              <RefreshCw className="w-3 h-3" />
            </button>
            <button
              onClick={() => setExpanded(!expanded)}
              className="p-1.5 rounded-lg bg-white/[0.04] border border-white/[0.08] text-white/50 hover:text-white/80 hover:bg-white/[0.08] transition-colors"
            >
              <motion.span animate={{ rotate: expanded ? 180 : 0 }}>
                <ChevronDown className="w-3 h-3" />
              </motion.span>
            </button>
            <button
              onClick={() => setDismissed(true)}
              className="p-1.5 rounded-lg bg-white/[0.04] border border-white/[0.08] text-white/50 hover:text-white/80 hover:bg-white/[0.08] transition-colors"
            >
              <X className="w-3 h-3" />
            </button>
          </div>
        </div>

        {/* Expanded diagnostics */}
        <AnimatePresence>
          {expanded && gpu && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="overflow-hidden"
            >
              <div className="px-4 pb-3 pt-1 space-y-2 border-t border-white/[0.04]">
                <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-[10px]">
                  <span className="text-white/30">Backend</span>
                  <span className="text-white/60 font-mono">{gpu.backend}</span>
                  <span className="text-white/30">Device</span>
                  <span className="text-white/60 font-mono">{gpu.deviceName || "—"}</span>
                  <span className="text-white/30">VRAM</span>
                  <span className="text-white/60 font-mono">
                    {gpu.vramMb > 0 ? `${gpu.vramMb} MB` : "—"}
                  </span>
                  <span className="text-white/30">NVIDIA Driver</span>
                  <span className={clsx("font-mono", gpu.driverInstalled ? "text-emerald-400/70" : "text-red-400/70")}>
                    {gpu.driverInstalled ? "Installed" : "Missing"}
                  </span>
                </div>

                {gpu.cudaError && (
                  <div className="mt-2 p-2 rounded-lg bg-black/20 border border-white/[0.04]">
                    <span className="text-[9px] text-white/30 uppercase tracking-wider">CUDA Error</span>
                    <p className="text-[10px] text-red-400/80 font-mono mt-1 break-all leading-relaxed">
                      {gpu.cudaError}
                    </p>
                  </div>
                )}

                {gpu.warnings.length > 0 && (
                  <div className="space-y-1 mt-1">
                    {gpu.warnings.map((w, i) => (
                      <p key={i} className="text-[10px] text-amber-400/60 leading-relaxed">
                        {w}
                      </p>
                    ))}
                  </div>
                )}

                {isDriverMissing && (
                  <a
                    href="https://www.nvidia.com/drivers"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1.5 mt-1 px-3 py-1.5 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-400/90 text-[10px] font-medium hover:bg-amber-500/15 transition-colors"
                  >
                    Download NVIDIA Drivers
                  </a>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>
    </AnimatePresence>
  );
}
