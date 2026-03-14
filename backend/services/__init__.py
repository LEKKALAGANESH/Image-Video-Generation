"""
AuraGen -- Services sub-package.

Re-exports the orchestration, segmentation, and quality-audit services.
"""

from services.generation_service import GenerationService, ImageJob, VideoJob
from services.segmentation_service import (
    SegmentationResult,
    SegmentationService,
    SegmentMask,
)
from services.quality_audit_service import (
    AuditCheck,
    AuditResult,
    QualityAuditService,
)
from services.auto_audit_hook import auto_audit_after_generation

__all__ = [
    "GenerationService",
    "ImageJob",
    "VideoJob",
    "SegmentationService",
    "SegmentMask",
    "SegmentationResult",
    "QualityAuditService",
    "AuditCheck",
    "AuditResult",
    "auto_audit_after_generation",
]
