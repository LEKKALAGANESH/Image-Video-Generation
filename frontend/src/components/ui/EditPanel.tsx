/**
 * AuraGen -- EditPanel (floating glass panel for Point-to-Edit actions).
 *
 * Appears near the selected region after SAM segmentation. Provides:
 *   - "Replace with..." text input
 *   - "Remove" one-click action
 *   - "Change style" dropdown
 *   - "Describe change" natural-language input (SemanticInput)
 *   - AI-generated smart suggestions
 *   - Dismiss via button or Escape key
 */

"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  Eraser,
  Palette,
  PenLine,
  Sparkles,
  X,
  Wand2,
  Film,
  Sun,
  ChevronDown,
} from "lucide-react";

import SemanticInput from "./SemanticInput";
import type { EditSuggestion, EditType } from "../../hooks/usePointToEdit";

// ---------------------------------------------------------------------------
// Icon resolver (maps backend icon names to Lucide components)
// ---------------------------------------------------------------------------

const ICON_MAP: Record<string, React.ComponentType<{ className?: string }>> = {
  eraser: Eraser,
  palette: Palette,
  sparkles: Sparkles,
  film: Film,
  sun: Sun,
  wand: Wand2,
  pen: PenLine,
};

function resolveIcon(name: string): React.ComponentType<{ className?: string }> {
  return ICON_MAP[name] ?? Sparkles;
}

// ---------------------------------------------------------------------------
// Style presets
// ---------------------------------------------------------------------------

const STYLE_PRESETS = [
  "Cinematic",
  "Watercolour",
  "Oil painting",
  "Pixel art",
  "Cyberpunk neon",
  "Studio Ghibli",
  "Photorealistic",
  "Low-poly 3D",
] as const;

// ---------------------------------------------------------------------------
// Slide-in animation variants
// ---------------------------------------------------------------------------

const panelVariants = {
  hidden: {
    opacity: 0,
    x: 24,
    scale: 0.96,
    filter: "blur(8px)",
  },
  visible: {
    opacity: 1,
    x: 0,
    scale: 1,
    filter: "blur(0px)",
    transition: { type: "spring", damping: 26, stiffness: 320 },
  },
  exit: {
    opacity: 0,
    x: 16,
    scale: 0.97,
    filter: "blur(6px)",
    transition: { duration: 0.2, ease: "easeIn" },
  },
};

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface EditPanelProps {
  /** Whether the panel is visible. */
  open: boolean;
  /** Callback to dismiss the panel. */
  onDismiss: () => void;
  /** Apply an edit. Returns the job_id or null on error. */
  onApplyEdit: (prompt: string, editType: EditType) => Promise<string | null>;
  /** AI suggestions from the backend. */
  suggestions?: EditSuggestion[];
  /** Confidence score of the segmentation. */
  confidence?: number;
  /** Whether an edit is currently being applied. */
  isApplying?: boolean;
  /** Segment label (if detected). */
  segmentLabel?: string | null;
  /** Optional extra class. */
  className?: string;
  /** Anchor position hint (for positioning near the selection). */
  anchorStyle?: React.CSSProperties;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function EditPanel({
  open,
  onDismiss,
  onApplyEdit,
  suggestions = [],
  confidence,
  isApplying = false,
  segmentLabel,
  className = "",
  anchorStyle,
}: EditPanelProps) {
  const [replaceText, setReplaceText] = useState("");
  const [showStyleDropdown, setShowStyleDropdown] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);

  // ── Keyboard: Escape dismisses ─────────────────────────────────────────

  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onDismiss();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onDismiss]);

  // Close style dropdown on outside click.
  useEffect(() => {
    if (!showStyleDropdown) return;
    const handler = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        setShowStyleDropdown(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [showStyleDropdown]);

  // ── Action handlers ────────────────────────────────────────────────────

  const handleReplace = useCallback(() => {
    const trimmed = replaceText.trim();
    if (!trimmed) return;
    onApplyEdit(`Replace with: ${trimmed}`, "replace");
    setReplaceText("");
  }, [replaceText, onApplyEdit]);

  const handleRemove = useCallback(() => {
    onApplyEdit("Remove this object and fill with surrounding background", "remove");
  }, [onApplyEdit]);

  const handleStyle = useCallback(
    (style: string) => {
      onApplyEdit(`Apply ${style} style to this region`, "style");
      setShowStyleDropdown(false);
    },
    [onApplyEdit],
  );

  const handleDescribe = useCallback(
    (prompt: string) => {
      onApplyEdit(prompt, "describe");
    },
    [onApplyEdit],
  );

  const handleSuggestion = useCallback(
    (s: EditSuggestion) => {
      onApplyEdit(s.prompt, s.edit_type);
    },
    [onApplyEdit],
  );

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          ref={panelRef}
          variants={panelVariants}
          initial="hidden"
          animate="visible"
          exit="exit"
          style={anchorStyle}
          className={`z-50 w-80 rounded-2xl border border-white/10 shadow-2xl
                      backdrop-blur-2xl overflow-hidden ${className}`}
          role="dialog"
          aria-label="Edit panel"
        >
          {/* Background fill */}
          <div
            className="absolute inset-0 -z-10"
            style={{
              background:
                "linear-gradient(160deg, rgba(15,15,30,0.88) 0%, rgba(10,10,25,0.94) 100%)",
            }}
          />

          {/* ── Header ───────────────────────────────────────────── */}
          <div className="flex items-center justify-between px-4 pt-3 pb-2">
            <div className="flex items-center gap-2">
              <Wand2 className="h-4 w-4 text-violet-400" />
              <span className="text-xs font-medium text-white/80 tracking-wide uppercase">
                Edit Region
              </span>
              {segmentLabel && (
                <span className="text-[10px] text-violet-300/60 ml-1">
                  ({segmentLabel})
                </span>
              )}
            </div>

            <div className="flex items-center gap-2">
              {confidence !== undefined && (
                <span className="text-[10px] text-white/30">
                  {(confidence * 100).toFixed(0)}% match
                </span>
              )}
              <motion.button
                onClick={onDismiss}
                whileHover={{ scale: 1.15 }}
                whileTap={{ scale: 0.9 }}
                className="flex items-center justify-center h-6 w-6 rounded-lg
                           bg-white/5 hover:bg-white/10 transition-colors"
                aria-label="Dismiss edit panel"
              >
                <X className="h-3.5 w-3.5 text-white/50" />
              </motion.button>
            </div>
          </div>

          <div className="h-px bg-white/5" />

          {/* ── Action buttons ───────────────────────────────────── */}
          <div className="px-4 pt-3 space-y-2">
            {/* Replace with... */}
            <div className="flex items-center gap-2">
              <div
                className="flex-1 flex items-center gap-2 rounded-xl px-3 py-2
                            border border-white/5"
                style={{ background: "rgba(255,255,255,0.04)" }}
              >
                <PenLine className="h-3.5 w-3.5 text-blue-400/70 shrink-0" />
                <input
                  type="text"
                  placeholder="Replace with..."
                  value={replaceText}
                  onChange={(e) => setReplaceText(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") handleReplace();
                  }}
                  disabled={isApplying}
                  className="flex-1 bg-transparent text-xs text-white/80
                             placeholder-white/25 outline-none"
                />
              </div>
            </div>

            {/* Quick-action row */}
            <div className="flex gap-2">
              {/* Remove button */}
              <motion.button
                onClick={handleRemove}
                disabled={isApplying}
                whileHover={{ scale: 1.04 }}
                whileTap={{ scale: 0.96 }}
                className="flex-1 flex items-center justify-center gap-1.5 rounded-xl
                           px-3 py-2 text-xs font-medium border border-white/5
                           text-red-300/80 hover:text-red-200
                           disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                style={{ background: "rgba(239,68,68,0.08)" }}
              >
                <Eraser className="h-3.5 w-3.5" />
                Remove
              </motion.button>

              {/* Change style dropdown */}
              <div className="relative flex-1">
                <motion.button
                  onClick={() => setShowStyleDropdown(!showStyleDropdown)}
                  disabled={isApplying}
                  whileHover={{ scale: 1.04 }}
                  whileTap={{ scale: 0.96 }}
                  className="w-full flex items-center justify-center gap-1.5 rounded-xl
                             px-3 py-2 text-xs font-medium border border-white/5
                             text-violet-300/80 hover:text-violet-200
                             disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                  style={{ background: "rgba(139,92,246,0.08)" }}
                >
                  <Palette className="h-3.5 w-3.5" />
                  Style
                  <ChevronDown className="h-3 w-3" />
                </motion.button>

                {/* Dropdown */}
                <AnimatePresence>
                  {showStyleDropdown && (
                    <motion.div
                      initial={{ opacity: 0, y: -4, scale: 0.96 }}
                      animate={{ opacity: 1, y: 0, scale: 1 }}
                      exit={{ opacity: 0, y: -4, scale: 0.96 }}
                      transition={{ duration: 0.15 }}
                      className="absolute top-full left-0 right-0 mt-1 z-10 rounded-xl
                                 border border-white/10 backdrop-blur-xl overflow-hidden"
                      style={{
                        background: "rgba(15,15,30,0.95)",
                      }}
                    >
                      {STYLE_PRESETS.map((style) => (
                        <button
                          key={style}
                          onClick={() => handleStyle(style)}
                          className="w-full text-left px-3 py-1.5 text-xs text-white/60
                                     hover:bg-white/5 hover:text-white/90 transition-colors"
                        >
                          {style}
                        </button>
                      ))}
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            </div>
          </div>

          {/* ── Natural language input ────────────────────────────── */}
          <div className="px-4 pt-3">
            <SemanticInput
              onSubmit={handleDescribe}
              isProcessing={isApplying}
              disabled={isApplying}
            />
          </div>

          {/* ── Smart suggestions ─────────────────────────────────── */}
          {suggestions.length > 0 && (
            <div className="px-4 pt-3 pb-1">
              <p className="text-[10px] uppercase tracking-wider text-white/25 mb-2">
                Suggestions
              </p>
              <div className="flex flex-wrap gap-1.5">
                {suggestions.map((s, i) => {
                  const Icon = resolveIcon(s.icon);
                  return (
                    <motion.button
                      key={i}
                      onClick={() => handleSuggestion(s)}
                      disabled={isApplying}
                      whileHover={{ scale: 1.05 }}
                      whileTap={{ scale: 0.95 }}
                      initial={{ opacity: 0, y: 6 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: i * 0.04 }}
                      className="flex items-center gap-1 rounded-lg px-2.5 py-1
                                 text-[11px] text-white/50 hover:text-white/80
                                 border border-white/5 hover:border-white/10
                                 disabled:opacity-30 transition-colors"
                      style={{ background: "rgba(255,255,255,0.03)" }}
                    >
                      <Icon className="h-3 w-3" />
                      {s.label}
                    </motion.button>
                  );
                })}
              </div>
            </div>
          )}

          {/* Bottom padding */}
          <div className="h-3" />
        </motion.div>
      )}
    </AnimatePresence>
  );
}
