/* ─────────────────────────────────────────────
 * AuraGen — useNetworkStatus Hook
 * Detects real-time bandwidth via the Network
 * Information API and classifies into quality
 * tiers (Low / Medium / High).
 * ───────────────────────────────────────────── */

"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { NetworkTier, EffectiveType, NetworkStatus } from "@/types";

/* ── Navigator.connection type augmentation ── */

interface NetworkInformation extends EventTarget {
  readonly effectiveType: EffectiveType;
  readonly downlink: number;
  readonly rtt: number;
  readonly saveData: boolean;
  onchange: ((this: NetworkInformation, ev: Event) => void) | null;
}

declare global {
  interface Navigator {
    readonly connection?: NetworkInformation;
    readonly mozConnection?: NetworkInformation;
    readonly webkitConnection?: NetworkInformation;
  }
}

/* ── Tier classification ─────────────────── */

const STORAGE_KEY = "auragen:low-bandwidth-mode";

/**
 * Classify network conditions into a quality tier.
 *
 * | Tier   | effectiveType | downlink      |
 * |--------|---------------|---------------|
 * | low    | slow-2g, 2g   | < 1.5 Mbps    |
 * | medium | 3g            | 1.5–7 Mbps    |
 * | high   | 4g            | > 7 Mbps      |
 */
function classifyTier(
  effectiveType: EffectiveType,
  downlink: number,
  saveData: boolean,
): NetworkTier {
  // Data-saver always forces low tier
  if (saveData) return "low";

  if (effectiveType === "slow-2g" || effectiveType === "2g") return "low";
  if (effectiveType === "3g" || downlink < 7) return "medium";
  return "high";
}

/**
 * Resolve the connection object across vendor prefixes.
 */
function getConnection(): NetworkInformation | undefined {
  if (typeof navigator === "undefined") return undefined;
  return navigator.connection ?? navigator.mozConnection ?? navigator.webkitConnection;
}

/* ── Hook ─────────────────────────────────── */

export function useNetworkStatus(): NetworkStatus & {
  setLowBandwidthMode: (enabled: boolean) => void;
  /** Manually feed a measured transfer speed (bytes/sec). */
  reportTransferSpeed: (bytesPerSec: number) => void;
} {
  // SSR-safe defaults — all browser API reads deferred to useEffect
  const [status, setStatus] = useState<NetworkStatus>({
    tier: "high",
    effectiveType: "4g",
    downlink: 10,
    rtt: 50,
    saveData: false,
    lowBandwidthMode: false,
    measuredSpeed: 0,
    supported: false,
  });

  // Hydrate from browser APIs after mount (avoids SSR mismatch)
  useEffect(() => {
    const connection = getConnection();
    const supported = connection !== undefined;
    const effectiveType: EffectiveType = connection?.effectiveType ?? "4g";
    const downlink = connection?.downlink ?? 10;
    const rtt = connection?.rtt ?? 50;
    const saveData = connection?.saveData ?? false;
    const storedLBM = localStorage.getItem(STORAGE_KEY) === "true";

    setStatus({
      tier: storedLBM ? "low" : classifyTier(effectiveType, downlink, saveData),
      effectiveType,
      downlink,
      rtt,
      saveData,
      lowBandwidthMode: storedLBM,
      measuredSpeed: 0,
      supported,
    });
  }, []);

  // Exponential moving average for measured speed
  const measuredSpeedRef = useRef(0);

  const updateFromConnection = useCallback(() => {
    const conn = getConnection();
    const effectiveType: EffectiveType = conn?.effectiveType ?? "4g";
    const downlink = conn?.downlink ?? 10;
    const rtt = conn?.rtt ?? 50;
    const saveData = conn?.saveData ?? false;

    setStatus((prev) => ({
      ...prev,
      effectiveType,
      downlink,
      rtt,
      saveData,
      tier: prev.lowBandwidthMode
        ? "low"
        : classifyTier(effectiveType, downlink, saveData),
    }));
  }, []);

  // Listen for connection changes
  useEffect(() => {
    const conn = getConnection();
    if (!conn) return;

    conn.addEventListener("change", updateFromConnection);
    return () => conn.removeEventListener("change", updateFromConnection);
  }, [updateFromConnection]);

  // Toggle low-bandwidth mode
  const setLowBandwidthMode = useCallback((enabled: boolean) => {
    localStorage.setItem(STORAGE_KEY, String(enabled));

    setStatus((prev) => ({
      ...prev,
      lowBandwidthMode: enabled,
      tier: enabled
        ? "low"
        : classifyTier(prev.effectiveType, prev.downlink, prev.saveData),
    }));
  }, []);

  // Report measured transfer speed (called from WebSocket chunk handler)
  const reportTransferSpeed = useCallback((bytesPerSec: number) => {
    // EMA with α = 0.3 — smooths spikes while tracking trends
    const alpha = 0.3;
    measuredSpeedRef.current =
      measuredSpeedRef.current === 0
        ? bytesPerSec
        : alpha * bytesPerSec + (1 - alpha) * measuredSpeedRef.current;

    const measuredMbps = (measuredSpeedRef.current * 8) / 1_000_000;

    setStatus((prev) => {
      // Reclassify tier if measured speed diverges significantly from reported downlink
      const effectiveDownlink = Math.min(prev.downlink, measuredMbps);
      const newTier = prev.lowBandwidthMode
        ? ("low" as NetworkTier)
        : classifyTier(prev.effectiveType, effectiveDownlink, prev.saveData);

      return {
        ...prev,
        measuredSpeed: measuredSpeedRef.current,
        tier: newTier,
      };
    });
  }, []);

  return {
    ...status,
    setLowBandwidthMode,
    reportTransferSpeed,
  };
}
