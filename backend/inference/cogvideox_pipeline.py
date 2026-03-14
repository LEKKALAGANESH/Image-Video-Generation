"""
AuraGen -- CogVideoX fallback video generation pipeline.

Used as a fallback when the primary Wan 2.1 pipeline fails.
Wraps the CogVideoX-2b text-to-video model behind the same lazy-loaded,
VRAM-friendly interface as VideoPipeline.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any, Callable, Optional

import torch

logger = logging.getLogger(__name__)


class CogVideoXPipelineWrapper:
    """CogVideoX-2b text-to-video pipeline — fallback for Wan 2.1."""

    def __init__(self, config: Any) -> None:
        self._config = config
        self._pipe: Any | None = None
        self._loaded: bool = False

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def load(self) -> None:
        if self._loaded:
            logger.info("CogVideoXPipeline is already loaded -- skipping.")
            return

        model_id = self._config.MODEL_VIDEO_FALLBACK
        logger.info("Loading CogVideoX fallback pipeline from '%s' ...", model_id)

        from diffusers import CogVideoXPipeline
        from inference.dtype_utils import build_load_kwargs, apply_vram_optimizations

        load_kwargs = build_load_kwargs(self._config)

        try:
            self._pipe = CogVideoXPipeline.from_pretrained(
                model_id,
                **load_kwargs,
            )
        except Exception as exc:
            raise RuntimeError(
                f"Could not load CogVideoX model '{model_id}': {exc}"
            ) from exc

        self._pipe = apply_vram_optimizations(self._pipe, self._config)

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

        self._loaded = True
        logger.info("CogVideoX fallback pipeline ready.")

    def generate(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 480,
        height: int = 320,
        num_frames: int = 17,
        num_steps: int = 20,
        guidance_scale: float = 6.0,
        seed: Optional[int] = None,
        progress_callback: Optional[Callable[[float], None]] = None,
    ) -> str:
        if not self._loaded or self._pipe is None:
            raise RuntimeError(
                "CogVideoXPipeline.generate() called before load()."
            )

        max_size: int = self._config.MAX_VIDEO_SIZE
        max_frames: int = self._config.MAX_VIDEO_FRAMES

        width = min(max(width, 64), max_size)
        height = min(max(height, 64), max_size)
        width = (width // 8) * 8
        height = (height // 8) * 8
        num_frames = min(max(num_frames, 1), max_frames)

        generator = torch.Generator(device="cpu")
        if seed is not None:
            generator.manual_seed(seed)
        else:
            generator.seed()

        def _on_step_end(
            pipe: Any,
            step: int,
            timestep: Any,
            callback_kwargs: dict[str, Any],
        ) -> dict[str, Any]:
            if progress_callback is not None:
                progress_callback(int((step / max(num_steps, 1)) * 100))
            return callback_kwargs

        output_dir: Path = self._config.output_path
        filename = f"{uuid.uuid4().hex}.mp4"
        filepath = output_dir / filename

        try:
            with torch.inference_mode():
                pipe_kwargs: dict[str, Any] = {
                    "prompt": prompt,
                    "num_frames": num_frames,
                    "num_inference_steps": num_steps,
                    "guidance_scale": guidance_scale,
                    "generator": generator,
                    "callback_on_step_end": _on_step_end,
                }

                # CogVideoX may not support width/height — try with, fall back without
                try:
                    pipe_kwargs["width"] = width
                    pipe_kwargs["height"] = height
                    if negative_prompt:
                        pipe_kwargs["negative_prompt"] = negative_prompt
                    result = self._pipe(**pipe_kwargs)
                except TypeError:
                    pipe_kwargs.pop("width", None)
                    pipe_kwargs.pop("height", None)
                    pipe_kwargs.pop("negative_prompt", None)
                    result = self._pipe(**pipe_kwargs)

            from diffusers.utils import export_to_video

            frames = result.frames[0]
            export_to_video(frames, str(filepath), fps=16)
            logger.info("CogVideoX video saved to %s", filepath)

            if progress_callback is not None:
                progress_callback(100)

            return filename

        except Exception as oom:
            from inference.dtype_utils import get_oom_error_class, safe_empty_cache
            if isinstance(oom, get_oom_error_class()) or "out of memory" in str(oom).lower():
                logger.error("GPU OOM during CogVideoX generation: %s", oom)
                safe_empty_cache()
                raise RuntimeError(
                    "GPU ran out of memory during CogVideoX fallback."
                ) from oom
            logger.error("CogVideoX generation failed.", exc_info=True)
            raise
        finally:
            from inference.dtype_utils import safe_empty_cache as _clean
            _clean()

    def unload(self) -> None:
        if self._pipe is not None:
            del self._pipe
            self._pipe = None
        self._loaded = False

        from inference.dtype_utils import safe_full_cleanup
        safe_full_cleanup()

        logger.info("CogVideoX pipeline unloaded and VRAM freed.")
