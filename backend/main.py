"""
AuraGen — FastAPI application entry point.

Starts the server with:

    uvicorn main:app --host 0.0.0.0 --port 8000 --reload

Or directly:

    python main.py
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response, StreamingResponse

from api.routes import router as api_router
from api.edit_routes import router as edit_router
from api.audit_routes import router as audit_router
from api.audio_routes import router as audio_router
from api.controlnet_routes import router as controlnet_router
from api.network_routes import router as network_router
from core.config import settings
from backend_queue.job_queue import job_queue
from websocket.manager import manager as ws_manager
from sse.manager import sse_manager

# Cloud burst service — instantiated at startup, wired into job queue
_cloud_burst_service = None

# ── Logging ───────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("auragen")


# ═════════════════════════════════════════════════════════════════════════════
# GPU Verification & Failover
# ═════════════════════════════════════════════════════════════════════════════

def _verify_gpu() -> None:
    """Run GPU diagnostics, configure the best available backend, and
    enforce VRAM-safe settings.  Unlike the previous ``_verify_cuda``,
    this does **not** crash the process — it falls back gracefully to
    DirectML or CPU so the UI stays functional and can display the
    exact error to the user.

    When ``DEVICE`` is set to a specific value (not "auto"), it is
    still validated and overridden if the requested backend is unavailable.
    """
    from core.gpu_diagnostics import run_diagnostics

    diag = run_diagnostics()

    # If user explicitly set DEVICE to something other than "auto",
    # validate it's actually available
    if settings.DEVICE != "auto" and settings.DEVICE != "":
        requested = settings.DEVICE
        if requested == "cuda" and not diag.cuda_available:
            logger.warning(
                "DEVICE=cuda requested but CUDA not available — auto-detecting instead"
            )
        elif requested == "privateuseone" and not diag.directml_available:
            logger.warning(
                "DEVICE=privateuseone requested but DirectML not available — auto-detecting"
            )
        else:
            # Requested device is available, use it directly
            logger.info("Using explicitly configured DEVICE=%s", requested)
            return

    # ── Apply backend to settings ────────────────────────────────────────
    if diag.backend == "cuda":
        settings.DEVICE = "cuda"
        logger.info("  GPU backend  : CUDA — %s (%d MB)", diag.device_name, diag.vram_mb)

        # Enforce 4-bit quant + offload for ≤4 GB VRAM
        if diag.vram_mb <= 4096:
            if not settings.QUANTIZE_4BIT:
                logger.warning("  Forcing 4-bit quantization ON (≤4 GB VRAM)")
                settings.QUANTIZE_4BIT = True
            if not settings.CPU_OFFLOAD:
                logger.warning("  Forcing CPU offloading ON (≤4 GB VRAM)")
                settings.CPU_OFFLOAD = True

    elif diag.backend == "directml":
        settings.DEVICE = "privateuseone"  # DirectML device string in PyTorch
        settings.QUANTIZE_4BIT = False  # NF4 not supported on DirectML
        settings.CPU_OFFLOAD = False  # sequential offload is CUDA-only
        logger.info("  GPU backend  : DirectML — %s", diag.device_name)

    else:
        settings.DEVICE = "cpu"
        settings.QUANTIZE_4BIT = False
        settings.CPU_OFFLOAD = False
        logger.warning("  GPU backend  : CPU (no GPU acceleration)")

    for w in diag.warnings:
        logger.warning("  ⚠  %s", w)


# ═════════════════════════════════════════════════════════════════════════════
# Lifespan
# ═════════════════════════════════════════════════════════════════════════════

async def _run_inference(job, progress_callback) -> str:
    """Bridge the async job queue to the synchronous GenerationService.

    This function is registered with ``job_queue.set_inference_fn()`` so
    that real model inference runs instead of the placeholder simulator.

    Parameters
    ----------
    job:
        The queue ``Job`` instance (has ``.type``, ``.prompt``, ``.params``, etc.).
    progress_callback:
        An **async** callable ``(progress: int, message: str) -> None``
        provided by ``JobQueue._make_progress_callback``.

    Returns
    -------
    str
        Output filename (relative to ``OUTPUT_DIR``).
    """
    from backend_queue.job_queue import JobType
    from services.generation_service import GenerationService, ImageJob, VideoJob

    loop = asyncio.get_running_loop()
    service = GenerationService()

    # The GenerationService pipelines call a *synchronous* progress callback
    # with a single int 0-100.  We need to bridge that to the *async* callback
    # provided by the job queue.
    def sync_progress(pct: int) -> None:
        """Schedule the async progress callback from the sync inference thread."""
        asyncio.run_coroutine_threadsafe(
            progress_callback(pct, f"Generating… {pct}%"),
            loop,
        )

    if job.type == JobType.IMAGE:
        image_job = ImageJob(
            prompt=job.prompt,
            negative_prompt=job.negative_prompt,
            width=job.params.get("width", 512),
            height=job.params.get("height", 512),
            num_steps=job.params.get("num_steps", 4),
            guidance_scale=job.params.get("guidance_scale", 0.0),
            seed=job.params.get("seed"),
        )
        return await loop.run_in_executor(
            None, lambda: service.generate_image(image_job, sync_progress)
        )

    elif job.type == JobType.VIDEO:
        video_job = VideoJob(
            prompt=job.prompt,
            negative_prompt=job.negative_prompt,
            width=job.params.get("width", 480),
            height=job.params.get("height", 320),
            num_frames=job.params.get("num_frames", 17),
            num_steps=job.params.get("num_steps", 20),
            guidance_scale=job.params.get("guidance_scale", 5.0),
            seed=job.params.get("seed"),
        )
        return await loop.run_in_executor(
            None, lambda: service.generate_video(video_job, sync_progress)
        )

    else:
        raise ValueError(f"Unsupported job type: {job.type}")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup / shutdown hook.

    * On startup  — verify GPU, enforce config, register inference, launch the
      job-queue worker.
    * On shutdown — gracefully stop the worker.
    """
    logger.info("AuraGen starting up…")

    # ── GPU probe — detect best backend, configure device ──────────────
    _verify_gpu()

    logger.info("  Image model : %s", settings.MODEL_IMAGE)
    logger.info("  Video model : %s (fallback: %s)", settings.MODEL_VIDEO, settings.MODEL_VIDEO_FALLBACK)
    logger.info("  Device      : %s", settings.DEVICE)
    logger.info("  Output dir  : %s", settings.output_path)
    logger.info("  4-bit quant : %s", settings.QUANTIZE_4BIT)
    logger.info("  CPU offload : %s", settings.CPU_OFFLOAD)
    logger.info("  V2 pipeline : %s", settings.USE_V2_PIPELINE)
    logger.info("  Cloud burst : %s", settings.CLOUD_ENABLED)
    logger.info("  Models dir  : %s", settings.models_path)

    # Ensure the output directory exists.
    settings.output_path.mkdir(parents=True, exist_ok=True)

    # ── Initialize CloudBurstService and wire into job queue ──────────
    global _cloud_burst_service
    try:
        from services.cloud_burst_service import CloudBurstService
        _cloud_burst_service = CloudBurstService(settings)
        job_queue.set_cloud_burst_service(_cloud_burst_service)
        if settings.CLOUD_ENABLED:
            logger.info("  Cloud provider: %s (burst thresholds: image=%dpx, frames=%d, VRAM=%dMB)",
                        settings.CLOUD_PROVIDER,
                        settings.BURST_THRESHOLD_IMAGE,
                        settings.BURST_THRESHOLD_FRAMES,
                        settings.VRAM_BUDGET_MB)
        else:
            logger.info("  Cloud burst service initialized (disabled — set CLOUD_ENABLED=true to activate)")
    except Exception as exc:
        logger.warning("  Cloud burst service unavailable: %s", exc)

    # Register the real inference function so the job queue uses the actual
    # generation pipelines instead of the placeholder simulator.
    job_queue.set_inference_fn(_run_inference)
    logger.info("Real inference function registered with job queue.")

    # Wire the SSE manager so job progress is broadcast to SSE clients too.
    job_queue.set_sse_manager(sse_manager)
    logger.info("SSE manager registered with job queue.")

    # Start the single-threaded job queue worker.
    job_queue.start()

    yield  # ← application is running

    # Shutdown.
    logger.info("AuraGen shutting down…")
    await job_queue.stop()


# ═════════════════════════════════════════════════════════════════════════════
# Application
# ═════════════════════════════════════════════════════════════════════════════

app = FastAPI(
    title="AuraGen",
    description="Premium AI image & video generation platform.",
    version="0.1.0",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*", "X-Network-Tier", "Importance"],
    expose_headers=["X-Served-Tier", "X-Network-Tier", "Accept-Ranges"],
)


# ── Network-Aware Cache Middleware ───────────────────────────────────────

class NetworkAwareCacheMiddleware(BaseHTTPMiddleware):
    """Inject Cache-Control and Vary headers on /outputs/* responses
    based on the detected network tier and file variant."""

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        response = await call_next(request)

        if request.url.path.startswith("/outputs/"):
            filename = request.url.path.split("/")[-1]

            # Determine variant type from filename suffix
            if "_thumb" in filename:
                ttl = settings.CACHE_TTL_THUMBNAIL
                tier_label = "thumbnail"
            elif "_preview" in filename:
                ttl = settings.CACHE_TTL_PREVIEW
                tier_label = "preview"
            else:
                ttl = settings.CACHE_TTL_FULL
                tier_label = "full"

            response.headers["Cache-Control"] = f"public, max-age={ttl}, s-maxage={ttl}, stale-while-revalidate=3600"
            response.headers["Vary"] = "X-Network-Tier, ECT, Save-Data, Downlink"
            response.headers.setdefault("X-Served-Tier", tier_label)

        return response


app.add_middleware(NetworkAwareCacheMiddleware)

# ── REST routes ───────────────────────────────────────────────────────────

app.include_router(api_router, prefix="/api")
app.include_router(edit_router)
app.include_router(audit_router)
app.include_router(audio_router)
app.include_router(controlnet_router)
app.include_router(network_router, prefix="/api")

# ── Static file serving for generated outputs ────────────────────────────
# Mount the resolved output directory so generated files are accessible at
# ``/outputs/{filename}``.  The API route at ``/api/outputs/{filename}``
# remains as a fallback with explicit MIME-type handling, but this mount
# provides proper caching headers, range-request support, and removes the
# dependency on CWD matching the backend directory.
_output_dir = settings.output_path
_output_dir.mkdir(parents=True, exist_ok=True)
app.mount(
    "/outputs",
    StaticFiles(directory=str(_output_dir)),
    name="outputs",
)


# ── WebSocket endpoint ───────────────────────────────────────────────────

# Timeout for WebSocket inactivity.  Video generation on a 4 GB card can
# take many minutes, so we keep the socket alive for up to 10 minutes of
# silence from the client.
WS_IDLE_TIMEOUT: float = 600.0  # seconds
WS_HEARTBEAT_INTERVAL: float = 30.0  # server-sent ping interval


@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str) -> None:
    """Per-client WebSocket connection with heartbeat keep-alive.

    The server pushes JSON messages with the schema::

        {
            "type": "progress" | "complete" | "error" | "hardware_error",
            "job_id": "<hex-uuid>",
            "data": { ... }
        }

    **Heartbeat**: The server sends ``{"type": "ping"}`` every 30 s.
    The client should reply with ``{"type": "pong"}`` (or any message)
    within 600 s to keep the connection open.

    **Hardware errors**: If the GPU backend or model loading fails, the
    socket stays alive and sends a ``hardware_error`` message so the UI
    can display the exact diagnostic instead of silently dropping.
    """
    # ── Accept — if this fails the socket was never opened, nothing to clean up
    try:
        await ws_manager.connect(websocket, client_id)
    except Exception as exc:
        logger.error("WebSocket accept failed for %s: %s", client_id, exc)
        return

    async def _heartbeat() -> None:
        """Periodically send a server-side ping to keep the connection and
        any intermediate proxies alive — even while the CPU is loading a
        model (which can block the event loop for minutes on iGPU)."""
        try:
            while True:
                await asyncio.sleep(WS_HEARTBEAT_INTERVAL)
                try:
                    await ws_manager.send_personal({"type": "ping"}, client_id)
                except Exception:
                    break  # connection already dead — exit cleanly
        except asyncio.CancelledError:
            pass

    heartbeat_task = asyncio.create_task(_heartbeat())

    try:
        # Send the current GPU health as the first message so the UI
        # immediately knows whether the hardware is degraded.
        try:
            from core.gpu_diagnostics import get_diagnostics
            diag = get_diagnostics()
            if not diag.healthy or diag.backend == "cpu":
                await ws_manager.send_personal({
                    "type": "hardware_error",
                    "data": {
                        "backend": diag.backend,
                        "device_name": diag.device_name,
                        "healthy": diag.healthy,
                        "warnings": diag.warnings,
                        "cuda_error": diag.cuda_error,
                        "message": (
                            f"GPU backend: {diag.backend}. "
                            + (diag.warnings[0] if diag.warnings else "No GPU acceleration available.")
                        ),
                    },
                }, client_id)
        except Exception as diag_exc:
            logger.debug("Could not send initial diagnostics: %s", diag_exc)

        while True:
            # Wait for inbound messages with a generous idle timeout.
            data = await asyncio.wait_for(
                websocket.receive_json(),
                timeout=WS_IDLE_TIMEOUT,
            )
            msg_type = data.get("type", "")
            if msg_type == "ping":
                await ws_manager.send_personal({"type": "pong"}, client_id)
            # "pong" responses from the client are silently consumed.
    except asyncio.TimeoutError:
        logger.warning("WebSocket %s timed out after %ds of inactivity", client_id, WS_IDLE_TIMEOUT)
        await ws_manager.disconnect(client_id)
    except WebSocketDisconnect:
        await ws_manager.disconnect(client_id)
    except Exception as exc:
        logger.error("WebSocket %s error: %s", client_id, exc)
        # Try to send a hardware_error before disconnecting
        try:
            await ws_manager.send_personal({
                "type": "hardware_error",
                "data": {"message": f"Server connection error: {exc}"},
            }, client_id)
        except Exception:
            pass
        await ws_manager.disconnect(client_id)
    finally:
        heartbeat_task.cancel()


# ── SSE endpoint ──────────────────────────────────────────────────────────

@app.get("/api/events/{client_id}")
async def sse_events(client_id: str, request: Request) -> StreamingResponse:
    """Server-Sent Events endpoint — unidirectional server-to-client stream.

    This is the preferred transport for frontends that only need to
    *receive* server pushes (progress, completion, errors).  The existing
    WebSocket at ``/ws/{client_id}`` is kept for backward compatibility
    and any future bidirectional needs.

    The stream emits events with the format::

        id: <monotonic-int>
        data: {"type": "progress"|"complete"|"error"|..., ...}

    A keepalive comment (``: keepalive``) is sent every 15 s of silence
    so proxies and browsers do not close the connection.
    """
    client = sse_manager.connect(client_id)

    # Send initial hardware status on connect so the UI immediately
    # knows whether the GPU backend is healthy or degraded.
    try:
        from core.gpu_diagnostics import run_diagnostics

        diag = run_diagnostics()
        await sse_manager.send_to(client_id, {
            "type": "connected",
            "gpu": {
                "device": diag.recommended_device,
                "vram_mb": diag.vram_total_mb,
                "driver": diag.driver_version or "N/A",
            },
        })
    except Exception as diag_exc:
        logger.debug("Could not send initial SSE diagnostics: %s", diag_exc)
        # Still send a minimal connected event so the client knows it's live
        await sse_manager.send_to(client_id, {"type": "connected"})

    async def event_generator():
        """Yield SSE-formatted text chunks until the client disconnects."""
        try:
            while True:
                # Bail out if the HTTP connection was dropped.
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(
                        client.queue.get(), timeout=15.0
                    )
                    event_id = event.pop("id", 0)
                    yield f"id: {event_id}\ndata: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    # SSE keepalive — comment lines are ignored by EventSource.
                    yield ": keepalive\n\n"
        finally:
            sse_manager.disconnect(client_id)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # disable Nginx buffering
        },
    )


# ═════════════════════════════════════════════════════════════════════════════
# Direct execution
# ═════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True,
        log_level="info",
    )
