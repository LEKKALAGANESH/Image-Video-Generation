/* ─────────────────────────────────────────────
 * AuraGen — MorphingCanvas
 * Responsive CSS Grid gallery of generation
 * cards with lightbox, proper URL resolution,
 * and clear media display.
 * ───────────────────────────────────────────── */

"use client";

import { useCallback, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Download,
  Trash2,
  Repeat,
  ZoomIn,
  ZoomOut,
  Sparkles,
  Image as ImageIcon,
  Film,
  Clock,
  AlertTriangle,
} from "lucide-react";
import { clsx } from "clsx";
import { useGenerationStore } from "@/hooks/useGenerationStore";
import { NeuralPulse } from "@/components/animations/NeuralPulse";
import { ResultMedia } from "@/components/canvas/ResultMedia";
import { MediaLightbox } from "@/components/canvas/MediaLightbox";
import { resolveMediaUrl } from "@/lib/media-url";
import { promptToDisplayName, promptToFilename } from "@/lib/prompt-to-name";
import type { CanvasItem, GenerationJob } from "@/types";

/* ── Status badge colors ─────────────────────── */

const STATUS_STYLES: Record<string, string> = {
  queued: "bg-amber-500/15 text-amber-400 border-amber-500/20",
  processing: "bg-indigo-500/15 text-indigo-400 border-indigo-500/20",
  completed: "bg-emerald-500/15 text-emerald-400 border-emerald-500/20",
  failed: "bg-red-500/15 text-red-400 border-red-500/20",
  cancelled: "bg-zinc-500/15 text-zinc-400 border-zinc-500/20",
};

const MODE_STYLES: Record<string, string> = {
  image: "bg-violet-500/15 text-violet-400 border-violet-500/20",
  video: "bg-rose-500/15 text-rose-400 border-rose-500/20",
  pose: "bg-teal-500/15 text-teal-400 border-teal-500/20",
};

/* ── Format relative time ────────────────────── */

function timeAgo(dateStr: string): string {
  const date = new Date(dateStr);
  if (isNaN(date.getTime())) return "just now";
  const seconds = Math.floor((Date.now() - date.getTime()) / 1000);
  if (seconds < 0) return "just now";
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return date.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
}

/* ── Single Generation Card ──────────────────── */

function GenerationGridCard({
  item,
  onRemove,
  onRemix,
  onOpenLightbox,
}: {
  item: CanvasItem;
  onRemove: (id: string) => void;
  onRemix: (item: CanvasItem) => void;
  onOpenLightbox: (id: string) => void;
}) {
  const { job } = item;

  const isLoading = job.status === "queued" || job.status === "processing";
  const isFailed = job.status === "failed";
  const isCompleted = job.status === "completed";
  const isCancelled = job.status === "cancelled";

  const resolvedUrl = useMemo(
    () => resolveMediaUrl(job.result_url),
    [job.result_url]
  );

  const handleDownload = useCallback(() => {
    if (!resolvedUrl) return;
    const a = document.createElement("a");
    a.href = resolvedUrl;
    a.download = promptToFilename(job.prompt, job.mode, job.job_id);
    a.style.display = "none";
    document.body.appendChild(a);
    a.click();
    setTimeout(() => document.body.removeChild(a), 100);
  }, [resolvedUrl, job.job_id, job.mode]);

  const handleMediaClick = useCallback(() => {
    if (isCompleted && resolvedUrl) {
      onOpenLightbox(item.id);
    }
  }, [isCompleted, resolvedUrl, onOpenLightbox, item.id]);

  // Aspect ratio based on mode
  const aspectClass =
    job.mode === "video" ? "aspect-video" : "aspect-square";

  return (
    <motion.div
      layout
      initial={{ opacity: 0, scale: 0.92, y: 20 }}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.92, y: -10 }}
      transition={{ type: "spring", stiffness: 400, damping: 30 }}
      className="group relative"
    >
      <div
        className={clsx(
          "rounded-2xl overflow-hidden transition-shadow duration-300",
          "bg-white/[0.03] border border-white/[0.06]",
          job.mode === "video"
            ? "border-l-2 border-l-rose-500/40"
            : job.mode === "pose"
              ? "border-l-2 border-l-teal-500/40"
              : "border-l-2 border-l-violet-500/40",
          "backdrop-blur-xl shadow-lg shadow-black/20",
          isCompleted && job.mode === "video"
            ? "hover:shadow-xl hover:shadow-rose-500/10 hover:border-rose-500/15"
            : isCompleted && job.mode === "image"
              ? "hover:shadow-xl hover:shadow-violet-500/10 hover:border-violet-500/15"
              : "hover:shadow-xl hover:shadow-black/30 hover:border-white/[0.1]"
        )}
      >
        {/* ── Media Preview Area ──────────────── */}
        <div className={clsx("relative", aspectClass, "bg-black/30")}>
          {/* Loading state */}
          {isLoading && (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 z-10">
              <NeuralPulse progress={job.progress} visible size="sm" />
              <div className="flex flex-col items-center gap-1">
                <span className="text-xs text-white/50 capitalize font-medium">
                  {job.status === "queued" ? "In queue..." : "Generating..."}
                </span>
                {job.status === "processing" && (
                  <div className="w-32 h-1 rounded-full bg-white/[0.06] overflow-hidden">
                    <motion.div
                      className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-violet-500"
                      initial={{ width: "0%" }}
                      animate={{ width: `${job.progress}%` }}
                      transition={{ duration: 0.5, ease: "easeOut" }}
                    />
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Error state */}
          {isFailed && (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 px-6 z-10">
              <div className="w-12 h-12 rounded-full bg-red-500/10 border border-red-500/20 flex items-center justify-center">
                <AlertTriangle className="w-5 h-5 text-red-400" />
              </div>
              <div className="text-center">
                <p className="text-xs font-medium text-red-400">
                  Generation failed
                </p>
                {job.error && (
                  <p className="text-[10px] text-red-400/60 mt-1 line-clamp-2 max-w-[200px]">
                    {job.error}
                  </p>
                )}
              </div>
            </div>
          )}

          {/* Cancelled state */}
          {isCancelled && (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 z-10">
              <span className="text-xs text-zinc-400">Cancelled</span>
            </div>
          )}

          {/* Completed — show media */}
          {isCompleted && resolvedUrl && (
            <ResultMedia
              src={resolvedUrl}
              alt={job.prompt}
              mode={job.mode === "video" ? "video" : "image"}
              className="w-full h-full"
              onExpand={handleMediaClick}
              objectFit="cover"
            />
          )}

          {/* Mode indicator badge */}
          {isCompleted && resolvedUrl && (
            <div className="absolute bottom-2 left-2 z-10 flex items-center gap-1 px-1.5 py-0.5 rounded-md bg-black/50 backdrop-blur-sm border border-white/10">
              {job.mode === "video" ? (
                <Film className="w-3 h-3 text-rose-400" />
              ) : (
                <ImageIcon className="w-3 h-3 text-violet-400" />
              )}
              <span className="text-[9px] font-medium text-white/70 uppercase">
                {job.mode}
              </span>
            </div>
          )}

          {/* Completed but no URL */}
          {isCompleted && !resolvedUrl && (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-white/20 z-10">
              {job.mode === "video" ? (
                <Film className="w-8 h-8" />
              ) : (
                <ImageIcon className="w-8 h-8" />
              )}
              <span className="text-[10px]">Preview unavailable</span>
            </div>
          )}

          {/* ── Hover Action Bar ────────────────── */}
          <div
            className={clsx(
              "absolute top-0 inset-x-0 z-20",
              "opacity-0 group-hover:opacity-100",
              "transition-opacity duration-200"
            )}
          >
            <div className="flex items-center justify-end gap-1 p-2">
              {isCompleted && resolvedUrl && (
                <motion.button
                  whileHover={{ scale: 1.1 }}
                  whileTap={{ scale: 0.9 }}
                  onClick={handleDownload}
                  className="p-2 rounded-xl bg-black/50 backdrop-blur-sm hover:bg-black/70 border border-white/10 transition-colors"
                  title="Download"
                >
                  <Download className="h-3.5 w-3.5 text-white/80" />
                </motion.button>
              )}
              <motion.button
                whileHover={{ scale: 1.1 }}
                whileTap={{ scale: 0.9 }}
                onClick={() => onRemix(item)}
                className="p-2 rounded-xl bg-black/50 backdrop-blur-sm hover:bg-black/70 border border-white/10 transition-colors"
                title="Remix prompt"
              >
                <Repeat className="h-3.5 w-3.5 text-white/80" />
              </motion.button>
              <motion.button
                whileHover={{ scale: 1.1 }}
                whileTap={{ scale: 0.9 }}
                onClick={() => onRemove(item.id)}
                className="p-2 rounded-xl bg-black/50 backdrop-blur-sm hover:bg-red-900/60 border border-white/10 transition-colors"
                title="Remove"
              >
                <Trash2 className="h-3.5 w-3.5 text-white/80" />
              </motion.button>
            </div>
          </div>
        </div>

        {/* ── Card Footer ──────────────────────── */}
        <div className="px-3.5 py-3 space-y-2">
          {/* Generated name */}
          <div className="flex items-center gap-1.5">
            <div className={clsx(
              "w-1.5 h-1.5 rounded-full flex-shrink-0",
              job.mode === "video" ? "bg-rose-400" : job.mode === "pose" ? "bg-teal-400" : "bg-violet-400"
            )} />
            <p className="text-[13px] font-semibold text-white/85 truncate">
              {promptToDisplayName(job.prompt)}
            </p>
          </div>
          {/* Prompt text */}
          <p className="text-[11px] text-white/40 leading-relaxed line-clamp-2">
            {job.prompt}
          </p>

          {/* Meta row */}
          <div className="flex items-center justify-between gap-2">
            {/* Timestamp */}
            <div className="flex items-center gap-1 text-[10px] text-white/30">
              <Clock className="w-3 h-3" />
              <span>{timeAgo(job.created_at)}</span>
            </div>

            {/* Badges */}
            <div className="flex items-center gap-1.5">
              {/* Mode badge */}
              <span
                className={clsx(
                  "px-1.5 py-0.5 rounded text-[9px] font-semibold uppercase tracking-wider border",
                  MODE_STYLES[job.mode] ?? MODE_STYLES.image
                )}
              >
                {job.mode}
              </span>

              {/* Status badge (only when not completed — completed is obvious from image) */}
              {job.status !== "completed" && (
                <span
                  className={clsx(
                    "px-1.5 py-0.5 rounded text-[9px] font-semibold uppercase tracking-wider border",
                    STATUS_STYLES[job.status] ?? STATUS_STYLES.queued
                  )}
                >
                  {job.status}
                </span>
              )}
            </div>
          </div>
        </div>
      </div>
    </motion.div>
  );
}

/* ── Main MorphingCanvas Component ─────────────── */

export function MorphingCanvas() {
  const canvasItems = useGenerationStore((s) => s.canvasItems);
  const removeItem = useGenerationStore((s) => s.removeCanvasItem);
  const setPrompt = useGenerationStore((s) => s.setPrompt);
  const setMode = useGenerationStore((s) => s.setMode);
  const lightboxJobId = useGenerationStore((s) => s.lightboxJobId);
  const setLightboxJobId = useGenerationStore((s) => s.setLightboxJobId);

  // Completed items for lightbox navigation
  const completedItems = useMemo(
    () =>
      canvasItems.filter(
        (item) => item.job.status === "completed" && item.job.result_url
      ),
    [canvasItems]
  );

  const lightboxIndex = useMemo(
    () => completedItems.findIndex((item) => item.id === lightboxJobId),
    [completedItems, lightboxJobId]
  );

  const lightboxJob: GenerationJob | null = useMemo(() => {
    if (lightboxIndex < 0) return null;
    return completedItems[lightboxIndex].job;
  }, [completedItems, lightboxIndex]);

  // Lightbox navigation
  const hasPrev = lightboxIndex > 0;
  const hasNext = lightboxIndex >= 0 && lightboxIndex < completedItems.length - 1;

  const handlePrev = useCallback(() => {
    if (lightboxIndex > 0) {
      setLightboxJobId(completedItems[lightboxIndex - 1].id);
    }
  }, [lightboxIndex, completedItems, setLightboxJobId]);

  const handleNext = useCallback(() => {
    if (lightboxIndex >= 0 && lightboxIndex < completedItems.length - 1) {
      setLightboxJobId(completedItems[lightboxIndex + 1].id);
    }
  }, [lightboxIndex, completedItems, setLightboxJobId]);

  const handleCloseLightbox = useCallback(() => {
    setLightboxJobId(null);
  }, [setLightboxJobId]);

  const handleOpenLightbox = useCallback(
    (id: string) => {
      setLightboxJobId(id);
    },
    [setLightboxJobId]
  );

  // Remix — copy prompt + mode back into sidebar
  const handleRemix = useCallback(
    (item: CanvasItem) => {
      setPrompt(item.job.prompt);
      setMode(item.job.mode);
    },
    [setPrompt, setMode]
  );

  // Items in reverse chronological order (newest first)
  const sortedItems = useMemo(
    () =>
      [...canvasItems].sort(
        (a, b) =>
          new Date(b.job.created_at).getTime() -
          new Date(a.job.created_at).getTime()
      ),
    [canvasItems]
  );

  return (
    <div className="relative flex-1 h-full overflow-y-auto bg-aura-dark">
      {/* Subtle gradient background */}
      <div
        className="fixed inset-0 pointer-events-none opacity-50"
        style={{
          background:
            "radial-gradient(ellipse at 20% 50%, rgba(99, 102, 241, 0.04) 0%, transparent 60%), radial-gradient(ellipse at 80% 20%, rgba(139, 92, 246, 0.03) 0%, transparent 50%)",
        }}
      />

      {/* ── Content ──────────────────────────── */}
      {canvasItems.length === 0 ? (
        /* ── Empty State ──────────────────────── */
        <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2, duration: 0.6 }}
            className="flex flex-col items-center gap-5"
          >
            <div className="w-20 h-20 rounded-3xl bg-gradient-to-br from-indigo-500/10 to-violet-500/10 border border-white/[0.06] flex items-center justify-center">
              <Sparkles className="h-8 w-8 text-indigo-400/50" />
            </div>
            <div className="text-center max-w-xs">
              <p className="text-sm text-white/50 font-medium">
                Your canvas is empty
              </p>
              <p className="text-xs text-white/25 mt-2 leading-relaxed">
                Enter a prompt in the sidebar and hit generate, or press{" "}
                <kbd className="px-1.5 py-0.5 rounded bg-white/[0.05] border border-white/[0.08] text-[10px] font-mono text-white/40">
                  Ctrl+K
                </kbd>{" "}
                to use the command bar.
              </p>
            </div>
          </motion.div>
        </div>
      ) : (
        /* ── Grid Layout ─────────────────────── */
        <div className="relative z-10 p-4 md:p-6 lg:p-8">
          {/* Item count header */}
          <div className="flex items-center justify-between mb-4">
            <p className="text-xs text-white/30 font-mono">
              {canvasItems.length} generation{canvasItems.length !== 1 ? "s" : ""}
            </p>
          </div>

          {/* Responsive grid: 1→2→3→4 columns */}
          <div
            className={clsx(
              "grid gap-4 md:gap-5 lg:gap-6",
              "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4"
            )}
          >
            <AnimatePresence mode="popLayout">
              {sortedItems.map((item) => (
                <GenerationGridCard
                  key={item.id}
                  item={item}
                  onRemove={removeItem}
                  onRemix={handleRemix}
                  onOpenLightbox={handleOpenLightbox}
                />
              ))}
            </AnimatePresence>
          </div>
        </div>
      )}

      {/* ── Zoom Controls — bottom right ──────── */}
      {canvasItems.length > 0 && (
        <div className="fixed bottom-4 right-4 flex items-center gap-1.5 z-30">
          <span className="px-2.5 py-1.5 rounded-xl bg-white/[0.03] border border-white/[0.06] backdrop-blur-xl text-[10px] font-mono text-white/30">
            {canvasItems.length} items
          </span>
        </div>
      )}

      {/* ── Lightbox ─────────────────────────── */}
      <MediaLightbox
        job={lightboxJob}
        onClose={handleCloseLightbox}
        onPrev={handlePrev}
        onNext={handleNext}
        hasPrev={hasPrev}
        hasNext={hasNext}
      />
    </div>
  );
}
