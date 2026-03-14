"""
AuraGen -- Audit API routes for the Physical Plausibility checker.

Endpoints
---------
POST /api/audit/image   -- Run a quality audit on a generated image.
POST /api/audit/video   -- Run a quality audit on a generated video.
GET  /api/audit/log     -- Retrieve the full audit failure log.
GET  /api/audit/stats   -- Summary statistics across all audits.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from core.config import settings
from services.quality_audit_service import AuditCheck, AuditResult, QualityAuditService

logger = logging.getLogger("auragen.audit_routes")

router = APIRouter(prefix="/api/audit", tags=["audit"])

# Module-level service singleton.
_audit_service: Optional[QualityAuditService] = None


def _get_service() -> QualityAuditService:
    """Return (and optionally create) the audit service singleton."""
    global _audit_service
    if _audit_service is None:
        _audit_service = QualityAuditService()
    return _audit_service


# =============================================================================
# Pydantic request / response models
# =============================================================================


class AuditImageRequest(BaseModel):
    """Request body for ``POST /api/audit/image``."""

    image_path: str = Field(
        ...,
        min_length=1,
        description="Absolute or output-relative path to the image file.",
    )
    prompt: str = Field(
        ...,
        min_length=1,
        description="The text prompt that produced the image.",
    )


class AuditVideoRequest(BaseModel):
    """Request body for ``POST /api/audit/video``."""

    video_path: str = Field(
        ...,
        min_length=1,
        description="Absolute or output-relative path to the video file.",
    )
    prompt: str = Field(
        ...,
        min_length=1,
        description="The text prompt that produced the video.",
    )


class AuditCheckResponse(BaseModel):
    """Per-check detail in the audit result."""

    name: str
    passed: bool
    score: int = Field(ge=0, le=100)
    detail: str


class AuditResultResponse(BaseModel):
    """Full audit result returned to the client."""

    file_path: str
    prompt: str
    checks: List[AuditCheckResponse]
    overall_score: int = Field(ge=0, le=100)
    passed: bool
    suggested_improvements: List[str]
    timestamp: str


class AuditLogEntry(BaseModel):
    """A single entry from log_improvements.json."""

    timestamp: str
    prompt: str
    file: str
    overall_score: int
    failed_checks: List[str]
    details: Dict[str, Any]
    suggested_improvements: List[str]


class AuditStatsResponse(BaseModel):
    """Summary statistics across all logged audits."""

    total_audits: int
    pass_count: int
    fail_count: int
    pass_rate: float = Field(description="0.0 to 1.0")
    average_score: float
    most_common_failures: List[Dict[str, Any]] = Field(
        description="Ranked list of {check_name, count}."
    )


# =============================================================================
# Helpers
# =============================================================================


def _audit_result_to_response(result: AuditResult) -> AuditResultResponse:
    """Convert an ``AuditResult`` dataclass to the Pydantic response model."""
    return AuditResultResponse(
        file_path=result.file_path,
        prompt=result.prompt,
        checks=[
            AuditCheckResponse(
                name=c.name,
                passed=c.passed,
                score=c.score,
                detail=c.detail,
            )
            for c in result.checks
        ],
        overall_score=result.overall_score,
        passed=result.passed,
        suggested_improvements=result.suggested_improvements,
        timestamp=result.timestamp,
    )


def _resolve_path(raw: str) -> Path:
    """Resolve a user-supplied path, checking output directory as fallback."""
    p = Path(raw)
    if p.is_absolute() and p.exists():
        return p
    candidate = settings.output_path / raw.lstrip("/").lstrip("\\")
    if candidate.exists():
        return candidate
    stripped = raw.replace("/outputs/", "", 1).replace("\\outputs\\", "", 1)
    candidate2 = settings.output_path / stripped
    if candidate2.exists():
        return candidate2
    raise FileNotFoundError(f"File not found: {raw}")


def _read_log() -> List[Dict[str, Any]]:
    """Read the full audit log from disk."""
    log_path = settings.output_path / "log_improvements.json"
    if not log_path.exists():
        return []
    try:
        raw = log_path.read_text(encoding="utf-8").strip()
        if not raw:
            return []
        entries = json.loads(raw)
        return entries if isinstance(entries, list) else []
    except (json.JSONDecodeError, OSError):
        return []


# =============================================================================
# Routes
# =============================================================================


@router.post(
    "/image",
    response_model=AuditResultResponse,
    status_code=status.HTTP_200_OK,
    summary="Run a quality audit on a generated image.",
)
async def audit_image(payload: AuditImageRequest) -> AuditResultResponse:
    """Execute all physical-plausibility checks on the given image."""
    try:
        resolved = _resolve_path(payload.image_path)
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Image not found: {payload.image_path}",
        )

    try:
        service = _get_service()
        result = service.audit_image(str(resolved), payload.prompt)
    except Exception as exc:
        logger.exception("Image audit failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Audit error: {exc}",
        )

    return _audit_result_to_response(result)


@router.post(
    "/video",
    response_model=AuditResultResponse,
    status_code=status.HTTP_200_OK,
    summary="Run a quality audit on a generated video.",
)
async def audit_video(payload: AuditVideoRequest) -> AuditResultResponse:
    """Execute all physical-plausibility checks on the given video."""
    try:
        resolved = _resolve_path(payload.video_path)
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Video not found: {payload.video_path}",
        )

    try:
        service = _get_service()
        result = service.audit_video(str(resolved), payload.prompt)
    except Exception as exc:
        logger.exception("Video audit failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Audit error: {exc}",
        )

    return _audit_result_to_response(result)


@router.get(
    "/log",
    response_model=List[AuditLogEntry],
    status_code=status.HTTP_200_OK,
    summary="Retrieve the full audit failure log.",
)
async def get_audit_log() -> List[Dict[str, Any]]:
    """Return every entry from ``outputs/log_improvements.json``."""
    return _read_log()


@router.get(
    "/stats",
    response_model=AuditStatsResponse,
    status_code=status.HTTP_200_OK,
    summary="Aggregate audit statistics.",
)
async def get_audit_stats() -> AuditStatsResponse:
    """Compute summary statistics across all logged audit entries."""
    entries = _read_log()
    total = len(entries)

    if total == 0:
        return AuditStatsResponse(
            total_audits=0,
            pass_count=0,
            fail_count=0,
            pass_rate=0.0,
            average_score=0.0,
            most_common_failures=[],
        )

    scores = [e.get("overall_score", 0) for e in entries]
    # All entries in the log are failures (score < 60), but compute pass/fail
    # based on the stored score for flexibility.
    pass_count = sum(1 for s in scores if s >= 60)
    fail_count = total - pass_count
    pass_rate = round(pass_count / total, 4) if total else 0.0
    avg_score = round(sum(scores) / total, 2)

    # Count failure occurrences.
    failure_counts: Dict[str, int] = {}
    for entry in entries:
        for check_name in entry.get("failed_checks", []):
            failure_counts[check_name] = failure_counts.get(check_name, 0) + 1

    most_common = sorted(
        [{"check_name": k, "count": v} for k, v in failure_counts.items()],
        key=lambda x: x["count"],
        reverse=True,
    )

    return AuditStatsResponse(
        total_audits=total,
        pass_count=pass_count,
        fail_count=fail_count,
        pass_rate=pass_rate,
        average_score=avg_score,
        most_common_failures=most_common,
    )
