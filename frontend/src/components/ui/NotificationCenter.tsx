/* ─────────────────────────────────────────────
 * AuraGen — Notification Center
 * Unified notification dropdown in TopNav.
 * Replaces stacked banners with a single
 * compact bell icon + dropdown panel.
 * ───────────────────────────────────────────── */

"use client";

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useDismiss } from "@/hooks/useDismiss";
import {
  Bell,
  X,
  Cpu,
  HardDrive,
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
} from "lucide-react";
import { clsx } from "clsx";

export interface NotificationItem {
  id: string;
  type: "warning" | "info" | "success";
  title: string;
  message: string;
  icon?: React.ReactNode;
}

interface NotificationCenterProps {
  /** GPU health status from useGPUHealth */
  gpuStatus: "loading" | "healthy" | "degraded" | "offline";
  /** GPU diagnostic data */
  gpu?: {
    backend?: string;
    device_name?: string;
    vram_mb?: number;
    cuda_error?: string;
  } | null;
}

export function NotificationCenter({ gpuStatus, gpu }: NotificationCenterProps) {
  const [open, setOpen] = useState(false);
  // useDismiss: click outside closes, Escape closes, auto-close after 8s
  const dismissRef = useDismiss({
    open,
    onClose: () => setOpen(false),
    autoCloseMs: 8000,
    closeOnEscape: true,
    closeOnClickOutside: true,
  });

  // Auto-open on every page visit (after GPU status loads)
  useEffect(() => {
    if (gpuStatus === "loading") return;
    const timer = setTimeout(() => setOpen(true), 800);
    return () => clearTimeout(timer);
  }, []); // empty deps = once on mount

  // Build notifications based on current state
  const notifications: NotificationItem[] = [];

  const isCpuOnly = gpu?.backend === "cpu" || gpu?.backend === "none";
  const isGpuDegraded = gpuStatus === "degraded" || gpuStatus === "offline";

  if (isGpuDegraded && !isCpuOnly) {
    notifications.push({
      id: "gpu-driver",
      type: "warning",
      title: "GPU Drivers Missing",
      message: "CUDA drivers not found. Install NVIDIA drivers for faster generation.",
      icon: <AlertTriangle className="w-3.5 h-3.5" />,
    });
  }

  if (isCpuOnly) {
    notifications.push({
      id: "cpu-mode",
      type: "warning",
      title: "CPU Mode Active",
      message: `Running on ${gpu?.device_name || "CPU"}. Generation takes 2-5 min per image.`,
      icon: <Cpu className="w-3.5 h-3.5" />,
    });
  }

  // Always show auto-download info
  notifications.push({
    id: "auto-download",
    type: "info",
    title: "Auto-Download Enabled",
    message: "Creations download to your device automatically. Cloud storage coming soon.",
    icon: <HardDrive className="w-3.5 h-3.5" />,
  });

  if (gpuStatus === "healthy") {
    notifications.push({
      id: "gpu-ok",
      type: "success",
      title: "GPU Ready",
      message: `${gpu?.device_name || "GPU"} detected${gpu?.vram_mb ? ` (${gpu.vram_mb} MB)` : ""}.`,
      icon: <CheckCircle2 className="w-3.5 h-3.5" />,
    });
  }

  const warningCount = notifications.filter((n) => n.type === "warning").length;

  const typeStyles = {
    warning: {
      border: "border-amber-500/25",
      bg: "bg-amber-500/[0.06]",
      iconBg: "bg-amber-500/15",
      iconColor: "text-amber-400",
      titleColor: "text-amber-300",
    },
    info: {
      border: "border-indigo-500/20",
      bg: "bg-indigo-500/[0.04]",
      iconBg: "bg-indigo-500/10",
      iconColor: "text-indigo-400",
      titleColor: "text-indigo-300",
    },
    success: {
      border: "border-emerald-500/20",
      bg: "bg-emerald-500/[0.04]",
      iconBg: "bg-emerald-500/10",
      iconColor: "text-emerald-400",
      titleColor: "text-emerald-300",
    },
  };

  return (
    <div className="relative" ref={dismissRef}>
      {/* Bell button */}
      <button
        onClick={() => setOpen((o) => !o)}
        className={clsx(
          "relative p-2 rounded-lg transition-colors",
          "bg-white/[0.03] border border-white/[0.06]",
          "text-white/40 hover:text-white/70 hover:bg-white/[0.06]",
          open && "bg-white/[0.06] text-white/70"
        )}
        title="Notifications"
        aria-expanded={open}
        aria-haspopup="dialog"
      >
        <Bell className="w-3.5 h-3.5" />
        {/* Badge */}
        {warningCount > 0 && (
          <span className="absolute -top-1 -right-1 flex items-center justify-center w-4 h-4 rounded-full bg-amber-500 text-[9px] font-bold text-black">
            {warningCount}
          </span>
        )}
        {warningCount === 0 && notifications.length > 0 && (
          <span className="absolute -top-0.5 -right-0.5 w-2 h-2 rounded-full bg-indigo-400" />
        )}
      </button>

      {/* Dropdown */}
      <AnimatePresence>
        {open && (
          <motion.div
            role="dialog"
            aria-label="System notifications"
            initial={{ opacity: 0, y: -4, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -4, scale: 0.98 }}
            transition={{ duration: 0.15, ease: "easeOut" }}
            className={clsx(
              "absolute right-0 top-full mt-2 z-50",
              "w-80 rounded-xl overflow-hidden",
              "border border-white/[0.08]",
              "backdrop-blur-[24px] [-webkit-backdrop-filter:blur(24px)]",
              "shadow-[0_8px_32px_rgba(0,0,0,0.4)]"
            )}
            style={{ background: "rgba(15, 15, 20, 0.92)" }}
          >
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-2.5 border-b border-white/[0.06]">
              <span className="text-xs font-semibold text-white/70 tracking-wide">
                System Status
              </span>
              <button
                onClick={() => setOpen(false)}
                className="text-white/30 hover:text-white/60 transition-colors"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>

            {/* Notification list */}
            <div className="py-1.5 max-h-72 overflow-y-auto">
              {notifications.map((n) => {
                const s = typeStyles[n.type];
                return (
                  <div
                    key={n.id}
                    role="status"
                    className={clsx(
                      "mx-2 my-1 px-3 py-2.5 rounded-lg",
                      "border",
                      s.border,
                      s.bg
                    )}
                  >
                    <div className="flex items-start gap-2.5">
                      <div
                        className={clsx(
                          "flex items-center justify-center w-6 h-6 rounded-md flex-shrink-0 mt-0.5",
                          s.iconBg,
                          s.iconColor
                        )}
                      >
                        {n.icon}
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className={clsx("text-[11px] font-semibold", s.titleColor)}>
                          {n.title}
                        </p>
                        <p className="text-[10px] text-white/45 leading-relaxed mt-0.5">
                          {n.message}
                        </p>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Footer */}
            <div className="px-4 py-2 border-t border-white/[0.06]">
              <p className="text-[9px] text-white/25 text-center">
                AuraGen Neural Studio
              </p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
