"""
AuraGen — GPU Diagnostics & Virtual-GPU Failover.

Runs before the FastAPI lifespan to detect the GPU state.  Instead of
hard-crashing when CUDA is missing, this module tries DirectML as a
Windows fallback and stores a machine-readable diagnostic report that
the ``/api/health-check`` endpoint surfaces to the UI.
"""

from __future__ import annotations

import logging
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("auragen.gpu")


@dataclass
class GPUDiagnostics:
    """Immutable snapshot of the GPU state at startup."""

    backend: str = "none"  # "cuda" | "directml" | "cpu" | "none"
    device_name: str = ""
    vram_mb: int = 0
    cuda_available: bool = False
    directml_available: bool = False
    driver_installed: bool = False
    nvidia_smi_output: str = ""
    cuda_error: str = ""
    torch_version: str = ""
    cuda_version: str = ""
    healthy: bool = False
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "backend": self.backend,
            "device_name": self.device_name,
            "vram_mb": self.vram_mb,
            "cuda_available": self.cuda_available,
            "directml_available": self.directml_available,
            "driver_installed": self.driver_installed,
            "nvidia_smi_output": self.nvidia_smi_output[:500],
            "cuda_error": self.cuda_error,
            "torch_version": self.torch_version,
            "cuda_version": self.cuda_version,
            "healthy": self.healthy,
            "warnings": self.warnings,
        }


# Module-level singleton — populated by ``run_diagnostics()``.
_diagnostics: Optional[GPUDiagnostics] = None


def get_diagnostics() -> GPUDiagnostics:
    """Return the cached diagnostic report (run ``run_diagnostics`` first)."""
    if _diagnostics is None:
        return run_diagnostics()
    return _diagnostics


def run_diagnostics() -> GPUDiagnostics:
    """Probe the system for GPU capabilities and choose the best backend.

    Order of preference:
    1. CUDA  (NVIDIA GPU with working drivers)
    2. DirectML  (Windows ML — any GPU, including Intel/AMD)
    3. CPU  (last resort — generation will be very slow)
    """
    global _diagnostics
    diag = GPUDiagnostics()

    # ── 1. Check PyTorch ────────────────────────────────────────────────
    try:
        import torch
        diag.torch_version = torch.__version__
        diag.cuda_version = torch.version.cuda or ""
    except ImportError:
        diag.cuda_error = "PyTorch is not installed"
        diag.warnings.append("PyTorch missing — install torch>=2.5.1")
        _diagnostics = diag
        return diag

    # ── 2. Probe nvidia-smi ─────────────────────────────────────────────
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            diag.driver_installed = True
            diag.nvidia_smi_output = result.stdout.strip()
            logger.info("nvidia-smi: %s", diag.nvidia_smi_output)
        else:
            diag.nvidia_smi_output = result.stderr.strip() or "nvidia-smi returned no output"
            logger.warning("nvidia-smi failed: %s", diag.nvidia_smi_output)
    except FileNotFoundError:
        diag.nvidia_smi_output = "nvidia-smi not found on PATH"
        logger.warning("nvidia-smi not found — NVIDIA driver may not be installed")
    except subprocess.TimeoutExpired:
        diag.nvidia_smi_output = "nvidia-smi timed out"
    except Exception as e:
        diag.nvidia_smi_output = str(e)

    # ── 3. Try CUDA ─────────────────────────────────────────────────────
    import torch

    if torch.cuda.is_available():
        diag.cuda_available = True
        diag.backend = "cuda"
        diag.device_name = torch.cuda.get_device_name(0)
        diag.vram_mb = torch.cuda.get_device_properties(0).total_mem // (1024 * 1024)
        diag.healthy = True
        logger.info("CUDA backend OK: %s (%d MB)", diag.device_name, diag.vram_mb)
        _diagnostics = diag
        return diag

    # CUDA not available — capture the specific error
    try:
        torch.cuda.init()
    except Exception as e:
        diag.cuda_error = str(e)
        logger.warning("CUDA init error: %s", diag.cuda_error)

    if not diag.cuda_error:
        diag.cuda_error = "torch.cuda.is_available() returned False (no specific error)"

    # ── 4. Try DirectML (Windows fallback) ──────────────────────────────
    try:
        import torch_directml  # type: ignore[import-untyped]
        dml_device = torch_directml.device()
        # Quick smoke test — create a tiny tensor on DirectML
        t = torch.tensor([1.0], device=dml_device)
        _ = (t * 2.0).item()
        del t

        diag.directml_available = True
        diag.backend = "directml"
        diag.device_name = f"DirectML ({torch_directml.device_name(0)})"
        diag.healthy = True
        diag.warnings.append(
            "Running on DirectML (Windows ML fallback). "
            "Performance will be lower than CUDA. "
            "Install NVIDIA drivers for full GPU acceleration."
        )
        logger.info("DirectML backend OK: %s", diag.device_name)
        _diagnostics = diag
        return diag
    except ImportError:
        logger.info("torch-directml not installed — DirectML fallback unavailable")
    except Exception as e:
        logger.warning("DirectML probe failed: %s", e)

    # ── 5. CPU fallback ─────────────────────────────────────────────────
    diag.backend = "cpu"
    diag.device_name = "CPU"
    diag.healthy = True  # app can start, just slowly
    diag.warnings.append(
        "No GPU backend available. Running on CPU — generation will be very slow. "
        "Install NVIDIA drivers or torch-directml for GPU acceleration."
    )
    logger.warning("Falling back to CPU — no GPU backend available")
    _diagnostics = diag
    return diag
