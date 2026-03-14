/* ─────────────────────────────────────────────
 * AuraGen — Sidebar
 * Right-side generation parameters panel with
 * mode tabs, prompt inputs, sliders, and the
 * big glowing Generate button.
 * ───────────────────────────────────────────── */

"use client";

import { useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Image as ImageIcon,
  Video,
  ChevronDown,
  Shuffle,
  Sparkles,
  Loader2,
  X,
  PersonStanding,
  Mic,
  Upload,
} from "lucide-react";
import { clsx } from "clsx";
import { useGenerationStore } from "@/hooks/useGenerationStore";
import { useDismiss } from "@/hooks/useDismiss";
import { NeuralPulse } from "@/components/animations/NeuralPulse";
import type { GenerationMode } from "@/types";

/* ── Slider sub-component ──────────────────── */

function ParamSlider({
  label,
  value,
  min,
  max,
  step,
  onChange,
  unit,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (v: number) => void;
  unit?: string;
}) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <label className="text-[11px] font-medium text-aura-text-secondary uppercase tracking-wider">
          {label}
        </label>
        <span className="text-xs font-mono text-aura-text-tertiary">
          {value}
          {unit ?? ""}
        </span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="glass-slider"
      />
    </div>
  );
}

/* ── Mode tab button ───────────────────────── */

function ModeTab({
  mode,
  active,
  onClick,
  icon: Icon,
  label,
}: {
  mode: GenerationMode;
  active: boolean;
  onClick: () => void;
  icon: typeof ImageIcon;
  label: string;
}) {
  return (
    <button
      onClick={onClick}
      className={clsx(
        "relative flex-1 flex items-center justify-center gap-2 py-2.5 text-sm font-medium rounded-xl transition-colors duration-200 z-10",
        active
          ? "text-aura-text-primary"
          : "text-aura-text-tertiary hover:text-aura-text-secondary"
      )}
    >
      <Icon className="h-4 w-4" />
      {label}
    </button>
  );
}

/* ── Main sidebar ──────────────────────────── */

interface SidebarProps {
  open?: boolean;
  onClose?: () => void;
}

export function Sidebar({ open, onClose }: SidebarProps) {
  const [negativeOpen, setNegativeOpen] = useState(false);

  const mode = useGenerationStore((s) => s.mode);
  const prompt = useGenerationStore((s) => s.prompt);
  const negativePrompt = useGenerationStore((s) => s.negativePrompt);
  const params = useGenerationStore((s) => s.params);
  const isGenerating = useGenerationStore((s) => s.isGenerating);
  const currentJobId = useGenerationStore((s) => s.currentJobId);
  const jobs = useGenerationStore((s) => s.jobs);

  const voiceActive = useGenerationStore((s) => s.voiceActive);
  const poseImage = useGenerationStore((s) => s.poseImage);

  const setMode = useGenerationStore((s) => s.setMode);
  const setPrompt = useGenerationStore((s) => s.setPrompt);
  const setNegativePrompt = useGenerationStore((s) => s.setNegativePrompt);
  const setParams = useGenerationStore((s) => s.setParams);
  const randomizeSeed = useGenerationStore((s) => s.randomizeSeed);
  const submitGeneration = useGenerationStore((s) => s.submitGeneration);
  const cancelJob = useGenerationStore((s) => s.cancelJob);
  const setPoseImage = useGenerationStore((s) => s.setPoseImage);

  const currentJob = currentJobId ? jobs.get(currentJobId) : null;
  const progress = currentJob?.progress ?? 0;

  const handleGenerate = useCallback(() => {
    if (isGenerating && currentJobId) {
      cancelJob(currentJobId);
    } else {
      submitGeneration();
    }
  }, [isGenerating, currentJobId, cancelJob, submitGeneration]);

  const dismissRef = useDismiss({
    open: open ?? false,
    onClose: () => onClose?.(),
    closeOnEscape: true,
    closeOnClickOutside: true,
  });

  function renderContent() {
    return (
      <>
        {/* ── Header ──────────────────────────── */}
        <div className="px-4 pt-4 pb-2">
          <h2 className="text-xs font-semibold uppercase tracking-[0.15em] text-aura-text-tertiary">
            Generation
          </h2>
        </div>

        {/* ── Mode tabs ───────────────────────── */}
        <div className="px-4 pb-4">
          <div className="flex items-center gap-2">
            <div className="relative flex items-center p-1 rounded-xl bg-white/[0.02] border border-white/[0.06] flex-1">
              {/* Animated indicator */}
              <motion.div
                className="absolute top-1 bottom-1 rounded-lg bg-aura-accent/15 border border-aura-accent/20"
                layoutId="mode-indicator"
                style={{
                  width: "calc(33.333% - 4px)",
                  left:
                    mode === "image"
                      ? 4
                      : mode === "video"
                        ? "calc(33.333% + 0px)"
                        : "calc(66.666% - 2px)",
                }}
                transition={{ type: "spring", stiffness: 400, damping: 30 }}
              />
              <ModeTab
                mode="image"
                active={mode === "image"}
                onClick={() => setMode("image")}
                icon={ImageIcon}
                label="Image"
              />
              <ModeTab
                mode="video"
                active={mode === "video"}
                onClick={() => setMode("video")}
                icon={Video}
                label="Video"
              />
              <ModeTab
                mode="pose"
                active={mode === "pose"}
                onClick={() => setMode("pose")}
                icon={PersonStanding}
                label="Pose"
              />
            </div>

            {/* Voice indicator */}
            {voiceActive && (
              <motion.div
                initial={{ scale: 0, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                exit={{ scale: 0, opacity: 0 }}
                className="flex items-center justify-center w-9 h-9 rounded-xl bg-red-500/10 border border-red-500/20"
                title="Voice active"
              >
                <Mic className="h-3.5 w-3.5 text-red-400" />
              </motion.div>
            )}
          </div>
        </div>

        {/* ── Scrollable parameters ───────────── */}
        <div className="flex-1 overflow-y-auto px-4 space-y-5 pb-4">
          {/* Prompt */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-[11px] font-medium text-aura-text-secondary uppercase tracking-wider">
                Prompt
              </label>
              <span
                className={clsx(
                  "text-[10px] font-mono",
                  prompt.length > 500
                    ? "text-red-400/70"
                    : "text-aura-text-tertiary"
                )}
              >
                {prompt.length}/500
              </span>
            </div>
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="A luminescent jellyfish floating through a neon-lit cyberpunk city..."
              maxLength={500}
              rows={4}
              className="glass-input resize-none !rounded-xl text-sm md:text-sm leading-relaxed"
            />
          </div>

          {/* Negative prompt (collapsible) */}
          <div>
            <button
              onClick={() => setNegativeOpen(!negativeOpen)}
              className="flex items-center gap-2 text-[11px] font-medium text-aura-text-tertiary uppercase tracking-wider hover:text-aura-text-secondary transition-colors w-full"
            >
              <motion.span
                animate={{ rotate: negativeOpen ? 180 : 0 }}
                transition={{ duration: 0.2 }}
              >
                <ChevronDown className="h-3.5 w-3.5" />
              </motion.span>
              Negative Prompt
            </button>
            <AnimatePresence>
              {negativeOpen && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.2 }}
                  className="overflow-hidden"
                >
                  <textarea
                    value={negativePrompt}
                    onChange={(e) => setNegativePrompt(e.target.value)}
                    placeholder="blurry, low quality, distorted..."
                    rows={2}
                    className="glass-input resize-none !rounded-xl text-sm mt-2"
                  />
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          {/* Divider */}
          <div className="h-px bg-white/[0.04]" />

          {/* Dimensions */}
          <div className="grid grid-cols-2 gap-3">
            <ParamSlider
              label="Width"
              value={params.width}
              min={256}
              max={2048}
              step={64}
              unit="px"
              onChange={(v) => setParams({ width: v })}
            />
            <ParamSlider
              label="Height"
              value={params.height}
              min={256}
              max={2048}
              step={64}
              unit="px"
              onChange={(v) => setParams({ height: v })}
            />
          </div>

          {/* Steps */}
          <ParamSlider
            label="Steps"
            value={params.steps}
            min={1}
            max={100}
            step={1}
            onChange={(v) => setParams({ steps: v })}
          />

          {/* Guidance Scale */}
          <ParamSlider
            label="Guidance Scale"
            value={params.guidance_scale}
            min={1}
            max={20}
            step={0.5}
            onChange={(v) => setParams({ guidance_scale: v })}
          />

          {/* Frames (video only) */}
          <AnimatePresence>
            {mode === "video" && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.2 }}
                className="overflow-hidden"
              >
                <ParamSlider
                  label="Frames"
                  value={params.frames ?? 24}
                  min={8}
                  max={120}
                  step={1}
                  onChange={(v) => setParams({ frames: v })}
                />
              </motion.div>
            )}
          </AnimatePresence>

          {/* Pose controls (pose only) */}
          <AnimatePresence>
            {mode === "pose" && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.2 }}
                className="overflow-hidden space-y-4"
              >
                {/* Pose image upload drop zone */}
                <div className="space-y-2">
                  <label className="text-[11px] font-medium text-aura-text-secondary uppercase tracking-wider">
                    Pose Image
                  </label>
                  <div
                    className={clsx(
                      "relative flex flex-col items-center justify-center rounded-xl border-2 border-dashed transition-colors duration-200 cursor-pointer overflow-hidden",
                      poseImage
                        ? "border-aura-accent/30 bg-aura-accent/[0.03]"
                        : "border-white/[0.08] bg-white/[0.01] hover:border-white/[0.15] hover:bg-white/[0.03]"
                    )}
                    style={{ minHeight: poseImage ? "auto" : 100 }}
                    onDragOver={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                    }}
                    onDrop={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      const file = e.dataTransfer.files?.[0];
                      if (file && file.type.startsWith("image/")) {
                        const reader = new FileReader();
                        reader.onload = (ev) => {
                          setPoseImage(ev.target?.result as string);
                        };
                        reader.readAsDataURL(file);
                      }
                    }}
                    onClick={() => {
                      const input = document.createElement("input");
                      input.type = "file";
                      input.accept = "image/*";
                      input.onchange = (e) => {
                        const file = (e.target as HTMLInputElement).files?.[0];
                        if (file) {
                          const reader = new FileReader();
                          reader.onload = (ev) => {
                            setPoseImage(ev.target?.result as string);
                          };
                          reader.readAsDataURL(file);
                        }
                      };
                      input.click();
                    }}
                  >
                    {poseImage ? (
                      <div className="relative w-full">
                        <img
                          src={poseImage}
                          alt="Pose reference"
                          className="w-full h-auto rounded-lg"
                          draggable={false}
                        />
                        <motion.button
                          whileHover={{ scale: 1.1 }}
                          whileTap={{ scale: 0.9 }}
                          onClick={(e) => {
                            e.stopPropagation();
                            setPoseImage(null);
                          }}
                          className="absolute top-2 right-2 p-1.5 rounded-lg bg-black/50 hover:bg-red-500/30 transition-colors"
                        >
                          <X className="h-3 w-3 text-white/80" />
                        </motion.button>
                      </div>
                    ) : (
                      <div className="flex flex-col items-center gap-2 py-4">
                        <Upload className="h-6 w-6 text-aura-text-tertiary" />
                        <span className="text-[11px] text-aura-text-tertiary">
                          Drop a skeleton/pose image here
                        </span>
                        <span className="text-[9px] text-aura-text-tertiary/60">
                          or click to browse
                        </span>
                      </div>
                    )}
                  </div>
                </div>

                {/* ControlNet Scale */}
                <ParamSlider
                  label="ControlNet Scale"
                  value={params.controlnet_scale ?? 1.0}
                  min={0}
                  max={2}
                  step={0.05}
                  onChange={(v) => setParams({ controlnet_scale: v })}
                />
              </motion.div>
            )}
          </AnimatePresence>

          {/* Seed */}
          <div className="space-y-2">
            <label className="text-[11px] font-medium text-aura-text-secondary uppercase tracking-wider">
              Seed
            </label>
            <div className="flex items-center gap-2">
              <input
                type="number"
                value={params.seed ?? ""}
                onChange={(e) =>
                  setParams({
                    seed: e.target.value ? Number(e.target.value) : null,
                  })
                }
                placeholder="Random"
                className="glass-input flex-1 !rounded-xl text-sm font-mono"
              />
              <motion.button
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.9, rotate: 180 }}
                onClick={randomizeSeed}
                className="p-2.5 rounded-xl bg-white/[0.03] border border-white/[0.06] hover:bg-white/[0.06] transition-colors"
                title="Random seed"
              >
                <Shuffle className="h-4 w-4 text-aura-text-secondary" />
              </motion.button>
            </div>
          </div>
        </div>

        {/* ── Generate button area ────────────── */}
        <div className="p-4 border-t border-white/[0.04]">
          {/* Neural pulse above button when generating */}
          <AnimatePresence>
            {isGenerating && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                className="flex justify-center pb-4 overflow-hidden"
              >
                <NeuralPulse progress={progress} visible size="sm" />
              </motion.div>
            )}
          </AnimatePresence>

          <motion.button
            whileHover={!isGenerating ? { scale: 1.02 } : undefined}
            whileTap={!isGenerating ? { scale: 0.98 } : undefined}
            onClick={handleGenerate}
            disabled={!prompt.trim() && !isGenerating}
            className={clsx(
              "relative w-full py-3 md:py-3.5 rounded-xl font-medium text-sm transition-all duration-300 overflow-hidden",
              "outline-none focus-visible:ring-2 focus-visible:ring-aura-accent/50",
              isGenerating
                ? "bg-red-500/15 border border-red-500/20 text-red-400 hover:bg-red-500/20"
                : "bg-aura-accent/90 text-white shadow-glow hover:shadow-glow-lg",
              !prompt.trim() &&
                !isGenerating &&
                "opacity-40 cursor-not-allowed"
            )}
          >
            {/* Animated glow background */}
            {!isGenerating && prompt.trim() && (
              <motion.div
                className="absolute inset-0 bg-gradient-to-r from-aura-accent/0 via-aura-glow/20 to-aura-accent/0"
                animate={{
                  x: ["-100%", "100%"],
                }}
                transition={{
                  duration: 3,
                  repeat: Infinity,
                  ease: "linear",
                }}
              />
            )}

            <span className="relative z-10 flex items-center justify-center gap-2">
              {isGenerating ? (
                <>
                  <X className="h-4 w-4" />
                  Cancel Generation
                </>
              ) : (
                <>
                  <Sparkles className="h-4 w-4" />
                  {mode === "pose"
                    ? "Animate Pose"
                    : `Generate ${mode === "image" ? "Image" : "Video"}`}
                </>
              )}
            </span>
          </motion.button>
        </div>
      </>
    );
  }

  return (
    <>
      {/* Desktop: always visible */}
      <div
        ref={dismissRef}
        className={clsx(
          // Desktop: fixed width sidebar
          "hidden lg:flex w-[340px] h-full flex-col glass-panel border-l border-white/[0.06] overflow-hidden",
          // 4K: wider sidebar
          "4k:w-[420px]"
        )}
      >
        {renderContent()}
      </div>

      {/* Mobile/Tablet: slide-over drawer */}
      <AnimatePresence>
        {open && (
          <>
            <motion.div
              className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm lg:hidden"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={onClose}
            />
            <motion.div
              ref={dismissRef}
              initial={{ x: "100%" }}
              animate={{ x: 0 }}
              exit={{ x: "100%" }}
              transition={{ type: "spring", stiffness: 300, damping: 30 }}
              className="fixed right-0 top-0 bottom-0 z-50 w-[85vw] max-w-[380px] flex flex-col glass-panel border-l border-white/[0.06] overflow-hidden lg:hidden"
              style={{ background: "rgba(10, 10, 18, 0.95)" }}
            >
              {/* Close button */}
              <div className="flex items-center justify-between px-4 pt-3 lg:hidden">
                <span className="text-xs font-semibold text-white/50">Settings</span>
                <button
                  onClick={onClose}
                  className="p-1.5 rounded-lg text-white/40 hover:text-white/80 hover:bg-white/[0.06] transition-colors"
                  aria-label="Close sidebar"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
              {renderContent()}
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </>
  );
}
