"""
AuraGen — Network-Aware Delivery Routes.

Provides endpoints for:
  - On-demand preview generation (``POST /api/network/preview``)
  - SSE stream with chunk-size metadata for bandwidth measurement
  - Network tier negotiation
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException, Header, Request, status
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field

from core.config import settings
from services.preview_service import generate_previews

logger = logging.getLogger("auragen.network")

router = APIRouter(tags=["network"])


# ═════════════════════════════════════════════════════════════════════════════
# Schemas
# ═════════════════════════════════════════════════════════════════════════════

class PreviewRequest(BaseModel):
    """Request to generate preview variants of an existing output."""
    filename: str = Field(..., description="Name of the file in /outputs/.")


class PreviewResponse(BaseModel):
    """URLs for the generated preview variants."""
    full_url: str
    preview_url: str | None = None
    thumb_url: str | None = None
    full_size_bytes: int = 0
    preview_size_bytes: int = 0
    media_type: str = "image/png"


class NetworkNegotiationResponse(BaseModel):
    """Server's recommendation based on the client's reported tier."""
    tier: str
    max_image_size: int
    max_video_frames: int
    enable_autoplay: bool
    serve_webp: bool


# ═════════════════════════════════════════════════════════════════════════════
# Preview generation
# ═════════════════════════════════════════════════════════════════════════════

@router.post(
    "/network/preview",
    response_model=PreviewResponse,
    summary="Generate compressed previews for an output file",
)
async def create_preview(req: PreviewRequest) -> PreviewResponse:
    """Generate thumbnail + preview variants for the given output file.

    The heavy lifting (PIL resize / ffmpeg transcode) runs in the default
    thread pool to avoid blocking the event loop.
    """
    safe_name = Path(req.filename).name
    source = settings.output_path / safe_name

    if not source.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Output file '{safe_name}' not found.",
        )

    # Run preview generation off the event loop
    loop = asyncio.get_running_loop()
    variants = await loop.run_in_executor(None, generate_previews, source)

    suffix = source.suffix.lower()
    media_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".mp4": "video/mp4",
        ".gif": "image/gif",
    }

    # File sizes
    full_size = source.stat().st_size
    preview_path_str = variants.get("preview")
    preview_size = 0
    if preview_path_str:
        preview_file = settings.output_path / Path(preview_path_str).name
        if preview_file.exists():
            preview_size = preview_file.stat().st_size

    return PreviewResponse(
        full_url=f"/outputs/{safe_name}",
        preview_url=variants.get("preview"),
        thumb_url=variants.get("thumbnail"),
        full_size_bytes=full_size,
        preview_size_bytes=preview_size,
        media_type=media_types.get(suffix, "application/octet-stream"),
    )


# ═════════════════════════════════════════════════════════════════════════════
# Network tier negotiation
# ═════════════════════════════════════════════════════════════════════════════

@router.get(
    "/network/negotiate",
    response_model=NetworkNegotiationResponse,
    summary="Negotiate delivery settings based on client network tier",
)
async def negotiate_tier(
    x_network_tier: str = Header(default="high", alias="X-Network-Tier"),
) -> NetworkNegotiationResponse:
    """Return server-side recommendations tailored to the client's network tier.

    The frontend sends its detected tier via the ``X-Network-Tier`` header;
    the backend responds with constraints and feature flags.
    """
    tier = x_network_tier.lower()
    if tier not in ("low", "medium", "high"):
        tier = "high"

    configs = {
        "low": {
            "max_image_size": 256,
            "max_video_frames": 0,      # don't auto-stream video
            "enable_autoplay": False,
            "serve_webp": True,          # smaller than PNG
        },
        "medium": {
            "max_image_size": 480,
            "max_video_frames": 16,
            "enable_autoplay": False,
            "serve_webp": True,
        },
        "high": {
            "max_image_size": settings.MAX_IMAGE_SIZE,
            "max_video_frames": settings.MAX_VIDEO_FRAMES,
            "enable_autoplay": True,
            "serve_webp": False,
        },
    }

    return NetworkNegotiationResponse(tier=tier, **configs[tier])


# ═════════════════════════════════════════════════════════════════════════════
# SSE stream with chunk-size metadata
# ═════════════════════════════════════════════════════════════════════════════

@router.get(
    "/network/stream/{filename}",
    summary="Stream a file via SSE with chunk-size metadata for bandwidth measurement",
)
async def stream_file(filename: str, request: Request) -> StreamingResponse:
    """Deliver a generated file as a chunked SSE stream.

    Each SSE event includes metadata so the frontend can calculate real
    transfer speed:

    ```
    event: chunk
    data: {"seq": 0, "bytes": 8192, "total": 245760, "ts": "..."}
    ```

    After all data chunks, a final ``event: done`` is sent.
    """
    safe_name = Path(filename).name
    file_path = settings.output_path / safe_name

    if not file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Output file '{safe_name}' not found.",
        )

    total_size = file_path.stat().st_size
    chunk_size = 8192  # 8 KB chunks for fine-grained measurement

    async def event_stream() -> AsyncGenerator[str, None]:
        seq = 0
        with open(file_path, "rb") as f:
            while True:
                # Check for client disconnect
                if await request.is_disconnected():
                    break

                chunk = f.read(chunk_size)
                if not chunk:
                    break

                # Encode binary chunk as base64 would be wasteful —
                # instead send metadata only; the client fetches the
                # actual file via the normal /outputs/ endpoint.
                event_data = json.dumps({
                    "seq": seq,
                    "bytes": len(chunk),
                    "total": total_size,
                    "ts": time.time(),
                    "progress": min(100, round(((seq + 1) * chunk_size / total_size) * 100)),
                })
                yield f"event: chunk\ndata: {event_data}\n\n"
                seq += 1

                # Small yield to prevent blocking
                await asyncio.sleep(0)

        yield f"event: done\ndata: {json.dumps({'total_bytes': total_size, 'chunks': seq})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
