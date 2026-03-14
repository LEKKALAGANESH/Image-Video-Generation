/* ─────────────────────────────────────────────
 * AuraGen — VoiceCommand
 * Floating microphone toggle button with speech
 * recognition, transcript bubble, and command
 * dispatching for the Morphing UI.
 * ───────────────────────────────────────────── */

"use client";

import { useEffect, useRef, useCallback, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Mic, MicOff, Loader2 } from "lucide-react";
import { useVoiceCommand } from "@/hooks/useVoiceCommand";
import { useGenerationStore } from "@/hooks/useGenerationStore";

/* ── Waveform bars (CSS-driven visualization) ── */

function WaveformBars() {
  return (
    <div className="flex items-center gap-[2px] h-4">
      {Array.from({ length: 5 }).map((_, i) => (
        <motion.div
          key={i}
          className="w-[2px] rounded-full bg-red-400/80"
          animate={{
            height: ["4px", "14px", "6px", "12px", "4px"],
          }}
          transition={{
            duration: 0.8,
            repeat: Infinity,
            ease: "easeInOut",
            delay: i * 0.1,
          }}
        />
      ))}
    </div>
  );
}

/* ── Main VoiceCommand component ─────────────── */

export function VoiceCommand() {
  const [hasMounted, setHasMounted] = useState(false);

  useEffect(() => {
    setHasMounted(true);
  }, []);

  const {
    isListening,
    transcript,
    isSupported,
    error,
    toggleListening,
    stopListening,
  } = useVoiceCommand();

  const [isProcessing, setIsProcessing] = useState(false);
  const lastProcessedRef = useRef("");

  const setMode = useGenerationStore((s) => s.setMode);
  const setPrompt = useGenerationStore((s) => s.setPrompt);
  const submitGeneration = useGenerationStore((s) => s.submitGeneration);
  const cancelJob = useGenerationStore((s) => s.cancelJob);
  const currentJobId = useGenerationStore((s) => s.currentJobId);
  const setVoiceActive = useGenerationStore((s) => s.setVoiceActive);

  // Sync voice active state to store
  useEffect(() => {
    setVoiceActive(isListening);
  }, [isListening, setVoiceActive]);

  // Dispatch voice commands when listening stops and we have a transcript
  const dispatchCommand = useCallback(
    async (text: string) => {
      if (!text.trim() || text === lastProcessedRef.current) return;
      lastProcessedRef.current = text;

      setIsProcessing(true);

      const lower = text.toLowerCase().trim();

      try {
        if (lower.startsWith("generate image of ")) {
          const prompt = text.slice("generate image of ".length).trim();
          setMode("image");
          setPrompt(prompt);
          await new Promise((r) => setTimeout(r, 100));
          await submitGeneration();
        } else if (lower.startsWith("generate video of ")) {
          const prompt = text.slice("generate video of ".length).trim();
          setMode("video");
          setPrompt(prompt);
          await new Promise((r) => setTimeout(r, 100));
          await submitGeneration();
        } else if (lower === "cancel") {
          if (currentJobId) {
            await cancelJob(currentJobId);
          }
        } else if (lower === "zoom in") {
          // Dispatch a custom event the canvas can listen for
          window.dispatchEvent(new CustomEvent("auragen:zoom", { detail: "in" }));
        } else if (lower === "zoom out") {
          window.dispatchEvent(new CustomEvent("auragen:zoom", { detail: "out" }));
        } else {
          // Any other text becomes the prompt
          setPrompt(text.trim());
        }
      } finally {
        setIsProcessing(false);
      }
    },
    [setMode, setPrompt, submitGeneration, cancelJob, currentJobId]
  );

  // When listening stops and we have a transcript, process it
  useEffect(() => {
    if (!isListening && transcript.trim()) {
      dispatchCommand(transcript);
    }
  }, [isListening, transcript, dispatchCommand]);

  // Don't render until client-side mount (prevents hydration mismatch)
  // or if speech recognition is unsupported
  if (!hasMounted || !isSupported) return null;

  // Determine state
  const state: "idle" | "listening" | "processing" = isProcessing
    ? "processing"
    : isListening
      ? "listening"
      : "idle";

  return (
    <div className="fixed bottom-6 left-6 z-50 flex flex-col items-start gap-3">
      {/* Transcript bubble */}
      <AnimatePresence>
        {isListening && transcript && (
          <motion.div
            initial={{ opacity: 0, y: 8, scale: 0.9 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 8, scale: 0.9 }}
            transition={{ type: "spring", stiffness: 400, damping: 25 }}
            className="glass-panel px-4 py-2.5 rounded-xl max-w-xs border border-white/[0.08] shadow-lg"
          >
            <p className="text-xs text-aura-text-secondary leading-relaxed">
              {transcript}
            </p>
            <div className="mt-1.5 flex items-center gap-2">
              <WaveformBars />
              <span className="text-[10px] text-aura-text-tertiary uppercase tracking-wider">
                Listening...
              </span>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Error message */}
      <AnimatePresence>
        {error && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 8 }}
            className="glass-panel px-3 py-2 rounded-lg border border-red-500/20 max-w-xs"
          >
            <p className="text-[10px] text-red-400/80">{error}</p>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Mic button */}
      <div className="relative">
        {/* Pulsing ring when listening */}
        <AnimatePresence>
          {state === "listening" && (
            <motion.div
              initial={{ scale: 0.8, opacity: 0 }}
              animate={{
                scale: [1, 1.4, 1],
                opacity: [0.6, 0, 0.6],
              }}
              exit={{ scale: 0.8, opacity: 0 }}
              transition={{
                duration: 1.5,
                repeat: Infinity,
                ease: "easeInOut",
              }}
              className="absolute inset-0 rounded-full border-2 border-red-400/60"
            />
          )}
        </AnimatePresence>

        {/* Second pulse ring (offset) */}
        <AnimatePresence>
          {state === "listening" && (
            <motion.div
              initial={{ scale: 0.8, opacity: 0 }}
              animate={{
                scale: [1, 1.6, 1],
                opacity: [0.4, 0, 0.4],
              }}
              exit={{ scale: 0.8, opacity: 0 }}
              transition={{
                duration: 1.5,
                repeat: Infinity,
                ease: "easeInOut",
                delay: 0.3,
              }}
              className="absolute inset-0 rounded-full border-2 border-red-400/30"
            />
          )}
        </AnimatePresence>

        <motion.button
          whileHover={{ scale: 1.08 }}
          whileTap={{ scale: 0.92 }}
          onClick={toggleListening}
          className={`
            relative z-10 flex items-center justify-center w-12 h-12 rounded-full
            glass-panel border transition-all duration-300 shadow-lg
            ${state === "listening"
              ? "border-red-400/40 bg-red-500/10 shadow-[0_0_20px_rgba(239,68,68,0.2)]"
              : state === "processing"
                ? "border-aura-accent/30 bg-aura-accent/10"
                : "border-white/[0.08] hover:border-white/[0.15] hover:bg-white/[0.04]"
            }
          `}
          aria-label={isListening ? "Stop listening" : "Start voice command"}
        >
          <AnimatePresence mode="wait">
            {state === "processing" ? (
              <motion.div
                key="processing"
                initial={{ opacity: 0, rotate: -90 }}
                animate={{ opacity: 1, rotate: 0 }}
                exit={{ opacity: 0, rotate: 90 }}
                transition={{ duration: 0.2 }}
              >
                <Loader2 className="h-5 w-5 text-aura-accent animate-spin" />
              </motion.div>
            ) : state === "listening" ? (
              <motion.div
                key="listening"
                initial={{ opacity: 0, scale: 0.5 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.5 }}
                transition={{ duration: 0.2 }}
              >
                <Mic className="h-5 w-5 text-red-400" />
              </motion.div>
            ) : (
              <motion.div
                key="idle"
                initial={{ opacity: 0, scale: 0.5 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.5 }}
                transition={{ duration: 0.2 }}
              >
                <Mic className="h-5 w-5 text-aura-text-secondary" />
              </motion.div>
            )}
          </AnimatePresence>
        </motion.button>
      </div>
    </div>
  );
}
