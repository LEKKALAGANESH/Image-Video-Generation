/* ─────────────────────────────────────────────
 * AuraGen — CommandBar
 * Semantic Cmd+K command palette for quick
 * generation, styled with liquid glass.
 * ───────────────────────────────────────────── */

"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Image as ImageIcon,
  Video,
  Scissors,
  Sparkles,
  Search,
  Command,
} from "lucide-react";
import { useGenerationStore } from "@/hooks/useGenerationStore";

const quickActions = [
  {
    label: "Generate Image",
    icon: ImageIcon,
    mode: "image" as const,
    color: "#6366f1",
  },
  {
    label: "Generate Video",
    icon: Video,
    mode: "video" as const,
    color: "#818cf8",
  },
  {
    label: "Edit Region",
    icon: Scissors,
    mode: null,
    color: "#a78bfa",
  },
  {
    label: "Surprise Me",
    icon: Sparkles,
    mode: null,
    color: "#c4b5fd",
  },
];

export function CommandBar() {
  const [inputValue, setInputValue] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const isOpen = useGenerationStore((s) => s.commandBarOpen);
  const setOpen = useGenerationStore((s) => s.setCommandBarOpen);
  const setMode = useGenerationStore((s) => s.setMode);
  const submitFromCommandBar = useGenerationStore(
    (s) => s.submitFromCommandBar
  );

  // Keyboard shortcut: Cmd/Ctrl + K
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setOpen(!isOpen);
      }
      if (e.key === "Escape" && isOpen) {
        e.preventDefault();
        setOpen(false);
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, setOpen]);

  // Auto-focus input when opened
  useEffect(() => {
    if (isOpen) {
      setInputValue("");
      // Slight delay for the animation
      const t = setTimeout(() => inputRef.current?.focus(), 100);
      return () => clearTimeout(t);
    }
  }, [isOpen]);

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      if (inputValue.trim()) {
        submitFromCommandBar(inputValue.trim());
        setInputValue("");
      }
    },
    [inputValue, submitFromCommandBar]
  );

  const handleQuickAction = useCallback(
    (action: (typeof quickActions)[number]) => {
      if (action.mode) {
        setMode(action.mode);
      }
      if (action.label === "Surprise Me") {
        const prompts = [
          "A luminescent jellyfish floating through a neon-lit cyberpunk city at night",
          "An ancient library carved into a crystal mountain, bathed in aurora light",
          "A futuristic garden where holographic flowers bloom in zero gravity",
        ];
        const randomPrompt = prompts[Math.floor(Math.random() * prompts.length)];
        submitFromCommandBar(randomPrompt);
      } else {
        setOpen(false);
        // Focus will go to the sidebar prompt textarea
      }
    },
    [setMode, setOpen, submitFromCommandBar]
  );

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Backdrop */}
          <motion.div
            className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            onClick={() => setOpen(false)}
          />

          {/* Command Panel */}
          <motion.div
            className="fixed inset-0 z-50 flex items-start justify-center pt-[20vh] md:pt-[18vh]"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          >
            <motion.div
              className="w-full max-w-[95vw] md:max-w-2xl mx-2 md:mx-4"
              initial={{ opacity: 0, y: -20, scale: 0.96 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -10, scale: 0.98 }}
              transition={{
                type: "spring",
                stiffness: 400,
                damping: 30,
              }}
            >
              <div
                className="glass-panel rounded-2xl overflow-hidden shadow-[0_25px_60px_rgba(0,0,0,0.6)]"
                role="dialog"
                aria-label="Command palette"
              >
                {/* Search input */}
                <form onSubmit={handleSubmit} className="relative">
                  <div className="flex items-center gap-3 px-3 md:px-5 py-3 md:py-4 border-b border-white/[0.06]">
                    <Search className="h-5 w-5 text-aura-text-tertiary flex-shrink-0" />
                    <input
                      ref={inputRef}
                      type="text"
                      value={inputValue}
                      onChange={(e) => setInputValue(e.target.value)}
                      placeholder="Describe what you want to create..."
                      aria-label="Enter a generation prompt"
                      className="flex-1 bg-transparent text-base text-aura-text-primary outline-none placeholder:text-aura-text-tertiary"
                    />
                    <kbd className="hidden sm:flex items-center gap-1 px-2 py-1 rounded-md bg-white/[0.04] border border-white/[0.08] text-[10px] text-aura-text-tertiary font-mono">
                      <Command className="h-2.5 w-2.5" />K
                    </kbd>
                  </div>
                </form>

                {/* Quick Actions */}
                <div className="p-3">
                  <p className="px-2 py-1.5 text-[11px] font-medium tracking-wider uppercase text-aura-text-tertiary">
                    Quick Actions
                  </p>
                  <div className="mt-1 grid grid-cols-1 xs:grid-cols-2 gap-2">
                    {quickActions.map((action) => (
                      <motion.button
                        key={action.label}
                        onClick={() => handleQuickAction(action)}
                        whileHover={{ scale: 1.02 }}
                        whileTap={{ scale: 0.98 }}
                        className="flex items-center gap-3 px-3 py-2.5 rounded-xl transition-colors duration-150 hover:bg-white/[0.04] text-left group"
                      >
                        <div
                          className="flex items-center justify-center w-8 h-8 rounded-lg transition-all duration-200 group-hover:shadow-lg"
                          style={{
                            background: `${action.color}15`,
                            boxShadow: `0 0 0 1px ${action.color}20`,
                          }}
                        >
                          <action.icon
                            className="h-4 w-4"
                            style={{ color: action.color }}
                          />
                        </div>
                        <span className="text-sm text-aura-text-secondary group-hover:text-aura-text-primary transition-colors">
                          {action.label}
                        </span>
                      </motion.button>
                    ))}
                  </div>
                </div>

                {/* Footer hint */}
                <div className="px-3 md:px-5 py-2 md:py-2.5 border-t border-white/[0.04] flex items-center justify-between">
                  <span className="text-[11px] text-aura-text-tertiary">
                    Type a prompt and press Enter to generate
                  </span>
                  <span className="text-[11px] text-aura-text-tertiary">
                    ESC to close
                  </span>
                </div>
              </div>
            </motion.div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
