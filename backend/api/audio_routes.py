"""
AuraGen -- Audio API routes.

Endpoints
---------
POST /api/audio/generate   -- Generate ambient audio from a text prompt.
POST /api/audio/attach     -- Mux audio onto a video file (stub).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from core.config import settings
from services.audio_synth_service import AudioSynthService

logger = logging.getLogger("auragen.audio")

router = APIRouter(prefix="/api/audio", tags=["audio"])

# Module-level service singleton.
_audio_service: Optional[AudioSynthService] = None


def _get_service() -> AudioSynthService:
    """Return (and optionally create) the audio synth service singleton."""
    global _audio_service
    if _audio_service is None:
        _audio_service = AudioSynthService()
    return _audio_service


# ═════════════════════════════════════════════════════════════════════════════
# Request / Response models
# ═════════════════════════════════════════════════════════════════════════════


class AudioGenerateRequest(BaseModel):
    """Payload for ``POST /api/audio/generate``."""

    prompt: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Text prompt describing the desired mood/environment.",
    )
    duration_seconds: float = Field(
        default=10.0,
        ge=1.0,
        le=120.0,
        description="Duration of the generated audio in seconds.",
    )


class AudioGenerateResponse(BaseModel):
    """Response from ``POST /api/audio/generate``."""

    audio_url: str = Field(
        ..., description="URL path to the generated audio file."
    )
    duration_seconds: float = Field(
        ..., description="Actual duration of the generated audio."
    )
    mood: str = Field(
        default="default", description="Detected mood category."
    )
    message: str = Field(
        default="Audio generated successfully.",
        description="Human-readable status message.",
    )


class AudioAttachRequest(BaseModel):
    """Payload for ``POST /api/audio/attach``."""

    video_path: str = Field(
        ...,
        min_length=1,
        description="Path or filename of the video to attach audio to.",
    )
    audio_path: str = Field(
        ...,
        min_length=1,
        description="Path or filename of the audio file to attach.",
    )


class AudioAttachResponse(BaseModel):
    """Response from ``POST /api/audio/attach``."""

    video_path: str = Field(
        ..., description="Path to the input video."
    )
    audio_path: str = Field(
        ..., description="Path to the input audio."
    )
    output_path: Optional[str] = Field(
        default=None,
        description="Path to the muxed output (None until implemented).",
    )
    message: str = Field(
        default="Audio attachment is not yet implemented.",
        description="Human-readable status message.",
    )


# ═════════════════════════════════════════════════════════════════════════════
# POST /api/audio/generate
# ═════════════════════════════════════════════════════════════════════════════


@router.post(
    "/generate",
    response_model=AudioGenerateResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate ambient audio from a text prompt.",
)
async def generate_audio(req: AudioGenerateRequest) -> AudioGenerateResponse:
    """Analyse the prompt, synthesise ambient audio, and return a download URL.

    The audio is generated synchronously in a thread pool so the event loop
    is not blocked.
    """
    service = _get_service()

    filename = f"{uuid.uuid4().hex}.wav"
    output_dir = settings.output_path / "audio"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = str(output_dir / filename)

    try:
        mood_info = service.analyze_prompt_mood(req.prompt)
        await asyncio.to_thread(
            service.generate_ambient,
            req.prompt,
            req.duration_seconds,
            output_file,
        )
    except Exception as exc:
        logger.exception("Audio generation failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Audio generation error: {exc}",
        )

    audio_url = f"/outputs/audio/{filename}"

    return AudioGenerateResponse(
        audio_url=audio_url,
        duration_seconds=req.duration_seconds,
        mood=mood_info["mood_name"],
        message="Audio generated successfully.",
    )


# ═════════════════════════════════════════════════════════════════════════════
# POST /api/audio/attach
# ═════════════════════════════════════════════════════════════════════════════


@router.post(
    "/attach",
    response_model=AudioAttachResponse,
    status_code=status.HTTP_200_OK,
    summary="Attach audio to a video file (stub).",
)
async def attach_audio(req: AudioAttachRequest) -> AudioAttachResponse:
    """Mux an audio track onto a video file.

    .. note::
        This is a stub endpoint. Full muxing (e.g., via ffmpeg) will be
        implemented in a future release. For now it validates the paths and
        returns them unchanged.
    """
    logger.info(
        "Audio attach requested: video=%s  audio=%s",
        req.video_path,
        req.audio_path,
    )

    return AudioAttachResponse(
        video_path=req.video_path,
        audio_path=req.audio_path,
        output_path=None,
        message="Audio attachment is not yet implemented. Paths returned for reference.",
    )
