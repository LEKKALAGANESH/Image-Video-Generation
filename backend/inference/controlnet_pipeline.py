"""
AuraGen -- ControlNet-Lite pose-to-image pipeline.

Allows users to upload a skeleton / pose image and have the AI generate an
image that respects the pose constraints.  Uses the OpenPose ControlNet for
Stable Diffusion 1.5.

Phase 3 will add real-time OpenPose / MediaPipe pose detection; for now
``detect_pose`` is a placeholder that returns the input image unchanged.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any, Callable, Optional

import torch

logger = logging.getLogger(__name__)


class ControlNetPipeline:
    """ControlNet (OpenPose) pipeline for pose-guided image generation.

    Lazy-loads the ControlNet model and a Stable Diffusion 1.5 base pipeline
    with the same VRAM optimisations used across AuraGen (4-bit quantisation,
    sequential CPU offload, torch.compile).
    """

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(self, config: Any) -> None:
        """Store configuration without loading any model.

        Parameters
        ----------
        config:
            A ``Settings`` (or duck-typed equivalent) that exposes at least
            ``DEVICE``, ``QUANTIZE_4BIT``, ``CPU_OFFLOAD``, and ``output_path``.
        """
        self._config = config
        self._pipe: Any | None = None
        self._controlnet: Any | None = None
        self._loaded: bool = False

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_loaded(self) -> bool:
        """Return *True* when the pipeline is resident in memory."""
        return self._loaded

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load(self) -> None:
        """Lazy-load the ControlNet + SD 1.5 pipeline.

        The method is idempotent -- calling it when already loaded is a no-op.

        Raises
        ------
        RuntimeError
            If models cannot be downloaded / instantiated.
        """
        if self._loaded:
            logger.info("ControlNetPipeline is already loaded -- skipping.")
            return

        logger.info("Loading ControlNet (OpenPose) pipeline ...")

        from diffusers import (  # noqa: WPS433 -- deferred imports
            ControlNetModel,
            StableDiffusionControlNetPipeline,
        )
        from inference.dtype_utils import build_load_kwargs, resolve_dtype

        # ── Device-aware dtype + optional NF4 quantisation ───────────────
        load_kwargs = build_load_kwargs(self._config)
        controlnet_load_kwargs: dict[str, Any] = {
            "torch_dtype": resolve_dtype(self._config.DEVICE),
        }

        # ── Load ControlNet ─────────────────────────────────────────────
        controlnet_id: str = "lllyasviel/control_v11p_sd15_openpose"
        try:
            self._controlnet = ControlNetModel.from_pretrained(
                controlnet_id, **controlnet_load_kwargs
            )
            logger.info("ControlNet loaded from '%s'.", controlnet_id)
        except Exception as exc:
            raise RuntimeError(
                f"Could not load ControlNet model '{controlnet_id}': {exc}"
            ) from exc

        # ── Load SD 1.5 base pipeline with ControlNet attached ──────────
        sd_model_id: str = "stable-diffusion-v1-5/stable-diffusion-v1-5"
        try:
            self._pipe = StableDiffusionControlNetPipeline.from_pretrained(
                sd_model_id,
                controlnet=self._controlnet,
                **load_kwargs,
            )
            logger.info("Base SD 1.5 pipeline loaded from '%s'.", sd_model_id)
        except Exception as exc:
            raise RuntimeError(
                f"Could not load SD 1.5 pipeline '{sd_model_id}': {exc}"
            ) from exc

        # ── VRAM optimisations ──────────────────────────────────────────
        from inference.dtype_utils import apply_vram_optimizations

        self._pipe = apply_vram_optimizations(self._pipe, self._config)

        # ── Optional torch.compile ──────────────────────────────────────
        try:
            if hasattr(self._pipe, "unet") and self._pipe.unet is not None:
                self._pipe.unet = torch.compile(
                    self._pipe.unet, mode="reduce-overhead"
                )
                logger.info("torch.compile applied to UNet.")
        except Exception:
            logger.warning(
                "torch.compile unavailable or failed -- running without compilation.",
                exc_info=True,
            )

        self._loaded = True
        logger.info("ControlNet pipeline ready.")

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    def generate_from_pose(
        self,
        prompt: str,
        pose_image_path: str,
        negative_prompt: str = "",
        width: int = 512,
        height: int = 512,
        num_steps: int = 20,
        guidance_scale: float = 7.5,
        controlnet_scale: float = 1.0,
        seed: Optional[int] = None,
        progress_callback: Optional[Callable[[float], None]] = None,
    ) -> str:
        """Generate an image conditioned on a pose skeleton.

        Parameters
        ----------
        prompt:
            The positive text description.
        pose_image_path:
            Path to a skeleton / pose image on disk.
        negative_prompt:
            Things the model should avoid.
        width, height:
            Desired output dimensions (clamped and snapped to multiples of 8).
        num_steps:
            Number of denoising steps.
        guidance_scale:
            Classifier-free guidance weight.
        controlnet_scale:
            How strongly the ControlNet conditions the generation (0.0-2.0).
        seed:
            Optional integer seed for reproducibility.  ``None`` -> random.
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
        FileNotFoundError
            If *pose_image_path* does not exist.
        """
        if not self._loaded or self._pipe is None:
            raise RuntimeError(
                "ControlNetPipeline.generate_from_pose() called before load(). "
                "Call load() first."
            )

        from PIL import Image  # noqa: WPS433 -- deferred import

        # ── Load and resize pose image ──────────────────────────────────
        pose_path = Path(pose_image_path)
        if not pose_path.exists():
            raise FileNotFoundError(f"Pose image not found: {pose_image_path}")

        pose_image: Image.Image = Image.open(pose_path).convert("RGB")

        # Clamp dimensions
        max_size: int = getattr(self._config, "MAX_IMAGE_SIZE", 768)
        width = min(max(width, 64), max_size)
        height = min(max(height, 64), max_size)
        width = (width // 8) * 8
        height = (height // 8) * 8

        pose_image = pose_image.resize((width, height), Image.LANCZOS)

        # ── Reproducible seed ───────────────────────────────────────────
        generator = torch.Generator(device="cpu")
        if seed is not None:
            generator.manual_seed(seed)
        else:
            generator.seed()

        # ── Step callback ───────────────────────────────────────────────
        def _on_step_end(
            pipe: Any,
            step: int,
            timestep: Any,
            callback_kwargs: dict[str, Any],
        ) -> dict[str, Any]:
            if progress_callback is not None:
                progress_callback(int((step / max(num_steps, 1)) * 100))
            return callback_kwargs

        # ── Run inference ───────────────────────────────────────────────
        output_dir: Path = self._config.output_path
        filename: str = f"{uuid.uuid4().hex}.png"
        filepath: Path = output_dir / filename

        try:
            with torch.inference_mode():
                pipe_kwargs: dict[str, Any] = {
                    "prompt": prompt,
                    "image": pose_image,
                    "width": width,
                    "height": height,
                    "num_inference_steps": num_steps,
                    "guidance_scale": guidance_scale,
                    "controlnet_conditioning_scale": controlnet_scale,
                    "generator": generator,
                    "callback_on_step_end": _on_step_end,
                }

                if negative_prompt:
                    pipe_kwargs["negative_prompt"] = negative_prompt

                result = self._pipe(**pipe_kwargs)

            image: Image.Image = result.images[0]
            image.save(str(filepath))
            logger.info("ControlNet image saved to %s", filepath)

            if progress_callback is not None:
                progress_callback(100)

            return filename

        except Exception as oom:
            from inference.dtype_utils import get_oom_error_class, safe_empty_cache
            if isinstance(oom, get_oom_error_class()) or "out of memory" in str(oom).lower():
                logger.error("GPU OOM during ControlNet generation: %s", oom)
                safe_empty_cache()
                raise RuntimeError(
                    "GPU ran out of memory.  Try smaller dimensions or fewer steps."
                ) from oom
            logger.error("ControlNet generation failed.", exc_info=True)
            raise
        finally:
            from inference.dtype_utils import safe_empty_cache as _clean
            _clean()

    # ------------------------------------------------------------------
    # Pose detection (placeholder -- Phase 3)
    # ------------------------------------------------------------------

    def detect_pose(self, image_path: str) -> str:
        """Detect the human pose skeleton in an image.

        .. note::

            This is a **placeholder** for Phase 3.  In production this method
            would use MediaPipe or OpenPose to extract a skeleton image from
            the input, save it to disk, and return the path to the skeleton.

        Parameters
        ----------
        image_path:
            Path to the source image on disk.

        Returns
        -------
        str
            Path to the skeleton image (currently returns *image_path*
            unchanged).
        """
        logger.info(
            "detect_pose() called (placeholder) -- returning input image: %s",
            image_path,
        )
        return image_path

    # ------------------------------------------------------------------
    # Teardown
    # ------------------------------------------------------------------

    def unload(self) -> None:
        """Release the pipeline and free VRAM."""
        if self._pipe is not None:
            del self._pipe
            self._pipe = None

        if self._controlnet is not None:
            del self._controlnet
            self._controlnet = None

        self._loaded = False

        from inference.dtype_utils import safe_full_cleanup
        safe_full_cleanup()

        logger.info("ControlNet pipeline unloaded and VRAM freed.")
