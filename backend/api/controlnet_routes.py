"""
AuraGen -- ControlNet API routes (pose-to-image generation).

Endpoints
---------
POST /api/generate/pose-to-image  -- Generate an image conditioned on a pose skeleton.
POST /api/pose/detect             -- Detect a pose skeleton from a source image (stub).
"""

from __future__ import annotations

import asyncio
import base64
import logging
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from core.config import settings
from inference.controlnet_pipeline import ControlNetPipeline

logger = logging.getLogger("auragen.controlnet")

router = APIRouter(prefix="/api", tags=["controlnet"])

# Module-level pipeline singleton (lazy-loaded on first request).
_controlnet_pipeline: ControlNetPipeline | None = None


def _get_pipeline() -> ControlNetPipeline:
    """Return (and optionally create + load) the ControlNet pipeline."""
    global _controlnet_pipeline
    if _controlnet_pipeline is None:
        _controlnet_pipeline = ControlNetPipeline(settings)
        _controlnet_pipeline.load()
    return _controlnet_pipeline


# ═════════════════════════════════════════════════════════════════════════════
# Request / Response schemas
# ═════════════════════════════════════════════════════════════════════════════


class PoseToImageRequest(BaseModel):
    """Payload for ``POST /api/generate/pose-to-image``."""

    prompt: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Text prompt describing the desired image.",
    )
    pose_image: str = Field(
        ...,
        min_length=1,
        description=(
            "Pose / skeleton image.  Can be a base64-encoded string "
            "(optionally with a ``data:image/...;base64,`` prefix) or "
            "an absolute file path on the server."
        ),
    )
    negative_prompt: str = Field(
        default="",
        max_length=2000,
        description="Things to avoid in the generated image.",
    )
    width: int = Field(
        default=512, ge=64, le=768, description="Image width in pixels."
    )
    height: int = Field(
        default=512, ge=64, le=768, description="Image height in pixels."
    )
    num_steps: int = Field(
        default=20, ge=1, le=100, description="Number of inference steps."
    )
    guidance_scale: float = Field(
        default=7.5,
        ge=1.0,
        le=30.0,
        description="Classifier-free guidance scale.",
    )
    controlnet_scale: float = Field(
        default=1.0,
        ge=0.0,
        le=2.0,
        description="ControlNet conditioning strength.",
    )
    seed: Optional[int] = Field(
        default=None,
        description="Random seed for reproducibility (None = random).",
    )


class PoseToImageResponse(BaseModel):
    """Returned when a pose-to-image job is accepted."""

    job_id: str = Field(..., description="Unique identifier for the job.")
    status: str = Field(default="pending", description="Current status.")
    message: str = Field(
        default="Pose-to-image generation job queued.",
        description="Human-readable status message.",
    )


class PoseDetectRequest(BaseModel):
    """Payload for ``POST /api/pose/detect``."""

    image_path: str = Field(
        ...,
        min_length=1,
        description="Path to the source image on the server.",
    )


class PoseDetectResponse(BaseModel):
    """Returned by the pose detection endpoint."""

    pose_image_path: str = Field(
        ...,
        description=(
            "Path to the detected pose skeleton image.  "
            "(Stub: returns the original image path.)"
        ),
    )
    message: str = Field(
        default="Pose detection complete.",
        description="Human-readable status message.",
    )


# ═════════════════════════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════════════════════════


def _resolve_pose_image(pose_image: str) -> str:
    """Resolve the pose image from a base64 string or file path.

    If *pose_image* looks like base64, decode it and write to a temporary
    file.  Otherwise treat it as a file path.

    Returns
    -------
    str
        Absolute path to the pose image on disk.

    Raises
    ------
    HTTPException
        If the image cannot be resolved.
    """
    # Strip optional data-URI prefix.
    raw: str = pose_image
    if raw.startswith("data:"):
        # e.g. "data:image/png;base64,iVBORw0KGgo..."
        try:
            raw = raw.split(",", 1)[1]
        except IndexError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Malformed data-URI for pose_image.",
            )

    # Try base64 decode.
    try:
        image_bytes: bytes = base64.b64decode(raw, validate=True)
        if len(image_bytes) < 8:
            raise ValueError("Decoded data too short to be an image.")

        # Write to a temp file.
        suffix: str = ".png"
        tmp_dir: Path = settings.output_path / "poses"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        tmp_path: Path = tmp_dir / f"pose_{uuid.uuid4().hex}{suffix}"
        tmp_path.write_bytes(image_bytes)
        logger.info("Base64 pose image written to %s", tmp_path)
        return str(tmp_path)

    except Exception:
        pass  # Not base64 -- try as file path.

    # Treat as file path.
    candidate = Path(pose_image)
    if candidate.is_file():
        return str(candidate.resolve())

    # Try relative to output dir.
    candidate2 = settings.output_path / pose_image.lstrip("/")
    if candidate2.is_file():
        return str(candidate2.resolve())

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Pose image not found: {pose_image}",
    )


# ═════════════════════════════════════════════════════════════════════════════
# POST /api/generate/pose-to-image
# ═════════════════════════════════════════════════════════════════════════════


@router.post(
    "/generate/pose-to-image",
    response_model=PoseToImageResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Generate an image from a pose skeleton",
    responses={
        404: {"description": "Pose image not found"},
        422: {"description": "Invalid request payload"},
        500: {"description": "Generation failed"},
    },
)
async def generate_pose_to_image(
    req: PoseToImageRequest,
) -> PoseToImageResponse:
    """Accept a pose-to-image request, run ControlNet inference, and return a job ID.

    The inference is dispatched to a background thread so the event loop is
    not blocked.  For simplicity this endpoint currently runs the inference
    synchronously in that thread and returns the result inline as
    ``job_id`` (the filename can be retrieved via ``GET /api/outputs/{job_id}``).
    """
    pose_path: str = _resolve_pose_image(req.pose_image)
    job_id: str = uuid.uuid4().hex

    try:
        pipeline: ControlNetPipeline = await asyncio.to_thread(_get_pipeline)

        result_filename: str = await asyncio.to_thread(
            pipeline.generate_from_pose,
            prompt=req.prompt,
            pose_image_path=pose_path,
            negative_prompt=req.negative_prompt,
            width=req.width,
            height=req.height,
            num_steps=req.num_steps,
            guidance_scale=req.guidance_scale,
            controlnet_scale=req.controlnet_scale,
            seed=req.seed,
            progress_callback=None,
        )

        return PoseToImageResponse(
            job_id=job_id,
            status="completed",
            message=f"Pose-to-image generation complete. Result: /api/outputs/{result_filename}",
        )

    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Generation failed: {exc}",
        )
    except Exception as exc:
        logger.exception("Unexpected error in pose-to-image generation")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error: {exc}",
        )


# ═════════════════════════════════════════════════════════════════════════════
# POST /api/pose/detect
# ═════════════════════════════════════════════════════════════════════════════


@router.post(
    "/pose/detect",
    response_model=PoseDetectResponse,
    status_code=status.HTTP_200_OK,
    summary="Detect pose skeleton from an image (stub)",
    responses={
        404: {"description": "Image not found"},
    },
)
async def detect_pose(req: PoseDetectRequest) -> PoseDetectResponse:
    """Extract a pose skeleton from a source image.

    .. note::

        This is a **stub** for Phase 3.  It currently returns the original
        image path unchanged.  In production this will use MediaPipe or
        OpenPose to extract a skeleton.
    """
    image_path = Path(req.image_path)

    # Also check relative to output dir.
    if not image_path.is_file():
        candidate = settings.output_path / req.image_path.lstrip("/")
        if candidate.is_file():
            image_path = candidate
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Image not found: {req.image_path}",
            )

    # Stub: use the pipeline's detect_pose (which just returns the input).
    pipeline: ControlNetPipeline = await asyncio.to_thread(_get_pipeline)
    pose_path: str = await asyncio.to_thread(
        pipeline.detect_pose, str(image_path.resolve())
    )

    return PoseDetectResponse(
        pose_image_path=pose_path,
        message="Pose detection complete (stub -- returned original image).",
    )
