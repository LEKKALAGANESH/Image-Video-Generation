/* ─────────────────────────────────────────────
 * AuraGen — API Client
 * ───────────────────────────────────────────── */

import type {
  GenerationJob,
  GenerationMode,
  GenerationParams,
  NetworkTier,
  ApiError,
} from "@/types";

const BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api";

/* ── Network tier state (set by useNetworkStatus) ── */

let _currentNetworkTier: NetworkTier = "high";

/** Called by the app root to keep the API client in sync with the network hook. */
export function setNetworkTier(tier: NetworkTier): void {
  _currentNetworkTier = tier;
}

export function getNetworkTier(): NetworkTier {
  return _currentNetworkTier;
}

/* ── helpers ────────────────────────────────── */

/** Extra fetch options for high-priority generation requests. */
const HIGH_PRIORITY_OPTIONS: RequestInit = {
  priority: "high",
};

async function request<T>(
  path: string,
  options?: RequestInit,
  /** When true, adds browser priority hints so the request is scheduled ahead of other network activity. */
  highPriority = false,
): Promise<T> {
  const url = `${BASE_URL}${path}`;

  const priorityHeaders: Record<string, string> = highPriority
    ? { Importance: "high" }
    : {};

  const res = await fetch(url, {
    ...(highPriority ? HIGH_PRIORITY_OPTIONS : {}),
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-Network-Tier": _currentNetworkTier,
      ...priorityHeaders,
      ...(options?.headers ?? {}),
    },
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    const err: ApiError = {
      detail: body.detail ?? "An unknown error occurred",
      status: res.status,
    };
    throw err;
  }

  return res.json() as Promise<T>;
}

/* ── response types ─────────────────────────── */

/** What the backend actually returns from /generate/* endpoints */
interface GenerationSubmitResponse {
  job_id: string;
  status: string;
  message: string;
  queue_position: number;
}

/* ── public api ─────────────────────────────── */

export async function generateImage(params: {
  prompt: string;
  negative_prompt: string;
  params: GenerationParams;
}): Promise<GenerationSubmitResponse> {
  return request<GenerationSubmitResponse>("/generate/image", {
    method: "POST",
    body: JSON.stringify(params),
  }, true);
}

export async function generateVideo(params: {
  prompt: string;
  negative_prompt: string;
  params: GenerationParams;
}): Promise<GenerationSubmitResponse> {
  return request<GenerationSubmitResponse>("/generate/video", {
    method: "POST",
    body: JSON.stringify(params),
  }, true);
}

export async function getJobStatus(jobId: string): Promise<GenerationJob> {
  return request<GenerationJob>(`/jobs/${jobId}`);
}

export async function cancelJob(jobId: string): Promise<{ message: string }> {
  return request<{ message: string }>(`/jobs/${jobId}/cancel`, {
    method: "POST",
  });
}

export async function listJobs(
  mode?: GenerationMode
): Promise<GenerationJob[]> {
  const query = mode ? `?mode=${mode}` : "";
  return request<GenerationJob[]>(`/jobs${query}`);
}

export async function generatePose(params: {
  prompt: string;
  negative_prompt: string;
  params: GenerationParams;
}): Promise<GenerationSubmitResponse> {
  return request<GenerationSubmitResponse>("/generate/pose-to-image", {
    method: "POST",
    body: JSON.stringify(params),
  }, true);
}

export async function generateAudio(
  prompt: string,
  duration: number
): Promise<GenerationJob> {
  return request<GenerationJob>("/audio/generate", {
    method: "POST",
    body: JSON.stringify({ prompt, duration }),
  }, true);
}

export type { GenerationSubmitResponse };
