"""
AuraGen -- Wan 2.1 video generation pipeline.

Wraps the Wan 2.1 1.3B text-to-video diffusion model behind a lazy-loaded,
VRAM-friendly interface designed for 4 GB NVIDIA GPUs.  Supports 4-bit NF4
quantisation, sequential CPU offloading, attention slicing, VAE
slicing / tiling, and optional torch.compile acceleration.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any, Callable, Optional

import torch

logger = logging.getLogger(__name__)


class VideoPipeline:
    """Wan 2.1 1.3B text-to-video pipeline with aggressive VRAM optimisations."""

    # ------------------------------------------------------------------
    # Construction -- deliberately lightweight; no model is loaded here.
    # ------------------------------------------------------------------

    def __init__(self, config: Any) -> None:
        """Store configuration without loading the model.

        Parameters
        ----------
        config:
            A ``Settings`` (or duck-typed equivalent) that exposes at least
            ``MODEL_VIDEO``, ``DEVICE``, ``QUANTIZE_4BIT``, ``CPU_OFFLOAD``,
            ``MAX_VIDEO_SIZE``, ``MAX_VIDEO_FRAMES``, and ``output_path``.
        """
        self._config = config
        self._pipe: Any | None = None
        self._loaded: bool = False

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_loaded(self) -> bool:
        """Return *True* when the underlying diffusion pipeline is resident."""
        return self._loaded

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load(self) -> None:
        """Lazy-load the Wan 2.1 pipeline with all VRAM optimisations applied.

        The method is idempotent -- calling it when the pipeline is already
        loaded is a no-op.

        Raises
        ------
        RuntimeError
            If CUDA is unavailable or the model cannot be downloaded /
            instantiated.
        """
        if self._loaded:
            logger.info("VideoPipeline is already loaded -- skipping.")
            return

        logger.info("Loading Wan 2.1 video pipeline from '%s' ...", self._config.MODEL_VIDEO)

        from diffusers import WanPipeline  # noqa: WPS433 -- deferred import
        from inference.dtype_utils import build_load_kwargs, apply_vram_optimizations

        # ── Device-aware dtype + optional NF4 quantisation ───────────────
        load_kwargs = build_load_kwargs(self._config)

        # ── Load the pipeline ────────────────────────────────────────────
        try:
            self._pipe = WanPipeline.from_pretrained(
                self._config.MODEL_VIDEO,
                **load_kwargs,
            )
        except Exception as exc:
            raise RuntimeError(
                f"Could not load Wan 2.1 model '{self._config.MODEL_VIDEO}': {exc}"
            ) from exc

        # ── VRAM optimisations ───────────────────────────────────────────
        self._pipe = apply_vram_optimizations(self._pipe, self._config)

        # VAE memory optimisations -- critical for video generation where
        # the VAE must decode many frames in sequence.
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

        # ── Optional torch.compile ───────────────────────────────────────
        try:
            if hasattr(self._pipe, "unet") and self._pipe.unet is not None:
                self._pipe.unet = torch.compile(
                    self._pipe.unet, mode="reduce-overhead"
                )
                logger.info("torch.compile applied to UNet.")
            elif hasattr(self._pipe, "transformer") and self._pipe.transformer is not None:
                self._pipe.transformer = torch.compile(
                    self._pipe.transformer, mode="reduce-overhead"
                )
                logger.info("torch.compile applied to transformer.")
        except Exception:
            logger.warning(
                "torch.compile unavailable or failed -- running without compilation.",
                exc_info=True,
            )

        self._loaded = True
        logger.info("Video pipeline ready.")

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
        num_steps: int = 20,
        guidance_scale: float = 5.0,
        seed: Optional[int] = None,
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
            Number of denoising steps.
        guidance_scale:
            Classifier-free guidance weight.
        seed:
            Optional integer seed for reproducibility.  ``None`` → random.
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
        """
        if not self._loaded or self._pipe is None:
            raise RuntimeError(
                "VideoPipeline.generate() called before load(). "
                "Call load() first."
            )

        # ── Clamp dimensions and frame count ─────────────────────────────
        max_size: int = self._config.MAX_VIDEO_SIZE
        max_frames: int = self._config.MAX_VIDEO_FRAMES

        width = min(max(width, 64), max_size)
        height = min(max(height, 64), max_size)
        # Ensure multiples of 8.
        width = (width // 8) * 8
        height = (height // 8) * 8
        num_frames = min(max(num_frames, 1), max_frames)

        # ── Reproducible seed ────────────────────────────────────────────
        generator = torch.Generator(device="cpu")
        if seed is not None:
            generator.manual_seed(seed)
        else:
            generator.seed()

        # ── Step callback ────────────────────────────────────────────────
        def _on_step_end(
            pipe: Any,
            step: int,
            timestep: Any,
            callback_kwargs: dict[str, Any],
        ) -> dict[str, Any]:
            if progress_callback is not None:
                progress_callback(int((step / max(num_steps, 1)) * 100))
            return callback_kwargs

        # ── Run inference ────────────────────────────────────────────────
        output_dir: Path = self._config.output_path
        filename = f"{uuid.uuid4().hex}.mp4"
        filepath = output_dir / filename

        try:
            with torch.inference_mode():
                pipe_kwargs: dict[str, Any] = {
                    "prompt": prompt,
                    "width": width,
                    "height": height,
                    "num_frames": num_frames,
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

            # ── Export to MP4 ────────────────────────────────────────────
            from diffusers.utils import export_to_video  # noqa: WPS433

            frames = result.frames[0]  # list of PIL images or tensor
            export_to_video(frames, str(filepath), fps=16)
            logger.info("Video saved to %s", filepath)

            # Signal 100 % completion.
            if progress_callback is not None:
                progress_callback(100)

            return filename

        except Exception as oom:
            from inference.dtype_utils import get_oom_error_class, safe_empty_cache
            if isinstance(oom, get_oom_error_class()) or "out of memory" in str(oom).lower():
                logger.error("GPU OOM during video generation: %s", oom)
                safe_empty_cache()
                raise RuntimeError(
                    "GPU ran out of memory.  Try smaller dimensions, fewer frames, "
                    "or fewer steps."
                ) from oom
            logger.error("Video generation failed.", exc_info=True)
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

        from inference.dtype_utils import safe_full_cleanup
        safe_full_cleanup()

        logger.info("Video pipeline unloaded and VRAM freed.")
