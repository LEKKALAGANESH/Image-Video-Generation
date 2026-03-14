/**
 * AuraGen -- SegmentOverlay (mask visualisation layer).
 *
 * Renders a semi-transparent coloured overlay on top of a generated image to
 * visualise the SAM2 segmentation mask. Supports:
 *   - Mask from a URL (PNG, white = foreground) or a raw 2D array
 *   - Smooth fade-in animation via Framer Motion
 *   - Adjustable overlay opacity and colour
 *   - Colour-coding for different segment indices
 *   - Hover effect that intensifies the segment boundary
 */

"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";

// ---------------------------------------------------------------------------
// Colour palette for multi-segment colour coding
// ---------------------------------------------------------------------------

const SEGMENT_COLOURS: readonly string[] = [
  "rgba(139, 92, 246, ALPHA)",   // violet-500
  "rgba(59, 130, 246, ALPHA)",   // blue-500
  "rgba(236, 72, 153, ALPHA)",   // pink-500
  "rgba(16, 185, 129, ALPHA)",   // emerald-500
  "rgba(245, 158, 11, ALPHA)",   // amber-500
  "rgba(239, 68, 68, ALPHA)",    // red-500
  "rgba(99, 102, 241, ALPHA)",   // indigo-500
  "rgba(14, 165, 233, ALPHA)",   // sky-500
];

function segmentColour(index: number, alpha: number): string {
  const template = SEGMENT_COLOURS[index % SEGMENT_COLOURS.length];
  return template.replace("ALPHA", alpha.toFixed(2));
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface SegmentOverlayProps {
  /** URL to a mask PNG (white = selected) returned by the segmentation API. */
  maskUrl?: string | null;
  /** Alternative: raw 2D mask data (0-255). Takes precedence over maskUrl. */
  maskData?: number[][] | null;
  /** Overlay opacity when not hovered (0-1). Default: 0.35 */
  opacity?: number;
  /** Overlay opacity on hover (0-1). Default: 0.55 */
  hoverOpacity?: number;
  /** Colour-coding index (for multi-segment scenarios). Default: 0 */
  segmentIndex?: number;
  /** Dimensions of the parent image (needed for canvas sizing). */
  width: number;
  height: number;
  /** Additional CSS class. */
  className?: string;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function SegmentOverlay({
  maskUrl,
  maskData,
  opacity = 0.35,
  hoverOpacity = 0.55,
  segmentIndex = 0,
  width,
  height,
  className = "",
}: SegmentOverlayProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [isHovered, setIsHovered] = useState(false);
  const [loaded, setLoaded] = useState(false);

  const activeOpacity = isHovered ? hoverOpacity : opacity;

  // Resolve colours.
  const fillColour = useMemo(() => segmentColour(segmentIndex, activeOpacity), [segmentIndex, activeOpacity]);
  const borderColour = useMemo(() => segmentColour(segmentIndex, Math.min(1, activeOpacity + 0.3)), [segmentIndex, activeOpacity]);

  // ------- Draw mask from raw 2D array -------

  const drawFromData = useCallback(
    (data: number[][]) => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;

      canvas.width = width;
      canvas.height = height;
      ctx.clearRect(0, 0, width, height);

      const imgData = ctx.createImageData(width, height);

      // Parse the target fill colour components.
      const match = fillColour.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
      const [r, g, b] = match ? [+match[1], +match[2], +match[3]] : [139, 92, 246];

      for (let row = 0; row < Math.min(data.length, height); row++) {
        for (let col = 0; col < Math.min(data[row].length, width); col++) {
          const val = data[row][col];
          if (val > 127) {
            const idx = (row * width + col) * 4;
            imgData.data[idx] = r;
            imgData.data[idx + 1] = g;
            imgData.data[idx + 2] = b;
            imgData.data[idx + 3] = Math.round(activeOpacity * 255);
          }
        }
      }
      ctx.putImageData(imgData, 0, 0);

      // Draw boundary glow.
      drawBoundary(ctx, imgData, width, height, borderColour);
      setLoaded(true);
    },
    [width, height, fillColour, borderColour, activeOpacity],
  );

  // ------- Draw mask from URL (PNG image) -------

  const drawFromUrl = useCallback(
    (url: string) => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;

      const img = new window.Image();
      img.crossOrigin = "anonymous";
      img.onload = () => {
        canvas.width = width;
        canvas.height = height;
        ctx.clearRect(0, 0, width, height);

        // Draw the mask image to an offscreen canvas to read pixel data.
        const offscreen = document.createElement("canvas");
        offscreen.width = width;
        offscreen.height = height;
        const offCtx = offscreen.getContext("2d")!;
        offCtx.drawImage(img, 0, 0, width, height);
        const maskPixels = offCtx.getImageData(0, 0, width, height);

        const imgData = ctx.createImageData(width, height);
        const match = fillColour.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
        const [r, g, b] = match ? [+match[1], +match[2], +match[3]] : [139, 92, 246];

        for (let i = 0; i < maskPixels.data.length; i += 4) {
          // Use the red channel of the mask as the foreground indicator.
          if (maskPixels.data[i] > 127) {
            imgData.data[i] = r;
            imgData.data[i + 1] = g;
            imgData.data[i + 2] = b;
            imgData.data[i + 3] = Math.round(activeOpacity * 255);
          }
        }
        ctx.putImageData(imgData, 0, 0);

        drawBoundary(ctx, imgData, width, height, borderColour);
        setLoaded(true);
      };
      img.onerror = () => {
        logger("Failed to load mask image from", url);
      };

      // Resolve relative URLs against the API base.
      const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
      img.src = url.startsWith("http") ? url : `${apiBase}${url}`;
    },
    [width, height, fillColour, borderColour, activeOpacity],
  );

  // ------- Trigger drawing -------

  useEffect(() => {
    setLoaded(false);
    if (maskData) {
      drawFromData(maskData);
    } else if (maskUrl) {
      drawFromUrl(maskUrl);
    }
  }, [maskData, maskUrl, drawFromData, drawFromUrl]);

  // ------- Render -------

  if (!maskUrl && !maskData) return null;

  return (
    <motion.canvas
      ref={canvasRef}
      initial={{ opacity: 0 }}
      animate={{ opacity: loaded ? 1 : 0 }}
      transition={{ duration: 0.45, ease: "easeOut" }}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      className={`absolute inset-0 pointer-events-auto ${className}`}
      style={{ width, height, mixBlendMode: "normal" }}
      aria-hidden="true"
    />
  );
}

// ---------------------------------------------------------------------------
// Boundary edge detection (simple Sobel-like pass)
// ---------------------------------------------------------------------------

function drawBoundary(
  ctx: CanvasRenderingContext2D,
  imgData: ImageData,
  w: number,
  h: number,
  colour: string,
) {
  // Extract alpha channel as a quick binary mask.
  const alpha = new Uint8Array(w * h);
  for (let i = 0; i < w * h; i++) {
    alpha[i] = imgData.data[i * 4 + 3] > 0 ? 1 : 0;
  }

  ctx.strokeStyle = colour;
  ctx.lineWidth = 1.5;
  ctx.beginPath();

  for (let y = 1; y < h - 1; y++) {
    for (let x = 1; x < w - 1; x++) {
      if (alpha[y * w + x] === 0) continue;
      // Check 4-connected neighbours.
      const isEdge =
        alpha[(y - 1) * w + x] === 0 ||
        alpha[(y + 1) * w + x] === 0 ||
        alpha[y * w + (x - 1)] === 0 ||
        alpha[y * w + (x + 1)] === 0;
      if (isEdge) {
        ctx.rect(x, y, 1, 1);
      }
    }
  }

  ctx.stroke();
}

// ---------------------------------------------------------------------------
// Tiny logger that avoids console noise in production
// ---------------------------------------------------------------------------

function logger(...args: unknown[]) {
  if (process.env.NODE_ENV === "development") {
    // eslint-disable-next-line no-console
    console.warn("[SegmentOverlay]", ...args);
  }
}
