"""
AuraGen -- Edit API routes (Point-to-Edit / SAM2 integration).

Endpoints
---------
POST /api/edit/segment     -- Run SAM2 segmentation at a click point.
POST /api/edit/apply       -- Queue an edit job (inpaint, replace, style, etc.).
GET  /api/edit/suggestions -- Fetch AI-suggested edits for a selected region.

The routes bridge the frontend's normalised (0-1) coordinate space to the
SegmentationService's pixel-space API, persist masks as PNGs, and compute
normalised bounding boxes for the overlay UI.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import uuid
from pathlib import Path
from typing import Annotated

import numpy as np
from fastapi import APIRouter, HTTPException, Query, status
from PIL import Image

from api.edit_schemas import (
    BoundingBox,
    EditRequest,
    EditResponse,
    EditType,
    SegmentRequest,
    SegmentResponse,
    Suggestion,
    SuggestionResponse,
)
from core.config import settings
from services.segmentation_service import SegmentationService

logger = logging.getLogger("auragen.edit")

router = APIRouter(prefix="/api/edit", tags=["edit"])

# Module-level service singleton (lazy-loaded on first request).
_segmentation_service: SegmentationService | None = None


def _get_service() -> SegmentationService:
    """Return (and optionally create + load) the segmentation service."""
    global _segmentation_service
    if _segmentation_service is None:
        _segmentation_service = SegmentationService()
        _segmentation_service.load()
    return _segmentation_service


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _masks_dir() -> Path:
    """Return the directory where mask PNGs are stored, creating it if needed."""
    d = settings.output_path / "masks"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _resolve_image_path(image_path: str) -> Path:
    """Resolve an image path that may be absolute or relative to /outputs."""
    p = Path(image_path)
    if p.is_absolute() and p.exists():
        return p
    # Try relative to the outputs directory.
    candidate = settings.output_path / image_path.lstrip("/")
    if candidate.exists():
        return candidate
    # Strip a leading /outputs/ prefix if present.
    stripped = image_path.replace("/outputs/", "", 1)
    candidate2 = settings.output_path / stripped
    if candidate2.exists():
        return candidate2
    raise FileNotFoundError(f"Image not found: {image_path}")


def _mask_filename(image_path: str, x: float, y: float) -> str:
    """Deterministic filename for a mask based on image + point."""
    key = f"{image_path}:{x:.6f}:{y:.6f}"
    digest = hashlib.sha256(key.encode()).hexdigest()[:16]
    return f"mask_{digest}.png"


def _bbox_from_mask(mask: np.ndarray) -> BoundingBox:
    """Compute a normalised (0-1) bounding box from a uint8 mask."""
    h, w = mask.shape[:2]
    rows = np.any(mask > 127, axis=1)
    cols = np.any(mask > 127, axis=0)

    if not rows.any():
        return BoundingBox(x=0.0, y=0.0, width=0.0, height=0.0)

    rmin = int(np.argmax(rows))
    rmax = int(h - np.argmax(rows[::-1]) - 1)
    cmin = int(np.argmax(cols))
    cmax = int(w - np.argmax(cols[::-1]) - 1)

    return BoundingBox(
        x=round(cmin / w, 4),
        y=round(rmin / h, 4),
        width=round((cmax - cmin) / w, 4),
        height=round((rmax - rmin) / h, 4),
    )


def _mask_confidence(mask: np.ndarray) -> float:
    """Estimate a confidence score from the mask.

    When SAM2 returns a real mask the score comes from the model. For the
    placeholder fallback we derive a rough heuristic from coverage area.
    """
    total = mask.size
    foreground = int(np.sum(mask > 127))
    if foreground == 0:
        return 0.0
    # Score biased toward medium-sized selections.
    ratio = foreground / total
    return round(min(0.98, 0.5 + ratio * 2.0), 4)


# =============================================================================
# POST /api/edit/segment
# =============================================================================

@router.post(
    "/segment",
    response_model=SegmentResponse,
    status_code=status.HTTP_200_OK,
    summary="Segment the region around a click point using SAM2.",
)
async def segment_image(payload: SegmentRequest) -> SegmentResponse:
    """Accept normalised click coordinates and return a segmentation mask.

    The backend converts normalised coordinates to pixel space, runs the
    SegmentationService, persists the mask as a PNG, and returns the mask
    URL with a normalised bounding box.
    """
    # Resolve the image and read its dimensions.
    try:
        abs_path = _resolve_image_path(payload.image_path)
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Image not found: {payload.image_path}",
        )

    try:
        img = Image.open(abs_path)
        img_w, img_h = img.size
        img.close()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Cannot read image: {exc}",
        )

    # Convert normalised coords to pixel coords.
    px = int(payload.x * img_w)
    py = int(payload.y * img_h)

    # Run segmentation in a thread pool so we don't block the event loop.
    service = _get_service()
    try:
        mask_np: np.ndarray = await asyncio.to_thread(
            service.segment_at_point,
            str(abs_path),
            px,
            py,
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Image not found: {payload.image_path}",
        )
    except Exception as exc:
        logger.exception("Segmentation failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Segmentation error: {exc}",
        )

    # Persist the mask as a PNG.
    mask_fname = _mask_filename(payload.image_path, payload.x, payload.y)
    mask_path = _masks_dir() / mask_fname
    mask_img = Image.fromarray(mask_np, mode="L")
    mask_img.save(str(mask_path), format="PNG")

    mask_url = f"/outputs/masks/{mask_fname}"
    bbox = _bbox_from_mask(mask_np)
    confidence = _mask_confidence(mask_np)

    return SegmentResponse(
        mask_url=mask_url,
        bbox=bbox,
        confidence=confidence,
        segment_label=None,
    )


# =============================================================================
# POST /api/edit/apply
# =============================================================================

@router.post(
    "/apply",
    response_model=EditResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue an edit job on a segmented region.",
)
async def apply_edit(payload: EditRequest) -> EditResponse:
    """Validate the edit request and enqueue it for processing.

    The actual inference (inpainting / style transfer / removal) is handled
    asynchronously by the job queue. This endpoint returns immediately with
    a ``job_id`` the client can poll or subscribe to via WebSocket.
    """
    # Verify the mask file exists.
    try:
        _resolve_image_path(payload.mask_url)
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Mask not found: {payload.mask_url}",
        )

    job_id = str(uuid.uuid4())

    # TODO: push to the real job queue (same pattern as generation jobs).
    # For now we log and return the job_id so the frontend flow is complete.
    logger.info(
        "Edit job queued: job_id=%s  type=%s  prompt=%r",
        job_id,
        payload.edit_type.value,
        payload.prompt[:80],
    )

    return EditResponse(
        job_id=job_id,
        message=f"Edit job ({payload.edit_type.value}) queued successfully.",
    )


# =============================================================================
# GET /api/edit/suggestions
# =============================================================================

# Placeholder suggestion catalogue.  In production this would be generated
# dynamically by analysing the selected region via CLIP or a VLM.
_DEFAULT_SUGGESTIONS: list[Suggestion] = [
    Suggestion(
        label="Remove object",
        prompt="Remove this object and fill with the surrounding background",
        edit_type=EditType.REMOVE,
        icon="eraser",
    ),
    Suggestion(
        label="Change colour",
        prompt="Change the colour of this region",
        edit_type=EditType.REPLACE,
        icon="palette",
    ),
    Suggestion(
        label="Enhance detail",
        prompt="Enhance the detail and sharpness of this region",
        edit_type=EditType.DESCRIBE,
        icon="sparkles",
    ),
    Suggestion(
        label="Apply cinematic style",
        prompt="Apply a cinematic colour grade with dramatic lighting",
        edit_type=EditType.STYLE,
        icon="film",
    ),
    Suggestion(
        label="Make it glow",
        prompt="Add a soft ethereal glow to this area",
        edit_type=EditType.STYLE,
        icon="sun",
    ),
]


@router.get(
    "/suggestions",
    response_model=SuggestionResponse,
    status_code=status.HTTP_200_OK,
    summary="Get AI-suggested edits for a region.",
)
async def get_suggestions(
    image_path: Annotated[
        str, Query(min_length=1, description="Path to the source image.")
    ],
    x: Annotated[
        float, Query(ge=0.0, le=1.0, description="Normalised x coordinate.")
    ],
    y: Annotated[
        float, Query(ge=0.0, le=1.0, description="Normalised y coordinate.")
    ],
) -> SuggestionResponse:
    """Return contextual edit suggestions for the clicked point.

    Currently uses a static catalogue. In production this would analyse the
    image region (via CLIP or a similar model) and generate targeted prompts.
    """
    logger.info(
        "Suggestions requested for %s at (%.3f, %.3f)", image_path, x, y
    )
    return SuggestionResponse(suggestions=_DEFAULT_SUGGESTIONS)
