"""
AuraGen -- Pydantic request / response schemas for the edit (Point-to-Edit) API.

These models handle SAM segmentation requests, edit application, and
AI-suggested edits for selected image regions.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# =============================================================================
# Enums
# =============================================================================

class EditType(str, Enum):
    """Supported edit operations on a segmented region."""

    REPLACE = "replace"
    REMOVE = "remove"
    STYLE = "style"
    DESCRIBE = "describe"


# =============================================================================
# Segment (SAM) — POST /api/edit/segment
# =============================================================================

class SegmentRequest(BaseModel):
    """Payload for requesting SAM segmentation at a specific point."""

    image_path: str = Field(
        ...,
        min_length=1,
        description="Server-side path or URL of the image to segment.",
    )
    x: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Normalised x coordinate of the click point (0-1).",
    )
    y: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Normalised y coordinate of the click point (0-1).",
    )


class BoundingBox(BaseModel):
    """Axis-aligned bounding box around the segmented region."""

    x: float = Field(..., description="Left edge (normalised 0-1).")
    y: float = Field(..., description="Top edge (normalised 0-1).")
    width: float = Field(..., description="Width (normalised 0-1).")
    height: float = Field(..., description="Height (normalised 0-1).")


class SegmentResponse(BaseModel):
    """Result of a SAM segmentation call."""

    mask_url: str = Field(
        ...,
        description="URL to the generated mask image (PNG, white = selected).",
    )
    bbox: BoundingBox = Field(
        ...,
        description="Bounding box of the segmented region.",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Model confidence score for this segmentation.",
    )
    segment_label: Optional[str] = Field(
        default=None,
        description="Optional semantic label for the detected segment.",
    )


# =============================================================================
# Apply Edit — POST /api/edit/apply
# =============================================================================

class EditRequest(BaseModel):
    """Payload to queue an edit job on a segmented region."""

    image_path: str = Field(
        ...,
        min_length=1,
        description="Server-side path or URL of the source image.",
    )
    mask_url: str = Field(
        ...,
        min_length=1,
        description="URL of the mask (as returned by /segment).",
    )
    prompt: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Natural-language description of the desired edit.",
    )
    edit_type: EditType = Field(
        ...,
        description="Category of edit to perform.",
    )
    style: Optional[str] = Field(
        default=None,
        max_length=200,
        description="Target style when edit_type is 'style'.",
    )


class EditResponse(BaseModel):
    """Acknowledgement after an edit job has been queued."""

    job_id: str = Field(
        ...,
        description="Unique identifier for the queued edit job.",
    )
    message: str = Field(
        default="Edit job queued successfully.",
        description="Human-readable status message.",
    )


# =============================================================================
# Suggestions — GET /api/edit/suggestions
# =============================================================================

class Suggestion(BaseModel):
    """A single AI-suggested edit."""

    label: str = Field(..., description="Short label for the suggestion.")
    prompt: str = Field(..., description="Ready-to-use prompt text.")
    edit_type: EditType = Field(..., description="Recommended edit type.")
    icon: str = Field(
        default="sparkles",
        description="Lucide icon name for the frontend.",
    )


class SuggestionRequest(BaseModel):
    """Query parameters for fetching edit suggestions."""

    image_path: str = Field(
        ...,
        min_length=1,
        description="Server-side path or URL of the image.",
    )
    x: float = Field(..., ge=0.0, le=1.0, description="Normalised x coordinate.")
    y: float = Field(..., ge=0.0, le=1.0, description="Normalised y coordinate.")


class SuggestionResponse(BaseModel):
    """List of AI-suggested edits for the selected region."""

    suggestions: list[Suggestion] = Field(
        default_factory=list,
        description="Ordered list of suggested edits.",
    )
