"""
AuraGen — Pydantic request / response schemas for every API endpoint.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ═════════════════════════════════════════════════════════════════════════════
# Enums
# ═════════════════════════════════════════════════════════════════════════════

class JobType(str, Enum):
    IMAGE = "image"
    VIDEO = "video"


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ═════════════════════════════════════════════════════════════════════════════
# Request models
# ═════════════════════════════════════════════════════════════════════════════

class ImageGenerationRequest(BaseModel):
    """Payload accepted by ``POST /generate/image``."""

    prompt: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Text prompt describing the desired image.",
    )
    negative_prompt: str = Field(
        default="",
        max_length=2000,
        description="Things to avoid in the generated image.",
    )
    width: int = Field(default=512, ge=64, le=768, description="Image width in pixels.")
    height: int = Field(default=512, ge=64, le=768, description="Image height in pixels.")
    num_steps: int = Field(default=4, ge=1, le=100, description="Number of inference steps.")
    guidance_scale: float = Field(
        default=0.0, ge=0.0, le=30.0, description="Classifier-free guidance scale."
    )
    seed: Optional[int] = Field(
        default=None, description="Random seed for reproducibility (None = random)."
    )


class VideoGenerationRequest(BaseModel):
    """Payload accepted by ``POST /generate/video``."""

    prompt: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Text prompt describing the desired video.",
    )
    negative_prompt: str = Field(
        default="",
        max_length=2000,
        description="Things to avoid in the generated video.",
    )
    width: int = Field(default=480, ge=64, le=480, description="Video width in pixels.")
    height: int = Field(default=320, ge=64, le=480, description="Video height in pixels.")
    num_frames: int = Field(
        default=33, ge=1, le=33, description="Number of video frames to generate."
    )
    num_steps: int = Field(default=20, ge=1, le=100, description="Number of inference steps.")
    guidance_scale: float = Field(
        default=7.5, ge=1.0, le=30.0, description="Classifier-free guidance scale."
    )
    seed: Optional[int] = Field(
        default=None, description="Random seed for reproducibility (None = random)."
    )


# ═════════════════════════════════════════════════════════════════════════════
# Response models
# ═════════════════════════════════════════════════════════════════════════════

class GenerationResponse(BaseModel):
    """Returned immediately when a generation request is accepted."""

    job_id: str = Field(..., description="Unique identifier for the queued job.")
    status: JobStatus = Field(..., description="Current status (will be 'pending').")
    message: str = Field(
        default="Job queued successfully.",
        description="Human-readable status message.",
    )
    queue_position: int = Field(
        default=0, description="Approximate position in the queue (0 = next up)."
    )


class JobResponse(BaseModel):
    """Full snapshot of a job — returned by ``GET /jobs/{job_id}``."""

    job_id: str
    job_type: JobType
    prompt: str
    negative_prompt: str
    status: JobStatus
    progress: int = Field(default=0, ge=0, le=100, description="Completion percentage.")
    result_url: Optional[str] = Field(
        default=None, description="URL to the generated artifact (when completed)."
    )
    error: Optional[str] = Field(
        default=None, description="Error message (when failed)."
    )
    created_at: datetime
    params: dict[str, Any] = Field(default_factory=dict)


class JobStatusResponse(BaseModel):
    """Lightweight status view."""

    job_id: str
    status: JobStatus
    progress: int = 0


class HealthResponse(BaseModel):
    """Response from the health-check endpoint."""

    status: str = "ok"
    version: str = "0.1.0"
    queue_size: int = 0
    active_connections: int = 0


class GPUHealthResponse(BaseModel):
    """Detailed GPU diagnostics for the frontend to display recovery UI."""

    status: str = "ok"
    version: str = "0.1.0"
    queue_size: int = 0
    active_connections: int = 0
    gpu: dict = Field(default_factory=dict, description="GPU diagnostic report")


class ErrorResponse(BaseModel):
    """Generic error envelope."""

    detail: str
