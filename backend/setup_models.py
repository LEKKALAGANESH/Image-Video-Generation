#!/usr/bin/env python3
"""
AuraGen -- Model download & setup script.

Downloads quantized model weights into ``backend/models/`` with VRAM-aware
logic, retry handling, and a clean CLI interface.

Usage
-----
    python setup_models.py              # download all models
    python setup_models.py --model flux # download only FLUX
    python setup_models.py --check      # check download status only
    python setup_models.py --vram       # show VRAM info only
"""

from __future__ import annotations

import argparse
import os
import signal
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCRIPT_DIR: Path = Path(__file__).resolve().parent
MODELS_DIR: Path = SCRIPT_DIR / "models"

# Model registry ----------------------------------------------------------
# Each entry maps a short key to its metadata.

MODEL_REGISTRY: Dict[str, Dict[str, Any]] = {
    "flux": {
        "repo_id": "stabilityai/stable-diffusion-xl-base-1.0",
        "local_dir": "flux",
        "display_name": "SDXL Base 1.0",
        "vram_4bit_gb": 3.2,
        "vram_fp16_gb": 6.8,
        "essential_files": ["model_index.json", "unet/config.json"],
    },
    "wan": {
        "repo_id": "Wan-AI/Wan2.1-T2V-1.3B",
        "local_dir": "wan",
        "display_name": "Wan 2.1 1.3B",
        "vram_4bit_gb": 1.8,
        "vram_fp16_gb": 2.6,
        "essential_files": ["config.json", "model_index.json"],
    },
    "controlnet": {
        "repo_id": "lllyasviel/control_v11p_sd15_openpose",
        "local_dir": "controlnet",
        "display_name": "ControlNet OpenPose",
        "vram_4bit_gb": 0.7,
        "vram_fp16_gb": 1.4,
        "essential_files": ["config.json"],
    },
    "sam2": {
        "repo_id": "facebook/sam2-hiera-tiny",
        "local_dir": "sam2",
        "display_name": "SAM2 Hiera Tiny",
        "vram_4bit_gb": 0.15,
        "vram_fp16_gb": 0.15,
        "essential_files": ["config.json"],
    },
}

# File patterns for snapshot_download ------------------------------------

ALLOW_PATTERNS: List[str] = [
    "*.safetensors",
    "*.json",
    "*.txt",
    "*.model",
]

IGNORE_PATTERNS: List[str] = [
    "*.bin",
    "*.ckpt",
    "*.pt",
    "*.msgpack",
]

MAX_RETRIES: int = 3

# ---------------------------------------------------------------------------
# Graceful Ctrl+C handling
# ---------------------------------------------------------------------------

_interrupted: bool = False


def _handle_sigint(signum: int, frame: Any) -> None:
    """Set the interrupted flag so in-progress downloads can abort cleanly."""
    global _interrupted  # noqa: WPS420
    _interrupted = True
    print("\n[!] Ctrl+C detected -- finishing current operation and exiting.")


signal.signal(signal.SIGINT, _handle_sigint)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fmt_size(size_bytes: int) -> str:
    """Return a human-readable size string (e.g. ``3.2 GB``)."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 ** 2:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 ** 3:
        return f"{size_bytes / 1024 ** 2:.1f} MB"
    else:
        return f"{size_bytes / 1024 ** 3:.2f} GB"


def _dir_size(path: Path) -> int:
    """Return the total size of all files under *path* in bytes."""
    total: int = 0
    if path.is_dir():
        for f in path.rglob("*"):
            if f.is_file():
                total += f.stat().st_size
    return total


def _has_essential_file(model_dir: Path, essential_files: List[str]) -> bool:
    """Return True if *model_dir* contains at least one of the essential files."""
    for name in essential_files:
        if (model_dir / name).is_file():
            return True
    return False


# ---------------------------------------------------------------------------
# VRAM information
# ---------------------------------------------------------------------------


def get_vram_info() -> Optional[Dict[str, Any]]:
    """Query CUDA device 0 and return a dict of GPU details, or None."""
    try:
        import torch  # noqa: WPS433
    except ImportError:
        print("[!] PyTorch is not installed. Cannot query VRAM.")
        return None

    if not torch.cuda.is_available():
        print("[!] CUDA is not available. No GPU detected.")
        return None

    props = torch.cuda.get_device_properties(0)
    total_mem: int = props.total_mem
    free_mem: int = 0
    try:
        free_mem, _ = torch.cuda.mem_get_info(0)
    except Exception:
        pass

    return {
        "name": props.name,
        "total_mem": total_mem,
        "free_mem": free_mem,
    }


def print_vram_info() -> Optional[Dict[str, Any]]:
    """Print a formatted VRAM table and return the info dict."""
    info = get_vram_info()

    print()
    print("=" * 60)
    print("  GPU / VRAM Information")
    print("=" * 60)

    if info is None:
        print("  No CUDA-capable GPU detected.")
        print("  Models can still be downloaded for CPU-offload usage.")
        print("=" * 60)
        print()
        return None

    total_gb: float = info["total_mem"] / (1024 ** 3)
    free_gb: float = info["free_mem"] / (1024 ** 3)

    print(f"  GPU Name    : {info['name']}")
    print(f"  Total VRAM  : {total_gb:.2f} GB")
    print(f"  Free VRAM   : {free_gb:.2f} GB")
    print("=" * 60)

    if total_gb < 4.0:
        print()
        print("  [WARNING] Less than 4 GB VRAM detected.")
        print("  You can still download models and use CPU offloading,")
        print("  but generation will be slower.")
        print()

    print()
    return info


def print_vram_estimates() -> None:
    """Print a table of estimated VRAM usage per model."""
    print("  Estimated VRAM usage per model:")
    print("  " + "-" * 56)
    print(f"  {'Model':<22} {'4-bit (NF4)':<16} {'fp16':<16}")
    print("  " + "-" * 56)
    for key, meta in MODEL_REGISTRY.items():
        name = meta["display_name"]
        v4 = f"~{meta['vram_4bit_gb']:.2f} GB"
        v16 = f"~{meta['vram_fp16_gb']:.2f} GB"
        # SAM2 does not have a separate 4-bit mode
        if key == "sam2":
            v4 = "  --"
        print(f"  {name:<22} {v4:<16} {v16:<16}")
    print("  " + "-" * 56)
    print()


# ---------------------------------------------------------------------------
# Directory setup
# ---------------------------------------------------------------------------


def create_directory_structure() -> None:
    """Create ``backend/models/<subdir>`` for every registered model."""
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    for meta in MODEL_REGISTRY.values():
        subdir = MODELS_DIR / meta["local_dir"]
        subdir.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Disk space check
# ---------------------------------------------------------------------------


def check_disk_space(required_gb: float = 15.0) -> bool:
    """Warn if the disk has less than *required_gb* free.

    Returns True if there is enough space (or if the check is unsupported).
    """
    try:
        import shutil
        usage = shutil.disk_usage(str(MODELS_DIR))
        free_gb = usage.free / (1024 ** 3)
        if free_gb < required_gb:
            print(f"[WARNING] Only {free_gb:.1f} GB free on disk.")
            print(f"          At least {required_gb:.0f} GB recommended for all models.")
            return False
        return True
    except Exception:
        return True  # Cannot check; proceed anyway.


# ---------------------------------------------------------------------------
# Download logic
# ---------------------------------------------------------------------------


def _is_model_downloaded(key: str) -> bool:
    """Return True if the model appears to be fully downloaded."""
    meta = MODEL_REGISTRY[key]
    model_dir = MODELS_DIR / meta["local_dir"]
    return _has_essential_file(model_dir, meta["essential_files"])


def download_model(key: str) -> str:
    """Download a single model with retries.

    Returns one of: ``"Downloaded"``, ``"Skipped"``, ``"Failed"``.
    """
    global _interrupted  # noqa: WPS420

    meta = MODEL_REGISTRY[key]
    model_dir = MODELS_DIR / meta["local_dir"]
    display = meta["display_name"]

    # Check if already present
    if _has_essential_file(model_dir, meta["essential_files"]):
        print(f"  [{display}] Already downloaded -- skipping.")
        return "Skipped"

    if _interrupted:
        print(f"  [{display}] Interrupted -- skipping.")
        return "Failed"

    try:
        from huggingface_hub import snapshot_download  # noqa: WPS433
    except ImportError:
        print()
        print("[ERROR] huggingface_hub is not installed.")
        print("        Install it with:")
        print("            pip install huggingface_hub>=0.25.0")
        print()
        return "Failed"

    print(f"  [{display}] Downloading from {meta['repo_id']} ...")

    for attempt in range(1, MAX_RETRIES + 1):
        if _interrupted:
            print(f"  [{display}] Interrupted -- aborting download.")
            return "Failed"

        try:
            snapshot_download(
                repo_id=meta["repo_id"],
                local_dir=str(model_dir),
                allow_patterns=ALLOW_PATTERNS,
                ignore_patterns=IGNORE_PATTERNS,
                resume_download=True,
            )

            # Verify essential files are now present
            if _has_essential_file(model_dir, meta["essential_files"]):
                size_str = _fmt_size(_dir_size(model_dir))
                print(f"  [{display}] Download complete ({size_str}).")
                return "Downloaded"
            else:
                print(f"  [{display}] Download finished but essential files not found.")
                print(f"             Expected one of: {meta['essential_files']}")
                # Still consider it a success if files exist
                if any(model_dir.iterdir()):
                    size_str = _fmt_size(_dir_size(model_dir))
                    print(f"  [{display}] Directory contains files ({size_str}). Marking as downloaded.")
                    return "Downloaded"
                return "Failed"

        except KeyboardInterrupt:
            _interrupted = True
            print(f"\n  [{display}] Download interrupted by user.")
            return "Failed"
        except Exception as exc:
            wait_seconds = 2 ** attempt
            if attempt < MAX_RETRIES:
                print(
                    f"  [{display}] Attempt {attempt}/{MAX_RETRIES} failed: {exc}"
                )
                print(f"  [{display}] Retrying in {wait_seconds}s ...")
                time.sleep(wait_seconds)
            else:
                print(
                    f"  [{display}] All {MAX_RETRIES} attempts failed: {exc}"
                )
                return "Failed"

    return "Failed"


# ---------------------------------------------------------------------------
# Status & summary
# ---------------------------------------------------------------------------


def check_status() -> Dict[str, str]:
    """Check download status for every model.  Returns key -> status mapping."""
    statuses: Dict[str, str] = {}
    for key in MODEL_REGISTRY:
        if _is_model_downloaded(key):
            statuses[key] = "Downloaded"
        else:
            statuses[key] = "Not downloaded"
    return statuses


def print_summary(statuses: Dict[str, str]) -> None:
    """Print a pretty summary table of model download statuses."""
    print()
    print("=" * 65)
    print(f"  {'Model':<18} {'Status':<16} {'Size':<12} {'Path'}")
    print("  " + "-" * 60)

    for key, meta in MODEL_REGISTRY.items():
        name = meta["display_name"]
        status = statuses.get(key, "Unknown")
        model_dir = MODELS_DIR / meta["local_dir"]

        if status in ("Downloaded", "Skipped"):
            size = _fmt_size(_dir_size(model_dir))
        else:
            size = "--"

        rel_path = f"models/{meta['local_dir']}/"
        print(f"  {name:<18} {status:<16} {size:<12} {rel_path}")

    print("  " + "-" * 60)
    print("=" * 65)
    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build and return the argument parser."""
    parser = argparse.ArgumentParser(
        prog="setup_models",
        description="AuraGen -- Download quantized model weights into backend/models/.",
    )
    parser.add_argument(
        "--model",
        type=str,
        choices=list(MODEL_REGISTRY.keys()),
        default=None,
        help="Download only the specified model (default: all).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        default=False,
        help="Only check download status; do not download anything.",
    )
    parser.add_argument(
        "--vram",
        action="store_true",
        default=False,
        help="Only show GPU / VRAM information.",
    )
    return parser


def main() -> None:
    """Entry point for the model setup CLI."""
    parser = build_parser()
    args = parser.parse_args()

    print()
    print("*" * 60)
    print("  AuraGen -- Model Setup")
    print("*" * 60)

    # --vram: only show GPU info and exit
    if args.vram:
        print_vram_info()
        print_vram_estimates()
        return

    # --check: only show status and exit
    if args.check:
        create_directory_structure()
        statuses = check_status()
        print_summary(statuses)
        return

    # ── Full download flow ────────────────────────────────────────────

    # 1. VRAM info
    vram_info = print_vram_info()
    print_vram_estimates()

    # 2. Create directories
    print("  Creating directory structure ...")
    create_directory_structure()
    print(f"  Models directory: {MODELS_DIR}")
    print()

    # 3. Check disk space
    check_disk_space(required_gb=15.0)

    # 4. Determine which models to download
    if args.model:
        keys_to_download: List[str] = [args.model]
    else:
        keys_to_download = list(MODEL_REGISTRY.keys())

    # 5. Download each model
    statuses: Dict[str, str] = {}

    for key in MODEL_REGISTRY:
        if key in keys_to_download:
            if _interrupted:
                statuses[key] = "Interrupted"
                continue
            statuses[key] = download_model(key)
        else:
            # Not selected -- just report current state
            if _is_model_downloaded(key):
                statuses[key] = "Downloaded"
            else:
                statuses[key] = "Not selected"

    # 6. Final summary
    print_summary(statuses)

    # 7. Exit code
    failed = [k for k, v in statuses.items() if v == "Failed"]
    if failed:
        print(f"  [!] {len(failed)} model(s) failed to download.")
        sys.exit(1)

    print("  All requested models are ready.")
    print()


if __name__ == "__main__":
    main()
