"""
AuraGen — Single-threaded async job queue.

Processes exactly **one** generation job at a time to prevent VRAM
out-of-memory errors on a 4 GB NVIDIA GPU.  Jobs are stored in an
``asyncio.Queue`` (bounded to ``MAX_QUEUE_SIZE``) and consumed by a
long-running ``worker`` coroutine started at application lifespan.

Progress updates are broadcast to every connected WebSocket client via
the :pymod:`websocket.manager` singleton **and** to every connected SSE
client via the :pymod:`sse.manager` singleton (when registered via
``set_sse_manager()``).

Cloud bursting: When a ``CloudBurstService`` is registered via
``set_cloud_burst_service()``, jobs that exceed local hardware thresholds
are transparently routed to a cloud provider before falling back to
local inference.
"""

from __future__ import annotations

import asyncio
import logging
import time
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from core.config import settings
from websocket.manager import manager as ws_manager

logger = logging.getLogger("auragen.queue")


# ═════════════════════════════════════════════════════════════════════════════
# Data types
# ═════════════════════════════════════════════════════════════════════════════

class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobType(str, Enum):
    IMAGE = "image"
    VIDEO = "video"


@dataclass
class Job:
    """Represents a single generation job."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    type: JobType = JobType.IMAGE
    prompt: str = ""
    negative_prompt: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    status: JobStatus = JobStatus.PENDING
    progress: int = 0          # 0 – 100
    result_url: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        """Serialise the job to a plain dict (JSON-safe)."""
        return {
            "job_id": self.id,
            "job_type": self.type.value,
            "prompt": self.prompt,
            "negative_prompt": self.negative_prompt,
            "params": self.params,
            "status": self.status.value,
            "progress": self.progress,
            "result_url": self.result_url,
            "error": self.error,
            "created_at": self.created_at.isoformat(),
        }


# ═════════════════════════════════════════════════════════════════════════════
# Queue implementation
# ═════════════════════════════════════════════════════════════════════════════

class JobQueue:
    """Async bounded queue that processes one job at a time."""

    def __init__(self, max_size: int = settings.MAX_QUEUE_SIZE) -> None:
        self._queue: asyncio.Queue[str] = asyncio.Queue(maxsize=max_size)
        # All known jobs, keyed by job id.
        self._jobs: dict[str, Job] = {}
        self._worker_task: Optional[asyncio.Task[None]] = None
        self._running: bool = False
        # Inference callback — set externally (avoids circular imports with
        # heavy model-loading modules).
        self._inference_fn: Any = None
        # Cloud burst service — set via ``set_cloud_burst_service()``
        self._cloud_burst_service: Any = None
        # SSE manager — set via ``set_sse_manager()``
        self._sse_manager: Any = None

    # ── public API ────────────────────────────────────────────────────────

    async def submit(self, job: Job) -> None:
        """Add *job* to the queue.

        Raises ``asyncio.QueueFull`` if the queue is at capacity.
        """
        self._jobs[job.id] = job
        try:
            self._queue.put_nowait(job.id)
        except asyncio.QueueFull:
            job.status = JobStatus.FAILED
            job.error = "Queue is full. Please try again later."
            raise
        logger.info("Job %s submitted (queue depth: %d)", job.id, self._queue.qsize())

    def get_status(self, job_id: str) -> Optional[Job]:
        """Return the :class:`Job` for *job_id*, or ``None``."""
        return self._jobs.get(job_id)

    async def cancel(self, job_id: str) -> bool:
        """Mark a job as cancelled.

        If the job is still ``PENDING`` it will be skipped when the worker
        picks it up.  If it is already ``RUNNING`` we set the flag so the
        inference callback can check and abort early.

        Returns ``True`` if the job was found and cancellation was requested.
        """
        job = self._jobs.get(job_id)
        if job is None:
            return False
        if job.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
            return False
        job.status = JobStatus.CANCELLED
        await self._broadcast({
            "type": "error",
            "job_id": job.id,
            "data": {"message": "Job cancelled by user."},
        })
        logger.info("Job %s cancelled", job_id)
        return True

    @property
    def queue_size(self) -> int:
        return self._queue.qsize()

    def set_inference_fn(self, fn: Any) -> None:
        """Register the async inference callable.

        Signature expected::

            async def inference(job: Job, progress_callback) -> str:
                ...  # returns the filename of the generated artifact
        """
        self._inference_fn = fn

    def set_cloud_burst_service(self, service: Any) -> None:
        """Register the ``CloudBurstService`` for hybrid local/cloud routing.

        When set, ``_process_job`` will attempt cloud bursting for jobs that
        exceed configured thresholds before falling back to local inference.
        """
        self._cloud_burst_service = service

    def set_sse_manager(self, manager: Any) -> None:
        """Register the :class:`SSEManager` for server-sent event broadcasting.

        When set, every ``ws_manager.broadcast()`` call in the queue is
        mirrored to connected SSE clients so both transports receive the
        same real-time updates.
        """
        self._sse_manager = manager

    # ── worker lifecycle ──────────────────────────────────────────────────

    def start(self) -> None:
        """Spawn the background worker task."""
        if self._running:
            return
        self._running = True
        self._worker_task = asyncio.create_task(self._worker(), name="job-queue-worker")
        logger.info("Job queue worker started")

    async def stop(self) -> None:
        """Gracefully shut down the worker."""
        self._running = False
        if self._worker_task is not None:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        logger.info("Job queue worker stopped")

    # ── internal worker loop ──────────────────────────────────────────────

    async def _worker(self) -> None:
        """Process jobs one-at-a-time until ``stop()`` is called."""
        logger.info("Worker loop running — waiting for jobs…")
        while self._running:
            try:
                job_id = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            job = self._jobs.get(job_id)
            if job is None:
                continue

            # Skip cancelled jobs.
            if job.status == JobStatus.CANCELLED:
                logger.info("Skipping cancelled job %s", job_id)
                continue

            await self._process_job(job)

    async def _process_job(self, job: Job) -> None:
        """Run a single job through the inference pipeline.

        When a ``CloudBurstService`` is registered and the job exceeds
        hardware thresholds, cloud bursting is attempted first.  If cloud
        execution fails (or is disabled), the job falls back transparently
        to local inference — the caller never knows the difference.
        """
        job.status = JobStatus.RUNNING
        job.progress = 0

        await self._broadcast({
            "type": "progress",
            "job_id": job.id,
            "data": {"status": "running", "progress": 0, "message": "Starting generation…"},
        })

        try:
            # ── Cloud burst attempt ──────────────────────────────────
            cloud_result = await self._try_cloud_burst(job)
            if cloud_result is not None:
                result_filename = cloud_result
            elif self._inference_fn is None:
                # Fallback: simulate generation when no real model is loaded.
                result_filename = await self._simulate_inference(job)
            else:
                result_filename = await self._inference_fn(job, self._make_progress_callback(job))

            if job.status == JobStatus.CANCELLED:
                logger.info("Job %s was cancelled during inference", job.id)
                return

            job.status = JobStatus.COMPLETED
            job.progress = 100
            job.result_url = f"/api/outputs/{result_filename}"

            await self._broadcast({
                "type": "complete",
                "job_id": job.id,
                "data": {
                    "status": "completed",
                    "progress": 100,
                    "result_url": job.result_url,
                },
            })
            logger.info("Job %s completed → %s", job.id, job.result_url)

        except torch_oom_error() as exc:
            job.status = JobStatus.FAILED
            job.error = (
                "Out of GPU memory. Try reducing the resolution or number of frames."
            )
            await self._broadcast({
                "type": "error",
                "job_id": job.id,
                "data": {"status": "failed", "message": job.error},
            })
            logger.error("OOM for job %s: %s", job.id, exc)

        except Exception as exc:
            job.status = JobStatus.FAILED
            job.error = str(exc)
            await self._broadcast({
                "type": "error",
                "job_id": job.id,
                "data": {"status": "failed", "message": job.error},
            })
            logger.error("Job %s failed: %s\n%s", job.id, exc, traceback.format_exc())

    # ── cloud burst ──────────────────────────────────────────────────────

    async def _try_cloud_burst(self, job: Job) -> Optional[str]:
        """Attempt to route the job to a cloud provider.

        Returns the output filename if cloud execution succeeds, or ``None``
        if cloud bursting is unavailable, disabled, not needed, or fails
        (so local inference should take over).
        """
        if self._cloud_burst_service is None:
            return None

        try:
            from services.generation_service import ImageJob, VideoJob

            # Build the appropriate job dataclass from the queue Job
            if job.type == JobType.IMAGE:
                cloud_job = ImageJob(
                    prompt=job.prompt,
                    negative_prompt=job.negative_prompt,
                    width=job.params.get("width", 512),
                    height=job.params.get("height", 512),
                    num_steps=job.params.get("num_steps", 20),
                    guidance_scale=job.params.get("guidance_scale", 7.5),
                    seed=job.params.get("seed"),
                )
            else:
                cloud_job = VideoJob(
                    prompt=job.prompt,
                    negative_prompt=job.negative_prompt,
                    width=job.params.get("width", 480),
                    height=job.params.get("height", 320),
                    num_frames=job.params.get("num_frames", 17),
                    num_steps=job.params.get("num_steps", 20),
                    guidance_scale=job.params.get("guidance_scale", 5.0),
                    seed=job.params.get("seed"),
                )

            # Check if this job should be cloud-burst
            if not self._cloud_burst_service.should_burst(cloud_job):
                return None

            logger.info("Job %s exceeds local thresholds — attempting cloud burst", job.id)

            progress_cb = self._make_progress_callback(job)
            await progress_cb(5, "Routing to cloud provider…")

            # CloudBurstService.route_job is synchronous (it manages its own
            # async loop internally), so run it in a thread to avoid blocking
            # the event loop.
            def _sync_progress(fraction: float) -> None:
                """Adapter: CloudBurstService passes float 0-1, convert to int 0-100."""
                pct = int(fraction * 100)
                # Fire-and-forget the async broadcast from the sync thread
                try:
                    import asyncio as _aio
                    loop = _aio.new_event_loop()
                    loop.run_until_complete(progress_cb(pct, "Processing on cloud…"))
                    loop.close()
                except Exception:
                    pass

            loop = asyncio.get_running_loop()
            result_filename = await loop.run_in_executor(
                None,
                lambda: self._cloud_burst_service.route_job(cloud_job, _sync_progress),
            )

            logger.info("Job %s completed via cloud burst → %s", job.id, result_filename)
            return result_filename

        except Exception as exc:
            logger.warning(
                "Cloud burst failed for job %s, falling back to local: %s",
                job.id, exc,
            )
            # Reset progress so local inference starts fresh
            job.progress = 0
            await self._broadcast({
                "type": "progress",
                "job_id": job.id,
                "data": {"status": "running", "progress": 0,
                         "message": "Cloud unavailable — running locally…"},
            })
            return None

    # ── helpers ───────────────────────────────────────────────────────────

    async def _broadcast(self, data: dict[str, Any]) -> None:
        """Broadcast *data* to both WebSocket and SSE clients.

        WebSocket broadcast is always attempted (backward compat).
        SSE broadcast is only attempted when an SSE manager has been
        registered via ``set_sse_manager()``.
        """
        await ws_manager.broadcast(data)
        if self._sse_manager is not None:
            await self._sse_manager.broadcast(data)

    def _make_progress_callback(self, job: Job):
        """Return an async callback that the inference function can call to
        report progress (0-100) with an optional human-readable message."""

        async def _callback(progress: int, message: str = "") -> None:
            job.progress = max(0, min(progress, 100))
            logger.info("Job %s progress: %d%% %s", job.id[:8], job.progress, message)
            await self._broadcast({
                "type": "progress",
                "job_id": job.id,
                "data": {
                    "status": "running",
                    "progress": job.progress,
                    "message": message,
                },
            })

        return _callback

    async def _simulate_inference(self, job: Job) -> str:
        """Placeholder inference that generates a tiny dummy file.

        Used when no real model is loaded (e.g. during development / CI).
        """
        import io
        from pathlib import Path

        callback = self._make_progress_callback(job)

        total_steps = 10
        for step in range(1, total_steps + 1):
            if job.status == JobStatus.CANCELLED:
                return ""
            await asyncio.sleep(0.3)
            pct = int(step / total_steps * 100)
            await callback(pct, f"Simulated step {step}/{total_steps}")

        # Write a tiny placeholder image.
        try:
            from PIL import Image

            img = Image.new("RGB", (64, 64), color=(42, 42, 42))
            filename = f"{job.id}.png"
            out_path = settings.output_path / filename
            img.save(str(out_path))
        except ImportError:
            # Pillow not available — write a raw bytes file instead.
            filename = f"{job.id}.bin"
            out_path = settings.output_path / filename
            out_path.write_bytes(b"\x00" * 64)

        return filename


# ── OOM sentinel ──────────────────────────────────────────────────────────

def torch_oom_error() -> type:
    """Return the appropriate OOM error class for the current backend.

    On CUDA: ``torch.cuda.OutOfMemoryError``
    On DirectML / CPU: ``RuntimeError`` (OOM manifests as RuntimeError)

    This avoids importing torch at module level (which is slow and might not
    be installed in test environments).
    """
    try:
        from inference.dtype_utils import get_oom_error_class
        return get_oom_error_class()
    except ImportError:
        try:
            import torch
            if torch.cuda.is_available():
                return torch.cuda.OutOfMemoryError
        except Exception:
            pass
        return RuntimeError


# Module-level singleton.
job_queue = JobQueue()
