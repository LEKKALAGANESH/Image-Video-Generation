/* ─────────────────────────────────────────────
 * AuraGen — Auto-Download Info Banner
 * Shows a dismissible notification explaining
 * that generated content auto-downloads to the
 * user's device, with future database storage.
 * ───────────────────────────────────────────── */

"use client";

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { HardDrive, X, CloudOff } from "lucide-react";

const STORAGE_KEY = "auragen-download-banner-dismissed";

export function AutoDownloadBanner() {
  const [dismissed, setDismissed] = useState(true); // start hidden to avoid hydration
  const [hasGenerated, setHasGenerated] = useState(false);

  // Check localStorage on mount (SSR-safe)
  useEffect(() => {
    const wasDismissed = localStorage.getItem(STORAGE_KEY) === "true";
    setDismissed(wasDismissed);
  }, []);

  // Listen for first generation completion
  useEffect(() => {
    function onComplete() {
      setHasGenerated(true);
    }
    window.addEventListener("auragen:generation-complete", onComplete);
    return () => window.removeEventListener("auragen:generation-complete", onComplete);
  }, []);

  const handleDismiss = () => {
    setDismissed(true);
    localStorage.setItem(STORAGE_KEY, "true");
  };

  // Show when: not dismissed AND (first visit OR generation completed)
  const visible = !dismissed;

  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8, transition: { duration: 0.15 } }}
          transition={{ duration: 0.25, ease: "easeOut" }}
          className="mx-4 mt-2 flex items-start gap-3 px-4 py-3 rounded-xl border border-indigo-500/20 bg-indigo-500/[0.04] backdrop-blur-sm"
        >
          <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-indigo-500/10 flex-shrink-0 mt-0.5">
            <HardDrive className="w-4 h-4 text-indigo-400" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-[11px] text-indigo-200/90 leading-relaxed">
              <span className="font-semibold text-indigo-200">Auto-Download Enabled</span>
              {" — "}
              Your generated images and videos are automatically downloaded to your device.
              Files are also cached locally for instant access.
            </p>
            <div className="flex items-center gap-1.5 mt-1.5">
              <CloudOff className="w-3 h-3 text-white/30" />
              <p className="text-[10px] text-white/40 leading-relaxed">
                Cloud storage & database sync coming soon for persistent access across devices.
              </p>
            </div>
          </div>
          <button
            onClick={handleDismiss}
            className="text-white/30 hover:text-white/60 transition-colors flex-shrink-0 mt-0.5"
            aria-label="Dismiss"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
