/* ---------------------------------------------
 * AuraGen -- GalleryPanel
 * Persistent gallery sidebar that displays
 * previously generated images from IndexedDB/OPFS.
 * Survives page refreshes.
 * --------------------------------------------- */

"use client";

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Clock, Image as ImageIcon, Trash2, FolderOpen, Loader2, Play } from "lucide-react";
import { clsx } from "clsx";
import { useGallery, type GalleryItem } from "@/hooks/useGallery";
import { deleteAsset, purgeOldAssets } from "@/lib/download-manager";
import { resolveMediaUrl } from "@/lib/media-url";
import { useDismiss } from "@/hooks/useDismiss";
import { promptToDisplayName } from "@/lib/prompt-to-name";

interface GalleryPanelProps {
  open: boolean;
  onClose: () => void;
}

export function GalleryPanel({ open, onClose }: GalleryPanelProps) {
  const { items, loading, refresh } = useGallery();
  const [purging, setPurging] = useState(false);

  const dismissRef = useDismiss({
    open,
    onClose,
    closeOnEscape: true,
    closeOnClickOutside: true,
  });

  // Run storage guard on mount — purge assets older than 24h
  useEffect(() => {
    purgeOldAssets().then((count) => {
      if (count > 0) refresh();
    }).catch(() => {});
  }, [refresh]);

  const handleDelete = async (item: GalleryItem) => {
    try {
      await deleteAsset(item.id);
      refresh();
    } catch (err) {
      console.warn("[Gallery] Delete failed:", err);
    }
  };

  const handlePurge = async () => {
    setPurging(true);
    try {
      await purgeOldAssets(0); // purge all
      refresh();
    } catch (err) {
      console.warn("[Gallery] Purge failed:", err);
    } finally {
      setPurging(false);
    }
  };

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          ref={dismissRef}
          initial={{ x: "100%", opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          exit={{ x: "100%", opacity: 0 }}
          transition={{ type: "spring", stiffness: 300, damping: 30 }}
          className="fixed right-0 top-0 md:top-14 bottom-0 w-full md:w-80 lg:w-96 z-40 flex flex-col border-l border-white/[0.06] backdrop-blur-[20px] [-webkit-backdrop-filter:blur(20px)]"
          style={{ background: "rgba(10, 10, 18, 0.95)" }}
          role="dialog"
          aria-label="Gallery"
        >
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-white/[0.06]">
            <div className="flex items-center gap-2">
              <FolderOpen className="w-4 h-4 text-aura-accent/70" />
              <span className="text-xs font-semibold text-white/80">Gallery</span>
              <span className="text-[10px] text-white/30 font-mono">
                {items.length}
              </span>
            </div>
            <div className="flex items-center gap-1.5">
              {items.length > 0 && (
                <button
                  onClick={handlePurge}
                  disabled={purging}
                  className="px-2 py-1 rounded-md text-[10px] text-white/40 hover:text-red-400 hover:bg-red-500/10 transition-colors disabled:opacity-50"
                  title="Clear all"
                >
                  {purging ? <Loader2 className="w-3 h-3 animate-spin" /> : "Clear All"}
                </button>
              )}
              <button
                onClick={onClose}
                aria-label="Close gallery"
                className="p-1.5 rounded-lg text-white/40 hover:text-white/80 hover:bg-white/[0.06] transition-colors"
              >
                <span className="text-xs">&times;</span>
              </button>
            </div>
          </div>

          {/* Content */}
          <div className="flex-1 overflow-y-auto p-3 space-y-2 aura-scroll">
            {loading ? (
              <div className="flex items-center justify-center h-32">
                <Loader2 className="w-5 h-5 text-white/20 animate-spin" />
              </div>
            ) : items.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-32 gap-2">
                <ImageIcon className="w-8 h-8 text-white/10" />
                <p className="text-[11px] text-white/30">No saved generations yet</p>
              </div>
            ) : (
              items.map((item) => (
                <GalleryCard
                  key={item.id}
                  item={item}
                  onDelete={() => handleDelete(item)}
                />
              ))
            )}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

/* ── Gallery Card ──────────────────────────── */

function GalleryCard({
  item,
  onDelete,
}: {
  item: GalleryItem;
  onDelete: () => void;
}) {
  const dateStr = new Date(item.savedAt).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="group relative rounded-xl overflow-hidden border border-white/[0.06] bg-white/[0.02]"
    >
      {/* Thumbnail */}
      <div className={clsx(
          "overflow-hidden relative",
          item.mimeType.startsWith("video/") ? "aspect-video" : "aspect-square",
          "bg-white/[0.01]"
        )}>
        {item.localUrl ? (
          item.mimeType.startsWith("video/") ? (
            <>
              <video
                src={item.localUrl}
                className="w-full h-full object-cover"
                crossOrigin="anonymous"
                muted
                playsInline
                loop
                preload="auto"
                onMouseEnter={(e) => (e.target as HTMLVideoElement).play().catch(() => {})}
                onMouseLeave={(e) => { const v = e.target as HTMLVideoElement; v.pause(); v.currentTime = 0; }}
              />
              <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                <div className="w-8 h-8 rounded-full bg-black/40 backdrop-blur-sm flex items-center justify-center">
                  <Play className="w-3.5 h-3.5 text-white/80 ml-0.5" fill="currentColor" />
                </div>
              </div>
            </>
          ) : (
            <img
              src={item.localUrl}
              alt={item.prompt}
              className="w-full h-full object-cover"
              loading="lazy"
            />
          )
        ) : (
          <div className="w-full h-full flex items-center justify-center">
            <ImageIcon className="w-6 h-6 text-white/10" />
          </div>
        )}
      </div>

      {/* Hover actions */}
      <div className="absolute top-1.5 right-1.5 opacity-0 group-hover:opacity-100 transition-opacity">
        <button
          onClick={onDelete}
          className="p-1.5 rounded-lg bg-black/50 backdrop-blur-sm border border-white/10 text-white/60 hover:text-red-400 transition-colors"
          title="Delete"
          aria-label="Delete item"
        >
          <Trash2 className="w-3 h-3" />
        </button>
      </div>

      {/* Footer */}
      <div className="px-2.5 py-2 space-y-1">
        <p className="text-[11px] font-medium text-white/75 truncate">
          {promptToDisplayName(item.prompt)}
        </p>
        <p className="text-[9px] text-white/35 line-clamp-1 leading-relaxed">
          {item.prompt}
        </p>
        <div className="flex items-center justify-between">
          <span className="flex items-center gap-1 text-[9px] text-white/30">
            <Clock className="w-2.5 h-2.5" />
            {dateStr}
          </span>
          <span className="text-[9px] text-white/20 font-mono">
            {item.size > 1024 * 1024
              ? `${(item.size / (1024 * 1024)).toFixed(1)} MB`
              : `${Math.round(item.size / 1024)} KB`}
          </span>
        </div>
      </div>
    </motion.div>
  );
}
