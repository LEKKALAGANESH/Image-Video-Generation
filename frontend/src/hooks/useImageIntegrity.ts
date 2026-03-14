/* ─────────────────────────────────────────────
 * AuraGen — Image Integrity Check Hook
 * Detects blank / solid-color images that
 * indicate a failed inference (dtype mismatch,
 * OOM truncation, etc.) and returns a warning.
 * ───────────────────────────────────────────── */

"use client";

import { useEffect, useState } from "react";

export type IntegrityStatus = "idle" | "checking" | "pass" | "blank";

/**
 * Samples an image URL to detect if the output is a solid color or blank.
 *
 * Draws the image on an offscreen canvas, samples a grid of pixels, and
 * checks if all sampled pixels are near-identical (within `tolerance`).
 *
 * @param imageUrl - URL of the generated image (or null/undefined)
 * @returns { status, dominantColor } — "blank" means solid-color output
 */
export function useImageIntegrity(imageUrl: string | null | undefined): {
  status: IntegrityStatus;
  dominantColor: string | null;
} {
  const [status, setStatus] = useState<IntegrityStatus>("idle");
  const [dominantColor, setDominantColor] = useState<string | null>(null);

  useEffect(() => {
    if (!imageUrl) {
      setStatus("idle");
      setDominantColor(null);
      return;
    }

    // Only check image files, not video
    if (imageUrl.endsWith(".mp4") || imageUrl.endsWith(".webm")) {
      setStatus("pass");
      return;
    }

    setStatus("checking");

    const img = new Image();
    img.crossOrigin = "anonymous";

    img.onload = () => {
      try {
        const canvas = document.createElement("canvas");
        // Downsample to 32x32 for fast analysis
        const size = 32;
        canvas.width = size;
        canvas.height = size;
        const ctx = canvas.getContext("2d");
        if (!ctx) {
          setStatus("pass");
          return;
        }

        ctx.drawImage(img, 0, 0, size, size);
        const data = ctx.getImageData(0, 0, size, size).data;

        // Sample first pixel as reference
        const refR = data[0];
        const refG = data[1];
        const refB = data[2];

        // Check if all pixels are within tolerance of the reference
        const tolerance = 12; // per channel (0-255)
        let uniformCount = 0;
        const totalPixels = size * size;

        for (let i = 0; i < data.length; i += 4) {
          const dr = Math.abs(data[i] - refR);
          const dg = Math.abs(data[i + 1] - refG);
          const db = Math.abs(data[i + 2] - refB);
          if (dr <= tolerance && dg <= tolerance && db <= tolerance) {
            uniformCount++;
          }
        }

        // If 95%+ of pixels match the reference → it's a solid/blank image
        const ratio = uniformCount / totalPixels;
        if (ratio >= 0.95) {
          setStatus("blank");
          setDominantColor(`rgb(${refR}, ${refG}, ${refB})`);
        } else {
          setStatus("pass");
          setDominantColor(null);
        }
      } catch {
        // Canvas tainted or other error — assume pass
        setStatus("pass");
      }
    };

    img.onerror = () => {
      // Can't load image — don't block, just pass
      setStatus("pass");
    };

    img.src = imageUrl;
  }, [imageUrl]);

  return { status, dominantColor };
}
