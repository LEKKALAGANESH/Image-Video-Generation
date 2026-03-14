"""
AuraGen -- FLUX Klein image generation pipeline.

Wraps the FLUX diffusion model behind a lazy-loaded, VRAM-friendly interface
designed for 4 GB NVIDIA GPUs.  Supports 4-bit NF4 quantisation via
bitsandbytes, sequential CPU offloading, attention slicing, and optional
torch.compile acceleration.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any, Callable, Optional

import torch

logger = logging.getLogger(__name__)


class ImagePipeline:
    """FLUX Klein text-to-image pipeline with aggressive VRAM optimisations."""

    # ------------------------------------------------------------------
    # Construction -- deliberately lightweight; no model is loaded here.
    # ------------------------------------------------------------------

    def __init__(self, config: Any) -> None:
        """Store configuration without loading the model.

        Parameters
        ----------
        config:
            A ``Settings`` (or duck-typed equivalent) that exposes at least
            ``MODEL_IMAGE``, ``DEVICE``, ``QUANTIZE_4BIT``, ``CPU_OFFLOAD``,
            ``MAX_IMAGE_SIZE``, and ``output_path``.
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
        """Lazy-load the FLUX pipeline with all VRAM optimisations applied.

        The method is idempotent -- calling it when the pipeline is already
        loaded is a no-op.

        Raises
        ------
        RuntimeError
            If CUDA is unavailable or the model cannot be downloaded /
            instantiated.
        """
        if self._loaded:
            logger.info("ImagePipeline is already loaded -- skipping.")
            return

        logger.info("Loading FLUX image pipeline from '%s' ...", self._config.MODEL_IMAGE)

        from diffusers import FluxPipeline  # noqa: WPS433 -- deferred import
        from inference.dtype_utils import build_load_kwargs, apply_vram_optimizations

        # ── Device-aware dtype + optional NF4 quantisation ───────────────
        load_kwargs = build_load_kwargs(self._config)

        # ── Load the pipeline ────────────────────────────────────────────
        try:
            self._pipe = FluxPipeline.from_pretrained(
                self._config.MODEL_IMAGE,
                **load_kwargs,
            )
        except Exception as exc:
            raise RuntimeError(
                f"Could not load FLUX model '{self._config.MODEL_IMAGE}': {exc}"
            ) from exc

        # ── VRAM optimisations ───────────────────────────────────────────
        self._pipe = apply_vram_optimizations(self._pipe, self._config)

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
        logger.info("Image pipeline ready.")

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    def generate(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 512,
        height: int = 512,
        num_steps: int = 4,
        guidance_scale: float = 0.0,
        seed: Optional[int] = None,
        progress_callback: Optional[Callable[[float], None]] = None,
    ) -> str:
        """Generate an image from a text prompt.

        Parameters
        ----------
        prompt:
            The positive text description.
        negative_prompt:
            Things the model should avoid.
        width, height:
            Desired output dimensions (clamped to ``MAX_IMAGE_SIZE``).
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
            The filename (relative to ``OUTPUT_DIR``) of the saved PNG.

        Raises
        ------
        RuntimeError
            If the pipeline has not been loaded or a CUDA OOM occurs.
        """
        if not self._loaded or self._pipe is None:
            raise RuntimeError(
                "ImagePipeline.generate() called before load(). "
                "Call load() first."
            )

        # ── Clamp dimensions ─────────────────────────────────────────────
        max_size: int = self._config.MAX_IMAGE_SIZE
        width = min(max(width, 64), max_size)
        height = min(max(height, 64), max_size)
        # Ensure multiples of 8 for diffusion models.
        width = (width // 8) * 8
        height = (height // 8) * 8

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
        filename = f"{uuid.uuid4().hex}.png"
        filepath = output_dir / filename

        try:
            with torch.inference_mode():
                pipe_kwargs: dict[str, Any] = {
                    "prompt": prompt,
                    "width": width,
                    "height": height,
                    "num_inference_steps": num_steps,
                    "guidance_scale": guidance_scale,
                    "generator": generator,
                    "callback_on_step_end": _on_step_end,
                }
                # FLUX.1-schnell is a distilled model and does not
                # support negative_prompt — always omit it.
                result = self._pipe(**pipe_kwargs)

            image = result.images[0]
            image.save(str(filepath))
            logger.info("Image saved to %s", filepath)

            # Signal 100 % completion.
            if progress_callback is not None:
                progress_callback(100)

            return filename

        except Exception as oom:
            from inference.dtype_utils import get_oom_error_class, safe_empty_cache
            if isinstance(oom, get_oom_error_class()) or "out of memory" in str(oom).lower():
                logger.error("GPU OOM during image generation: %s", oom)
                safe_empty_cache()
                raise RuntimeError(
                    "GPU ran out of memory.  Try smaller dimensions or fewer steps."
                ) from oom
            raise
        except Exception:
            logger.error("Image generation failed.", exc_info=True)
            raise
        finally:
            from inference.dtype_utils import safe_empty_cache
            safe_empty_cache()

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

        logger.info("Image pipeline unloaded and VRAM freed.")
