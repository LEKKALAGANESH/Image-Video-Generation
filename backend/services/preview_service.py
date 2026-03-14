"""
AuraGen — Preview Service.

Generates compressed preview and thumbnail variants of generated media
for network-aware delivery.  Uses PIL for images and ffmpeg (if available)
for video transcoding.

Quality presets:
  - **thumbnail**: 128px max dimension, JPEG q20
  - **preview**:   480px max dimension, JPEG q45
  - **full**:      original resolution (pass-through)
"""

from __future__ import annotations

import logging
import os
import subprocess
import shutil
from pathlib import Path
from typing import Literal

from PIL import Image

from core.config import settings

logger = logging.getLogger("auragen.preview")

PreviewTier = Literal["thumbnail", "preview"]

# ── Configuration ────────────────────────────────────────────────────────────

PREVIEW_CONFIG = {
    "thumbnail": {"max_size": 128, "quality": 20, "suffix": "_thumb"},
    "preview":   {"max_size": 480, "quality": 45, "suffix": "_preview"},
}

_ffmpeg_path: str | None = shutil.which("ffmpeg")


# ═════════════════════════════════════════════════════════════════════════════
# Image previews (PIL)
# ═════════════════════════════════════════════════════════════════════════════

def generate_image_preview(
    source_path: Path,
    tier: PreviewTier = "preview",
) -> Path | None:
    """Create a compressed JPEG preview of *source_path*.

    Returns the path to the preview file, or ``None`` on failure.
    """
    cfg = PREVIEW_CONFIG[tier]
    stem = source_path.stem
    out_name = f"{stem}{cfg['suffix']}.jpg"
    out_path = source_path.parent / out_name

    # Skip if already generated
    if out_path.exists():
        return out_path

    try:
        with Image.open(source_path) as img:
            img = img.convert("RGB")
            img.thumbnail((cfg["max_size"], cfg["max_size"]), Image.LANCZOS)
            img.save(out_path, "JPEG", quality=cfg["quality"], optimize=True)

        logger.info(
            "Generated %s preview: %s → %s (%d bytes)",
            tier,
            source_path.name,
            out_name,
            out_path.stat().st_size,
        )
        return out_path

    except Exception as exc:
        logger.warning("Failed to generate %s preview for %s: %s", tier, source_path.name, exc)
        return None


def generate_all_image_previews(source_path: Path) -> dict[str, Path | None]:
    """Generate both thumbnail and preview variants for an image."""
    return {
        "thumbnail": generate_image_preview(source_path, "thumbnail"),
        "preview": generate_image_preview(source_path, "preview"),
    }


# ═════════════════════════════════════════════════════════════════════════════
# Video previews (ffmpeg)
# ═════════════════════════════════════════════════════════════════════════════

def generate_video_preview(
    source_path: Path,
    tier: PreviewTier = "preview",
) -> Path | None:
    """Create a compressed video preview using ffmpeg.

    For **preview** tier: re-encode at 480p, CRF 32, fast preset.
    For **thumbnail** tier: extract a single poster frame as JPEG.
    """
    cfg = PREVIEW_CONFIG[tier]
    stem = source_path.stem

    if tier == "thumbnail":
        # Extract poster frame
        out_name = f"{stem}{cfg['suffix']}.jpg"
        out_path = source_path.parent / out_name
        if out_path.exists():
            return out_path

        if _ffmpeg_path is None:
            # Fallback: no ffmpeg — skip video thumbnail
            logger.debug("ffmpeg not found; skipping video thumbnail for %s", source_path.name)
            return None

        try:
            subprocess.run(
                [
                    _ffmpeg_path, "-y",
                    "-i", str(source_path),
                    "-vframes", "1",
                    "-q:v", "8",
                    "-vf", f"scale={cfg['max_size']}:-2",
                    str(out_path),
                ],
                capture_output=True,
                timeout=15,
                check=True,
            )
            logger.info("Generated video thumbnail: %s", out_name)
            return out_path
        except Exception as exc:
            logger.warning("Video thumbnail failed for %s: %s", source_path.name, exc)
            return None

    # Preview tier — compressed video
    out_name = f"{stem}{cfg['suffix']}.mp4"
    out_path = source_path.parent / out_name
    if out_path.exists():
        return out_path

    if _ffmpeg_path is None:
        logger.debug("ffmpeg not found; skipping video preview for %s", source_path.name)
        return None

    try:
        subprocess.run(
            [
                _ffmpeg_path, "-y",
                "-i", str(source_path),
                "-vf", f"scale={cfg['max_size']}:-2",
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-crf", "32",
                "-an",
                "-movflags", "+faststart",
                str(out_path),
            ],
            capture_output=True,
            timeout=60,
            check=True,
        )
        logger.info(
            "Generated video preview: %s (%d bytes)",
            out_name,
            out_path.stat().st_size,
        )
        return out_path
    except Exception as exc:
        logger.warning("Video preview failed for %s: %s", source_path.name, exc)
        return None


def generate_all_video_previews(source_path: Path) -> dict[str, Path | None]:
    """Generate both thumbnail and preview variants for a video."""
    return {
        "thumbnail": generate_video_preview(source_path, "thumbnail"),
        "preview": generate_video_preview(source_path, "preview"),
    }


# ═════════════════════════════════════════════════════════════════════════════
# Unified entry point
# ═════════════════════════════════════════════════════════════════════════════

def generate_previews(source_path: Path) -> dict[str, str | None]:
    """Generate all preview variants for a media file.

    Returns a dict of ``{"thumbnail": url_or_none, "preview": url_or_none}``
    relative to the outputs mount.
    """
    suffix = source_path.suffix.lower()
    is_video = suffix in {".mp4", ".webm", ".avi", ".mov"}

    if is_video:
        paths = generate_all_video_previews(source_path)
    else:
        paths = generate_all_image_previews(source_path)

    # Convert paths to URL-relative strings
    result: dict[str, str | None] = {}
    for key, path in paths.items():
        if path is not None and path.exists():
            result[key] = f"/outputs/{path.name}"
        else:
            result[key] = None

    return result
