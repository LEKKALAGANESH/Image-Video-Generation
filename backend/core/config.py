"""
AuraGen — Application configuration.

Centralizes all tunable settings using Pydantic BaseSettings so values can be
overridden via environment variables or a .env file without touching code.
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Global application settings.

    Every field can be overridden by setting the corresponding environment
    variable (case-insensitive, prefixed with ``AURAGEN_`` when
    ``env_prefix`` is configured — here we keep it simple with no prefix).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Model identifiers ────────────────────────────────────────────────
    MODEL_IMAGE: str = "black-forest-labs/FLUX.1-schnell"
    MODEL_VIDEO: str = "Wan-AI/Wan2.1-T2V-1.3B"
    MODEL_VIDEO_FALLBACK: str = "THUDM/CogVideoX-2b"

    # ── Hardware / runtime ───────────────────────────────────────────────
    # "auto" = detect at startup (CUDA → DirectML → CPU)
    DEVICE: str = "auto"
    QUANTIZE_4BIT: bool = False
    CPU_OFFLOAD: bool = False

    # ── Generation constraints (keep VRAM < 4 GB) ───────────────────────
    MAX_IMAGE_SIZE: int = 768
    MAX_VIDEO_FRAMES: int = 33
    MAX_VIDEO_SIZE: int = 480

    # ── V2 Video settings ────────────────────────────────────────────────
    MODEL_VIDEO_V2: str = "Wan-AI/Wan2.1-T2V-1.3B-Distilled"
    MODEL_VIDEO_V2_FALLBACK: str = "Wan-AI/Wan2.1-T2V-1.3B"
    VIDEO_DEFAULT_FPS: int = 16
    VIDEO_PHYSICS_MODES: list[str] = ["natural", "cinematic", "slow-motion"]
    USE_V2_PIPELINE: bool = True

    # ── Storage ──────────────────────────────────────────────────────────
    OUTPUT_DIR: str = "./outputs"
    MODELS_DIR: str = "./models"

    # ── Server ───────────────────────────────────────────────────────────
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    # ── Queue ────────────────────────────────────────────────────────────
    MAX_QUEUE_SIZE: int = 10

    # ── Cloud bursting ────────────────────────────────────────────────────
    CLOUD_ENABLED: bool = False
    CLOUD_PROVIDER: str = "huggingface"  # "huggingface" | "replicate"
    HF_API_TOKEN: str = ""
    REPLICATE_API_TOKEN: str = ""
    VRAM_BUDGET_MB: int = 3500  # 4GB minus OS overhead
    BURST_THRESHOLD_IMAGE: int = 1024  # burst if dimension exceeds this
    BURST_THRESHOLD_FRAMES: int = 60  # burst if frames exceed this

    # ── Network-Aware Delivery ────────────────────────────────────────────
    PREVIEW_MAX_SIZE: int = 480         # max dimension for preview tier
    THUMBNAIL_MAX_SIZE: int = 128       # max dimension for thumbnail tier
    PREVIEW_JPEG_QUALITY: int = 45      # JPEG quality for previews
    THUMBNAIL_JPEG_QUALITY: int = 20    # JPEG quality for thumbnails
    AUTO_GENERATE_PREVIEWS: bool = True # auto-generate on job completion
    CACHE_TTL_FULL: int = 86400         # 24h TTL for full-res assets
    CACHE_TTL_PREVIEW: int = 604800     # 7d TTL for compressed previews
    CACHE_TTL_THUMBNAIL: int = 2592000  # 30d TTL for thumbnails

    # ── Helpers ──────────────────────────────────────────────────────────

    @property
    def output_path(self) -> Path:
        """Return the resolved output directory, creating it if needed."""
        path = Path(self.OUTPUT_DIR).resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def models_path(self) -> Path:
        """Return the resolved models directory, creating it if needed."""
        path = Path(self.MODELS_DIR).resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path


# Module-level singleton so other modules can simply ``from core.config import settings``.
settings = Settings()
