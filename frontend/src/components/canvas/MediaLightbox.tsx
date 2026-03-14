/* AuraGen — MediaLightbox
 * Fullscreen viewer for generated images and videos. */

"use client";

import { useCallback, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X, Download, ChevronLeft, ChevronRight } from "lucide-react";
import { resolveMediaUrl, getMediaType } from "@/lib/media-url";
import { promptToDisplayName, promptToFilename } from "@/lib/prompt-to-name";
import type { GenerationJob } from "@/types";

interface MediaLightboxProps {
  /** The job to display, or null to hide. */
  job: GenerationJob | null;
  /** Local object URL from auto-download (preferred over result_url). */
  localUrl?: string | null;
  /** Close handler. */
  onClose: () => void;
  /** Navigate to previous item. */
  onPrev?: () => void;
  /** Navigate to next item. */
  onNext?: () => void;
  /** Whether prev/next exist. */
  hasPrev?: boolean;
  hasNext?: boolean;
}

export function MediaLightbox({
  job,
  localUrl,
  onClose,
  onPrev,
  onNext,
  hasPrev = false,
  hasNext = false,
}: MediaLightboxProps) {
  const overlayRef = useRef<HTMLDivElement>(null);

  // Determine media source — prefer localUrl, fallback to resolved backend URL
  const mediaSrc = localUrl || resolveMediaUrl(job?.result_url);
  const mediaType = job?.mode === "video" ? "video" : getMediaType(job?.result_url);

  // Keyboard handling
  useEffect(() => {
    if (!job) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") { onClose(); e.preventDefault(); }
      if (e.key === "ArrowLeft" && hasPrev) { onPrev?.(); e.preventDefault(); }
      if (e.key === "ArrowRight" && hasNext) { onNext?.(); e.preventDefault(); }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [job, onClose, onPrev, onNext, hasPrev, hasNext]);

  // Lock body scroll when open
  useEffect(() => {
    if (!job) return;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = ""; };
  }, [job]);

  const handleDownload = useCallback(() => {
    if (!mediaSrc || !job) return;
    const a = document.createElement("a");
    a.href = mediaSrc;
    a.download = promptToFilename(job.prompt, job.mode, job.job_id);
    a.style.display = "none";
    document.body.appendChild(a);
    a.click();
    setTimeout(() => document.body.removeChild(a), 100);
  }, [mediaSrc, job]);

  const handleOverlayClick = useCallback((e: React.MouseEvent) => {
    if (e.target === overlayRef.current) onClose();
  }, [onClose]);

  return (
    <AnimatePresence>
      {job && mediaSrc && (
        <motion.div
          ref={overlayRef}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
          className="fixed inset-0 z-[100] flex items-center justify-center bg-black/80 backdrop-blur-md"
          onClick={handleOverlayClick}
          role="dialog"
          aria-label="Media viewer"
          aria-modal="true"
        >
          {/* Close button */}
          <button
            onClick={onClose}
            className="absolute top-4 right-4 z-10 p-2 rounded-xl bg-white/10 hover:bg-white/20 border border-white/10 text-white/70 hover:text-white transition-colors"
            aria-label="Close viewer"
          >
            <X className="w-5 h-5" />
          </button>

          {/* Download button */}
          <button
            onClick={handleDownload}
            className="absolute top-4 right-16 z-10 p-2 rounded-xl bg-white/10 hover:bg-white/20 border border-white/10 text-white/70 hover:text-white transition-colors"
            aria-label="Download"
          >
            <Download className="w-5 h-5" />
          </button>

          {/* Previous arrow */}
          {hasPrev && (
            <button
              onClick={onPrev}
              className="absolute left-4 top-1/2 -translate-y-1/2 z-10 p-2 rounded-xl bg-white/10 hover:bg-white/20 border border-white/10 text-white/70 hover:text-white transition-colors"
              aria-label="Previous"
            >
              <ChevronLeft className="w-6 h-6" />
            </button>
          )}

          {/* Next arrow */}
          {hasNext && (
            <button
              onClick={onNext}
              className="absolute right-4 top-1/2 -translate-y-1/2 z-10 p-2 rounded-xl bg-white/10 hover:bg-white/20 border border-white/10 text-white/70 hover:text-white transition-colors"
              aria-label="Next"
            >
              <ChevronRight className="w-6 h-6" />
            </button>
          )}

          {/* Media content */}
          <motion.div
            initial={{ scale: 0.9, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.9, opacity: 0 }}
            transition={{ type: "spring", stiffness: 300, damping: 30 }}
            className="relative max-w-[90vw] max-h-[85vh] flex flex-col items-center"
            onClick={(e) => e.stopPropagation()}
          >
            {mediaType === "video" ? (
              <video
                src={mediaSrc}
                className="max-w-[90vw] max-h-[75vh] rounded-xl shadow-2xl"
                crossOrigin="anonymous"
                preload="auto"
                controls
                autoPlay
                loop
                playsInline
                style={{ objectFit: "contain" }}
                onError={(e) => console.warn("[AuraGen] Lightbox video error:", (e.target as HTMLVideoElement)?.error?.message)}
              />
            ) : (
              <img
                src={mediaSrc}
                alt={job.prompt}
                className="max-w-[90vw] max-h-[75vh] rounded-xl shadow-2xl object-contain"
                draggable={false}
              />
            )}

            {/* Prompt text */}
            <div className="mt-4 px-4 max-w-lg text-center">
              <p className="text-base font-semibold text-white/90 mb-1">
                {promptToDisplayName(job.prompt)}
              </p>
              <p className="text-xs text-white/50 leading-relaxed line-clamp-3">
                {job.prompt}
              </p>
              <p className="text-[10px] text-white/30 mt-1 font-mono">
                {job.mode} &middot; {(() => {
                  const d = new Date(job.created_at);
                  return isNaN(d.getTime()) ? "Just now" : d.toLocaleString();
                })()}
              </p>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
