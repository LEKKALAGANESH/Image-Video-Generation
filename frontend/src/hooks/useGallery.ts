/* ─────────────────────────────────────────────
 * AuraGen — Persistent Gallery Hook
 * Loads gallery assets from IndexedDB + OPFS
 * so creations persist even when backend is offline.
 * ───────────────────────────────────────────── */

"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import {
  getAllAssets,
  getLocalFileURL,
  type GalleryAsset,
} from "@/lib/download-manager";

export interface GalleryItem extends GalleryAsset {
  /** Object URL for local display (null if OPFS file was deleted). */
  localUrl: string | null;
}

export function useGallery() {
  const [items, setItems] = useState<GalleryItem[]>([]);
  const [loading, setLoading] = useState(true);
  /** Track active object URLs so we can revoke them on refresh/unmount. */
  const activeUrlsRef = useRef<string[]>([]);

  /** Revoke all outstanding object URLs to free browser RAM. */
  const revokeAll = useCallback(() => {
    for (const url of activeUrlsRef.current) {
      try { URL.revokeObjectURL(url); } catch { /* already revoked */ }
    }
    activeUrlsRef.current = [];
  }, []);

  const refresh = useCallback(async () => {
    setLoading(true);
    // Release previous object URLs before creating new ones
    revokeAll();
    try {
      const assets = await getAllAssets();
      // Sort newest first
      assets.sort((a, b) => b.savedAt - a.savedAt);

      // Resolve local URLs in parallel
      const resolved = await Promise.all(
        assets.map(async (asset) => {
          const localUrl = asset.persisted
            ? await getLocalFileURL(asset.filename)
            : null;
          return { ...asset, localUrl };
        }),
      );

      // Track the new object URLs for later cleanup
      activeUrlsRef.current = resolved
        .map((r) => r.localUrl)
        .filter((u): u is string => u !== null);

      setItems(resolved);
    } catch (err) {
      console.warn("[AuraGen Gallery] Failed to load:", err);
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [revokeAll]);

  useEffect(() => {
    refresh();
    // Revoke all object URLs when the hook unmounts
    return revokeAll;
  }, [refresh, revokeAll]);

  return { items, loading, refresh };
}
