/* ─────────────────────────────────────────────
 * AuraGen — useDismiss
 * Combines click-outside, Escape key, and
 * optional auto-close timer into one hook.
 * Use for any popup, dropdown, or panel.
 * ───────────────────────────────────────────── */

"use client";

import { useEffect, useRef, useCallback, type RefObject } from "react";
import { useClickOutside } from "./useClickOutside";

interface UseDismissOptions {
  /** Whether the popup is currently open. */
  open: boolean;
  /** Called to close the popup. */
  onClose: () => void;
  /** Auto-close after this many ms (0 = disabled). Default: 0 */
  autoCloseMs?: number;
  /** Close on Escape key. Default: true */
  closeOnEscape?: boolean;
  /** Close on click outside. Default: true */
  closeOnClickOutside?: boolean;
}

/**
 * All-in-one dismiss hook for popups.
 * Returns a ref to attach to the popup container.
 *
 * Features:
 * - Click outside to close
 * - Escape key to close
 * - Auto-close after timeout
 * - Resets timer on user interaction inside popup
 */
export function useDismiss({
  open,
  onClose,
  autoCloseMs = 0,
  closeOnEscape = true,
  closeOnClickOutside = true,
}: UseDismissOptions): RefObject<HTMLDivElement | null> {
  const ref = useRef<HTMLDivElement>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const stableClose = useCallback(() => {
    onClose();
  }, [onClose]);

  // Click outside
  useClickOutside(ref, stableClose, open && closeOnClickOutside);

  // Escape key
  useEffect(() => {
    if (!open || !closeOnEscape) return;

    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.preventDefault();
        stableClose();
      }
    }

    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [open, closeOnEscape, stableClose]);

  // Auto-close timer
  useEffect(() => {
    if (!open || autoCloseMs <= 0) return;

    timerRef.current = setTimeout(stableClose, autoCloseMs);

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [open, autoCloseMs, stableClose]);

  // Reset timer on mouse activity inside popup
  useEffect(() => {
    if (!open || autoCloseMs <= 0) return;

    const el = ref.current;
    if (!el) return;

    function resetTimer() {
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(stableClose, autoCloseMs);
    }

    el.addEventListener("mousemove", resetTimer);
    el.addEventListener("touchstart", resetTimer);
    return () => {
      el.removeEventListener("mousemove", resetTimer);
      el.removeEventListener("touchstart", resetTimer);
    };
  }, [open, autoCloseMs, stableClose]);

  return ref;
}
