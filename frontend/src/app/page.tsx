/* ─────────────────────────────────────────────
 * AuraGen — Main Page
 * Assembles the full workspace: nav, sidebar,
 * canvas, command bar, and SSE integration.
 * ───────────────────────────────────────────── */

"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  Zap,
  Command,
  FolderOpen,
  Menu,
} from "lucide-react";
import { MorphingCanvas } from "@/components/canvas/MorphingCanvas";
import { Sidebar } from "@/components/layout/Sidebar";
import { CommandBar } from "@/components/command-bar/CommandBar";
import { VoiceCommand } from "@/components/ui/VoiceCommand";
import { NotificationCenter } from "@/components/ui/NotificationCenter";
import { GalleryPanel } from "@/components/ui/GalleryPanel";
import { useSSE, type ConnectionStatus } from "@/hooks/useSSE";
import { useNetworkStatus } from "@/hooks/useNetworkStatus";
import { useGPUHealth } from "@/hooks/useGPUHealth";
import { useGenerationStore } from "@/hooks/useGenerationStore";
import { setNetworkTier } from "@/lib/api";
import type { WebSocketMessage } from "@/types";

/* ── Top Navigation Bar ─────────────────────── */

function TopNav({
  status,
  onCommandBarOpen,
  onReconnect,
  onToggleGallery,
  onToggleSidebar,
  gpuStatus,
  gpu,
}: {
  status: ConnectionStatus;
  onCommandBarOpen: () => void;
  onReconnect: () => void;
  onToggleGallery: () => void;
  onToggleSidebar: () => void;
  gpuStatus: "loading" | "healthy" | "degraded" | "offline";
  gpu?: { backend?: string; device_name?: string; vram_mb?: number; cuda_error?: string } | null;
}) {
  return (
    <header className="h-14 flex items-center justify-between px-5 glass-panel border-b border-white/[0.06] z-30 relative">
      {/* Mobile menu button */}
      <button
        onClick={onToggleSidebar}
        className="p-2 rounded-lg bg-white/[0.03] border border-white/[0.06] text-white/40 hover:text-white/70 hover:bg-white/[0.06] transition-colors lg:hidden"
        aria-label="Toggle sidebar"
      >
        <Menu className="w-4 h-4" />
      </button>

      {/* Logo */}
      <div className="flex items-center gap-3">
        <motion.div
          className="flex items-center justify-center w-8 h-8 rounded-lg bg-aura-accent/15 border border-aura-accent/20"
          animate={{
            boxShadow: [
              "0 0 10px rgba(99, 102, 241, 0.15)",
              "0 0 20px rgba(99, 102, 241, 0.3)",
              "0 0 10px rgba(99, 102, 241, 0.15)",
            ],
          }}
          transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}
        >
          <Zap className="h-4 w-4 text-aura-accent" />
        </motion.div>
        <div>
          <h1 className="text-sm font-bold tracking-wide glow-text text-aura-text-primary">
            AuraGen
          </h1>
          <p className="text-[9px] tracking-[0.2em] uppercase text-aura-text-tertiary -mt-0.5">
            Neural Studio
          </p>
        </div>
      </div>

      {/* Center: Command bar trigger */}
      <motion.button
        whileHover={{ scale: 1.02 }}
        whileTap={{ scale: 0.98 }}
        onClick={onCommandBarOpen}
        className="hidden md:flex items-center gap-3 px-4 py-2 rounded-xl bg-white/[0.02] border border-white/[0.06] hover:bg-white/[0.04] hover:border-white/[0.1] transition-all duration-200 group"
      >
        <span className="text-xs text-aura-text-tertiary group-hover:text-aura-text-secondary transition-colors">
          Describe what you want to create...
        </span>
        <kbd className="flex items-center gap-1 px-1.5 py-0.5 rounded-md bg-white/[0.04] border border-white/[0.06] text-[10px] font-mono text-aura-text-tertiary">
          <Command className="h-2.5 w-2.5" />K
        </kbd>
      </motion.button>

      {/* Right: Gallery + Connection Status */}
      <div className="flex items-center gap-3">
        {/* Notifications */}
        <NotificationCenter gpuStatus={gpuStatus} gpu={gpu} />

        {/* Gallery toggle */}
        <button
          onClick={onToggleGallery}
          className="p-2 rounded-lg bg-white/[0.03] border border-white/[0.06] text-white/40 hover:text-white/70 hover:bg-white/[0.06] transition-colors"
          title="Gallery"
        >
          <FolderOpen className="w-3.5 h-3.5" />
        </button>

        {/* Connection Status */}
        <div
          className="flex items-center gap-2 cursor-pointer"
          onClick={() => status === "disconnected" && onReconnect()}
        >
          <div className={`w-2 h-2 rounded-full ${
            status === "connected"
              ? "bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.6)]"
              : status === "connecting"
                ? "bg-amber-400 animate-pulse"
                : "bg-red-400"
          }`} />
          <span className={`text-xs font-medium ${
            status === "connected" ? "text-emerald-300"
            : status === "connecting" ? "text-amber-300"
            : "text-red-300"
          }`}>
            {status === "connected" ? "Live" : status === "connecting" ? "Connecting..." : "Offline"}
          </span>
        </div>
      </div>
    </header>
  );
}

/* ── Main Page ──────────────────────────────── */

export default function HomePage() {
  const { status: wsStatus, lastMessage, reconnect } = useSSE();
  const network = useNetworkStatus();
  const gpuHealth = useGPUHealth();
  const updateJobFromWS = useGenerationStore((s) => s.updateJobFromWS);
  const setCommandBarOpen = useGenerationStore((s) => s.setCommandBarOpen);
  const mode = useGenerationStore((s) => s.mode);
  const [galleryOpen, setGalleryOpen] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  // Keep the API client in sync with the detected network tier
  useEffect(() => {
    setNetworkTier(network.tier);
  }, [network.tier]);

  // Route SSE messages into the store
  useEffect(() => {
    if (lastMessage) {
      updateJobFromWS(lastMessage as unknown as WebSocketMessage);
    }
  }, [lastMessage, updateJobFromWS]);

  return (
    <div className="h-screen w-screen flex flex-col overflow-hidden bg-aura-dark">
      {/* Subtle mode-based background gradient */}
      <motion.div
        className="fixed inset-0 pointer-events-none z-0"
        animate={{
          background:
            mode === "image"
              ? "radial-gradient(ellipse at 20% 80%, rgba(99, 102, 241, 0.04) 0%, transparent 50%)"
              : mode === "video"
                ? "radial-gradient(ellipse at 80% 20%, rgba(236, 72, 153, 0.04) 0%, transparent 50%)"
                : "radial-gradient(ellipse at 50% 50%, rgba(52, 211, 153, 0.04) 0%, transparent 50%)",
        }}
        transition={{ duration: 1.5, ease: "easeInOut" }}
      />

      {/* Top navigation */}
      <TopNav
        status={wsStatus}
        onCommandBarOpen={() => setCommandBarOpen(true)}
        onReconnect={reconnect}
        onToggleGallery={() => setGalleryOpen((o) => !o)}
        onToggleSidebar={() => setSidebarOpen((o) => !o)}
        gpuStatus={gpuHealth.status}
        gpu={gpuHealth.gpu}
      />

      {/* Main workspace */}
      <div className="flex flex-1 overflow-hidden">
        {/* Canvas (center, fills remaining space) */}
        <MorphingCanvas />

        {/* Right sidebar — generation params */}
        <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />
      </div>

      {/* Voice command — floating bottom-left */}
      <VoiceCommand />

      {/* Command bar overlay (Cmd+K) */}
      <CommandBar />

      {/* Persistent gallery panel (right slide-over) */}
      <GalleryPanel open={galleryOpen} onClose={() => setGalleryOpen(false)} />
    </div>
  );
}
