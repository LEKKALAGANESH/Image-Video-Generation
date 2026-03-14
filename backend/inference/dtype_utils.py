"""
AuraGen -- Device-aware dtype selection and VRAM optimization helpers.

Centralises the logic that decides torch dtype, quantization config, and
device placement so every pipeline uses a consistent, hardware-correct
configuration.

Supports three backends:
  * **CUDA**       — NVIDIA GPUs: float16, NF4 quantisation, CPU offload
  * **DirectML**   — Intel/AMD/Qualcomm on Windows: float16 (stable ops)
  * **CPU**        — Fallback: float32 only (fp16 produces garbage on CPU)
"""

from __future__ import annotations

import logging
from typing import Any

import torch

logger = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════════════════════════
# Device helpers
# ═════════════════════════════════════════════════════════════════════════════

def get_directml_device() -> Any:
    """Return a ``torch_directml.device()`` if available, else None."""
    try:
        import torch_directml  # type: ignore[import-untyped]
        return torch_directml.device()
    except (ImportError, Exception):
        return None


def safe_empty_cache() -> None:
    """Clear GPU cache if CUDA is available.  No-op on DirectML / CPU."""
    try:
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


def safe_ipc_collect() -> None:
    """Run ``torch.cuda.ipc_collect()`` if available.  No-op otherwise."""
    try:
        if torch.cuda.is_available():
            torch.cuda.ipc_collect()
    except Exception:
        pass


def safe_full_cleanup() -> None:
    """Best-effort GPU memory cleanup across all backends."""
    safe_empty_cache()
    safe_ipc_collect()


def get_oom_error_class() -> type:
    """Return the OOM exception class for the current backend.

    On non-CUDA systems, returns ``RuntimeError`` since DirectML and CPU
    do not raise ``torch.cuda.OutOfMemoryError``.
    """
    try:
        if torch.cuda.is_available():
            return torch.cuda.OutOfMemoryError
    except Exception:
        pass
    return RuntimeError


# ═════════════════════════════════════════════════════════════════════════════
# Dtype resolution
# ═════════════════════════════════════════════════════════════════════════════

def resolve_dtype(device: str) -> torch.dtype:
    """Return the correct compute dtype for the given device string.

    * ``"cuda"``          → ``torch.float16``
    * ``"privateuseone"`` → ``torch.float32`` (DirectML fp16 is unstable
      for complex diffusion models — float32 is safer for correctness)
    * ``"cpu"``           → ``torch.float32`` (CPU fp16 produces garbage)
    """
    if device == "cuda" and torch.cuda.is_available():
        return torch.float16
    # DirectML: float32 is safer for correctness with diffusion models.
    # Intel Iris Xe handles fp32 well; fp16 causes intermittent NaN/black.
    if device == "privateuseone":
        return torch.float32
    # CPU or any unsupported device — must use float32
    return torch.float32


def build_load_kwargs(config: Any) -> dict[str, Any]:
    """Build the ``from_pretrained`` kwargs dict with device-correct dtype
    and optional NF4 quantization.

    Returns a dict suitable for splatting into ``Pipeline.from_pretrained(**kw)``.
    """
    dtype = resolve_dtype(config.DEVICE)
    load_kwargs: dict[str, Any] = {"torch_dtype": dtype}

    # NF4 quantization only makes sense on CUDA (requires bitsandbytes)
    if config.QUANTIZE_4BIT and config.DEVICE == "cuda":
        try:
            from diffusers import BitsAndBytesConfig as DiffusersBnBConfig

            nf4_config = DiffusersBnBConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=dtype,
            )
            load_kwargs["quantization_config"] = nf4_config
            logger.info(
                "NF4 quantization enabled (compute_dtype=%s).", dtype
            )
        except ImportError:
            logger.warning(
                "bitsandbytes / DiffusersBnBConfig not available — "
                "falling back to %s without quantization.",
                dtype,
            )
        except Exception:
            logger.warning(
                "Failed to configure NF4 quantization — falling back to %s.",
                dtype,
                exc_info=True,
            )
    elif config.QUANTIZE_4BIT and config.DEVICE != "cuda":
        logger.warning(
            "4-bit quantization requested but device is '%s' — "
            "ignoring (NF4 requires CUDA + bitsandbytes). Using %s.",
            config.DEVICE,
            dtype,
        )

    logger.info("Pipeline load dtype: %s (device=%s)", dtype, config.DEVICE)
    return load_kwargs


# ═════════════════════════════════════════════════════════════════════════════
# VRAM optimizations
# ═════════════════════════════════════════════════════════════════════════════

def apply_vram_optimizations(pipe: Any, config: Any) -> Any:
    """Apply standard VRAM optimizations to a loaded diffusers pipeline.

    Returns the (possibly moved) pipeline.
    """
    device = config.DEVICE

    if config.CPU_OFFLOAD and device == "cuda":
        pipe.enable_sequential_cpu_offload()
        logger.info("Sequential CPU offloading enabled.")
    elif device == "cuda":
        pipe = pipe.to("cuda")
    elif device == "privateuseone":
        # DirectML: move to the DirectML device
        dml_dev = get_directml_device()
        if dml_dev is not None:
            try:
                pipe = pipe.to(dml_dev)
                logger.info("Pipeline moved to DirectML device.")
            except Exception as e:
                logger.warning(
                    "Failed to move pipeline to DirectML (%s) — falling back to CPU.", e
                )
                pipe = pipe.to("cpu")
        else:
            logger.warning("DirectML device not available — falling back to CPU.")
            pipe = pipe.to("cpu")
    else:
        pipe = pipe.to("cpu")

    # Attention slicing — always safe to enable, reduces peak memory
    try:
        pipe.enable_attention_slicing()
        logger.info("Attention slicing enabled.")
    except Exception:
        logger.debug("Attention slicing not available.", exc_info=True)

    # VAE slicing — process VAE in slices instead of all at once.
    # Critical for integrated GPUs (Intel Iris Xe) with shared memory.
    if device in ("privateuseone", "cpu"):
        try:
            pipe.vae.enable_slicing()
            logger.info("VAE slicing enabled (iGPU memory optimization).")
        except Exception:
            logger.debug("VAE slicing not available.", exc_info=True)

    return pipe
