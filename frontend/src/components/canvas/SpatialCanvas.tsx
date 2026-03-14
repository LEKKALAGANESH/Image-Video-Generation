/* ─────────────────────────────────────────────
 * AuraGen — SpatialCanvas
 * Infinite, pannable + zoomable workspace for
 * displaying generated media cards.
 * ───────────────────────────────────────────── */

"use client";

import { useCallback, useRef, useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Download,
  Trash2,
  Repeat,
  ZoomIn,
  ZoomOut,
  Maximize2,
  Move,
  Image as ImageIcon,
  Film,
} from "lucide-react";
import { clsx } from "clsx";
import { useGenerationStore } from "@/hooks/useGenerationStore";
import { NeuralPulse } from "@/components/animations/NeuralPulse";
import type { CanvasItem } from "@/types";

/* ── Canvas card for a single generation ──── */

function CanvasCard({
  item,
  canvasScale,
  onDragEnd,
  onRemove,
  onRemix,
}: {
  item: CanvasItem;
  canvasScale: number;
  onDragEnd: (id: string, x: number, y: number) => void;
  onRemove: (id: string) => void;
  onRemix: (item: CanvasItem) => void;
}) {
  const { job } = item;
  const isLoading =
    job.status === "queued" || job.status === "processing";
  const isFailed = job.status === "failed";
  const isCompleted = job.status === "completed";

  const handleDownload = useCallback(() => {
    if (job.result_url) {
      const a = document.createElement("a");
      a.href = job.result_url;
      a.download = `auragen-${job.job_id}.png`;
      a.click();
    }
  }, [job]);

  return (
    <motion.div
      drag
      dragMomentum={false}
      dragElastic={0}
      onDragEnd={(_, info) => {
        onDragEnd(
          item.id,
          item.position.x + info.offset.x / canvasScale,
          item.position.y + info.offset.y / canvasScale
        );
      }}
      initial={{ opacity: 0, scale: 0.8 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.6 }}
      transition={{
        type: "spring",
        stiffness: 300,
        damping: 25,
      }}
      className="absolute group cursor-grab active:cursor-grabbing"
      style={{
        left: item.position.x,
        top: item.position.y,
        width: item.size.width,
      }}
    >
      <div className="glass-panel-hover rounded-xl overflow-hidden">
        {/* Image / Video preview area */}
        <div
          className="relative bg-aura-surface/50 flex items-center justify-center overflow-hidden"
          style={{
            height: item.size.height,
            minHeight: 120,
          }}
        >
          {isLoading && (
            <div className="flex flex-col items-center gap-3">
              <NeuralPulse
                progress={job.progress}
                visible
                size="sm"
              />
              <span className="text-[11px] text-aura-text-tertiary capitalize">
                {job.status}...
              </span>
            </div>
          )}

          {isFailed && (
            <div className="flex flex-col items-center gap-2 px-4 text-center">
              <div className="w-10 h-10 rounded-full bg-red-500/10 flex items-center justify-center">
                <span className="text-red-400 text-lg">!</span>
              </div>
              <span className="text-xs text-red-400/80">
                {job.error ?? "Generation failed"}
              </span>
            </div>
          )}

          {isCompleted && job.result_url && (
            <img
              src={job.result_url}
              alt={job.prompt}
              className="w-full h-full object-cover"
              draggable={false}
            />
          )}

          {isCompleted && !job.result_url && (
            <div className="flex flex-col items-center gap-2 text-aura-text-tertiary">
              {job.mode === "image" ? (
                <ImageIcon className="h-8 w-8" />
              ) : (
                <Film className="h-8 w-8" />
              )}
              <span className="text-xs">Preview unavailable</span>
            </div>
          )}

          {/* Hover action bar */}
          {isCompleted && (
            <div className="absolute bottom-0 inset-x-0 opacity-0 group-hover:opacity-100 transition-opacity duration-200">
              <div className="flex items-center justify-center gap-1 p-2 bg-gradient-to-t from-black/60 to-transparent">
                <motion.button
                  whileHover={{ scale: 1.1 }}
                  whileTap={{ scale: 0.9 }}
                  onClick={handleDownload}
                  className="p-1.5 rounded-lg bg-white/10 hover:bg-white/20 transition-colors"
                  title="Download"
                >
                  <Download className="h-3.5 w-3.5 text-white/80" />
                </motion.button>
                <motion.button
                  whileHover={{ scale: 1.1 }}
                  whileTap={{ scale: 0.9 }}
                  onClick={() => onRemix(item)}
                  className="p-1.5 rounded-lg bg-white/10 hover:bg-white/20 transition-colors"
                  title="Remix"
                >
                  <Repeat className="h-3.5 w-3.5 text-white/80" />
                </motion.button>
                <motion.button
                  whileHover={{ scale: 1.1 }}
                  whileTap={{ scale: 0.9 }}
                  onClick={() => onRemove(item.id)}
                  className="p-1.5 rounded-lg bg-white/10 hover:bg-red-500/30 transition-colors"
                  title="Delete"
                >
                  <Trash2 className="h-3.5 w-3.5 text-white/80" />
                </motion.button>
              </div>
            </div>
          )}
        </div>

        {/* Card footer — prompt + meta */}
        <div className="px-3 py-2.5 border-t border-white/[0.04]">
          <p className="text-[11px] text-aura-text-secondary leading-relaxed line-clamp-2">
            {job.prompt}
          </p>
          <div className="mt-1.5 flex items-center justify-between">
            <span className="text-[10px] text-aura-text-tertiary font-mono">
              {new Date(job.created_at).toLocaleTimeString([], {
                hour: "2-digit",
                minute: "2-digit",
              })}
            </span>
            <span
              className={clsx(
                "text-[10px] font-medium uppercase tracking-wider",
                job.status === "completed" && "text-emerald-400/70",
                job.status === "processing" && "text-aura-glow/70",
                job.status === "queued" && "text-aura-text-tertiary",
                job.status === "failed" && "text-red-400/70",
                job.status === "cancelled" && "text-yellow-400/70"
              )}
            >
              {job.mode}
            </span>
          </div>
        </div>
      </div>
    </motion.div>
  );
}

/* ── Main canvas component ─────────────────── */

export function SpatialCanvas() {
  const canvasRef = useRef<HTMLDivElement>(null);

  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [scale, setScale] = useState(1);
  const [isPanning, setIsPanning] = useState(false);
  const [spaceHeld, setSpaceHeld] = useState(false);

  const canvasItems = useGenerationStore((s) => s.canvasItems);
  const updatePos = useGenerationStore((s) => s.updateCanvasItemPosition);
  const removeItem = useGenerationStore((s) => s.removeCanvasItem);
  const setPrompt = useGenerationStore((s) => s.setPrompt);
  const setMode = useGenerationStore((s) => s.setMode);

  // Space key for pan mode
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.code === "Space" && !e.repeat && !(e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement)) {
        e.preventDefault();
        setSpaceHeld(true);
      }
    }
    function onKeyUp(e: KeyboardEvent) {
      if (e.code === "Space") {
        setSpaceHeld(false);
        setIsPanning(false);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("keyup", onKeyUp);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("keyup", onKeyUp);
    };
  }, []);

  // Pan with mouse drag when space is held
  const panStart = useRef({ x: 0, y: 0 });
  const panOrigin = useRef({ x: 0, y: 0 });

  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      if (!spaceHeld) return;
      e.preventDefault();
      setIsPanning(true);
      panStart.current = { x: e.clientX, y: e.clientY };
      panOrigin.current = { ...pan };
    },
    [spaceHeld, pan]
  );

  const handleMouseMove = useCallback(
    (e: React.MouseEvent) => {
      if (!isPanning) return;
      const dx = e.clientX - panStart.current.x;
      const dy = e.clientY - panStart.current.y;
      setPan({
        x: panOrigin.current.x + dx,
        y: panOrigin.current.y + dy,
      });
    },
    [isPanning]
  );

  const handleMouseUp = useCallback(() => {
    setIsPanning(false);
  }, []);

  // Zoom with scroll wheel
  const handleWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault();
    const delta = e.deltaY > 0 ? -0.05 : 0.05;
    setScale((s) => Math.min(Math.max(s + delta, 0.2), 3));
  }, []);

  // Zoom controls
  const zoomIn = useCallback(() => {
    setScale((s) => Math.min(s + 0.15, 3));
  }, []);

  const zoomOut = useCallback(() => {
    setScale((s) => Math.max(s - 0.15, 0.2));
  }, []);

  const resetView = useCallback(() => {
    setPan({ x: 0, y: 0 });
    setScale(1);
  }, []);

  // Remix — copy prompt back into sidebar
  const handleRemix = useCallback(
    (item: CanvasItem) => {
      setPrompt(item.job.prompt);
      setMode(item.job.mode);
    },
    [setPrompt, setMode]
  );

  return (
    <div className="relative flex-1 h-full overflow-hidden bg-aura-dark">
      {/* Canvas surface */}
      <div
        ref={canvasRef}
        className={clsx(
          "absolute inset-0",
          spaceHeld ? "canvas-grab" : "cursor-default",
          isPanning && "!cursor-grabbing"
        )}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        onWheel={handleWheel}
      >
        {/* Dot grid background */}
        <div
          className="absolute inset-0 opacity-[0.04]"
          style={{
            backgroundImage: `radial-gradient(circle, rgba(255,255,255,0.5) 1px, transparent 1px)`,
            backgroundSize: `${32 * scale}px ${32 * scale}px`,
            backgroundPosition: `${pan.x % (32 * scale)}px ${pan.y % (32 * scale)}px`,
          }}
        />

        {/* Transform container */}
        <div
          className="absolute"
          style={{
            transform: `translate(${pan.x}px, ${pan.y}px) scale(${scale})`,
            transformOrigin: "0 0",
          }}
        >
          <AnimatePresence>
            {canvasItems.map((item) => (
              <CanvasCard
                key={item.id}
                item={item}
                canvasScale={scale}
                onDragEnd={updatePos}
                onRemove={removeItem}
                onRemix={handleRemix}
              />
            ))}
          </AnimatePresence>
        </div>
      </div>

      {/* Empty state */}
      {canvasItems.length === 0 && (
        <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3, duration: 0.5 }}
            className="flex flex-col items-center gap-4"
          >
            <div className="w-16 h-16 rounded-2xl bg-aura-accent/[0.06] border border-aura-accent/10 flex items-center justify-center">
              <Maximize2 className="h-7 w-7 text-aura-accent/40" />
            </div>
            <div className="text-center">
              <p className="text-sm text-aura-text-secondary font-medium">
                Your canvas is empty
              </p>
              <p className="text-xs text-aura-text-tertiary mt-1 max-w-xs">
                Write a prompt in the sidebar or press{" "}
                <kbd className="px-1.5 py-0.5 rounded bg-white/[0.04] border border-white/[0.08] text-[10px] font-mono">
                  Ctrl+K
                </kbd>{" "}
                to get started
              </p>
            </div>
          </motion.div>
        </div>
      )}

      {/* Zoom controls — bottom right */}
      <div className="absolute bottom-4 right-4 flex items-center gap-1.5">
        <motion.button
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          onClick={zoomOut}
          className="p-2 rounded-lg glass-panel hover:bg-white/[0.04] transition-colors"
          title="Zoom out"
        >
          <ZoomOut className="h-4 w-4 text-aura-text-secondary" />
        </motion.button>
        <div className="px-2.5 py-1.5 rounded-lg glass-panel text-[11px] font-mono text-aura-text-tertiary min-w-[52px] text-center">
          {Math.round(scale * 100)}%
        </div>
        <motion.button
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          onClick={zoomIn}
          className="p-2 rounded-lg glass-panel hover:bg-white/[0.04] transition-colors"
          title="Zoom in"
        >
          <ZoomIn className="h-4 w-4 text-aura-text-secondary" />
        </motion.button>
        <motion.button
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          onClick={resetView}
          className="p-2 rounded-lg glass-panel hover:bg-white/[0.04] transition-colors"
          title="Reset view"
        >
          <Move className="h-4 w-4 text-aura-text-secondary" />
        </motion.button>
      </div>
    </div>
  );
}
