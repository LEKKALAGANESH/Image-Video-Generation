/* ─────────────────────────────────────────────
 * AuraGen — useClickOutside
 * Reusable hook: closes any popup/dropdown
 * when the user clicks outside its container.
 * ───────────────────────────────────────────── */

"use client";

import { useEffect, type RefObject } from "react";

/**
 * Calls `onClose` when a mousedown/touchstart event
 * occurs outside the element referenced by `ref`.
 *
 * @param ref - React ref attached to the popup container
 * @param onClose - callback to run when clicking outside
 * @param enabled - whether the listener is active (default: true)
 */
export function useClickOutside(
  ref: RefObject<HTMLElement | null>,
  onClose: () => void,
  enabled = true,
): void {
  useEffect(() => {
    if (!enabled) return;

    function handler(e: MouseEvent | TouchEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        onClose();
      }
    }

    document.addEventListener("mousedown", handler);
    document.addEventListener("touchstart", handler);
    return () => {
      document.removeEventListener("mousedown", handler);
      document.removeEventListener("touchstart", handler);
    };
  }, [ref, onClose, enabled]);
}
