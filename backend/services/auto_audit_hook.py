"""
AuraGen -- Auto-audit hook for post-generation quality checks.

Provides ``auto_audit_after_generation`` which is designed to be called
from the job-queue worker immediately after a generation job completes.
It runs the appropriate audit (image or video) and logs failures
automatically.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from core.config import settings
from services.quality_audit_service import AuditResult, QualityAuditService

logger = logging.getLogger("auragen.auto_audit")

# Module-level singleton so the service is reused across invocations.
_audit_service: QualityAuditService | None = None


def _get_audit_service() -> QualityAuditService:
    """Return (and optionally create) the audit service singleton."""
    global _audit_service
    if _audit_service is None:
        _audit_service = QualityAuditService()
    return _audit_service


def auto_audit_after_generation(
    job: Any,
    result_filename: str,
) -> AuditResult:
    """Run a quality audit on a freshly generated artifact.

    This function is intended to be called **synchronously** by the
    job-queue worker after every successful generation.  It inspects the
    file extension to decide whether to run an image or video audit.

    Parameters
    ----------
    job:
        The ``Job`` dataclass from ``backend_queue.job_queue``.  Must have at
        least ``.prompt`` (str) and ``.type`` attributes.  The ``type``
        attribute should be a ``JobType`` enum with a ``.value`` of
        ``"image"`` or ``"video"``.
    result_filename:
        The filename (relative to ``settings.output_path``) of the
        generated artifact, e.g. ``"abc123.png"`` or ``"def456.mp4"``.

    Returns
    -------
    AuditResult
        The full audit result.  If the score is below 60 the failure is
        automatically logged to ``outputs/log_improvements.json``.
    """
    service = _get_audit_service()

    # Resolve the full file path.
    file_path = settings.output_path / result_filename
    abs_path = str(file_path)

    # Extract the prompt from the job.
    prompt: str = getattr(job, "prompt", "") or ""

    # Determine job type.
    job_type_str: str = ""
    job_type = getattr(job, "type", None)
    if job_type is not None:
        job_type_str = getattr(job_type, "value", str(job_type)).lower()

    # Fallback: infer from file extension.
    ext = Path(result_filename).suffix.lower()
    is_video = job_type_str == "video" or ext in (".mp4", ".avi", ".mov", ".webm", ".gif")

    logger.info(
        "Auto-audit starting for %s (type=%s, prompt=%r)",
        result_filename,
        "video" if is_video else "image",
        prompt[:80],
    )

    try:
        if is_video:
            result = service.audit_video(abs_path, prompt)
        else:
            result = service.audit_image(abs_path, prompt)
    except Exception as exc:
        logger.error(
            "Auto-audit failed for %s: %s", result_filename, exc, exc_info=True
        )
        # Return a minimal failing result so the caller still gets something.
        from services.quality_audit_service import AuditCheck

        result = AuditResult(
            file_path=abs_path,
            prompt=prompt,
            checks=[
                AuditCheck(
                    name="audit_error",
                    passed=False,
                    score=0,
                    detail=f"Audit could not be completed: {exc}",
                )
            ],
            overall_score=0,
            passed=False,
            suggested_improvements=["Audit system encountered an error. Check logs."],
        )
        service.log_failure(result, prompt)
        return result

    logger.info(
        "Auto-audit complete for %s: score=%d, passed=%s",
        result_filename,
        result.overall_score,
        result.passed,
    )

    return result
