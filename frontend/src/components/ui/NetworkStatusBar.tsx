/* ─────────────────────────────────────────────
 * AuraGen — NetworkStatusBar
 * Glass indicator showing real-time network tier
 * with a manual "Low-Bandwidth Mode" toggle.
 * ───────────────────────────────────────────── */

"use client";

import { motion, AnimatePresence } from "framer-motion";
import { clsx } from "clsx";
import {
  Wifi,
  WifiOff,
  WifiLow,
  Gauge,
  ChevronDown,
  ChevronUp,
  Zap,
} from "lucide-react";
import { useState, useCallback } from "react";
import type { NetworkTier, NetworkStatus } from "@/types";

interface NetworkStatusBarProps {
  status: NetworkStatus;
  onToggleLowBandwidth: (enabled: boolean) => void;
}

const tierConfig: Record<
  NetworkTier,
  { label: string; icon: typeof Wifi; color: string; bgClass: string; borderClass: string }
> = {
  high: {
    label: "High Quality",
    icon: Wifi,
    color: "text-emerald-400",
    bgClass: "bg-emerald-400/[0.06]",
    borderClass: "border-emerald-400/[0.15]",
  },
  medium: {
    label: "Balanced",
    icon: WifiLow,
    color: "text-amber-400",
    bgClass: "bg-amber-400/[0.06]",
    borderClass: "border-amber-400/[0.15]",
  },
  low: {
    label: "Data Saver",
    icon: WifiOff,
    color: "text-red-400",
    bgClass: "bg-red-400/[0.06]",
    borderClass: "border-red-400/[0.15]",
  },
};

function formatSpeed(bytesPerSec: number): string {
  if (bytesPerSec === 0) return "—";
  const mbps = (bytesPerSec * 8) / 1_000_000;
  if (mbps >= 1) return `${mbps.toFixed(1)} Mbps`;
  const kbps = (bytesPerSec * 8) / 1_000;
  return `${kbps.toFixed(0)} Kbps`;
}

export function NetworkStatusBar({
  status,
  onToggleLowBandwidth,
}: NetworkStatusBarProps) {
  const [expanded, setExpanded] = useState(false);
  const config = tierConfig[status.tier];
  const Icon = config.icon;

  const toggleExpanded = useCallback(() => setExpanded((p) => !p), []);

  return (
    <div className="relative">
      {/* Compact indicator */}
      <motion.button
        onClick={toggleExpanded}
        className={clsx(
          "flex items-center gap-2 px-2.5 py-1 rounded-lg text-[10px] font-medium transition-colors border",
          config.bgClass,
          config.borderClass,
          config.color,
        )}
        whileHover={{ scale: 1.02 }}
        whileTap={{ scale: 0.98 }}
        title={`Network: ${config.label} (${status.downlink} Mbps)`}
      >
        <Icon className="w-3 h-3" />
        <span className="hidden sm:inline">{config.label}</span>
        {expanded ? (
          <ChevronUp className="w-2.5 h-2.5 opacity-50" />
        ) : (
          <ChevronDown className="w-2.5 h-2.5 opacity-50" />
        )}
      </motion.button>

      {/* Expanded panel */}
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ opacity: 0, y: -4, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -4, scale: 0.95 }}
            transition={{ duration: 0.15 }}
            className={clsx(
              "absolute right-0 top-full mt-2 w-64 z-50",
              "rounded-xl border border-white/[0.08]",
              "backdrop-blur-[24px] [-webkit-backdrop-filter:blur(24px)]",
              "shadow-[0_8px_32px_rgba(0,0,0,0.4)]",
            )}
            style={{ background: "rgba(18, 18, 26, 0.95)" }}
          >
            <div className="p-3 space-y-3">
              {/* Header */}
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-semibold text-white/80 tracking-wide">
                  Network Quality
                </span>
                <span
                  className={clsx(
                    "px-2 py-0.5 rounded-full text-[9px] font-bold uppercase tracking-wider",
                    config.bgClass,
                    config.color,
                  )}
                >
                  {config.label}
                </span>
              </div>

              {/* Stats grid */}
              <div className="grid grid-cols-2 gap-2">
                <div className="px-2.5 py-1.5 rounded-lg bg-white/[0.03] border border-white/[0.05]">
                  <p className="text-[9px] text-white/40 uppercase tracking-wider">
                    Connection
                  </p>
                  <p className="text-xs text-white/80 font-mono mt-0.5">
                    {status.effectiveType.toUpperCase()}
                  </p>
                </div>
                <div className="px-2.5 py-1.5 rounded-lg bg-white/[0.03] border border-white/[0.05]">
                  <p className="text-[9px] text-white/40 uppercase tracking-wider">
                    Downlink
                  </p>
                  <p className="text-xs text-white/80 font-mono mt-0.5">
                    {status.downlink} Mbps
                  </p>
                </div>
                <div className="px-2.5 py-1.5 rounded-lg bg-white/[0.03] border border-white/[0.05]">
                  <p className="text-[9px] text-white/40 uppercase tracking-wider">
                    Latency
                  </p>
                  <p className="text-xs text-white/80 font-mono mt-0.5">
                    {status.rtt} ms
                  </p>
                </div>
                <div className="px-2.5 py-1.5 rounded-lg bg-white/[0.03] border border-white/[0.05]">
                  <p className="text-[9px] text-white/40 uppercase tracking-wider">
                    Transfer
                  </p>
                  <p className="text-xs text-white/80 font-mono mt-0.5">
                    {formatSpeed(status.measuredSpeed)}
                  </p>
                </div>
              </div>

              {/* Tier visualization */}
              <div className="flex items-center gap-1.5">
                <Gauge className="w-3 h-3 text-white/30" />
                <div className="flex-1 h-1.5 rounded-full bg-white/[0.06] overflow-hidden">
                  <motion.div
                    className="h-full rounded-full"
                    style={{
                      background:
                        status.tier === "high"
                          ? "linear-gradient(90deg, #10b981, #34d399)"
                          : status.tier === "medium"
                            ? "linear-gradient(90deg, #f59e0b, #fbbf24)"
                            : "linear-gradient(90deg, #f43f5e, #fb7185)",
                    }}
                    animate={{
                      width:
                        status.tier === "high"
                          ? "100%"
                          : status.tier === "medium"
                            ? "55%"
                            : "20%",
                    }}
                    transition={{ duration: 0.5, ease: "easeOut" }}
                  />
                </div>
              </div>

              {/* Low-Bandwidth Mode toggle */}
              <div className="flex items-center justify-between py-1.5 px-1">
                <div className="flex items-center gap-2">
                  <Zap className="w-3.5 h-3.5 text-white/50" />
                  <div>
                    <p className="text-[11px] text-white/70 font-medium">
                      Low-Bandwidth Mode
                    </p>
                    <p className="text-[9px] text-white/35 mt-0.5">
                      Force compressed previews
                    </p>
                  </div>
                </div>
                <button
                  role="switch"
                  aria-checked={status.lowBandwidthMode}
                  onClick={() => onToggleLowBandwidth(!status.lowBandwidthMode)}
                  className={clsx(
                    "relative w-9 h-5 rounded-full transition-colors duration-200",
                    status.lowBandwidthMode
                      ? "bg-indigo-500/60 border border-indigo-400/30"
                      : "bg-white/[0.08] border border-white/[0.1]",
                  )}
                >
                  <motion.div
                    className={clsx(
                      "absolute top-0.5 w-4 h-4 rounded-full shadow-sm",
                      status.lowBandwidthMode
                        ? "bg-white"
                        : "bg-white/50",
                    )}
                    animate={{ left: status.lowBandwidthMode ? 18 : 2 }}
                    transition={{ type: "spring", stiffness: 500, damping: 30 }}
                  />
                </button>
              </div>

              {/* Data saver notice */}
              {status.saveData && (
                <div className="px-2 py-1.5 rounded-lg bg-amber-500/[0.08] border border-amber-500/[0.15]">
                  <p className="text-[10px] text-amber-400/80">
                    Device data saver is active — using compressed assets.
                  </p>
                </div>
              )}

              {/* API support notice */}
              {!status.supported && (
                <p className="text-[9px] text-white/25 text-center">
                  Network API not supported — defaulting to high tier.
                </p>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
