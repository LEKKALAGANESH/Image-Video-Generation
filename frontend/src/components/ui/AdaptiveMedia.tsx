/* ─────────────────────────────────────────────
 * AuraGen — AdaptiveMedia
 * Network-aware media renderer that toggles
 * between <img> / <video>, high-res / low-res
 * based on the current NetworkTier.
 * ───────────────────────────────────────────── */

"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import { motion } from "framer-motion";
import { clsx } from "clsx";
import { Film } from "lucide-react";
import type { NetworkTier } from "@/types";

interface AdaptiveMediaProps {
  /** Full-resolution URL (image or video). */
  src: string;
  /** Compressed preview URL. */
  previewSrc?: string;
  /** Thumbnail URL (tiny placeholder). */
  thumbSrc?: string;
  /** MIME type of the full-res asset. */
  mediaType?: string;
  /** Current network quality tier. */
  tier: NetworkTier;
  /** Alt text for accessibility. */
  alt: string;
  /** CSS class for the container. */
  className?: string;
  /** Full-res file size in bytes (for display). */
  fullSizeBytes?: number;
}

/**
 * Determines which source URL to load based on network tier:
 * - **high**: Full-resolution asset, autoplay video
 * - **medium**: Preview image; video shows poster only (click-to-play)
 * - **low**: Thumbnail only; tap to upgrade to preview
 */
export function AdaptiveMedia({
  src,
  previewSrc,
  thumbSrc,
  mediaType,
  tier,
  alt,
  className,
  fullSizeBytes,
}: AdaptiveMediaProps) {
  const isVideo =
    mediaType?.startsWith("video/") || src.endsWith(".mp4") || src.endsWith(".webm");
  const [upgraded, setUpgraded] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);

  // Reset upgrade state when tier changes or src changes
  useEffect(() => {
    setUpgraded(false);
    setLoaded(false);
  }, [src, tier]);

  // Resolve the display source based on tier + upgrade state
  const resolvedSrc = (() => {
    if (upgraded) return src;
    switch (tier) {
      case "high":
        return src;
      case "medium":
        return previewSrc ?? src;
      case "low":
        return thumbSrc ?? previewSrc ?? src;
    }
  })();

  const handleUpgrade = useCallback(() => {
    setUpgraded(true);
  }, []);

  return (
    <div className={clsx("relative overflow-hidden", className)}>
      {/* Main media element */}
      {isVideo && tier === "high" ? (
        <motion.video
          ref={videoRef}
          src={resolvedSrc}
          className="w-full h-full object-cover"
          crossOrigin="anonymous"
          preload="auto"
          autoPlay
          loop
          muted
          playsInline
          initial={{ opacity: 0 }}
          animate={{ opacity: loaded ? 1 : 0 }}
          onLoadedData={() => setLoaded(true)}
        />
      ) : isVideo && tier === "medium" && !upgraded ? (
        /* Video on medium tier: show poster frame as image, click to play */
        <div className="relative w-full h-full">
          <motion.img
            src={previewSrc ?? thumbSrc ?? src}
            alt={alt}
            className="w-full h-full object-cover"
            initial={{ opacity: 0, scale: 1.05 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.5 }}
          />
          <button
            onClick={handleUpgrade}
            className="absolute inset-0 flex items-center justify-center bg-black/30 backdrop-blur-[2px] group/play hover:bg-black/40 transition-colors"
            aria-label="Play video"
          >
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-white/10 border border-white/20 text-white/80 group-hover/play:text-white group-hover/play:bg-white/15 transition-all">
              <Film className="w-4 h-4" />
              <span className="text-xs font-medium">Play Video</span>
            </div>
          </button>
        </div>
      ) : isVideo && upgraded ? (
        <motion.video
          ref={videoRef}
          src={src}
          className="w-full h-full object-cover"
          crossOrigin="anonymous"
          preload="auto"
          autoPlay
          loop
          muted
          playsInline
          initial={{ opacity: 0 }}
          animate={{ opacity: loaded ? 1 : 0 }}
          onLoadedData={() => setLoaded(true)}
        />
      ) : (
        <motion.img
          src={resolvedSrc}
          alt={alt}
          className="w-full h-full object-cover"
          initial={{ opacity: 0, scale: 1.05 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.5, ease: "easeOut" }}
          loading={tier === "low" ? "lazy" : "eager"}
        />
      )}

    </div>
  );
}
