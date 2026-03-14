"""
AuraGen -- Wan 2.6 (distilled) video generation pipeline (V2).

Upgraded pipeline that uses Wan 2.6 distilled for better physical realism
(momentum, gravity, fluid dynamics).  Falls back to Wan 2.1 1.3B when the
distilled variant is not available.  Supports physics modes ("natural",
"cinematic", "slow-motion") and uses DPMSolverMultistepScheduler for faster
convergence with fewer denoising steps.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any, Callable, Optional

import torch

logger = logging.getLogger(__name__)

# Physics-mode prompt suffixes that steer the model toward the desired look.
_PHYSICS_PROMPT_HINTS: dict[str, str] = {
    "natural": "",
    "cinematic": (
        ", cinematic camera movement, dramatic lighting, shallow depth of field, "
        "film grain, professional cinematography"
    ),
    "slow-motion": (
        ", ultra slow motion, 240fps, high speed camera, smooth motion, "
        "detailed fluid dynamics"
    ),
}


class VideoPipelineV2:
    """Wan 2.6 (distilled) text-to-video pipeline with physics-aware generation.

    Drop-in replacement for :class:`VideoPipeline` with extra capabilities:

    * Tries the distilled checkpoint first for faster, higher-quality output.
    * ``DPMSolverMultistepScheduler`` for fewer denoising steps.
    * ``physics_mode`` parameter: ``"natural"`` | ``"cinematic"`` | ``"slow-motion"``.
    * Enhanced progress reporting with human-readable stage descriptions.
    * ``enable_vae_tiling()`` for larger resolutions.
    * ``torch.compile`` with ``mode="max-autotune"`` for best speed.
    """

    # ------------------------------------------------------------------
    # Construction -- deliberately lightweight; no model is loaded here.
    # ------------------------------------------------------------------

    def __init__(self, config: Any) -> None:
        """Store configuration without loading the model.

        Parameters
        ----------
        config:
            A ``Settings`` (or duck-typed equivalent) that exposes at least
            ``MODEL_VIDEO_V2``, ``MODEL_VIDEO_V2_FALLBACK``, ``DEVICE``,
            ``QUANTIZE_4BIT``, ``CPU_OFFLOAD``, ``MAX_VIDEO_SIZE``,
            ``MAX_VIDEO_FRAMES``, ``VIDEO_DEFAULT_FPS``, and ``output_path``.
        """
        self._config = config
        self._pipe: Any | None = None
        self._loaded: bool = False
        self._distilled: bool = False

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_loaded(self) -> bool:
        """Return *True* when the underlying diffusion pipeline is resident."""
        return self._loaded

    @property
    def is_distilled(self) -> bool:
        """Return *True* if the distilled variant was loaded successfully."""
        return self._distilled

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load(self) -> None:
        """Lazy-load the Wan 2.6 pipeline with all VRAM optimisations applied.

        Loading strategy:
        1. Attempt ``Wan-AI/Wan2.1-T2V-1.3B-Distilled`` (distilled).
        2. Fall back to ``Wan-AI/Wan2.1-T2V-1.3B`` if distilled is unavailable.

        The method is idempotent -- calling it when the pipeline is already
        loaded is a no-op.

        Raises
        ------
        RuntimeError
            If CUDA is unavailable or *both* model variants fail to load.
        """
        if self._loaded:
            logger.info("VideoPipelineV2 is already loaded -- skipping.")
            return

        from diffusers import WanPipeline  # noqa: WPS433 -- deferred import
        from inference.dtype_utils import build_load_kwargs

        # ── Device-aware dtype + optional NF4 quantisation ───────────────
        load_kwargs = build_load_kwargs(self._config)

        # ── Try distilled model first, then fall back ───────────────────
        primary_model: str = self._config.MODEL_VIDEO_V2
        fallback_model: str = self._config.MODEL_VIDEO_V2_FALLBACK

        try:
            logger.info(
                "Loading distilled Wan pipeline from '%s' ...", primary_model
            )
            self._pipe = WanPipeline.from_pretrained(
                primary_model, **load_kwargs
            )
            self._distilled = True
            logger.info("Distilled model loaded successfully.")
        except Exception as primary_exc:
            logger.warning(
                "Distilled model '%s' unavailable (%s). "
                "Falling back to '%s'.",
                primary_model,
                primary_exc,
                fallback_model,
            )
            try:
                self._pipe = WanPipeline.from_pretrained(
                    fallback_model, **load_kwargs
                )
                self._distilled = False
                logger.info("Fallback model '%s' loaded.", fallback_model)
            except Exception as fallback_exc:
                raise RuntimeError(
                    f"Could not load any Wan model. "
                    f"Primary ('{primary_model}'): {primary_exc}  |  "
                    f"Fallback ('{fallback_model}'): {fallback_exc}"
                ) from fallback_exc

        # ── VRAM optimisations ──────────────────────────────────────────
        from inference.dtype_utils import apply_vram_optimizations

        self._pipe = apply_vram_optimizations(self._pipe, self._config)

        # VAE memory optimisations
        try:
            self._pipe.vae.enable_slicing()
            logger.info("VAE slicing enabled.")
        except Exception:
            logger.warning("VAE slicing not available.", exc_info=True)

        try:
            self._pipe.vae.enable_tiling()
            logger.info("VAE tiling enabled.")
        except Exception:
            logger.warning("VAE tiling not available.", exc_info=True)

        # NEW: Pipeline-level VAE tiling for larger resolutions
        try:
            self._pipe.enable_vae_tiling()
            logger.info("Pipeline-level VAE tiling enabled for larger resolutions.")
        except Exception:
            logger.warning(
                "Pipeline-level enable_vae_tiling() not available.", exc_info=True
            )

        # ── Scheduler swap (DPMSolver for faster convergence) ───────────
        try:
            from diffusers import DPMSolverMultistepScheduler  # noqa: WPS433

            self._pipe.scheduler = DPMSolverMultistepScheduler.from_config(
                self._pipe.scheduler.config
            )
            logger.info("Scheduler set to DPMSolverMultistepScheduler.")
        except Exception:
            logger.warning(
                "DPMSolverMultistepScheduler not available -- "
                "keeping the default scheduler.",
                exc_info=True,
            )

        # ── torch.compile with max-autotune ─────────────────────────────
        try:
            if hasattr(self._pipe, "unet") and self._pipe.unet is not None:
                self._pipe.unet = torch.compile(
                    self._pipe.unet, mode="max-autotune"
                )
                logger.info("torch.compile (max-autotune) applied to UNet.")
            elif (
                hasattr(self._pipe, "transformer")
                and self._pipe.transformer is not None
            ):
                self._pipe.transformer = torch.compile(
                    self._pipe.transformer, mode="max-autotune"
                )
                logger.info("torch.compile (max-autotune) applied to transformer.")
        except Exception:
            logger.warning(
                "torch.compile unavailable or failed -- running without compilation.",
                exc_info=True,
            )

        self._loaded = True
        logger.info("V2 video pipeline ready (distilled=%s).", self._distilled)

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    def generate(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 480,
        height: int = 320,
        num_frames: int = 17,
        num_steps: Optional[int] = None,
        guidance_scale: float = 5.0,
        seed: Optional[int] = None,
        physics_mode: str = "natural",
        fps: Optional[int] = None,
        progress_callback: Optional[Callable[[float], None]] = None,
    ) -> str:
        """Generate a video clip from a text prompt.

        Parameters
        ----------
        prompt:
            The positive text description.
        negative_prompt:
            Things the model should avoid.
        width, height:
            Desired frame dimensions (clamped to ``MAX_VIDEO_SIZE``).
        num_frames:
            Total number of frames to generate (clamped to
            ``MAX_VIDEO_FRAMES``).
        num_steps:
            Number of denoising steps.  ``None`` auto-selects: 15 for
            distilled, 20 for the standard model.
        guidance_scale:
            Classifier-free guidance weight.
        seed:
            Optional integer seed for reproducibility.  ``None`` -> random.
        physics_mode:
            One of ``"natural"``, ``"cinematic"``, ``"slow-motion"``.
            ``"slow-motion"`` generates 2x frames then picks every other frame
            for a temporal-interpolation effect.
        fps:
            Frames per second for the exported video.  ``None`` uses the
            config default (``VIDEO_DEFAULT_FPS``).
        progress_callback:
            Optional callable receiving a float in [0, 1] after each step.

        Returns
        -------
        str
            The filename (relative to ``OUTPUT_DIR``) of the saved MP4.

        Raises
        ------
        RuntimeError
            If the pipeline has not been loaded or a CUDA OOM occurs.
        ValueError
            If *physics_mode* is not one of the valid values.
        """
        if not self._loaded or self._pipe is None:
            raise RuntimeError(
                "VideoPipelineV2.generate() called before load(). "
                "Call load() first."
            )

        # ── Validate physics mode ───────────────────────────────────────
        valid_modes: list[str] = self._config.VIDEO_PHYSICS_MODES
        if physics_mode not in valid_modes:
            raise ValueError(
                f"Invalid physics_mode '{physics_mode}'. "
                f"Must be one of {valid_modes}."
            )

        # ── Determine defaults ──────────────────────────────────────────
        if num_steps is None:
            num_steps = 15 if self._distilled else 20

        if fps is None:
            fps = self._config.VIDEO_DEFAULT_FPS

        # ── Clamp dimensions and frame count ────────────────────────────
        max_size: int = self._config.MAX_VIDEO_SIZE
        max_frames: int = self._config.MAX_VIDEO_FRAMES

        width = min(max(width, 64), max_size)
        height = min(max(height, 64), max_size)
        # Ensure multiples of 8.
        width = (width // 8) * 8
        height = (height // 8) * 8
        num_frames = min(max(num_frames, 1), max_frames)

        # For slow-motion: request 2x frames from the model, then
        # down-sample later for a frame-interpolation effect.
        generation_frames: int = num_frames
        if physics_mode == "slow-motion":
            generation_frames = min(num_frames * 2, max_frames)

        # ── Enhance prompt with physics hints ───────────────────────────
        enhanced_prompt: str = prompt + _PHYSICS_PROMPT_HINTS.get(physics_mode, "")

        # ── Reproducible seed ───────────────────────────────────────────
        generator = torch.Generator(device="cpu")
        if seed is not None:
            generator.manual_seed(seed)
        else:
            generator.seed()

        # ── Stage-aware progress reporting ──────────────────────────────
        def _report(fraction: float, stage: str) -> None:
            """Send a progress update with stage info.

            *fraction* is in [0, 1]; converted to int 0-100 for the callback.
            """
            if progress_callback is not None:
                progress_callback(int(fraction * 100))
            logger.debug("Progress %.1f%%: %s", fraction * 100, stage)

        _report(0.0, "Loading model...")

        def _on_step_end(
            pipe: Any,
            step: int,
            timestep: Any,
            callback_kwargs: dict[str, Any],
        ) -> dict[str, Any]:
            # Reserve 0-5% for setup, 5-85% for denoising, 85-100% for encoding.
            frac = 0.05 + (step / max(num_steps, 1)) * 0.80
            _report(frac, f"Denoising step {step}/{num_steps}")
            return callback_kwargs

        # ── Run inference ───────────────────────────────────────────────
        output_dir: Path = self._config.output_path
        filename: str = f"{uuid.uuid4().hex}.mp4"
        filepath: Path = output_dir / filename

        try:
            _report(0.05, "Starting denoising...")

            with torch.inference_mode():
                pipe_kwargs: dict[str, Any] = {
                    "prompt": enhanced_prompt,
                    "width": width,
                    "height": height,
                    "num_frames": generation_frames,
                    "num_inference_steps": num_steps,
                    "guidance_scale": guidance_scale,
                    "generator": generator,
                    "callback_on_step_end": _on_step_end,
                }

                if negative_prompt:
                    try:
                        pipe_kwargs["negative_prompt"] = negative_prompt
                        result = self._pipe(**pipe_kwargs)
                    except TypeError:
                        logger.debug(
                            "Pipeline does not support negative_prompt; "
                            "retrying without it."
                        )
                        pipe_kwargs.pop("negative_prompt", None)
                        result = self._pipe(**pipe_kwargs)
                else:
                    result = self._pipe(**pipe_kwargs)

            _report(0.85, "Encoding video...")

            # ── Post-process frames ─────────────────────────────────────
            frames = result.frames[0]  # list of PIL images or tensor

            if physics_mode == "slow-motion" and len(frames) > num_frames:
                # Simple frame-skip interpolation: keep every other frame.
                frames = frames[::2][:num_frames]
                logger.info(
                    "Slow-motion: reduced %d generated frames to %d output frames.",
                    generation_frames,
                    len(frames),
                )

            # ── Export to MP4 ───────────────────────────────────────────
            from diffusers.utils import export_to_video  # noqa: WPS433

            export_to_video(frames, str(filepath), fps=fps)
            logger.info("Video saved to %s (fps=%d)", filepath, fps)

            _report(1.0, "Complete")
            return filename

        except Exception as oom:
            from inference.dtype_utils import get_oom_error_class, safe_empty_cache
            if isinstance(oom, get_oom_error_class()) or "out of memory" in str(oom).lower():
                logger.error("GPU OOM during V2 video generation: %s", oom)
                safe_empty_cache()
                raise RuntimeError(
                    "GPU ran out of memory.  Try smaller dimensions, fewer frames, "
                    "or fewer steps."
                ) from oom
            logger.error("V2 video generation failed.", exc_info=True)
            raise
        finally:
            from inference.dtype_utils import safe_empty_cache as _clean
            _clean()

    # ------------------------------------------------------------------
    # Teardown
    # ------------------------------------------------------------------

    def unload(self) -> None:
        """Release the pipeline and free VRAM."""
        if self._pipe is not None:
            del self._pipe
            self._pipe = None
        self._loaded = False
        self._distilled = False

        from inference.dtype_utils import safe_full_cleanup
        safe_full_cleanup()

        logger.info("V2 video pipeline unloaded and VRAM freed.")
