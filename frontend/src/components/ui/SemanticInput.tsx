/**
 * AuraGen -- SemanticInput ("No More Points" natural-language input).
 *
 * A premium glass-themed text input for natural language editing commands.
 * Features an animated cycling placeholder, gradient border, and a
 * processing indicator.
 */

"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Loader2, Send, Sparkles } from "lucide-react";

// ---------------------------------------------------------------------------
// Placeholder examples that cycle
// ---------------------------------------------------------------------------

const PLACEHOLDER_EXAMPLES = [
  "Make the sky more dramatic...",
  "Remove the person in the background...",
  "Change the car color to red...",
  "Add a sunset glow to the scene...",
  "Turn day into night...",
  "Make it look like a painting...",
  "Add rain to the scene...",
  "Brighten the shadows...",
] as const;

const CYCLE_INTERVAL_MS = 3200;

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface SemanticInputProps {
  /** Called when the user submits (Enter or button click). */
  onSubmit: (prompt: string) => void;
  /** External loading state. */
  isProcessing?: boolean;
  /** Disable the input. */
  disabled?: boolean;
  /** Additional CSS classes. */
  className?: string;
}

export default function SemanticInput({
  onSubmit,
  isProcessing = false,
  disabled = false,
  className = "",
}: SemanticInputProps) {
  const [value, setValue] = useState("");
  const [placeholderIdx, setPlaceholderIdx] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  // ── Cycle placeholder text ────────────────────────────────────────────

  useEffect(() => {
    const timer = setInterval(() => {
      setPlaceholderIdx((prev) => (prev + 1) % PLACEHOLDER_EXAMPLES.length);
    }, CYCLE_INTERVAL_MS);
    return () => clearInterval(timer);
  }, []);

  // ── Handlers ──────────────────────────────────────────────────────────

  const handleSubmit = useCallback(() => {
    const trimmed = value.trim();
    if (!trimmed || isProcessing || disabled) return;
    onSubmit(trimmed);
    setValue("");
  }, [value, isProcessing, disabled, onSubmit]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSubmit();
      }
    },
    [handleSubmit],
  );

  // ── Derived ───────────────────────────────────────────────────────────

  const showPlaceholder = value.length === 0;
  const canSubmit = value.trim().length > 0 && !isProcessing && !disabled;

  return (
    <div className={`relative group ${className}`}>
      {/* Gradient border glow */}
      <div
        className="absolute -inset-[1px] rounded-2xl opacity-60 group-hover:opacity-100
                    transition-opacity duration-500 pointer-events-none"
        style={{
          background:
            "linear-gradient(135deg, rgba(139,92,246,0.5), rgba(59,130,246,0.5), rgba(236,72,153,0.3))",
          filter: "blur(1px)",
        }}
      />

      {/* Glass container */}
      <div
        className="relative flex items-center gap-3 rounded-2xl px-4 py-3
                    backdrop-blur-xl border border-white/10"
        style={{
          background:
            "linear-gradient(135deg, rgba(255,255,255,0.07) 0%, rgba(255,255,255,0.03) 100%)",
        }}
      >
        {/* Sparkle icon */}
        <Sparkles className="h-4 w-4 shrink-0 text-violet-400/70" />

        {/* Input area with animated placeholder */}
        <div className="relative flex-1 min-w-0">
          <input
            ref={inputRef}
            type="text"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={disabled || isProcessing}
            className="w-full bg-transparent text-sm text-white/90 placeholder-transparent
                       outline-none disabled:opacity-50"
            aria-label="Describe your edit"
          />

          {/* Animated cycling placeholder */}
          {showPlaceholder && (
            <div className="absolute inset-0 flex items-center pointer-events-none overflow-hidden">
              <AnimatePresence mode="wait">
                <motion.span
                  key={placeholderIdx}
                  initial={{ opacity: 0, y: 8, filter: "blur(4px)" }}
                  animate={{ opacity: 0.5, y: 0, filter: "blur(0px)" }}
                  exit={{ opacity: 0, y: -8, filter: "blur(4px)" }}
                  transition={{ duration: 0.4, ease: "easeInOut" }}
                  className="text-sm text-white/40 whitespace-nowrap"
                >
                  {PLACEHOLDER_EXAMPLES[placeholderIdx]}
                </motion.span>
              </AnimatePresence>
            </div>
          )}
        </div>

        {/* Submit / processing indicator */}
        <motion.button
          type="button"
          onClick={handleSubmit}
          disabled={!canSubmit}
          whileHover={canSubmit ? { scale: 1.1 } : {}}
          whileTap={canSubmit ? { scale: 0.92 } : {}}
          className="relative shrink-0 flex items-center justify-center h-8 w-8
                     rounded-xl transition-colors duration-200
                     disabled:opacity-30 disabled:cursor-not-allowed"
          style={{
            background: canSubmit
              ? "linear-gradient(135deg, rgba(139,92,246,0.6), rgba(59,130,246,0.6))"
              : "rgba(255,255,255,0.05)",
          }}
          aria-label="Submit edit"
        >
          <AnimatePresence mode="wait">
            {isProcessing ? (
              <motion.div
                key="loader"
                initial={{ opacity: 0, rotate: -90 }}
                animate={{ opacity: 1, rotate: 0 }}
                exit={{ opacity: 0, rotate: 90 }}
                transition={{ duration: 0.2 }}
              >
                <Loader2 className="h-4 w-4 text-white/80 animate-spin" />
              </motion.div>
            ) : (
              <motion.div
                key="send"
                initial={{ opacity: 0, rotate: -90 }}
                animate={{ opacity: 1, rotate: 0 }}
                exit={{ opacity: 0, rotate: 90 }}
                transition={{ duration: 0.2 }}
              >
                <Send className="h-4 w-4 text-white/80" />
              </motion.div>
            )}
          </AnimatePresence>
        </motion.button>
      </div>
    </div>
  );
}
