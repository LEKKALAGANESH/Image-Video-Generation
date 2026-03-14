"""
AuraGen -- Generation orchestration service.

Provides a singleton ``GenerationService`` that manages the lifecycle of the
image and video pipelines, ensuring that at most one GPU-heavy model is
resident in VRAM at any time.  This is essential on 4 GB cards where both
models simply cannot coexist.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import torch

from core.config import Settings, settings
from inference.image_pipeline import ImagePipeline
from inference.video_pipeline import VideoPipeline
from inference.cogvideox_pipeline import CogVideoXPipelineWrapper

logger = logging.getLogger(__name__)


# ── Lightweight job data classes ─────────────────────────────────────────────


@dataclass
class ImageJob:
    """All parameters needed for a single image generation request."""

    prompt: str
    negative_prompt: str = ""
    width: int = 512
    height: int = 512
    num_steps: int = 4
    guidance_scale: float = 0.0
    seed: Optional[int] = None


@dataclass
class VideoJob:
    """All parameters needed for a single video generation request."""

    prompt: str
    negative_prompt: str = ""
    width: int = 480
    height: int = 320
    num_frames: int = 17
    num_steps: int = 20
    guidance_scale: float = 5.0
    seed: Optional[int] = None


# ── Singleton service ────────────────────────────────────────────────────────


class GenerationService:
    """Singleton that owns both inference pipelines.

    Only **one** pipeline may be loaded at a time.  Calling
    ``generate_image`` automatically unloads the video pipeline (and vice
    versa) before proceeding.  A threading lock serialises all load / unload /
    generate operations so the service is safe to call from async workers.
    """

    _instance: Optional[GenerationService] = None
    _init_lock: threading.Lock = threading.Lock()

    # ── Singleton constructor ────────────────────────────────────────────

    def __new__(cls, config: Optional[Settings] = None) -> GenerationService:
        if cls._instance is None:
            with cls._init_lock:
                # Double-checked locking.
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance._initialise(config or settings)
                    cls._instance = instance
        return cls._instance

    def _initialise(self, config: Settings) -> None:
        """One-time setup (called from ``__new__`` on first instantiation)."""
        self._config = config
        self._image_pipeline = ImagePipeline(config)
        self._video_pipeline = VideoPipeline(config)
        self._cogvideox_pipeline = CogVideoXPipelineWrapper(config)
        self._lock = threading.Lock()
        logger.info("GenerationService initialised (singleton).")

    # ── Public helpers ───────────────────────────────────────────────────

    @property
    def image_pipeline_loaded(self) -> bool:
        return self._image_pipeline.is_loaded

    @property
    def video_pipeline_loaded(self) -> bool:
        return self._video_pipeline.is_loaded

    @property
    def cogvideox_pipeline_loaded(self) -> bool:
        return self._cogvideox_pipeline.is_loaded

    # ── Image generation ─────────────────────────────────────────────────

    def generate_image(
        self,
        job: ImageJob,
        progress_callback: Optional[Callable[[float], None]] = None,
    ) -> str:
        """Generate an image, managing VRAM automatically.

        Parameters
        ----------
        job:
            Encapsulated generation parameters.
        progress_callback:
            Optional callable receiving a float in [0, 1].

        Returns
        -------
        str
            Output filename (relative to ``OUTPUT_DIR``).

        Raises
        ------
        RuntimeError
            On CUDA OOM or model-loading failures.
        """
        with self._lock:
            try:
                # Free VRAM -- only one model at a time.
                if self._video_pipeline.is_loaded:
                    logger.info("Unloading video pipeline to make room for image pipeline.")
                    self._video_pipeline.unload()
                if self._cogvideox_pipeline.is_loaded:
                    logger.info("Unloading CogVideoX pipeline to make room for image pipeline.")
                    self._cogvideox_pipeline.unload()

                if not self._image_pipeline.is_loaded:
                    logger.info("Loading image pipeline ...")
                    self._image_pipeline.load()

                return self._image_pipeline.generate(
                    prompt=job.prompt,
                    negative_prompt=job.negative_prompt,
                    width=job.width,
                    height=job.height,
                    num_steps=job.num_steps,
                    guidance_scale=job.guidance_scale,
                    seed=job.seed,
                    progress_callback=progress_callback,
                )

            except Exception as oom:
                from inference.dtype_utils import get_oom_error_class
                if isinstance(oom, get_oom_error_class()) or "out of memory" in str(oom).lower():
                    logger.error("GPU OOM during image generation -- forcing cleanup.")
                    self._force_cleanup()
                    raise RuntimeError(
                        "GPU out of memory during image generation. "
                        "Try reducing dimensions or inference steps."
                    ) from oom
                raise
            except RuntimeError:
                raise
            except Exception as exc:
                logger.error("Unexpected error in generate_image: %s", exc, exc_info=True)
                raise RuntimeError(f"Image generation failed: {exc}") from exc

    # ── Video generation ─────────────────────────────────────────────────

    def generate_video(
        self,
        job: VideoJob,
        progress_callback: Optional[Callable[[float], None]] = None,
    ) -> str:
        """Generate a video clip, managing VRAM automatically.

        Tries the primary Wan 2.1 pipeline first. If it fails at any
        stage (load or generate), falls back to CogVideoX-2b.
        """
        with self._lock:
            # Free VRAM -- only one model at a time.
            if self._image_pipeline.is_loaded:
                logger.info("Unloading image pipeline to make room for video pipeline.")
                self._image_pipeline.unload()

            # ── Try primary pipeline (Wan 2.1) ─────────────────────
            try:
                if self._cogvideox_pipeline.is_loaded:
                    self._cogvideox_pipeline.unload()

                if not self._video_pipeline.is_loaded:
                    logger.info("Loading primary video pipeline (Wan 2.1) ...")
                    self._video_pipeline.load()

                return self._video_pipeline.generate(
                    prompt=job.prompt,
                    negative_prompt=job.negative_prompt,
                    width=job.width,
                    height=job.height,
                    num_frames=job.num_frames,
                    num_steps=job.num_steps,
                    guidance_scale=job.guidance_scale,
                    seed=job.seed,
                    progress_callback=progress_callback,
                )

            except Exception as primary_err:
                logger.warning(
                    "Primary video pipeline (Wan 2.1) failed: %s — "
                    "falling back to CogVideoX",
                    primary_err,
                )
                # Unload failed primary pipeline
                try:
                    self._video_pipeline.unload()
                except Exception:
                    pass

                # ── Fallback: CogVideoX ────────────────────────────
                try:
                    if not self._cogvideox_pipeline.is_loaded:
                        logger.info("Loading fallback video pipeline (CogVideoX) ...")
                        self._cogvideox_pipeline.load()

                    return self._cogvideox_pipeline.generate(
                        prompt=job.prompt,
                        negative_prompt=job.negative_prompt,
                        width=job.width,
                        height=job.height,
                        num_frames=job.num_frames,
                        num_steps=job.num_steps,
                        guidance_scale=job.guidance_scale,
                        seed=job.seed,
                        progress_callback=progress_callback,
                    )

                except Exception as fallback_err:
                    logger.error(
                        "Both video pipelines failed. "
                        "Primary (Wan 2.1): %s | Fallback (CogVideoX): %s",
                        primary_err,
                        fallback_err,
                    )
                    self._force_cleanup()
                    raise RuntimeError(
                        f"All video pipelines failed. "
                        f"Wan 2.1: {primary_err} | CogVideoX: {fallback_err}"
                    ) from fallback_err

    # ── Cleanup ──────────────────────────────────────────────────────────

    def unload_all(self) -> None:
        """Unload every pipeline and free all VRAM.

        Safe to call even if nothing is loaded.
        """
        with self._lock:
            self._force_cleanup()

    def _force_cleanup(self) -> None:
        """Unconditionally unload both pipelines (caller must hold lock)."""
        self._image_pipeline.unload()
        self._video_pipeline.unload()
        self._cogvideox_pipeline.unload()
        from inference.dtype_utils import safe_full_cleanup
        safe_full_cleanup()
        logger.info("All pipelines unloaded; VRAM freed.")
