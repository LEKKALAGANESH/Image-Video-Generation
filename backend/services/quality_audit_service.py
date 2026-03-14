"""
AuraGen -- Physical Plausibility quality-control service.

Provides ``QualityAuditService`` which runs a battery of heuristic checks on
generated images and videos to detect common failure modes such as excessive
noise, blown-out highlights, blank outputs, and temporal flickering.

No ML models are required -- all checks use pure PIL / numpy operations.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from PIL import Image, ImageFilter

from core.config import settings

logger = logging.getLogger("auragen.quality_audit")


# =============================================================================
# Data classes
# =============================================================================


@dataclass
class AuditCheck:
    """Result of a single quality check."""

    name: str
    passed: bool
    score: int  # 0-100
    detail: str


@dataclass
class AuditResult:
    """Aggregate audit result for an image or video."""

    file_path: str
    prompt: str
    checks: List[AuditCheck]
    overall_score: int
    passed: bool  # True if overall_score >= 60
    suggested_improvements: List[str]
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a plain dictionary (JSON-safe)."""
        return {
            "file_path": self.file_path,
            "prompt": self.prompt,
            "checks": [asdict(c) for c in self.checks],
            "overall_score": self.overall_score,
            "passed": self.passed,
            "suggested_improvements": self.suggested_improvements,
            "timestamp": self.timestamp,
        }


# =============================================================================
# Service
# =============================================================================


class QualityAuditService:
    """Runs physical-plausibility checks on generated images and videos.

    All checks are implemented with PIL and numpy -- no GPU or ML model
    is required.
    """

    # Thresholds (tunable)
    MIN_RESOLUTION: int = 256
    MAX_RESOLUTION: int = 8192
    BRIGHTNESS_PERCENTILE_THRESHOLD: float = 0.80
    NOISE_VARIANCE_THRESHOLD: float = 3000.0
    EDGE_DENSITY_MAX: float = 0.45
    ASPECT_RATIO_MIN: float = 0.25
    ASPECT_RATIO_MAX: float = 4.0
    SOLID_COLOR_STD_THRESHOLD: float = 5.0
    TEMPORAL_DIFF_THRESHOLD: float = 40.0  # mean pixel diff
    MOTION_MIN_DIFF: float = 1.5  # minimum mean diff for "motion detected"
    PASS_THRESHOLD: int = 60

    def __init__(self) -> None:
        self._log_path: Path = settings.output_path / "log_improvements.json"
        logger.info(
            "QualityAuditService initialised (log: %s)", self._log_path
        )

    # =====================================================================
    # Image audit
    # =====================================================================

    def audit_image(self, image_path: str, prompt: str) -> AuditResult:
        """Run all image-level quality checks.

        Parameters
        ----------
        image_path:
            Absolute or output-relative path to the generated image.
        prompt:
            The text prompt that produced the image.

        Returns
        -------
        AuditResult
            Aggregated result with per-check details.
        """
        img = Image.open(image_path).convert("RGB")
        arr = np.array(img, dtype=np.float32)

        checks: List[AuditCheck] = [
            self._check_resolution(img),
            self._check_color_distribution(arr),
            self._check_noise(arr),
            self._check_edge_coherence(img, arr),
            self._check_aspect_ratio(img),
            self._check_blank_solid(arr),
            self._check_prompt_length_correlation(img, arr, prompt),
        ]

        overall_score = self._compute_overall_score(checks)
        passed = overall_score >= self.PASS_THRESHOLD

        failed_names = [c.name for c in checks if not c.passed]
        suggestions = self.get_improvement_suggestions(failed_names)

        result = AuditResult(
            file_path=str(image_path),
            prompt=prompt,
            checks=checks,
            overall_score=overall_score,
            passed=passed,
            suggested_improvements=suggestions,
        )

        if not passed:
            self.log_failure(result, prompt)

        return result

    # =====================================================================
    # Video audit
    # =====================================================================

    def audit_video(self, video_path: str, prompt: str) -> AuditResult:
        """Run quality checks on a video file.

        Extracts the first, middle, and last frames and runs per-frame
        image audits, plus video-specific temporal checks.

        Parameters
        ----------
        video_path:
            Path to the generated video (MP4).
        prompt:
            The text prompt that produced the video.

        Returns
        -------
        AuditResult
        """
        frames = self._extract_frames(video_path)

        if not frames:
            return AuditResult(
                file_path=str(video_path),
                prompt=prompt,
                checks=[
                    AuditCheck(
                        name="frame_extraction",
                        passed=False,
                        score=0,
                        detail="Could not extract any frames from the video.",
                    )
                ],
                overall_score=0,
                passed=False,
                suggested_improvements=[
                    "Video file appears corrupt or unreadable."
                ],
            )

        # Run image audit on first, middle, last frames.
        frame_checks: List[AuditCheck] = []
        frame_scores: List[int] = []

        sample_indices = self._pick_sample_indices(len(frames))
        for idx in sample_indices:
            frame = frames[idx]
            arr = np.array(frame, dtype=np.float32)
            checks_for_frame = [
                self._check_resolution(frame),
                self._check_color_distribution(arr),
                self._check_noise(arr),
                self._check_edge_coherence(frame, arr),
                self._check_blank_solid(arr),
            ]
            score = self._compute_overall_score(checks_for_frame)
            frame_scores.append(score)

        avg_frame_score = int(np.mean(frame_scores)) if frame_scores else 0
        frame_checks.append(
            AuditCheck(
                name="frame_quality",
                passed=avg_frame_score >= self.PASS_THRESHOLD,
                score=avg_frame_score,
                detail=f"Average frame quality score: {avg_frame_score}/100 "
                f"across {len(sample_indices)} sampled frames.",
            )
        )

        # Video-specific checks.
        frame_checks.append(self._check_temporal_consistency(frames))
        frame_checks.append(self._check_motion(frames))
        frame_checks.append(self._check_frame_count(frames))

        overall_score = self._compute_overall_score(frame_checks)
        passed = overall_score >= self.PASS_THRESHOLD

        failed_names = [c.name for c in frame_checks if not c.passed]
        suggestions = self.get_improvement_suggestions(failed_names)

        result = AuditResult(
            file_path=str(video_path),
            prompt=prompt,
            checks=frame_checks,
            overall_score=overall_score,
            passed=passed,
            suggested_improvements=suggestions,
        )

        if not passed:
            self.log_failure(result, prompt)

        return result

    # =====================================================================
    # Logging
    # =====================================================================

    def log_failure(self, result: AuditResult, prompt: str) -> None:
        """Append a failure entry to ``outputs/log_improvements.json``.

        Creates the file with an empty JSON array if it does not exist.
        """
        self._log_path.parent.mkdir(parents=True, exist_ok=True)

        # Read existing entries.
        entries: List[Dict[str, Any]] = []
        if self._log_path.exists():
            try:
                raw = self._log_path.read_text(encoding="utf-8").strip()
                if raw:
                    entries = json.loads(raw)
                    if not isinstance(entries, list):
                        entries = []
            except (json.JSONDecodeError, OSError):
                entries = []

        failed_checks = [c.name for c in result.checks if not c.passed]
        details = {c.name: c.detail for c in result.checks}

        entry: Dict[str, Any] = {
            "timestamp": result.timestamp,
            "prompt": prompt,
            "file": result.file_path,
            "overall_score": result.overall_score,
            "failed_checks": failed_checks,
            "details": details,
            "suggested_improvements": result.suggested_improvements,
        }

        entries.append(entry)

        self._log_path.write_text(
            json.dumps(entries, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info(
            "Logged audit failure for %s (score=%d)",
            result.file_path,
            result.overall_score,
        )

    # =====================================================================
    # Improvement suggestions
    # =====================================================================

    _SUGGESTION_MAP: Dict[str, str] = {
        "noise_detection": (
            "Increase inference steps or reduce guidance scale"
        ),
        "color_distribution": (
            "Try adjusting prompt for balanced lighting"
        ),
        "color_distribution_dark": (
            "Try adding 'bright, well-lit' to your prompt"
        ),
        "color_distribution_bright": (
            "Try adding 'balanced lighting' to your prompt"
        ),
        "edge_coherence": (
            "Reduce image resolution or increase steps"
        ),
        "temporal_consistency": (
            "Reduce number of frames or increase video steps"
        ),
        "blank_image": (
            "Check that the model loaded correctly, try a different prompt"
        ),
        "no_motion": (
            "Add motion keywords to prompt: 'moving', 'walking', 'flowing'"
        ),
        "resolution": (
            "Adjust output dimensions to at least 256x256"
        ),
        "aspect_ratio": (
            "Use a more standard aspect ratio (between 1:4 and 4:1)"
        ),
        "frame_count": (
            "Ensure the video generation produces enough frames"
        ),
        "frame_quality": (
            "Individual frames have quality issues -- review image audit suggestions"
        ),
        "prompt_complexity": (
            "Your prompt may be too simple for the output complexity, or vice versa"
        ),
    }

    def get_improvement_suggestions(
        self, failed_checks: List[str]
    ) -> List[str]:
        """Map failed check names to actionable suggestions.

        Parameters
        ----------
        failed_checks:
            List of check ``name`` values that did not pass.

        Returns
        -------
        list[str]
            Human-readable improvement suggestions.
        """
        suggestions: List[str] = []
        seen: set[str] = set()
        for name in failed_checks:
            suggestion = self._SUGGESTION_MAP.get(name)
            if suggestion and suggestion not in seen:
                suggestions.append(suggestion)
                seen.add(suggestion)
        return suggestions

    # =====================================================================
    # Individual checks
    # =====================================================================

    def _check_resolution(self, img: Image.Image) -> AuditCheck:
        """Check that the image resolution is within sane bounds."""
        w, h = img.size
        if w < self.MIN_RESOLUTION or h < self.MIN_RESOLUTION:
            return AuditCheck(
                name="resolution",
                passed=False,
                score=20,
                detail=f"Image is {w}x{h}, below minimum {self.MIN_RESOLUTION}x{self.MIN_RESOLUTION}.",
            )
        if w > self.MAX_RESOLUTION or h > self.MAX_RESOLUTION:
            return AuditCheck(
                name="resolution",
                passed=False,
                score=30,
                detail=f"Image is {w}x{h}, exceeds maximum {self.MAX_RESOLUTION}x{self.MAX_RESOLUTION}.",
            )
        # Score scales with resolution up to a sweet spot.
        score = min(100, int(60 + (min(w, h) / 1024) * 40))
        return AuditCheck(
            name="resolution",
            passed=True,
            score=score,
            detail=f"Resolution {w}x{h} is within acceptable range.",
        )

    def _check_color_distribution(self, arr: np.ndarray) -> AuditCheck:
        """Check for overly dark or bright images using histogram analysis.

        Flags the image if more than 80% of pixels fall in the bottom 10%
        or top 10% of the brightness range.
        """
        # Convert to grayscale luminance.
        gray = 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]
        total_pixels = gray.size

        dark_pixels = int(np.sum(gray < 25.5))  # bottom 10% of 0-255
        bright_pixels = int(np.sum(gray > 229.5))  # top 10% of 0-255

        dark_ratio = dark_pixels / total_pixels
        bright_ratio = bright_pixels / total_pixels

        if dark_ratio > self.BRIGHTNESS_PERCENTILE_THRESHOLD:
            return AuditCheck(
                name="color_distribution_dark",
                passed=False,
                score=int((1.0 - dark_ratio) * 100),
                detail=f"{dark_ratio:.1%} of pixels are in the bottom 10% brightness. Image is too dark.",
            )

        if bright_ratio > self.BRIGHTNESS_PERCENTILE_THRESHOLD:
            return AuditCheck(
                name="color_distribution_bright",
                passed=False,
                score=int((1.0 - bright_ratio) * 100),
                detail=f"{bright_ratio:.1%} of pixels are in the top 10% brightness. Image is too bright.",
            )

        # Healthy distribution.
        balance = 1.0 - max(dark_ratio, bright_ratio)
        score = max(60, min(100, int(balance * 120)))
        return AuditCheck(
            name="color_distribution",
            passed=True,
            score=score,
            detail=f"Color distribution is balanced (dark: {dark_ratio:.1%}, bright: {bright_ratio:.1%}).",
        )

    def _check_noise(self, arr: np.ndarray) -> AuditCheck:
        """Detect noise by computing local variance across 8x8 patches.

        High average variance across small patches indicates noisy or
        failed generation.
        """
        gray = 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]
        h, w = gray.shape
        patch_size = 8

        # Truncate to fit whole patches.
        h_trunc = (h // patch_size) * patch_size
        w_trunc = (w // patch_size) * patch_size
        if h_trunc == 0 or w_trunc == 0:
            return AuditCheck(
                name="noise_detection",
                passed=True,
                score=50,
                detail="Image too small for noise analysis.",
            )

        cropped = gray[:h_trunc, :w_trunc]
        patches = cropped.reshape(
            h_trunc // patch_size, patch_size, w_trunc // patch_size, patch_size
        )
        patch_vars = patches.var(axis=(1, 3))
        avg_variance = float(np.mean(patch_vars))

        if avg_variance > self.NOISE_VARIANCE_THRESHOLD:
            score = max(0, int(100 - (avg_variance / self.NOISE_VARIANCE_THRESHOLD) * 50))
            return AuditCheck(
                name="noise_detection",
                passed=False,
                score=score,
                detail=f"Average patch variance {avg_variance:.1f} exceeds threshold {self.NOISE_VARIANCE_THRESHOLD}. Likely noisy.",
            )

        score = max(60, min(100, int(100 - (avg_variance / self.NOISE_VARIANCE_THRESHOLD) * 40)))
        return AuditCheck(
            name="noise_detection",
            passed=True,
            score=score,
            detail=f"Noise level acceptable (avg patch variance: {avg_variance:.1f}).",
        )

    def _check_edge_coherence(
        self, img: Image.Image, arr: np.ndarray
    ) -> AuditCheck:
        """Apply a Sobel-like edge filter and check edge density.

        Excessively high edge density suggests artifacts or fragmentation.
        """
        gray_img = img.convert("L")
        edges = gray_img.filter(ImageFilter.FIND_EDGES)
        edge_arr = np.array(edges, dtype=np.float32)

        # Edge density = fraction of pixels above a threshold.
        threshold = 50.0
        edge_pixels = int(np.sum(edge_arr > threshold))
        total_pixels = edge_arr.size
        edge_density = edge_pixels / total_pixels

        if edge_density > self.EDGE_DENSITY_MAX:
            score = max(0, int(100 - (edge_density / self.EDGE_DENSITY_MAX) * 60))
            return AuditCheck(
                name="edge_coherence",
                passed=False,
                score=score,
                detail=f"Edge density {edge_density:.3f} exceeds {self.EDGE_DENSITY_MAX}. Possible artifacts.",
            )

        score = max(60, min(100, int(100 - edge_density * 100)))
        return AuditCheck(
            name="edge_coherence",
            passed=True,
            score=score,
            detail=f"Edge coherence acceptable (density: {edge_density:.3f}).",
        )

    def _check_aspect_ratio(self, img: Image.Image) -> AuditCheck:
        """Verify the aspect ratio is within a sane range (0.25 to 4.0)."""
        w, h = img.size
        if h == 0:
            return AuditCheck(
                name="aspect_ratio",
                passed=False,
                score=0,
                detail="Image has zero height.",
            )
        ratio = w / h
        if ratio < self.ASPECT_RATIO_MIN or ratio > self.ASPECT_RATIO_MAX:
            return AuditCheck(
                name="aspect_ratio",
                passed=False,
                score=30,
                detail=f"Aspect ratio {ratio:.2f} is outside [{self.ASPECT_RATIO_MIN}, {self.ASPECT_RATIO_MAX}].",
            )
        # Score higher for ratios closer to 1:1 or common cinema ratios.
        deviation = abs(ratio - 1.0)
        score = max(70, int(100 - deviation * 15))
        return AuditCheck(
            name="aspect_ratio",
            passed=True,
            score=score,
            detail=f"Aspect ratio {ratio:.2f} is acceptable.",
        )

    def _check_blank_solid(self, arr: np.ndarray) -> AuditCheck:
        """Detect if the image is essentially a single solid colour."""
        std = float(np.std(arr))
        if std < self.SOLID_COLOR_STD_THRESHOLD:
            mean_color = arr.mean(axis=(0, 1)).astype(int).tolist()
            return AuditCheck(
                name="blank_image",
                passed=False,
                score=0,
                detail=f"Image appears blank/solid (std={std:.2f}, mean color ~{mean_color}).",
            )
        score = min(100, max(70, int(70 + (std / 50) * 30)))
        return AuditCheck(
            name="blank_image",
            passed=True,
            score=score,
            detail=f"Image has sufficient colour variation (std={std:.2f}).",
        )

    def _check_prompt_length_correlation(
        self,
        img: Image.Image,
        arr: np.ndarray,
        prompt: str,
    ) -> AuditCheck:
        """Heuristic: longer prompts should produce more complex images.

        Measures edge density as a proxy for visual complexity and compares
        to prompt word count.
        """
        word_count = len(prompt.split())

        gray_img = img.convert("L")
        edges = gray_img.filter(ImageFilter.FIND_EDGES)
        edge_arr = np.array(edges, dtype=np.float32)
        edge_density = float(np.sum(edge_arr > 50)) / edge_arr.size

        # Heuristic: expect at least 0.01 edge density per 5 words of prompt.
        expected_min_density = min(0.3, word_count * 0.002)

        if word_count > 15 and edge_density < expected_min_density:
            return AuditCheck(
                name="prompt_complexity",
                passed=False,
                score=45,
                detail=f"Prompt has {word_count} words but edge density is only {edge_density:.4f} "
                f"(expected >= {expected_min_density:.4f}). Output may be too simple.",
            )

        score = min(100, max(65, int(70 + edge_density * 100)))
        return AuditCheck(
            name="prompt_complexity",
            passed=True,
            score=score,
            detail=f"Prompt complexity ({word_count} words) matches output complexity (edge density {edge_density:.4f}).",
        )

    # =====================================================================
    # Video-specific checks
    # =====================================================================

    def _check_temporal_consistency(
        self, frames: List[Image.Image]
    ) -> AuditCheck:
        """Compare adjacent sampled frames for flickering.

        Large pixel-level differences between consecutive frames indicate
        temporal instability.
        """
        if len(frames) < 2:
            return AuditCheck(
                name="temporal_consistency",
                passed=True,
                score=70,
                detail="Only one frame available; temporal check skipped.",
            )

        diffs: List[float] = []
        for i in range(len(frames) - 1):
            a = np.array(frames[i].convert("RGB"), dtype=np.float32)
            b = np.array(frames[i + 1].convert("RGB"), dtype=np.float32)
            # Resize if shapes don't match.
            if a.shape != b.shape:
                smaller = frames[i + 1].resize(frames[i].size)
                b = np.array(smaller.convert("RGB"), dtype=np.float32)
            mean_diff = float(np.mean(np.abs(a - b)))
            diffs.append(mean_diff)

        max_diff = max(diffs)
        avg_diff = float(np.mean(diffs))

        if max_diff > self.TEMPORAL_DIFF_THRESHOLD:
            score = max(0, int(100 - (max_diff / self.TEMPORAL_DIFF_THRESHOLD) * 50))
            return AuditCheck(
                name="temporal_consistency",
                passed=False,
                score=score,
                detail=f"Max frame diff {max_diff:.2f} exceeds threshold {self.TEMPORAL_DIFF_THRESHOLD}. "
                f"Possible flickering (avg diff: {avg_diff:.2f}).",
            )

        score = max(65, min(100, int(100 - (max_diff / self.TEMPORAL_DIFF_THRESHOLD) * 35)))
        return AuditCheck(
            name="temporal_consistency",
            passed=True,
            score=score,
            detail=f"Temporal consistency acceptable (max diff: {max_diff:.2f}, avg: {avg_diff:.2f}).",
        )

    def _check_motion(self, frames: List[Image.Image]) -> AuditCheck:
        """Verify there is some visible motion between frames.

        A completely static output likely means the video pipeline
        produced the same frame repeatedly.
        """
        if len(frames) < 2:
            return AuditCheck(
                name="no_motion",
                passed=True,
                score=50,
                detail="Only one frame; motion check skipped.",
            )

        first = np.array(frames[0].convert("RGB"), dtype=np.float32)
        last = np.array(frames[-1].convert("RGB"), dtype=np.float32)
        if first.shape != last.shape:
            resized = frames[-1].resize(frames[0].size)
            last = np.array(resized.convert("RGB"), dtype=np.float32)

        mean_diff = float(np.mean(np.abs(first - last)))

        if mean_diff < self.MOTION_MIN_DIFF:
            return AuditCheck(
                name="no_motion",
                passed=False,
                score=15,
                detail=f"Almost no motion detected between first and last frame (diff: {mean_diff:.3f}). "
                f"Video may be static.",
            )

        score = min(100, max(65, int(65 + mean_diff * 2)))
        return AuditCheck(
            name="no_motion",
            passed=True,
            score=score,
            detail=f"Motion detected (first-last diff: {mean_diff:.2f}).",
        )

    def _check_frame_count(self, frames: List[Image.Image]) -> AuditCheck:
        """Check that the video has a reasonable number of frames."""
        count = len(frames)
        if count < 2:
            return AuditCheck(
                name="frame_count",
                passed=False,
                score=10,
                detail=f"Video has only {count} frame(s). Expected at least 2.",
            )
        if count < 8:
            return AuditCheck(
                name="frame_count",
                passed=True,
                score=50,
                detail=f"Video has {count} frames. Short but valid.",
            )
        score = min(100, 60 + count)
        return AuditCheck(
            name="frame_count",
            passed=True,
            score=score,
            detail=f"Video has {count} frames.",
        )

    # =====================================================================
    # Helpers
    # =====================================================================

    @staticmethod
    def _compute_overall_score(checks: List[AuditCheck]) -> int:
        """Compute a weighted overall score from individual checks.

        Failed checks are weighted 1.5x to pull the score down faster.
        """
        if not checks:
            return 0
        total_weight = 0.0
        weighted_sum = 0.0
        for c in checks:
            weight = 1.5 if not c.passed else 1.0
            weighted_sum += c.score * weight
            total_weight += weight * 100
        if total_weight == 0:
            return 0
        return int((weighted_sum / total_weight) * 100)

    @staticmethod
    def _pick_sample_indices(frame_count: int) -> List[int]:
        """Pick first, middle, and last frame indices."""
        if frame_count == 0:
            return []
        if frame_count == 1:
            return [0]
        if frame_count == 2:
            return [0, 1]
        mid = frame_count // 2
        return [0, mid, frame_count - 1]

    @staticmethod
    def _extract_frames(video_path: str) -> List[Image.Image]:
        """Extract frames from a video file.

        Tries OpenCV first; falls back to extracting frames from GIF or
        returning an empty list for unsupported formats.
        """
        path = Path(video_path)
        frames: List[Image.Image] = []

        # Try OpenCV first.
        try:
            import cv2  # type: ignore[import-untyped]

            cap = cv2.VideoCapture(str(path))
            if not cap.isOpened():
                logger.warning("OpenCV could not open %s", video_path)
            else:
                while True:
                    ret, frame = cap.read()
                    if not ret:
                        break
                    # Convert BGR -> RGB.
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    frames.append(Image.fromarray(rgb))
                cap.release()
                if frames:
                    return frames
        except ImportError:
            logger.debug("OpenCV not available; trying PIL for frame extraction.")

        # Fallback: PIL can read multi-frame formats (GIF, TIFF, WebP).
        try:
            img = Image.open(path)
            n_frames = getattr(img, "n_frames", 1)
            for i in range(n_frames):
                img.seek(i)
                frames.append(img.copy().convert("RGB"))
            return frames
        except Exception as exc:
            logger.warning("PIL frame extraction failed for %s: %s", video_path, exc)

        return frames
