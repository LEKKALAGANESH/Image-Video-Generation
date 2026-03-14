/* ─────────────────────────────────────────────
 * AuraGen — Generation Store (Zustand)
 * Central state management for the generation
 * pipeline, canvas items, and UI state.
 * ───────────────────────────────────────────── */

"use client";

import { create } from "zustand";
import type {
  GenerationMode,
  GenerationParams,
  GenerationJob,
  CanvasItem,
  WebSocketMessage,
} from "@/types";
import { generateImage, generateVideo, generatePose, cancelJob as apiCancelJob } from "@/lib/api";

/* ── types ──────────────────────────────────── */

interface GenerationState {
  // Generation parameters
  mode: GenerationMode;
  prompt: string;
  negativePrompt: string;
  params: GenerationParams;

  // Job tracking
  jobs: Map<string, GenerationJob>;
  currentJobId: string | null;
  isGenerating: boolean;

  // Canvas
  canvasItems: CanvasItem[];

  // Pose
  poseImage: string | null;

  // Voice
  voiceActive: boolean;

  // Command bar
  commandBarOpen: boolean;

  // Lightbox
  lightboxJobId: string | null;

  // Actions
  setMode: (mode: GenerationMode) => void;
  setPoseImage: (image: string | null) => void;
  setVoiceActive: (active: boolean) => void;
  setPrompt: (prompt: string) => void;
  setNegativePrompt: (negativePrompt: string) => void;
  setParams: (params: Partial<GenerationParams>) => void;
  submitGeneration: () => Promise<void>;
  updateJobFromWS: (message: WebSocketMessage) => void;
  cancelJob: (jobId: string) => Promise<void>;
  removeCanvasItem: (id: string) => void;
  updateCanvasItemPosition: (id: string, x: number, y: number) => void;
  setCommandBarOpen: (open: boolean) => void;
  submitFromCommandBar: (prompt: string) => Promise<void>;
  randomizeSeed: () => void;
  setLightboxJobId: (id: string | null) => void;
}

/* ── default params ─────────────────────────── */

const DEFAULT_IMAGE_PARAMS: GenerationParams = {
  width: 512,
  height: 512,
  steps: 4,
  guidance_scale: 0.0,
  seed: null,
};

const DEFAULT_VIDEO_PARAMS: GenerationParams = {
  width: 480,
  height: 320,
  steps: 20,
  guidance_scale: 5.0,
  seed: null,
  frames: 17,
};

const DEFAULT_POSE_PARAMS: GenerationParams = {
  width: 512,
  height: 768,
  steps: 20,
  guidance_scale: 7.5,
  seed: null,
  controlnet_scale: 1.0,
};

/* ── constants ─────────────────────────────── */

/** Maximum jobs to keep in memory. Oldest completed/failed jobs are pruned. */
const MAX_JOBS = 20;

function pruneJobs(jobs: Map<string, GenerationJob>): Map<string, GenerationJob> {
  if (jobs.size <= MAX_JOBS) return jobs;
  // Sort entries: active jobs first (keep), then by newest first
  const entries = [...jobs.entries()].sort(([, a], [, b]) => {
    const aActive = a.status === "processing" || a.status === "queued" ? 1 : 0;
    const bActive = b.status === "processing" || b.status === "queued" ? 1 : 0;
    if (aActive !== bActive) return bActive - aActive;
    return (b.completed_at ?? b.created_at ?? "").localeCompare(
      a.completed_at ?? a.created_at ?? "",
    );
  });
  return new Map(entries.slice(0, MAX_JOBS));
}

/* ── store ──────────────────────────────────── */

export const useGenerationStore = create<GenerationState>((set, get) => ({
  mode: "image",
  prompt: "",
  negativePrompt: "",
  params: { ...DEFAULT_IMAGE_PARAMS },
  jobs: new Map(),
  currentJobId: null,
  isGenerating: false,
  canvasItems: [],
  poseImage: null,
  voiceActive: false,
  commandBarOpen: false,
  lightboxJobId: null,

  setMode: (mode) => {
    const defaults =
      mode === "image"
        ? DEFAULT_IMAGE_PARAMS
        : mode === "video"
          ? DEFAULT_VIDEO_PARAMS
          : DEFAULT_POSE_PARAMS;
    set({ mode, params: { ...defaults } });
  },

  setPoseImage: (image) => set({ poseImage: image }),

  setVoiceActive: (active) => set({ voiceActive: active }),

  setPrompt: (prompt) => set({ prompt }),

  setNegativePrompt: (negativePrompt) => set({ negativePrompt }),

  setParams: (partial) =>
    set((s) => ({ params: { ...s.params, ...partial } })),

  randomizeSeed: () =>
    set((s) => ({
      params: {
        ...s.params,
        seed: Math.floor(Math.random() * 2_147_483_647),
      },
    })),

  submitGeneration: async () => {
    const { mode, prompt, negativePrompt, params } = get();
    if (!prompt.trim() || get().isGenerating) return;

    set({ isGenerating: true });

    try {
      const apiFn =
        mode === "image"
          ? generateImage
          : mode === "video"
            ? generateVideo
            : generatePose;

      const submitParams = { ...params };
      if (mode === "pose") {
        const poseImage = get().poseImage;
        if (poseImage) {
          submitParams.pose_image = poseImage;
        }
      }

      // API returns only { job_id, status, message, queue_position }
      // Construct the full GenerationJob from known store state
      const apiResponse = await apiFn({
        prompt: prompt.trim(),
        negative_prompt: negativePrompt.trim(),
        params: submitParams,
      });

      const fullJob: GenerationJob = {
        job_id: apiResponse.job_id,
        prompt: prompt.trim(),
        negative_prompt: negativePrompt.trim(),
        mode,
        params: { ...submitParams },
        status: "queued",
        progress: 0,
        created_at: new Date().toISOString(),
      };

      const jobs = new Map(get().jobs);
      jobs.set(fullJob.job_id, fullJob);

      // Auto-arrange in rough grid to avoid overlap
      const existingCount = get().canvasItems.length;
      const col = existingCount % 3;
      const row = Math.floor(existingCount / 3);
      const canvasItem: CanvasItem = {
        id: fullJob.job_id,
        job: fullJob,
        position: {
          x: 40 + col * 360,
          y: 40 + row * 340,
        },
        size: { width: Math.max(params.width / 1.5, 280), height: Math.max(params.height / 1.5, 200) },
      };

      set({
        jobs,
        currentJobId: fullJob.job_id,
        canvasItems: [...get().canvasItems, canvasItem],
      });
    } catch (err) {
      console.error("[AuraGen] Generation failed:", err);
      set({ isGenerating: false });
    }
  },

  updateJobFromWS: (message) => {
    set((state) => {
      const existing = state.jobs.get(message.job_id);
      if (!existing) return state;

      // ── Normalise backend message types to frontend status ──────────
      // Backend sends: "progress", "complete", "error"
      // Frontend expects: "processing", "completed", "failed", "cancelled"
      const msgType = message.type;
      const isComplete = msgType === "complete" || msgType === "completed";
      const isFailed = msgType === "error" || msgType === "failed";
      const isProgress = msgType === "progress";
      const isCancelled = msgType === "cancelled";

      const newStatus: GenerationJob["status"] = isProgress
        ? "processing"
        : isComplete
          ? "completed"
          : isFailed
            ? "failed"
            : isCancelled
              ? "cancelled"
              : existing.status;

      // ── Extract progress/result_url/error from nested data or top-level ──
      const data = message.data;
      const newProgress =
        data?.progress ?? message.progress ?? existing.progress;
      const newResultUrl =
        data?.result_url ?? message.result_url ?? existing.result_url;
      const newError =
        (isFailed ? data?.message : undefined) ??
        message.error ??
        existing.error;

      // Log every progress change
      if (newProgress !== existing.progress) {
        console.log(`[AuraGen] Job ${message.job_id.slice(0, 8)}… progress: ${existing.progress}% → ${newProgress}%`);
      }
      if (newStatus !== existing.status) {
        console.log(`[AuraGen] Job ${message.job_id.slice(0, 8)}… status: ${existing.status} → ${newStatus}`);
      }

      // Skip update if nothing meaningful changed
      if (
        newStatus === existing.status &&
        newProgress === existing.progress &&
        newResultUrl === existing.result_url &&
        newError === existing.error
      ) {
        return state;
      }

      const updated: GenerationJob = {
        ...existing,
        status: newStatus,
        progress: newProgress,
        result_url: newResultUrl,
        thumbnail_url: message.thumbnail_url ?? existing.thumbnail_url,
        error: newError,
        completed_at:
          isComplete || isFailed
            ? new Date().toISOString()
            : existing.completed_at,
      };

      const jobs = new Map(state.jobs);
      jobs.set(message.job_id, updated);

      const canvasItems = state.canvasItems.map((item) =>
        item.id === message.job_id ? { ...item, job: updated } : item
      );

      const isStillGenerating = !isComplete && !isFailed && !isCancelled;

      return {
        jobs: isStillGenerating ? jobs : pruneJobs(jobs),
        canvasItems,
        isGenerating:
          state.currentJobId === message.job_id
            ? isStillGenerating
            : state.isGenerating,
      };
    });
  },

  cancelJob: async (jobId) => {
    try {
      await apiCancelJob(jobId);
      const jobs = new Map(get().jobs);
      const existing = jobs.get(jobId);
      if (existing) {
        jobs.set(jobId, { ...existing, status: "cancelled" });
      }
      set({
        jobs,
        isGenerating:
          get().currentJobId === jobId ? false : get().isGenerating,
      });
    } catch (err) {
      console.error("[AuraGen] Cancel failed:", err);
    }
  },

  removeCanvasItem: (id) =>
    set((s) => {
      const jobs = new Map(s.jobs);
      jobs.delete(id);
      return {
        canvasItems: s.canvasItems.filter((item) => item.id !== id),
        jobs,
      };
    }),

  updateCanvasItemPosition: (id, x, y) =>
    set((s) => ({
      canvasItems: s.canvasItems.map((item) =>
        item.id === id ? { ...item, position: { x, y } } : item
      ),
    })),

  setCommandBarOpen: (open) => set({ commandBarOpen: open }),

  setLightboxJobId: (id) => set({ lightboxJobId: id }),

  submitFromCommandBar: async (prompt) => {
    set({ prompt, commandBarOpen: false });
    // Small delay so the UI updates before submitting
    await new Promise((r) => setTimeout(r, 50));
    get().submitGeneration();
  },
}));
