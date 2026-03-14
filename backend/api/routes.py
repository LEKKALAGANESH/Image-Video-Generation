"""
AuraGen — API route definitions.

All routes are grouped under an ``APIRouter`` which is included by
``main.py`` with the ``/api`` prefix.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, Request, status
from fastapi.responses import FileResponse, StreamingResponse

from api.schemas import (
    ErrorResponse,
    GenerationResponse,
    GPUHealthResponse,
    HealthResponse,
    ImageGenerationRequest,
    JobResponse,
    JobStatus,
    JobType,
    VideoGenerationRequest,
)
from core.config import settings
from backend_queue.job_queue import Job, JobQueue, job_queue
from backend_queue.job_queue import JobStatus as QueueJobStatus
from backend_queue.job_queue import JobType as QueueJobType
from websocket.manager import manager as ws_manager

logger = logging.getLogger("auragen.api")

router = APIRouter()


# ═════════════════════════════════════════════════════════════════════════════
# Health
# ═════════════════════════════════════════════════════════════════════════════

@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    tags=["system"],
)
async def health_check() -> HealthResponse:
    """Return basic service health information."""
    return HealthResponse(
        status="ok",
        version="0.1.0",
        queue_size=job_queue.queue_size,
        active_connections=ws_manager.active_count,
    )


@router.get(
    "/health-check",
    response_model=GPUHealthResponse,
    summary="Detailed health check with GPU diagnostics",
    tags=["system"],
)
async def health_check_detailed() -> GPUHealthResponse:
    """Return service health plus full GPU diagnostic report.

    The frontend uses this to decide whether to show a
    "Driver Update Required" toast or "GPU Recovery Mode" UI.
    """
    from core.gpu_diagnostics import get_diagnostics

    diag = get_diagnostics()
    gpu_status = "ok" if diag.healthy else "degraded"

    return GPUHealthResponse(
        status=gpu_status,
        version="0.1.0",
        queue_size=job_queue.queue_size,
        active_connections=ws_manager.active_count,
        gpu=diag.to_dict(),
    )


# ═════════════════════════════════════════════════════════════════════════════
# Image generation
# ═════════════════════════════════════════════════════════════════════════════

@router.post(
    "/generate/image",
    response_model=GenerationResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue an image generation job",
    tags=["generation"],
    responses={
        429: {"model": ErrorResponse, "description": "Queue is full"},
    },
)
async def generate_image(req: ImageGenerationRequest) -> GenerationResponse:
    """Accept an image-generation request and place it on the job queue.

    The response is returned **immediately** — the caller should poll
    ``GET /jobs/{job_id}`` or listen on the WebSocket for progress updates.
    """
    # Clamp dimensions to configured maximum.
    width = min(req.width, settings.MAX_IMAGE_SIZE)
    height = min(req.height, settings.MAX_IMAGE_SIZE)

    job = Job(
        type=QueueJobType.IMAGE,
        prompt=req.prompt,
        negative_prompt=req.negative_prompt,
        params={
            "width": width,
            "height": height,
            "num_steps": req.num_steps,
            "guidance_scale": req.guidance_scale,
            "seed": req.seed,
        },
    )

    try:
        await job_queue.submit(job)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Generation queue is full. Please try again later.",
        )

    return GenerationResponse(
        job_id=job.id,
        status=JobStatus.PENDING,
        message="Image generation job queued successfully.",
        queue_position=job_queue.queue_size,
    )


# ═════════════════════════════════════════════════════════════════════════════
# Video generation
# ═════════════════════════════════════════════════════════════════════════════

@router.post(
    "/generate/video",
    response_model=GenerationResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue a video generation job",
    tags=["generation"],
    responses={
        429: {"model": ErrorResponse, "description": "Queue is full"},
    },
)
async def generate_video(req: VideoGenerationRequest) -> GenerationResponse:
    """Accept a video-generation request and place it on the job queue."""
    width = min(req.width, settings.MAX_VIDEO_SIZE)
    height = min(req.height, settings.MAX_VIDEO_SIZE)
    num_frames = min(req.num_frames, settings.MAX_VIDEO_FRAMES)

    job = Job(
        type=QueueJobType.VIDEO,
        prompt=req.prompt,
        negative_prompt=req.negative_prompt,
        params={
            "width": width,
            "height": height,
            "num_frames": num_frames,
            "num_steps": req.num_steps,
            "guidance_scale": req.guidance_scale,
            "seed": req.seed,
        },
    )

    try:
        await job_queue.submit(job)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Generation queue is full. Please try again later.",
        )

    return GenerationResponse(
        job_id=job.id,
        status=JobStatus.PENDING,
        message="Video generation job queued successfully.",
        queue_position=job_queue.queue_size,
    )


# ═════════════════════════════════════════════════════════════════════════════
# Job management
# ═════════════════════════════════════════════════════════════════════════════

@router.get(
    "/jobs/{job_id}",
    response_model=JobResponse,
    summary="Get job status",
    tags=["jobs"],
    responses={
        404: {"model": ErrorResponse, "description": "Job not found"},
    },
)
async def get_job(job_id: str) -> JobResponse:
    """Return the full state of a generation job."""
    job = job_queue.get_status(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found.",
        )
    return JobResponse(
        job_id=job.id,
        job_type=JobType(job.type.value),
        prompt=job.prompt,
        negative_prompt=job.negative_prompt,
        status=JobStatus(job.status.value),
        progress=job.progress,
        result_url=job.result_url,
        error=job.error,
        created_at=job.created_at,
        params=job.params,
    )


@router.post(
    "/jobs/{job_id}/cancel",
    response_model=JobResponse,
    summary="Cancel a job",
    tags=["jobs"],
    responses={
        404: {"model": ErrorResponse, "description": "Job not found"},
        409: {"model": ErrorResponse, "description": "Job cannot be cancelled"},
    },
)
async def cancel_job(job_id: str) -> JobResponse:
    """Request cancellation of a queued or running job."""
    cancelled = await job_queue.cancel(job_id)
    if not cancelled:
        job = job_queue.get_status(job_id)
        if job is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job '{job_id}' not found.",
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Job '{job_id}' cannot be cancelled (status: {job.status.value}).",
        )

    job = job_queue.get_status(job_id)
    assert job is not None  # we just cancelled it, so it must exist
    return JobResponse(
        job_id=job.id,
        job_type=JobType(job.type.value),
        prompt=job.prompt,
        negative_prompt=job.negative_prompt,
        status=JobStatus(job.status.value),
        progress=job.progress,
        result_url=job.result_url,
        error=job.error,
        created_at=job.created_at,
        params=job.params,
    )


# ═════════════════════════════════════════════════════════════════════════════
# Chunked streaming output (OPFS-friendly)
# ═════════════════════════════════════════════════════════════════════════════

STREAM_CHUNK_SIZE = 64 * 1024  # 64 KB chunks


@router.head(
    "/stream/{filename}",
    summary="Probe file size and Range support",
    tags=["outputs"],
    responses={
        404: {"model": ErrorResponse, "description": "File not found"},
    },
)
async def stream_output_head(filename: str) -> StreamingResponse:
    """Return file metadata for parallel chunk download probing.

    The frontend's ``downloadWithParallelChunks`` sends a HEAD request
    to discover ``Content-Length`` and ``Accept-Ranges`` support before
    deciding whether to use parallel Range-based downloads.
    """
    import os

    safe_name = Path(filename).name
    file_path = settings.output_path / safe_name

    if not file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Output file '{safe_name}' not found.",
        )

    file_size = os.path.getsize(file_path)
    suffix = file_path.suffix.lower()
    media_types = {
        ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".webp": "image/webp", ".mp4": "video/mp4", ".gif": "image/gif",
    }
    media_type = media_types.get(suffix, "application/octet-stream")

    # Return empty body with metadata headers
    return StreamingResponse(
        iter([]),
        media_type=media_type,
        headers={
            "Content-Length": str(file_size),
            "Accept-Ranges": "bytes",
            "X-File-Size": str(file_size),
        },
    )


@router.get(
    "/stream/{filename}",
    summary="Stream a generated file in chunks",
    tags=["outputs"],
    responses={
        404: {"model": ErrorResponse, "description": "File not found"},
    },
)
async def stream_output(filename: str, request: Request) -> StreamingResponse:
    """Stream a generated file using chunked transfer encoding.

    Supports HTTP Range requests for parallel chunk downloads.  When a
    ``Range: bytes=start-end`` header is present, only that byte range
    is returned with a ``206 Partial Content`` status.

    Designed for the frontend's DownloadManager to pipe chunks directly
    into OPFS.  After opening the file, ``torch.cuda.empty_cache()`` is
    called immediately so the "saving" phase does not block the next
    "generating" phase on 4 GB VRAM cards.
    """
    import os

    safe_name = Path(filename).name
    file_path = settings.output_path / safe_name

    if not file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Output file '{safe_name}' not found.",
        )

    file_size = os.path.getsize(file_path)

    # Determine MIME type
    suffix = file_path.suffix.lower()
    media_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".mp4": "video/mp4",
        ".gif": "image/gif",
    }
    media_type = media_types.get(suffix, "application/octet-stream")

    # ── Range request handling ───────────────────────────────────────
    range_header = request.headers.get("range")
    if range_header:
        # Parse "bytes=start-end"
        try:
            range_spec = range_header.strip().replace("bytes=", "")
            parts = range_spec.split("-")
            range_start = int(parts[0]) if parts[0] else 0
            range_end = int(parts[1]) if parts[1] else file_size - 1
        except (ValueError, IndexError):
            raise HTTPException(
                status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
                detail="Invalid Range header.",
            )

        range_end = min(range_end, file_size - 1)
        content_length = range_end - range_start + 1

        async def _stream_range():
            try:
                from inference.dtype_utils import safe_empty_cache
                safe_empty_cache()
            except Exception:
                pass

            with open(file_path, "rb") as f:
                f.seek(range_start)
                remaining = content_length
                while remaining > 0:
                    chunk_size = min(STREAM_CHUNK_SIZE, remaining)
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk

        return StreamingResponse(
            _stream_range(),
            status_code=206,
            media_type=media_type,
            headers={
                "Content-Range": f"bytes {range_start}-{range_end}/{file_size}",
                "Content-Length": str(content_length),
                "Accept-Ranges": "bytes",
                "Cache-Control": f"public, max-age={settings.CACHE_TTL_FULL}",
            },
        )

    # ── Full file response ───────────────────────────────────────────
    async def _stream():
        # Free GPU VRAM immediately so the next generation can start
        try:
            from inference.dtype_utils import safe_empty_cache
            safe_empty_cache()
            logger.debug("GPU cache cleared before streaming %s", safe_name)
        except Exception:
            pass

        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(STREAM_CHUNK_SIZE)
                if not chunk:
                    break
                yield chunk

    return StreamingResponse(
        _stream(),
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name}"',
            "Content-Length": str(file_size),
            "X-File-Size": str(file_size),
            "Accept-Ranges": "bytes",
            "Cache-Control": f"public, max-age={settings.CACHE_TTL_FULL}",
        },
    )


# ═════════════════════════════════════════════════════════════════════════════
# Static output serving
# ═════════════════════════════════════════════════════════════════════════════

@router.get(
    "/outputs/{filename}",
    summary="Serve a generated file",
    tags=["outputs"],
    responses={
        404: {"model": ErrorResponse, "description": "File not found"},
    },
)
async def get_output(
    filename: str,
    x_network_tier: str = Header(default="high", alias="X-Network-Tier"),
) -> FileResponse:
    """Serve a generated image or video file from the output directory.

    When the ``X-Network-Tier`` header indicates a constrained connection
    (``low`` or ``medium``), the server redirects to a compressed preview
    variant if one exists.
    """
    # Sanitise — prevent directory traversal.
    safe_name = Path(filename).name
    file_path = settings.output_path / safe_name

    if not file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Output file '{safe_name}' not found.",
        )

    # Network-aware variant selection
    tier = x_network_tier.lower()
    stem = file_path.stem

    if tier == "low":
        # Try thumbnail first
        thumb = settings.output_path / f"{stem}_thumb.jpg"
        if thumb.is_file():
            return FileResponse(
                path=str(thumb),
                media_type="image/jpeg",
                filename=thumb.name,
                headers={"X-Served-Tier": "thumbnail", "Cache-Control": f"public, max-age={settings.CACHE_TTL_THUMBNAIL}"},
            )
    if tier in ("low", "medium"):
        # Try preview
        preview_jpg = settings.output_path / f"{stem}_preview.jpg"
        preview_mp4 = settings.output_path / f"{stem}_preview.mp4"
        preview = preview_jpg if preview_jpg.is_file() else (preview_mp4 if preview_mp4.is_file() else None)
        if preview:
            pmime = "image/jpeg" if preview.suffix == ".jpg" else "video/mp4"
            return FileResponse(
                path=str(preview),
                media_type=pmime,
                filename=preview.name,
                headers={"X-Served-Tier": "preview", "Cache-Control": f"public, max-age={settings.CACHE_TTL_PREVIEW}"},
            )

    # Guess media type.
    suffix = file_path.suffix.lower()
    media_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".mp4": "video/mp4",
        ".gif": "image/gif",
    }
    media_type = media_types.get(suffix, "application/octet-stream")

    return FileResponse(
        path=str(file_path),
        media_type=media_type,
        filename=safe_name,
        headers={"X-Served-Tier": "full", "Cache-Control": f"public, max-age={settings.CACHE_TTL_FULL}"},
    )
