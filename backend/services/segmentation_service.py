"""
AuraGen -- SAM2 segmentation service.

Provides point-based and automatic object segmentation using the SAM2 (Segment
Anything 2) tiny model.  The service is designed for low-VRAM environments and
follows the same lazy-load pattern as the generation pipelines.

NOTE: The model loading is fully implemented but the inference methods
currently return **placeholder data** when SAM2 inference fails or is
unavailable.  Full SAM2 inference will be wired up in Phase 2 once the SAM2
build / weight setup is validated in the target environment.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import numpy as np

logger = logging.getLogger(__name__)

# ── Result data classes ──────────────────────────────────────────────────────


@dataclass
class SegmentMask:
    """A single segmentation mask with its bounding box and confidence."""

    mask: np.ndarray  # (H, W) boolean / uint8 array
    bbox: tuple[int, int, int, int]  # (x_min, y_min, x_max, y_max)
    score: float = 0.0
    label: str = ""


@dataclass
class SegmentationResult:
    """Container for a full segmentation response."""

    segments: list[SegmentMask] = field(default_factory=list)
    image_width: int = 0
    image_height: int = 0


# ── Service ──────────────────────────────────────────────────────────────────


class SegmentationService:
    """SAM2-based segmentation with point prompts and automatic detection.

    The service lazy-loads the SAM2 *tiny* checkpoint to keep VRAM usage
    minimal.  On a 4 GB GPU the model occupies roughly 150 MB in fp16.
    """

    # SAM2 tiny model identifier -- lightweight, suitable for real-time use.
    SAM2_MODEL_ID: str = "facebook/sam2-hiera-tiny"

    def __init__(self) -> None:
        self._model: Any | None = None
        self._processor: Any | None = None
        self._loaded: bool = False

    # ── Properties ───────────────────────────────────────────────────────

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    # ── Loading ──────────────────────────────────────────────────────────

    def load(self) -> None:
        """Load the SAM2 tiny model and processor.

        Uses ``transformers`` auto-classes so the correct architecture is
        resolved from the Hub automatically.

        Raises
        ------
        RuntimeError
            If the model cannot be loaded (missing weights, no CUDA, etc.).
        """
        if self._loaded:
            logger.info("SegmentationService already loaded -- skipping.")
            return

        logger.info("Loading SAM2 segmentation model '%s' ...", self.SAM2_MODEL_ID)

        try:
            import torch
            from transformers import Sam2Model, Sam2Processor  # type: ignore[attr-defined]

            from inference.dtype_utils import resolve_dtype, apply_vram_optimizations
            from core.config import settings

            dtype = resolve_dtype(settings.DEVICE)
            self._processor = Sam2Processor.from_pretrained(self.SAM2_MODEL_ID)
            self._model = Sam2Model.from_pretrained(
                self.SAM2_MODEL_ID,
                torch_dtype=dtype,
            )
            # Move to the detected device (CUDA / DirectML / CPU)
            if settings.DEVICE == "cuda":
                self._model.to("cuda")
            elif settings.DEVICE == "privateuseone":
                from inference.dtype_utils import get_directml_device
                dml = get_directml_device()
                if dml is not None:
                    self._model.to(dml)
                else:
                    self._model.to("cpu")
            else:
                self._model.to("cpu")
            self._model.eval()
            self._loaded = True
            logger.info("SAM2 segmentation model loaded successfully.")
        except ImportError:
            logger.warning(
                "SAM2 dependencies (transformers with SAM2 support) not "
                "installed.  Segmentation will use placeholder stubs."
            )
        except Exception:
            logger.warning(
                "Failed to load SAM2 model.  Segmentation will use "
                "placeholder stubs.",
                exc_info=True,
            )

    # ── Point-based segmentation ─────────────────────────────────────────

    def segment_at_point(
        self,
        image_path: str,
        x: int,
        y: int,
    ) -> np.ndarray:
        """Segment the object at pixel coordinates ``(x, y)``.

        Parameters
        ----------
        image_path:
            Absolute path to the input image.
        x, y:
            Click coordinates in pixel space.

        Returns
        -------
        np.ndarray
            A binary mask of shape ``(H, W)`` with dtype ``uint8``
            (255 = foreground, 0 = background).

        Raises
        ------
        FileNotFoundError
            If *image_path* does not exist.
        """
        path = Path(image_path)
        if not path.is_file():
            raise FileNotFoundError(f"Image not found: {image_path}")

        from PIL import Image  # noqa: WPS433

        image = Image.open(path).convert("RGB")
        width, height = image.size

        # TODO Phase 2: Wire up full SAM2 inference once build is validated.
        #   1. Prepare input_points tensor from (x, y).
        #   2. Run self._processor(image, input_points=...) to get model inputs.
        #   3. Forward through self._model(**inputs).
        #   4. Post-process masks via self._processor.post_process_masks().
        #   5. Return the highest-confidence mask.

        if self._loaded and self._model is not None and self._processor is not None:
            try:
                import torch

                input_points = [[[x, y]]]
                inputs = self._processor(
                    images=image,
                    input_points=input_points,
                    return_tensors="pt",
                ).to(self._model.device, dtype=self._model.dtype)

                with torch.inference_mode():
                    outputs = self._model(**inputs)

                masks = self._processor.post_process_masks(
                    outputs.pred_masks,
                    inputs["original_sizes"],
                    inputs["reshaped_input_sizes"],
                )
                # Take the highest-scoring mask.
                best_mask = masks[0][0, 0].cpu().numpy().astype(np.uint8) * 255
                return best_mask

            except Exception:
                logger.warning(
                    "SAM2 inference failed; returning placeholder mask.",
                    exc_info=True,
                )

        # ── Placeholder: circle mask centred on the click point ──────────
        logger.info(
            "Returning placeholder segmentation mask for point (%d, %d).", x, y
        )
        mask = np.zeros((height, width), dtype=np.uint8)
        radius = min(width, height) // 8
        yy, xx = np.ogrid[:height, :width]
        circle = ((xx - x) ** 2 + (yy - y) ** 2) <= radius ** 2
        mask[circle] = 255
        return mask

    # ── Automatic object detection ───────────────────────────────────────

    def get_objects(
        self,
        image_path: str,
    ) -> list[SegmentMask]:
        """Detect and segment all salient objects in the image.

        Parameters
        ----------
        image_path:
            Absolute path to the input image.

        Returns
        -------
        list[SegmentMask]
            A list of ``SegmentMask`` instances, each containing the binary
            mask, bounding box, and confidence score.

        Raises
        ------
        FileNotFoundError
            If *image_path* does not exist.
        """
        path = Path(image_path)
        if not path.is_file():
            raise FileNotFoundError(f"Image not found: {image_path}")

        from PIL import Image  # noqa: WPS433

        image = Image.open(path).convert("RGB")
        width, height = image.size

        # TODO Phase 2: Replace placeholder with SAM2 automatic mask generator.
        #   1. Use SamAutomaticMaskGenerator (or the SAM2 equivalent) to
        #      produce all masks.
        #   2. Filter by score threshold and area.
        #   3. Convert each mask dict into a SegmentMask dataclass.

        if self._loaded and self._model is not None and self._processor is not None:
            try:
                import torch

                # SAM2 automatic segmentation typically uses a grid of points.
                # Generate a coarse grid of prompt points.
                grid_size = 4
                step_x = width // (grid_size + 1)
                step_y = height // (grid_size + 1)
                points = []
                for gy in range(1, grid_size + 1):
                    for gx in range(1, grid_size + 1):
                        points.append([gx * step_x, gy * step_y])

                input_points = [points]
                inputs = self._processor(
                    images=image,
                    input_points=input_points,
                    return_tensors="pt",
                ).to(self._model.device, dtype=self._model.dtype)

                with torch.inference_mode():
                    outputs = self._model(**inputs)

                masks = self._processor.post_process_masks(
                    outputs.pred_masks,
                    inputs["original_sizes"],
                    inputs["reshaped_input_sizes"],
                )

                segments: list[SegmentMask] = []
                scores = outputs.iou_scores[0]  # (num_masks, 3)

                for idx in range(masks[0].shape[1]):
                    binary = masks[0][0, idx].cpu().numpy().astype(np.uint8)
                    if binary.sum() == 0:
                        continue
                    ys, xs = np.where(binary > 0)
                    bbox = (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()))
                    score = float(scores[idx].max()) if idx < scores.shape[0] else 0.0
                    segments.append(
                        SegmentMask(
                            mask=binary * 255,
                            bbox=bbox,
                            score=score,
                            label=f"object_{idx}",
                        )
                    )

                if segments:
                    return segments

            except Exception:
                logger.warning(
                    "SAM2 automatic segmentation failed; returning placeholders.",
                    exc_info=True,
                )

        # ── Placeholder: three synthetic rectangles ──────────────────────
        logger.info("Returning placeholder object segments.")
        segments = []
        for i, (rx, ry, rw, rh) in enumerate(
            [
                (width // 6, height // 6, width // 3, height // 3),
                (width // 2, height // 4, width // 4, height // 4),
                (width // 5, height // 2, width // 3, height // 5),
            ]
        ):
            mask = np.zeros((height, width), dtype=np.uint8)
            x_end = min(rx + rw, width)
            y_end = min(ry + rh, height)
            mask[ry:y_end, rx:x_end] = 255
            segments.append(
                SegmentMask(
                    mask=mask,
                    bbox=(rx, ry, x_end, y_end),
                    score=0.9 - i * 0.1,
                    label=f"placeholder_{i}",
                )
            )
        return segments

    # ── Cleanup ──────────────────────────────────────────────────────────

    def unload(self) -> None:
        """Release the SAM2 model and free VRAM."""
        if self._model is not None:
            del self._model
            self._model = None
        if self._processor is not None:
            del self._processor
            self._processor = None
        self._loaded = False

        try:
            from inference.dtype_utils import safe_empty_cache
            safe_empty_cache()
        except ImportError:
            pass

        logger.info("Segmentation model unloaded.")
