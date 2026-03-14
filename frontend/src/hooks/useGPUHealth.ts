/* ─────────────────────────────────────────────
 * AuraGen — GPU Health Hook
 * Polls /api/health-check on mount and exposes
 * the GPU diagnostic state for recovery UI.
 * ───────────────────────────────────────────── */

"use client";

import { useEffect, useState, useCallback } from "react";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api";

export interface GPUHealth {
  backend: string;       // "cuda" | "directml" | "cpu" | "none"
  deviceName: string;
  vramMb: number;
  cudaAvailable: boolean;
  directmlAvailable: boolean;
  driverInstalled: boolean;
  cudaError: string;
  healthy: boolean;
  warnings: string[];
}

export type GPUStatus = "loading" | "healthy" | "degraded" | "offline";

interface UseGPUHealthReturn {
  status: GPUStatus;
  gpu: GPUHealth | null;
  error: string | null;
  retry: () => void;
}

const EMPTY_GPU: GPUHealth = {
  backend: "none",
  deviceName: "",
  vramMb: 0,
  cudaAvailable: false,
  directmlAvailable: false,
  driverInstalled: false,
  cudaError: "",
  healthy: false,
  warnings: [],
};

export function useGPUHealth(): UseGPUHealthReturn {
  const [status, setStatus] = useState<GPUStatus>("loading");
  const [gpu, setGPU] = useState<GPUHealth | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetch_ = useCallback(async () => {
    setStatus("loading");
    setError(null);

    try {
      const res = await fetch(`${API_BASE}/health-check`, {
        signal: AbortSignal.timeout(5000),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      const g = data.gpu ?? {};
      const health: GPUHealth = {
        backend: g.backend ?? "none",
        deviceName: g.device_name ?? "",
        vramMb: g.vram_mb ?? 0,
        cudaAvailable: g.cuda_available ?? false,
        directmlAvailable: g.directml_available ?? false,
        driverInstalled: g.driver_installed ?? false,
        cudaError: g.cuda_error ?? "",
        healthy: g.healthy ?? false,
        warnings: g.warnings ?? [],
      };

      setGPU(health);
      setStatus(
        health.backend === "cuda"
          ? "healthy"
          : health.healthy
            ? "degraded"
            : "offline",
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Backend unreachable");
      setGPU(EMPTY_GPU);
      setStatus("offline");
    }
  }, []);

  useEffect(() => {
    fetch_();
  }, [fetch_]);

  return { status, gpu, error, retry: fetch_ };
}
