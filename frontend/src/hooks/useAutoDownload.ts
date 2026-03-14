/* ─────────────────────────────────────────────
 * AuraGen — Auto-Download Hook
 * Automatically streams completed job outputs
 * into OPFS via the DownloadManager. Exposes
 * phase/percent for ThreePhaseProgress display.
 * ───────────────────────────────────────────── */

"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import {
  downloadToLocal,
  getLocalFileURL,
  getAsset,
  type DownloadPhase,
  type DownloadProgress,
} from "@/lib/download-manager";
import { resolveMediaUrl } from "@/lib/media-url";
import { promptToFilename } from "@/lib/prompt-to-name";
import type { GenerationJob } from "@/types";

interface UseAutoDownloadReturn {
  /** Current download phase. */
  phase: DownloadPhase;
  /** Download progress 0–100. */
  percent: number;
  /** Local object URL once download completes (or from cache). */
  localUrl: string | null;
}

/**
 * Watches a generation job. When it transitions to "completed" with a
 * result_url, automatically downloads it to OPFS and tracks progress.
 *
 * If the asset already exists in the local gallery (from a previous
 * session), it resolves instantly without re-downloading.
 */
/**
 * Trigger a browser download to the user's Downloads folder.
 * Uses a hidden <a download> element for cross-browser compatibility.
 */
function triggerBrowserDownload(url: string, filename: string): void {
  try {
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.style.display = "none";
    document.body.appendChild(a);
    a.click();
    // Clean up after a short delay
    setTimeout(() => {
      document.body.removeChild(a);
    }, 100);
  } catch (err) {
    console.warn("[AuraGen] Browser download trigger failed:", err);
  }
}

export function useAutoDownload(job: GenerationJob): UseAutoDownloadReturn {
  const [phase, setPhase] = useState<DownloadPhase>("idle");
  const [percent, setPercent] = useState(0);
  const [localUrl, setLocalUrl] = useState<string | null>(null);
  const downloadStarted = useRef(false);

  const handleProgress = useCallback((p: DownloadProgress) => {
    setPhase(p.phase);
    setPercent(p.percent);
  }, []);

  useEffect(() => {
    // Only act on completed jobs with a result URL
    if (job.status !== "completed" || !job.result_url) return;
    // Only start once per job
    if (downloadStarted.current) return;
    downloadStarted.current = true;

    let cancelled = false;

    (async () => {
      // Extract filename from result_url (e.g. "/outputs/abc.png" → "abc.png")
      const filename = job.result_url!.split("/").pop();
      if (!filename) return;

      // Check if already cached locally
      try {
        const existing = await getAsset(job.job_id);
        if (existing?.persisted) {
          const cached = await getLocalFileURL(existing.filename);
          if (cached && !cancelled) {
            setLocalUrl(cached);
            setPhase("ready");
            setPercent(100);
            return;
          }
        }
      } catch {
        // Not cached — proceed with download
      }

      if (cancelled) return;

      try {
        const url = await downloadToLocal(
          job.job_id,
          filename,
          job.prompt,
          handleProgress,
        );
        if (!cancelled) {
          setLocalUrl(url);
          // Notify the app that generation content is ready
          try {
            window.dispatchEvent(new CustomEvent("auragen:generation-complete", { detail: { jobId: job.job_id } }));
          } catch { /* SSR guard */ }
          // Trigger browser download to the user's Downloads folder
          const downloadName = promptToFilename(job.prompt, job.mode, job.job_id);
          triggerBrowserDownload(url, downloadName);
        }
      } catch (err) {
        console.warn("[AuraGen] Auto-download failed:", err);
        // Fallback: try direct browser download from backend URL
        if (!cancelled && job.result_url) {
          const resolvedUrl = resolveMediaUrl(job.result_url);
          const fallbackName = promptToFilename(job.prompt, job.mode, job.job_id);
          if (resolvedUrl) triggerBrowserDownload(resolvedUrl, fallbackName);
          setPhase("idle");
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [job.status, job.result_url, job.job_id, job.prompt, handleProgress]);

  // Revoke the object URL when the component unmounts to free browser RAM
  useEffect(() => {
    return () => {
      if (localUrl) {
        try { URL.revokeObjectURL(localUrl); } catch { /* already revoked */ }
      }
    };
  }, [localUrl]);

  return { phase, percent, localUrl };
}
