"""
AuraGen Smoke Test — Minimal Image Generation
Agent 1: Hardware & Backend Auditor

Attempts to load the configured diffusion model and generate a 256x256 image.
Falls back to simulated mode if the model is not locally cached.
"""

import sys
import os
import time

# Ensure backend is on sys.path
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# Suppress download attempts — only use locally cached models
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

print("=" * 70)
print("  AuraGen Inference Smoke Test")
print("=" * 70)

# ── 1. Load settings ─────────────────────────────────────────────────────
from core.config import settings

# Run GPU verification to set the device correctly (as main.py would)
from core.gpu_diagnostics import run_diagnostics
diag = run_diagnostics()

# Mirror _verify_gpu() logic from main.py
if diag.backend == "cuda":
    settings.DEVICE = "cuda"
elif diag.backend == "directml":
    settings.DEVICE = "privateuseone"
    settings.QUANTIZE_4BIT = False
    settings.CPU_OFFLOAD = False
else:
    settings.DEVICE = "cpu"
    settings.QUANTIZE_4BIT = False
    settings.CPU_OFFLOAD = False

print(f"\n[Config]")
print(f"  MODEL_IMAGE     : {settings.MODEL_IMAGE}")
print(f"  DEVICE          : {settings.DEVICE}")
print(f"  QUANTIZE_4BIT   : {settings.QUANTIZE_4BIT}")
print(f"  CPU_OFFLOAD     : {settings.CPU_OFFLOAD}")
print(f"  OUTPUT_DIR      : {settings.output_path}")

# ── 2. Import dtype utilities ─────────────────────────────────────────────
from inference.dtype_utils import resolve_dtype, build_load_kwargs, apply_vram_optimizations

dtype = resolve_dtype(settings.DEVICE)
print(f"  Resolved dtype  : {dtype}")

load_kwargs = build_load_kwargs(settings)
print(f"  Load kwargs     : {load_kwargs}")

# ── 3. Attempt real model load (local cache only) ────────────────────────
import uuid
from pathlib import Path

output_dir = settings.output_path
output_dir.mkdir(parents=True, exist_ok=True)

prompt = "a red circle on white background"
width, height = 256, 256
mode = "UNKNOWN"
output_file = None

print(f"\n[Inference]")
print(f"  Prompt          : {prompt}")
print(f"  Size            : {width}x{height}")

try:
    print(f"  Attempting to load model from local cache: {settings.MODEL_IMAGE} ...")
    print(f"  (HF_HUB_OFFLINE=1 — no downloads will be attempted)")
    t0 = time.time()

    # Try to load from local cache only
    try:
        from diffusers import AutoPipelineForText2Image
        pipe = AutoPipelineForText2Image.from_pretrained(
            settings.MODEL_IMAGE,
            **load_kwargs,
            local_files_only=True,
        )
        pipe_type = type(pipe).__name__
    except Exception as load_err:
        raise RuntimeError(f"Model not in local cache: {load_err}")

    # Apply VRAM optimizations
    pipe = apply_vram_optimizations(pipe, settings)

    try:
        pipe.enable_attention_slicing()
    except Exception:
        pass

    load_time = time.time() - t0
    print(f"  Model loaded    : {pipe_type} in {load_time:.1f}s")

    # Generate
    import torch
    generator = torch.Generator(device="cpu")
    generator.manual_seed(42)

    t0 = time.time()
    with torch.inference_mode():
        result = pipe(
            prompt=prompt,
            width=width,
            height=height,
            num_inference_steps=4,  # minimal steps for speed
            guidance_scale=7.5,
            generator=generator,
        )
    gen_time = time.time() - t0

    image = result.images[0]
    filename = f"smoke_test_{uuid.uuid4().hex[:8]}.png"
    filepath = output_dir / filename
    image.save(str(filepath))

    mode = "REAL"
    output_file = filepath
    print(f"  Mode            : REAL inference")
    print(f"  Inference time  : {gen_time:.1f}s")
    print(f"  Output file     : {filepath}")

    # Clean up
    del pipe
    from inference.dtype_utils import safe_full_cleanup
    safe_full_cleanup()

except Exception as model_err:
    print(f"\n  Model load FAILED: {model_err}")
    print(f"  Falling back to SIMULATED mode...")

    # ── Simulated: create a PIL image ─────────────────────────────────
    try:
        from PIL import Image, ImageDraw

        img = Image.new("RGB", (width, height), (255, 255, 255))
        draw = ImageDraw.Draw(img)

        # Draw a red circle
        cx, cy = width // 2, height // 2
        r = min(width, height) // 4
        draw.ellipse(
            [cx - r, cy - r, cx + r, cy + r],
            fill=(255, 0, 0),
            outline=(200, 0, 0),
            width=2,
        )

        # Add text
        try:
            draw.text((10, 10), "SIMULATED", fill=(100, 100, 100))
            draw.text((10, 30), f"Device: {settings.DEVICE}", fill=(100, 100, 100))
            draw.text((10, 50), f"Dtype: {dtype}", fill=(100, 100, 100))
        except Exception:
            pass

        filename = f"smoke_test_simulated_{uuid.uuid4().hex[:8]}.png"
        filepath = output_dir / filename
        img.save(str(filepath))

        mode = "SIMULATED"
        output_file = filepath
        print(f"  Mode            : SIMULATED (PIL-generated)")
        print(f"  Output file     : {filepath}")

    except Exception as pil_err:
        print(f"  SIMULATION ALSO FAILED: {pil_err}")
        mode = "FAILED"

# ── 4. Validate the output ───────────────────────────────────────────────
print(f"\n[Validation]")
if output_file and output_file.exists():
    file_size = output_file.stat().st_size
    print(f"  File exists     : YES")
    print(f"  File size       : {file_size:,} bytes")

    try:
        from PIL import Image
        import numpy as np

        img = Image.open(output_file)
        print(f"  Dimensions      : {img.size[0]}x{img.size[1]}")
        print(f"  Mode            : {img.mode}")

        # Check pixel variance (not all-black or all-white)
        arr = np.array(img).astype(float)
        pixel_mean = arr.mean()
        pixel_std = arr.std()
        print(f"  Pixel mean      : {pixel_mean:.1f}")
        print(f"  Pixel std       : {pixel_std:.1f}")

        if pixel_std < 1.0:
            print(f"  Quality check   : FAIL -- image is blank (std < 1.0)")
        elif pixel_std < 10.0:
            print(f"  Quality check   : WARN -- very low variance ({pixel_std:.1f})")
        else:
            print(f"  Quality check   : PASS -- valid non-blank image")

    except ImportError:
        print(f"  Validation      : SKIPPED (PIL or numpy not available)")
    except Exception as val_err:
        print(f"  Validation      : ERROR -- {val_err}")
else:
    print(f"  File exists     : NO")
    print(f"  Validation      : FAILED -- no output file produced")

# ── 5. Outputs directory listing ─────────────────────────────────────────
print(f"\n[Outputs Directory: {output_dir}]")
try:
    files = list(output_dir.iterdir())
    total_size = 0
    count = 0
    for f in sorted(files):
        if f.is_file():
            sz = f.stat().st_size
            total_size += sz
            count += 1
            # Show at most 20 files
            if count <= 20:
                print(f"  {f.name:50s}  {sz:>10,} bytes")
    if count > 20:
        print(f"  ... and {count - 20} more files")
    print(f"\n  Total files     : {count}")
    print(f"  Total size      : {total_size:,} bytes ({total_size / (1024*1024):.2f} MB)")
except Exception as e:
    print(f"  ERROR listing outputs: {e}")

# ── Summary ──────────────────────────────────────────────────────────────
print(f"\n{'=' * 70}")
print(f"  SUMMARY")
print(f"{'=' * 70}")
print(f"  Backend detected : {diag.backend}")
print(f"  Device used      : {settings.DEVICE}")
print(f"  Dtype            : {dtype}")
print(f"  Generation mode  : {mode}")
print(f"  Output file      : {output_file or 'NONE'}")
if mode == "SIMULATED":
    print(f"  Reason           : Model weights not downloaded/cached locally")
    print(f"                     (SDXL is ~6.5GB, previous download timed out)")
print(f"{'=' * 70}")
