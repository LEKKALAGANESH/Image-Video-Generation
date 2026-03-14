/**
 * AuraGen -- PointToEdit overlay component.
 *
 * Renders on top of a generated image when the user enters "edit mode".
 * Captures click coordinates, shows a pulsing crosshair, requests SAM2
 * segmentation, visualises the returned mask, and presents a floating
 * EditPanel with natural-language editing options.
 *
 * All UI elements follow the Liquid Glass design language with Framer
 * Motion animations.
 */

"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { MousePointerClick, Scan, X } from "lucide-react";

import { usePointToEdit } from "../../hooks/usePointToEdit";
import SegmentOverlay from "./SegmentOverlay";
import EditPanel from "../ui/EditPanel";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface PointToEditProps {
  /** Server-side path or URL of the generated image. */
  imagePath: string;
  /** Source URL used by the <img> element to display the image. */
  imageSrc: string;
  /** Natural width of the image in pixels. */
  imageWidth: number;
  /** Natural height of the image in pixels. */
  imageHeight: number;
  /** Callback fired when an edit job is successfully queued. */
  onEditQueued?: (jobId: string) => void;
  /** Additional CSS class on the root container. */
  className?: string;
}

// ---------------------------------------------------------------------------
// Crosshair sub-component (pulsing animated indicator)
// ---------------------------------------------------------------------------

interface CrosshairProps {
  x: number;
  y: number;
  isSegmenting: boolean;
}

function Crosshair({ x, y, isSegmenting }: CrosshairProps) {
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.3 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.5 }}
      transition={{ type: "spring", damping: 20, stiffness: 350 }}
      className="absolute pointer-events-none z-20"
      style={{
        left: x,
        top: y,
        transform: "translate(-50%, -50%)",
      }}
    >
      {/* Outer pulsing ring */}
      <motion.div
        animate={{
          scale: [1, 1.6, 1],
          opacity: [0.6, 0, 0.6],
        }}
        transition={{
          duration: 1.8,
          repeat: Infinity,
          ease: "easeInOut",
        }}
        className="absolute -inset-4 rounded-full border-2"
        style={{ borderColor: "rgba(139, 92, 246, 0.5)" }}
      />

      {/* Inner pulsing ring */}
      <motion.div
        animate={{
          scale: [1, 1.3, 1],
          opacity: [0.8, 0.2, 0.8],
        }}
        transition={{
          duration: 1.2,
          repeat: Infinity,
          ease: "easeInOut",
          delay: 0.3,
        }}
        className="absolute -inset-2 rounded-full border"
        style={{ borderColor: "rgba(139, 92, 246, 0.7)" }}
      />

      {/* Centre dot */}
      <motion.div
        animate={
          isSegmenting
            ? { scale: [1, 1.3, 1], opacity: [1, 0.5, 1] }
            : { scale: 1, opacity: 1 }
        }
        transition={
          isSegmenting
            ? { duration: 0.6, repeat: Infinity, ease: "easeInOut" }
            : {}
        }
        className="h-2.5 w-2.5 rounded-full"
        style={{
          background:
            "radial-gradient(circle, rgba(167,139,250,1) 0%, rgba(139,92,246,0.8) 100%)",
          boxShadow: "0 0 12px 4px rgba(139,92,246,0.4)",
        }}
      />

      {/* Crosshair lines */}
      {[0, 90, 180, 270].map((deg) => (
        <motion.div
          key={deg}
          initial={{ scaleX: 0 }}
          animate={{ scaleX: 1 }}
          transition={{ delay: 0.1, duration: 0.25 }}
          className="absolute"
          style={{
            width: 12,
            height: 1,
            background: "rgba(139,92,246,0.6)",
            transformOrigin: "left center",
            left: "50%",
            top: "50%",
            transform: `rotate(${deg}deg) translateX(6px) translateY(-0.5px)`,
          }}
        />
      ))}
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Edit-mode banner
// ---------------------------------------------------------------------------

function EditModeBanner({ onExit }: { onExit: () => void }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: -12 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -12 }}
      transition={{ duration: 0.25 }}
      className="absolute top-3 left-1/2 -translate-x-1/2 z-30 flex items-center gap-2
                 rounded-xl px-4 py-2 border border-white/10 backdrop-blur-xl"
      style={{
        background:
          "linear-gradient(135deg, rgba(15,15,30,0.85) 0%, rgba(10,10,25,0.9) 100%)",
      }}
    >
      <Scan className="h-3.5 w-3.5 text-violet-400" />
      <span className="text-xs text-white/70 select-none">
        Click on the image to select a region
      </span>
      <span className="text-[10px] text-white/30 ml-1 select-none">(Esc to exit)</span>
      <motion.button
        onClick={onExit}
        whileHover={{ scale: 1.1 }}
        whileTap={{ scale: 0.9 }}
        className="ml-1 flex items-center justify-center h-5 w-5 rounded-md
                   bg-white/5 hover:bg-white/10 transition-colors"
        aria-label="Exit edit mode"
      >
        <X className="h-3 w-3 text-white/50" />
      </motion.button>
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function PointToEdit({
  imagePath,
  imageSrc,
  imageWidth,
  imageHeight,
  onEditQueued,
  className = "",
}: PointToEditProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [displaySize, setDisplaySize] = useState({ w: imageWidth, h: imageHeight });

  const {
    editMode,
    selectedPoint,
    currentMask,
    isSegmenting,
    isApplying,
    suggestions,
    error,
    enterEditMode,
    exitEditMode,
    selectPoint,
    applyEdit,
    clearSelection,
  } = usePointToEdit(imagePath);

  // ------- Track rendered size of the image container -------

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setDisplaySize({
          w: entry.contentRect.width,
          h: entry.contentRect.height,
        });
      }
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // ------- Click handler: capture normalised coords -------

  const handleImageClick = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      if (!editMode) return;
      const rect = e.currentTarget.getBoundingClientRect();
      const normX = (e.clientX - rect.left) / rect.width;
      const normY = (e.clientY - rect.top) / rect.height;
      selectPoint(
        Math.max(0, Math.min(1, normX)),
        Math.max(0, Math.min(1, normY)),
      );
    },
    [editMode, selectPoint],
  );

  // ------- Edit panel position (near the selected point) -------

  const panelStyle = useMemo<React.CSSProperties>(() => {
    if (!selectedPoint) return { display: "none" };
    const px = selectedPoint.x * displaySize.w;
    const py = selectedPoint.y * displaySize.h;
    // Place the panel to the right of the click, or left if too close to edge.
    const panelWidth = 320;
    const rightSpace = displaySize.w - px;
    const placeRight = rightSpace > panelWidth + 24;

    return {
      position: "absolute" as const,
      top: Math.max(8, Math.min(py - 60, displaySize.h - 300)),
      ...(placeRight
        ? { left: px + 20 }
        : { right: displaySize.w - px + 20 }),
      zIndex: 40,
    };
  }, [selectedPoint, displaySize]);

  // ------- Apply edit wrapper -------

  const handleApplyEdit = useCallback(
    async (prompt: string, editType: "replace" | "remove" | "style" | "describe") => {
      const jobId = await applyEdit(prompt, editType);
      if (jobId && onEditQueued) {
        onEditQueued(jobId);
      }
      return jobId;
    },
    [applyEdit, onEditQueued],
  );

  // ------- Crosshair pixel position -------

  const crosshairPos = useMemo(() => {
    if (!selectedPoint) return null;
    return {
      x: selectedPoint.x * displaySize.w,
      y: selectedPoint.y * displaySize.h,
    };
  }, [selectedPoint, displaySize]);

  return (
    <div
      className={`relative select-none ${className}`}
      style={{ width: displaySize.w, height: displaySize.h }}
    >
      {/* The generated image */}
      <div
        ref={containerRef}
        onClick={handleImageClick}
        className={`relative overflow-hidden rounded-2xl ${
          editMode ? "cursor-crosshair" : "cursor-default"
        }`}
        role={editMode ? "button" : undefined}
        aria-label={editMode ? "Click to select a region for editing" : undefined}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={imageSrc}
          alt="Generated image"
          width={imageWidth}
          height={imageHeight}
          className="block w-full h-auto"
          draggable={false}
        />

        {/* Dimming overlay when in edit mode */}
        <AnimatePresence>
          {editMode && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.3 }}
              className="absolute inset-0 bg-black/20 pointer-events-none"
            />
          )}
        </AnimatePresence>

        {/* Segment mask overlay */}
        <AnimatePresence>
          {currentMask && (
            <SegmentOverlay
              maskUrl={currentMask.mask_url}
              width={displaySize.w}
              height={displaySize.h}
              segmentIndex={0}
              opacity={0.35}
              hoverOpacity={0.5}
            />
          )}
        </AnimatePresence>

        {/* Pulsing crosshair at click point */}
        <AnimatePresence>
          {crosshairPos && editMode && (
            <Crosshair
              x={crosshairPos.x}
              y={crosshairPos.y}
              isSegmenting={isSegmenting}
            />
          )}
        </AnimatePresence>
      </div>

      {/* Edit-mode banner */}
      <AnimatePresence>
        {editMode && <EditModeBanner onExit={exitEditMode} />}
      </AnimatePresence>

      {/* Error toast */}
      <AnimatePresence>
        {error && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 8 }}
            className="absolute bottom-3 left-1/2 -translate-x-1/2 z-30 rounded-xl
                       px-4 py-2 border border-red-500/20 backdrop-blur-xl
                       text-xs text-red-300/90"
            style={{ background: "rgba(30,10,10,0.85)" }}
          >
            {error}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Floating edit panel */}
      <EditPanel
        open={!!currentMask && editMode}
        onDismiss={clearSelection}
        onApplyEdit={handleApplyEdit}
        suggestions={suggestions}
        confidence={currentMask?.confidence}
        isApplying={isApplying}
        segmentLabel={currentMask?.segment_label}
        anchorStyle={panelStyle}
      />

      {/* Edit-mode toggle button (shown when NOT in edit mode) */}
      <AnimatePresence>
        {!editMode && (
          <motion.button
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.8 }}
            whileHover={{ scale: 1.06 }}
            whileTap={{ scale: 0.94 }}
            onClick={enterEditMode}
            className="absolute bottom-4 right-4 z-20 flex items-center gap-2
                       rounded-xl px-4 py-2.5 border border-white/10
                       backdrop-blur-xl transition-colors"
            style={{
              background:
                "linear-gradient(135deg, rgba(139,92,246,0.2) 0%, rgba(59,130,246,0.15) 100%)",
            }}
            aria-label="Enter edit mode"
          >
            <MousePointerClick className="h-4 w-4 text-violet-300" />
            <span className="text-xs font-medium text-white/80">Edit</span>
          </motion.button>
        )}
      </AnimatePresence>

      {/* Segmenting loader */}
      <AnimatePresence>
        {isSegmenting && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="absolute bottom-3 left-1/2 -translate-x-1/2 z-30 flex items-center gap-2
                       rounded-xl px-4 py-2 border border-white/10 backdrop-blur-xl"
            style={{ background: "rgba(15,15,30,0.85)" }}
          >
            <motion.div
              animate={{ rotate: 360 }}
              transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
              className="h-3.5 w-3.5 rounded-full border-2 border-violet-400/30
                         border-t-violet-400"
            />
            <span className="text-xs text-white/60">Segmenting...</span>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
