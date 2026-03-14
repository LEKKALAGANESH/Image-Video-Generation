/* ─────────────────────────────────────────────
 * AuraGen — Core Type Definitions
 * ───────────────────────────────────────────── */

export type GenerationMode = "image" | "video" | "pose";

export interface GenerationParams {
  width: number;
  height: number;
  steps: number;
  guidance_scale: number;
  seed: number | null;
  frames?: number; // video-only
  controlnet_scale?: number; // pose-only
  pose_image?: string; // pose-only
}

export interface GenerationRequest {
  prompt: string;
  negative_prompt: string;
  mode: GenerationMode;
  params: GenerationParams;
}

export type JobStatus =
  | "queued"
  | "processing"
  | "completed"
  | "failed"
  | "cancelled";

export interface GenerationJob {
  job_id: string;
  prompt: string;
  negative_prompt: string;
  mode: GenerationMode;
  params: GenerationParams;
  status: JobStatus;
  progress: number; // 0–100
  result_url?: string;
  thumbnail_url?: string;
  error?: string;
  created_at: string;
  completed_at?: string;
}

export interface CanvasItem {
  id: string;
  job: GenerationJob;
  position: { x: number; y: number };
  size: { width: number; height: number };
  depth?: number;
}

export interface WebSocketMessage {
  type: "progress" | "complete" | "completed" | "error" | "failed" | "cancelled" | "queued";
  job_id: string;
  /** Nested payload sent by the backend for progress/complete/error messages. */
  data?: {
    status?: string;
    progress?: number;
    message?: string;
    result_url?: string;
  };
  /** Legacy top-level fields (kept for backward compatibility). */
  progress?: number;
  result_url?: string;
  thumbnail_url?: string;
  error?: string;
}

export interface ApiError {
  detail: string;
  status: number;
}

/* ── Network-Aware Delivery Types ──────────── */

/** Quality tiers driven by real-time bandwidth detection. */
export type NetworkTier = "low" | "medium" | "high";

/** Effective connection type from navigator.connection API. */
export type EffectiveType = "slow-2g" | "2g" | "3g" | "4g";

/** Real-time network status snapshot. */
export interface NetworkStatus {
  /** Current quality tier (derived from effectiveType + downlink). */
  tier: NetworkTier;
  /** Raw effective connection type from the browser. */
  effectiveType: EffectiveType;
  /** Estimated downlink speed in Mbps. */
  downlink: number;
  /** Round-trip time estimate in ms. */
  rtt: number;
  /** Whether data-saver mode is enabled on the device. */
  saveData: boolean;
  /** User override: force low-bandwidth mode regardless of detection. */
  lowBandwidthMode: boolean;
  /** Measured transfer speed from last chunk (bytes/sec), 0 if unknown. */
  measuredSpeed: number;
  /** Whether the browser supports the Network Information API. */
  supported: boolean;
}

/** Extended WebSocket message with chunk metadata for bandwidth measurement. */
export interface ChunkedWebSocketMessage extends WebSocketMessage {
  /** Byte size of the payload for transfer speed calculation. */
  chunk_bytes?: number;
  /** Server-side timestamp (ISO) when this chunk was emitted. */
  server_ts?: string;
  /** Preview URL (compressed version for low-bandwidth clients). */
  preview_url?: string;
}

/** Media delivery variant returned by the backend. */
export interface MediaVariant {
  /** Full-resolution URL. */
  full_url: string;
  /** Compressed preview URL (JPEG q30, max 480px). */
  preview_url: string;
  /** Thumbnail URL (JPEG q20, max 128px). */
  thumb_url: string;
  /** File size in bytes of the full-resolution asset. */
  full_size_bytes: number;
  /** File size in bytes of the preview. */
  preview_size_bytes: number;
  /** MIME type of the full-res asset. */
  media_type: string;
}
