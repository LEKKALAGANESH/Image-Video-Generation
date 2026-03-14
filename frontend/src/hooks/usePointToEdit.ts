/**
 * AuraGen -- usePointToEdit hook.
 *
 * Encapsulates all state and side-effects for the Point-to-Edit workflow:
 *   1. Enter / exit edit mode
 *   2. Capture a click point and request SAM segmentation
 *   3. Receive and store the mask
 *   4. Submit an edit (replace / remove / style / describe)
 *   5. Fetch contextual AI suggestions
 */

import { useCallback, useEffect, useRef, useState } from "react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface BoundingBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface SegmentResult {
  mask_url: string;
  bbox: BoundingBox;
  confidence: number;
  segment_label: string | null;
}

export interface EditSuggestion {
  label: string;
  prompt: string;
  edit_type: "replace" | "remove" | "style" | "describe";
  icon: string;
}

export type EditType = "replace" | "remove" | "style" | "describe";

export interface PointToEditState {
  /** Whether the overlay is active and accepting clicks. */
  editMode: boolean;
  /** Last clicked point (normalised 0-1). */
  selectedPoint: { x: number; y: number } | null;
  /** Mask returned by SAM (or null if not yet received). */
  currentMask: SegmentResult | null;
  /** True while the segmentation request is in flight. */
  isSegmenting: boolean;
  /** True while an edit is being applied. */
  isApplying: boolean;
  /** The user's natural-language edit prompt. */
  editPrompt: string;
  /** AI-suggested edits for the selected point. */
  suggestions: EditSuggestion[];
  /** Error message, if any. */
  error: string | null;
}

export interface PointToEditActions {
  enterEditMode: () => void;
  exitEditMode: () => void;
  selectPoint: (x: number, y: number) => Promise<void>;
  setEditPrompt: (prompt: string) => void;
  applyEdit: (prompt: string, editType: EditType) => Promise<string | null>;
  clearSelection: () => void;
  fetchSuggestions: (x: number, y: number) => Promise<void>;
}

// ---------------------------------------------------------------------------
// API helpers
// ---------------------------------------------------------------------------

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function apiSegment(
  imagePath: string,
  x: number,
  y: number,
): Promise<SegmentResult> {
  const res = await fetch(`${API_BASE}/api/edit/segment`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ image_path: imagePath, x, y }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "Segmentation failed");
  }
  return res.json();
}

async function apiApplyEdit(
  imagePath: string,
  maskUrl: string,
  prompt: string,
  editType: EditType,
  style?: string,
): Promise<{ job_id: string }> {
  const res = await fetch(`${API_BASE}/api/edit/apply`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      image_path: imagePath,
      mask_url: maskUrl,
      prompt,
      edit_type: editType,
      ...(style ? { style } : {}),
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "Edit failed");
  }
  return res.json();
}

async function apiFetchSuggestions(
  imagePath: string,
  x: number,
  y: number,
): Promise<EditSuggestion[]> {
  const params = new URLSearchParams({
    image_path: imagePath,
    x: x.toFixed(4),
    y: y.toFixed(4),
  });
  const res = await fetch(`${API_BASE}/api/edit/suggestions?${params}`);
  if (!res.ok) return [];
  const data = await res.json();
  return data.suggestions ?? [];
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function usePointToEdit(imagePath: string): PointToEditState & PointToEditActions {
  const [editMode, setEditMode] = useState(false);
  const [selectedPoint, setSelectedPoint] = useState<{ x: number; y: number } | null>(null);
  const [currentMask, setCurrentMask] = useState<SegmentResult | null>(null);
  const [isSegmenting, setIsSegmenting] = useState(false);
  const [isApplying, setIsApplying] = useState(false);
  const [editPrompt, setEditPrompt] = useState("");
  const [suggestions, setSuggestions] = useState<EditSuggestion[]>([]);
  const [error, setError] = useState<string | null>(null);

  // Abort controller ref for cancelling in-flight requests on unmount / mode change.
  const abortRef = useRef<AbortController | null>(null);

  // Reset everything when edit mode is exited.
  const clearSelection = useCallback(() => {
    setSelectedPoint(null);
    setCurrentMask(null);
    setIsSegmenting(false);
    setIsApplying(false);
    setEditPrompt("");
    setSuggestions([]);
    setError(null);
  }, []);

  const enterEditMode = useCallback(() => {
    clearSelection();
    setEditMode(true);
  }, [clearSelection]);

  const exitEditMode = useCallback(() => {
    abortRef.current?.abort();
    setEditMode(false);
    clearSelection();
  }, [clearSelection]);

  // Escape key exits edit mode.
  useEffect(() => {
    if (!editMode) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") exitEditMode();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [editMode, exitEditMode]);

  // ------- selectPoint -------

  const selectPoint = useCallback(
    async (x: number, y: number) => {
      if (!editMode) return;
      setError(null);
      setSelectedPoint({ x, y });
      setCurrentMask(null);
      setIsSegmenting(true);
      setSuggestions([]);

      try {
        const [segResult, sugResult] = await Promise.all([
          apiSegment(imagePath, x, y),
          apiFetchSuggestions(imagePath, x, y),
        ]);
        setCurrentMask(segResult);
        setSuggestions(sugResult);
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : "Segmentation failed";
        setError(msg);
      } finally {
        setIsSegmenting(false);
      }
    },
    [editMode, imagePath],
  );

  // ------- applyEdit -------

  const applyEdit = useCallback(
    async (prompt: string, editType: EditType): Promise<string | null> => {
      if (!currentMask) {
        setError("No region selected");
        return null;
      }
      setIsApplying(true);
      setError(null);
      try {
        const result = await apiApplyEdit(
          imagePath,
          currentMask.mask_url,
          prompt,
          editType,
        );
        return result.job_id;
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : "Edit failed";
        setError(msg);
        return null;
      } finally {
        setIsApplying(false);
      }
    },
    [currentMask, imagePath],
  );

  // ------- fetchSuggestions -------

  const fetchSuggestions = useCallback(
    async (x: number, y: number) => {
      const results = await apiFetchSuggestions(imagePath, x, y);
      setSuggestions(results);
    },
    [imagePath],
  );

  return {
    // state
    editMode,
    selectedPoint,
    currentMask,
    isSegmenting,
    isApplying,
    editPrompt,
    suggestions,
    error,
    // actions
    enterEditMode,
    exitEditMode,
    selectPoint,
    setEditPrompt,
    applyEdit,
    clearSelection,
    fetchSuggestions,
  };
}
