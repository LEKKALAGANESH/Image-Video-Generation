"""
AuraGen -- Hybrid-cloud bursting service.

Provides a smart routing layer that decides whether to run a generation job
locally on the 4 GB GPU or burst to a cloud API when the task is too heavy.

Cloud providers are abstracted behind the ``CloudProvider`` base class so new
backends can be added without touching the routing logic.
"""

from __future__ import annotations

import abc
import asyncio
import io
import logging
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

import httpx

from core.config import Settings, settings
from services.generation_service import GenerationService, ImageJob, VideoJob

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Cloud provider abstraction
# ═══════════════════════════════════════════════════════════════════════════════


class CloudProvider(abc.ABC):
    """Base class for all cloud inference providers."""

    name: str = "base"

    @abc.abstractmethod
    async def generate(self, prompt: str, params: Dict[str, Any]) -> bytes:
        """Send a generation request and return the raw image/video bytes.

        Parameters
        ----------
        prompt:
            The text prompt for generation.
        params:
            Provider-specific parameters (width, height, etc.).

        Returns
        -------
        bytes
            Raw binary content of the generated artifact.
        """
        ...


class HuggingFaceProvider(CloudProvider):
    """Cloud provider using the Hugging Face Inference API (free tier).

    Uses the ``stabilityai/stable-diffusion-xl-base-1.0`` model by default,
    which is available on the free inference API.
    """

    name: str = "huggingface"

    # Default model endpoint on HF Inference API.
    DEFAULT_MODEL = "black-forest-labs/FLUX.1-schnell"
    BASE_URL = "https://router.huggingface.co/hf-inference/models"

    def __init__(self, api_token: str, model: Optional[str] = None) -> None:
        self._api_token = api_token
        self._model = model or self.DEFAULT_MODEL
        self._url = f"{self.BASE_URL}/{self._model}"

    async def generate(self, prompt: str, params: Dict[str, Any]) -> bytes:
        """Call the HF Inference API and return raw image bytes.

        Parameters
        ----------
        prompt:
            Text prompt for the generation.
        params:
            Additional parameters forwarded to the API payload.

        Returns
        -------
        bytes
            PNG/JPEG image bytes returned by the API.

        Raises
        ------
        RuntimeError
            If the API returns a non-200 status or an error payload.
        """
        headers: Dict[str, str] = {}
        if self._api_token:
            headers["Authorization"] = f"Bearer {self._api_token}"

        payload: Dict[str, Any] = {
            "inputs": prompt,
            "parameters": {
                "width": params.get("width", 512),
                "height": params.get("height", 512),
                "num_inference_steps": params.get("num_steps", 20),
                "guidance_scale": params.get("guidance_scale", 7.5),
            },
        }

        negative = params.get("negative_prompt", "")
        if negative:
            payload["parameters"]["negative_prompt"] = negative

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                self._url,
                headers=headers,
                json=payload,
            )

        if response.status_code != 200:
            detail = response.text[:500]
            raise RuntimeError(
                f"HuggingFace API returned {response.status_code}: {detail}"
            )

        # The Inference API returns raw image bytes on success.
        content_type = response.headers.get("content-type", "")
        if "json" in content_type:
            # Sometimes the API returns JSON errors even with a 200 status.
            import json

            try:
                body = response.json()
                if isinstance(body, dict) and "error" in body:
                    raise RuntimeError(f"HuggingFace API error: {body['error']}")
            except json.JSONDecodeError:
                pass

        return response.content


class ReplicateProvider(CloudProvider):
    """Cloud provider stub for the Replicate API.

    This is a placeholder implementation. In production you would implement the
    full Replicate prediction lifecycle (create -> poll -> fetch output).
    """

    name: str = "replicate"

    # Example model version (SDXL on Replicate).
    DEFAULT_VERSION = "stability-ai/sdxl:latest"
    BASE_URL = "https://api.replicate.com/v1/predictions"

    def __init__(self, api_token: str, version: Optional[str] = None) -> None:
        self._api_token = api_token
        self._version = version or self.DEFAULT_VERSION

    async def generate(self, prompt: str, params: Dict[str, Any]) -> bytes:
        """Submit a prediction to Replicate and return the result bytes.

        .. note::
            This is a stub implementation. A real integration would poll the
            prediction endpoint until completion and then download the output.

        Raises
        ------
        RuntimeError
            Always, until a real Replicate token and integration are provided.
        """
        if not self._api_token:
            raise RuntimeError(
                "Replicate API token is not configured. "
                "Set REPLICATE_API_TOKEN in your environment."
            )

        headers = {
            "Authorization": f"Token {self._api_token}",
            "Content-Type": "application/json",
        }

        payload = {
            "version": self._version,
            "input": {
                "prompt": prompt,
                "width": params.get("width", 512),
                "height": params.get("height", 512),
                "num_inference_steps": params.get("num_steps", 20),
                "guidance_scale": params.get("guidance_scale", 7.5),
            },
        }

        negative = params.get("negative_prompt", "")
        if negative:
            payload["input"]["negative_prompt"] = negative

        async with httpx.AsyncClient(timeout=180.0) as client:
            # Step 1: Create prediction.
            create_resp = await client.post(
                self.BASE_URL,
                headers=headers,
                json=payload,
            )

            if create_resp.status_code not in (200, 201):
                raise RuntimeError(
                    f"Replicate API returned {create_resp.status_code}: "
                    f"{create_resp.text[:500]}"
                )

            prediction = create_resp.json()
            prediction_url = prediction.get("urls", {}).get("get", "")
            if not prediction_url:
                raise RuntimeError(
                    "Replicate prediction response missing status URL."
                )

            # Step 2: Poll until completed (up to 3 minutes).
            max_polls = 60
            for _ in range(max_polls):
                await asyncio.sleep(3.0)
                poll_resp = await client.get(prediction_url, headers=headers)
                if poll_resp.status_code != 200:
                    continue
                status_data = poll_resp.json()
                pred_status = status_data.get("status", "")
                if pred_status == "succeeded":
                    output = status_data.get("output")
                    if isinstance(output, list) and len(output) > 0:
                        # Output is usually a list of URLs.
                        image_url = output[0]
                        image_resp = await client.get(image_url)
                        if image_resp.status_code == 200:
                            return image_resp.content
                    raise RuntimeError(
                        "Replicate prediction succeeded but output is empty."
                    )
                elif pred_status == "failed":
                    error = status_data.get("error", "Unknown error")
                    raise RuntimeError(f"Replicate prediction failed: {error}")

            raise RuntimeError(
                "Replicate prediction timed out after polling."
            )


# ═══════════════════════════════════════════════════════════════════════════════
# Cloud burst service
# ═══════════════════════════════════════════════════════════════════════════════


class CloudBurstService:
    """Smart routing layer for hybrid local/cloud generation.

    Analyses each incoming job to decide whether the local 4 GB GPU can handle
    it.  When the job exceeds the hardware budget the service transparently
    bursts it to a configured cloud inference provider.

    Parameters
    ----------
    config:
        Application settings (``Settings`` instance).
    """

    # Bytes-per-pixel estimate: channels (4 for RGBA) * 4 bytes (fp32).
    _BYTES_PER_PIXEL: int = 4 * 4

    def __init__(self, config: Settings) -> None:
        self._config = config
        self._providers: Dict[str, CloudProvider] = {}
        self._init_providers()

    # ── Provider initialisation ───────────────────────────────────────────

    def _init_providers(self) -> None:
        """Instantiate the available cloud providers based on configuration."""
        self._providers["huggingface"] = HuggingFaceProvider(
            api_token=self._config.HF_API_TOKEN,
        )
        self._providers["replicate"] = ReplicateProvider(
            api_token=self._config.REPLICATE_API_TOKEN,
        )

    @property
    def cloud_providers(self) -> List[str]:
        """Return the list of registered provider names."""
        return list(self._providers.keys())

    def _get_provider(self) -> CloudProvider:
        """Return the currently configured cloud provider."""
        name = self._config.CLOUD_PROVIDER.lower()
        if name not in self._providers:
            raise ValueError(
                f"Unknown cloud provider '{name}'. "
                f"Available: {', '.join(self._providers)}"
            )
        return self._providers[name]

    # ── VRAM estimation ───────────────────────────────────────────────────

    def estimate_vram_mb(self, job: Union[ImageJob, VideoJob]) -> float:
        """Estimate peak VRAM usage for a job in megabytes.

        The estimate uses a simplified heuristic:
        ``width * height * channels * bytes_per_channel`` for images, with an
        additional ``num_frames`` multiplier for video jobs.  A constant
        overhead factor accounts for model weights, activations, and KV cache.

        Parameters
        ----------
        job:
            An ``ImageJob`` or ``VideoJob`` dataclass.

        Returns
        -------
        float
            Estimated VRAM consumption in megabytes.
        """
        channels = 4  # RGBA
        bytes_per_channel = 4  # fp32

        pixel_bytes = job.width * job.height * channels * bytes_per_channel

        if isinstance(job, VideoJob):
            pixel_bytes *= job.num_frames

        # Convert to MB.
        pixel_mb = pixel_bytes / (1024 * 1024)

        # Add overhead for model weights, optimizer state, activations.
        # Rough multiplier: ~2x for diffusion model overhead.
        model_overhead_mb = 1500.0  # base model footprint estimate
        activation_factor = 2.0

        total_mb = pixel_mb * activation_factor + model_overhead_mb
        return round(total_mb, 2)

    # ── Decision logic ────────────────────────────────────────────────────

    def should_burst(self, job: Union[ImageJob, VideoJob]) -> bool:
        """Decide whether a job should be sent to the cloud.

        The decision tree:

        1. If ``CLOUD_ENABLED`` is ``False`` → always run locally.
        2. If the job type is ``"upscale_4k"`` → always burst.
        3. If image dimensions exceed ``BURST_THRESHOLD_IMAGE`` → burst.
        4. If video frame count exceeds ``BURST_THRESHOLD_FRAMES`` → burst.
        5. If estimated VRAM exceeds ``VRAM_BUDGET_MB`` → burst.
        6. Otherwise → run locally.

        Parameters
        ----------
        job:
            An ``ImageJob`` or ``VideoJob`` dataclass.

        Returns
        -------
        bool
            ``True`` if the job should be sent to the cloud.
        """
        if not self._config.CLOUD_ENABLED:
            return False

        # Video generation is not supported by current cloud providers
        # (HuggingFace FLUX.1-schnell is image-only). Always run locally.
        if isinstance(job, VideoJob):
            logger.info("Video job detected -- running locally (cloud video not supported).")
            return False

        # Check for explicit upscale_4k job type (conveyed via prompt prefix
        # or a custom attribute if present).
        job_type_str = getattr(job, "job_type", None) or ""
        if job_type_str == "upscale_4k":
            logger.info("Job is upscale_4k -- forcing cloud burst.")
            return True

        # Dimension check.
        if job.width > self._config.BURST_THRESHOLD_IMAGE:
            logger.info(
                "Width %d exceeds burst threshold %d -- bursting to cloud.",
                job.width,
                self._config.BURST_THRESHOLD_IMAGE,
            )
            return True

        if job.height > self._config.BURST_THRESHOLD_IMAGE:
            logger.info(
                "Height %d exceeds burst threshold %d -- bursting to cloud.",
                job.height,
                self._config.BURST_THRESHOLD_IMAGE,
            )
            return True

        # Frame count check (video only).
        if isinstance(job, VideoJob):
            if job.num_frames > self._config.BURST_THRESHOLD_FRAMES:
                logger.info(
                    "Frame count %d exceeds burst threshold %d -- bursting.",
                    job.num_frames,
                    self._config.BURST_THRESHOLD_FRAMES,
                )
                return True

        # VRAM budget check.
        estimated = self.estimate_vram_mb(job)
        if estimated > self._config.VRAM_BUDGET_MB:
            logger.info(
                "Estimated VRAM %.1f MB exceeds budget %d MB -- bursting.",
                estimated,
                self._config.VRAM_BUDGET_MB,
            )
            return True

        return False

    # ── Job routing ───────────────────────────────────────────────────────

    def route_job(
        self,
        job: Union[ImageJob, VideoJob],
        progress_callback: Optional[Callable[[float], None]] = None,
    ) -> str:
        """Route a job to local GPU or cloud provider and return the filename.

        If cloud execution fails, the service automatically falls back to
        local generation as a safety net.

        Parameters
        ----------
        job:
            An ``ImageJob`` or ``VideoJob`` to execute.
        progress_callback:
            Optional callable receiving a float in ``[0, 1]``.

        Returns
        -------
        str
            Output filename (relative to ``OUTPUT_DIR``).

        Raises
        ------
        RuntimeError
            If both cloud and local execution fail.
        """
        if self.should_burst(job):
            logger.info("Routing job to cloud provider '%s'.", self._config.CLOUD_PROVIDER)
            try:
                return self._run_cloud(job, progress_callback)
            except Exception as exc:
                logger.warning(
                    "Cloud execution failed (%s), falling back to local: %s",
                    self._config.CLOUD_PROVIDER,
                    exc,
                )
                if progress_callback:
                    progress_callback(0.0)
                return self._run_local(job, progress_callback)
        else:
            logger.info("Routing job to local GPU.")
            return self._run_local(job, progress_callback)

    # ── Local execution ───────────────────────────────────────────────────

    def _run_local(
        self,
        job: Union[ImageJob, VideoJob],
        progress_callback: Optional[Callable[[float], None]] = None,
    ) -> str:
        """Execute a job on the local GPU via ``GenerationService``.

        Parameters
        ----------
        job:
            The generation job.
        progress_callback:
            Optional progress reporter.

        Returns
        -------
        str
            Output filename.
        """
        service = GenerationService(self._config)

        if isinstance(job, ImageJob):
            return service.generate_image(job, progress_callback)
        else:
            return service.generate_video(job, progress_callback)

    # ── Cloud execution ───────────────────────────────────────────────────

    def _run_cloud(
        self,
        job: Union[ImageJob, VideoJob],
        progress_callback: Optional[Callable[[float], None]] = None,
    ) -> str:
        """Execute a job on a cloud provider and save the result locally.

        Progress is estimated based on elapsed time vs. a conservative
        timeout, since cloud APIs typically don't stream progress.

        Parameters
        ----------
        job:
            The generation job.
        progress_callback:
            Optional progress reporter.

        Returns
        -------
        str
            Output filename (relative to ``OUTPUT_DIR``).

        Raises
        ------
        RuntimeError
            If the cloud provider returns an error.
        """
        provider = self._get_provider()

        # Build params dict from the job.
        params: Dict[str, Any] = {
            "width": job.width,
            "height": job.height,
            "num_steps": job.num_steps,
            "guidance_scale": job.guidance_scale,
            "negative_prompt": job.negative_prompt,
        }
        if isinstance(job, VideoJob):
            params["num_frames"] = job.num_frames
        if job.seed is not None:
            params["seed"] = job.seed

        # Estimate total time for progress reporting.
        estimated_seconds = 30.0  # conservative default for cloud APIs.

        # Report initial progress.
        if progress_callback:
            progress_callback(0.05)

        # Run the async provider in a synchronous context.
        start_time = time.monotonic()

        # Create a background progress reporter.
        stop_progress = False

        def _progress_ticker() -> None:
            """Report estimated progress while waiting for the cloud API."""
            import threading

            while not stop_progress:
                elapsed = time.monotonic() - start_time
                fraction = min(0.90, elapsed / estimated_seconds)
                if progress_callback:
                    progress_callback(fraction)
                time.sleep(1.0)

        import threading

        progress_thread: Optional[threading.Thread] = None
        if progress_callback:
            progress_thread = threading.Thread(
                target=_progress_ticker, daemon=True
            )
            progress_thread.start()

        try:
            # Run the async generate call.
            loop: Optional[asyncio.AbstractEventLoop] = None
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            logger.info("Cloud API URL: %s", provider._url)
            if loop and loop.is_running():
                # We're inside an existing event loop -- use a new thread.
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(
                        asyncio.run,
                        provider.generate(job.prompt, params),
                    )
                    result_bytes = future.result(timeout=180.0)
            else:
                try:
                    result_bytes = asyncio.run(
                        provider.generate(job.prompt, params)
                    )
                except Exception as cloud_exc:
                    logger.error("Cloud API call failed: %s: %s", type(cloud_exc).__name__, cloud_exc)
                    raise
        finally:
            stop_progress = True
            if progress_thread is not None:
                progress_thread.join(timeout=2.0)

        # Validate: if this is a video job, verify the response is actual video data
        # (not an image returned by an image-only API)
        if isinstance(job, VideoJob) and len(result_bytes) > 4:
            # Check for JPEG header (FF D8 FF) or PNG header (89 50 4E 47)
            header = result_bytes[:4]
            if header[:3] == b'\xff\xd8\xff' or header[:4] == b'\x89PNG':
                raise RuntimeError(
                    "Cloud API returned an image instead of video. "
                    "The cloud provider does not support video generation."
                )

        # Determine output extension and filename.
        if isinstance(job, VideoJob):
            ext = ".mp4"
        else:
            ext = ".png"

        filename = f"{uuid.uuid4().hex}{ext}"
        output_path = Path(self._config.OUTPUT_DIR).resolve()
        output_path.mkdir(parents=True, exist_ok=True)
        file_path = output_path / filename

        file_path.write_bytes(result_bytes)
        logger.info("Cloud result saved to %s (%d bytes).", file_path, len(result_bytes))

        if progress_callback:
            progress_callback(1.0)

        return filename
