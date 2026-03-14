/* AuraGen — ResultMedia
 * Unified image/video display with loading, error, and interaction states.
 *
 * IMAGE mode: click opens lightbox via onExpand.
 * VIDEO mode: click toggles play/pause, hover reveals controls overlay,
 *             dedicated expand button (top-right) opens lightbox via onExpand. */

"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Play,
  Pause,
  Maximize2,
  Volume2,
  VolumeX,
  AlertCircle,
  Image as ImageIcon,
  Film,
  Loader2,
} from "lucide-react";
import { clsx } from "clsx";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface ResultMediaProps {
  /** Resolved absolute URL for the media. */
  src: string | null;
  /** Alt text for images. */
  alt?: string;
  /** Media type. */
  mode: "image" | "video";
  /** Additional CSS classes for the container. */
  className?: string;
  /** Called when user wants to expand to lightbox.
   *  For images: on click. For videos: on the expand button. */
  onExpand?: () => void;
  /** Object-fit mode. */
  objectFit?: "cover" | "contain";
}

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export function ResultMedia({
  src,
  alt = "Generated content",
  mode,
  className,
  onExpand,
  objectFit = "cover",
}: ResultMediaProps) {
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [muted, setMuted] = useState(true);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [hovered, setHovered] = useState(false);

  const videoRef = useRef<HTMLVideoElement>(null);
  const progressRef = useRef<HTMLDivElement>(null);
  const rafRef = useRef<number | null>(null);

  /* ---------- time‑tracking via rAF ---------- */

  const trackTime = useCallback(() => {
    if (videoRef.current) {
      setCurrentTime(videoRef.current.currentTime);
    }
    rafRef.current = requestAnimationFrame(trackTime);
  }, []);

  useEffect(() => {
    if (playing) {
      rafRef.current = requestAnimationFrame(trackTime);
    } else if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    return () => {
      if (rafRef.current !== null) {
        cancelAnimationFrame(rafRef.current);
        rafRef.current = null;
      }
    };
  }, [playing, trackTime]);

  /* ---------- video interaction handlers ---------- */

  const togglePlayPause = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      const vid = videoRef.current;
      if (!vid) return;

      if (playing) {
        vid.pause();
        setPlaying(false);
      } else {
        vid.play().then(() => setPlaying(true)).catch(() => {});
      }
    },
    [playing],
  );

  const toggleMute = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      const vid = videoRef.current;
      if (!vid) return;
      vid.muted = !vid.muted;
      setMuted(vid.muted);
    },
    [],
  );

  const handleExpandClick = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      onExpand?.();
    },
    [onExpand],
  );

  const handleProgressClick = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      const bar = progressRef.current;
      const vid = videoRef.current;
      if (!bar || !vid || !duration) return;
      const rect = bar.getBoundingClientRect();
      const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
      vid.currentTime = ratio * duration;
      setCurrentTime(vid.currentTime);
    },
    [duration],
  );

  /* ---------- early‑return states ---------- */

  // No source — placeholder
  if (!src) {
    return (
      <div className={clsx("flex items-center justify-center bg-white/[0.02]", className)}>
        <div className="flex flex-col items-center gap-2 text-white/20">
          {mode === "video" ? <Film className="w-8 h-8" /> : <ImageIcon className="w-8 h-8" />}
          <span className="text-[10px]">No preview</span>
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className={clsx("flex items-center justify-center bg-white/[0.02]", className)}>
        <div className="flex flex-col items-center gap-2 text-red-400/60">
          <AlertCircle className="w-6 h-6" />
          <span className="text-[10px]">Failed to load</span>
        </div>
      </div>
    );
  }

  /* ---------- progress fraction ---------- */
  const progress = duration > 0 ? currentTime / duration : 0;

  /* ---------- render ---------- */
  return (
    <div
      className={clsx("relative overflow-hidden bg-black/20 group", className, {
        "cursor-pointer": mode === "image",
      })}
      onClick={mode === "image" ? () => onExpand?.() : undefined}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {/* Loading spinner */}
      <AnimatePresence>
        {!loaded && (
          <motion.div
            initial={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="absolute inset-0 flex items-center justify-center z-10 bg-white/[0.02]"
          >
            <Loader2 className="w-6 h-6 text-white/20 animate-spin" />
          </motion.div>
        )}
      </AnimatePresence>

      {/* ======= VIDEO MODE ======= */}
      {mode === "video" ? (
        <>
          {/* The <video> element — click toggles play/pause */}
          <video
            ref={videoRef}
            className={clsx(
              "w-full h-full cursor-pointer transition-opacity duration-300",
              objectFit === "cover" ? "object-cover" : "object-contain",
              loaded ? "opacity-100" : "opacity-0",
            )}
            crossOrigin="anonymous"
            preload="auto"
            muted={muted}
            playsInline
            loop
            onClick={togglePlayPause}
            onLoadedMetadata={() => {
              if (videoRef.current) {
                setDuration(videoRef.current.duration);
              }
            }}
            onLoadedData={() => setLoaded(true)}
            onError={(e) => {
              console.warn("[AuraGen] Video load error:", (e.target as HTMLVideoElement)?.error?.message);
              setError(true);
            }}
            onPlay={() => setPlaying(true)}
            onPause={() => setPlaying(false)}
          >
            <source src={src} type="video/mp4" />
          </video>

          {/* Center play/pause button — visible when paused, or on hover while playing */}
          <AnimatePresence>
            {loaded && (!playing || hovered) && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.15 }}
                className="absolute inset-0 flex items-center justify-center z-10 pointer-events-none"
              >
                <button
                  type="button"
                  onClick={togglePlayPause}
                  className={clsx(
                    "pointer-events-auto",
                    "w-12 h-12 rounded-full bg-black/50 backdrop-blur-sm",
                    "border border-white/20 flex items-center justify-center",
                    "hover:bg-black/70 hover:scale-110 transition-all",
                  )}
                  aria-label={playing ? "Pause" : "Play"}
                >
                  {playing ? (
                    <Pause className="w-5 h-5 text-white/90" fill="currentColor" />
                  ) : (
                    <Play className="w-5 h-5 text-white/90 ml-0.5" fill="currentColor" />
                  )}
                </button>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Bottom controls bar — shown on hover */}
          <AnimatePresence>
            {loaded && hovered && (
              <motion.div
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 6 }}
                transition={{ duration: 0.15 }}
                className={clsx(
                  "absolute bottom-0 left-0 right-0 z-20",
                  "bg-gradient-to-t from-black/70 to-transparent",
                  "px-2 pt-5 pb-2 flex flex-col gap-1",
                )}
              >
                {/* Progress bar */}
                <div
                  ref={progressRef}
                  onClick={handleProgressClick}
                  className="w-full h-1 rounded-full bg-white/20 cursor-pointer group/bar"
                >
                  <div
                    className="h-full rounded-full bg-white/70 transition-[width] duration-100"
                    style={{ width: `${progress * 100}%` }}
                  />
                </div>

                {/* Time + mute row */}
                <div className="flex items-center justify-between text-[10px] text-white/70">
                  <span>
                    {formatTime(currentTime)} / {formatTime(duration)}
                  </span>

                  <button
                    type="button"
                    onClick={toggleMute}
                    className="p-0.5 hover:text-white transition-colors"
                    aria-label={muted ? "Unmute" : "Mute"}
                  >
                    {muted ? (
                      <VolumeX className="w-3.5 h-3.5" />
                    ) : (
                      <Volume2 className="w-3.5 h-3.5" />
                    )}
                  </button>
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Top-right expand button — shown on hover */}
          <AnimatePresence>
            {loaded && hovered && (
              <motion.button
                type="button"
                initial={{ opacity: 0, scale: 0.8 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.8 }}
                transition={{ duration: 0.12 }}
                onClick={handleExpandClick}
                className={clsx(
                  "absolute top-2 right-2 z-20",
                  "w-7 h-7 rounded-md bg-black/50 backdrop-blur-sm",
                  "border border-white/20 flex items-center justify-center",
                  "hover:bg-black/70 hover:scale-110 transition-all",
                )}
                aria-label="Expand to lightbox"
              >
                <Maximize2 className="w-3.5 h-3.5 text-white/80" />
              </motion.button>
            )}
          </AnimatePresence>
        </>
      ) : (
        /* ======= IMAGE MODE ======= */
        <motion.img
          src={src}
          alt={alt}
          className={clsx(
            "w-full h-full",
            objectFit === "cover" ? "object-cover" : "object-contain",
          )}
          initial={{ opacity: 0 }}
          animate={{ opacity: loaded ? 1 : 0 }}
          transition={{ duration: 0.3 }}
          draggable={false}
          onLoad={() => setLoaded(true)}
          onError={() => setError(true)}
        />
      )}
    </div>
  );
}
