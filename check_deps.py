#!/usr/bin/env python3
"""
AuraGen — Dependency & Import Audit (Intel Iris Xe Edition)

Verifies that every import used across the backend codebase actually
resolves in the current environment, and flags NVIDIA-only packages
that will crash on Intel hardware.

Usage:
    python check_deps.py          # Full audit (prints report)
    python check_deps.py --json   # Machine-readable JSON output

Exit codes:
    0 = All checks passed
    1 = Critical issues found (missing core deps or NVIDIA-only packages)
    2 = Warnings only (optional deps missing)
"""

from __future__ import annotations

import importlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

# ── Packages that MUST be importable for the backend to function ────────────
CORE_DEPS = [
    ("torch", "PyTorch — core ML framework"),
    ("fastapi", "FastAPI — web server"),
    ("uvicorn", "Uvicorn — ASGI server"),
    ("pydantic", "Pydantic — data validation"),
    ("pydantic_settings", "Pydantic Settings — env config"),
    ("PIL", "Pillow — image processing"),
    ("numpy", "NumPy — numerical computing"),
    ("httpx", "httpx — async HTTP client"),
    ("websockets", "websockets — WS protocol"),
    ("aiofiles", "aiofiles — async file I/O"),
    ("safetensors", "safetensors — fast model loading"),
    ("huggingface_hub", "HuggingFace Hub — model downloads"),
    ("accelerate", "Accelerate — device placement"),
]

# ── Packages needed for ML inference ───────────────────────────────────────
ML_DEPS = [
    ("diffusers", "Diffusers — diffusion pipelines"),
    ("transformers", "Transformers — model architectures"),
]

# ── Intel / DirectML specific ──────────────────────────────────────────────
INTEL_DEPS = [
    ("torch_directml", "torch-directml — Intel/AMD GPU acceleration"),
]

# ── NVIDIA-only packages that should NOT be present on Intel ───────────────
NVIDIA_ONLY = [
    ("bitsandbytes", "bitsandbytes — NF4 quantization (NVIDIA CUDA only)"),
    ("xformers", "xFormers — memory-efficient attention (NVIDIA CUDA only)"),
]


@dataclass
class AuditResult:
    core_ok: list[str] = field(default_factory=list)
    core_missing: list[str] = field(default_factory=list)
    ml_ok: list[str] = field(default_factory=list)
    ml_missing: list[str] = field(default_factory=list)
    intel_ok: list[str] = field(default_factory=list)
    intel_missing: list[str] = field(default_factory=list)
    nvidia_present: list[str] = field(default_factory=list)
    nvidia_absent: list[str] = field(default_factory=list)
    torch_info: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def check_import(module_name: str) -> tuple[bool, str]:
    """Try to import a module. Returns (success, version_or_error)."""
    try:
        mod = importlib.import_module(module_name)
        version = getattr(mod, "__version__", "installed")
        return True, version
    except ImportError as e:
        return False, str(e)
    except Exception as e:
        return False, f"import error: {e}"


def run_audit() -> AuditResult:
    result = AuditResult()

    print("=" * 60)
    print("  AuraGen Dependency Audit — Intel Iris Xe Edition")
    print("=" * 60)
    print(f"  Python: {sys.version}")
    print()

    # ── Core dependencies ────────────────────────────────────────────────
    print("-- Core Dependencies --------------------------------------------------")
    for mod, desc in CORE_DEPS:
        ok, info = check_import(mod)
        status = f"  [OK]   {desc}: {info}" if ok else f"  [FAIL] {desc}: {info}"
        print(status)
        (result.core_ok if ok else result.core_missing).append(f"{mod} ({info})")
        if not ok:
            result.errors.append(f"CRITICAL: {mod} is not installed — {desc}")

    # ── ML dependencies ──────────────────────────────────────────────────
    print("\n-- ML / Diffusion Dependencies ----------------------------------------")
    for mod, desc in ML_DEPS:
        ok, info = check_import(mod)
        status = f"  [OK]   {desc}: {info}" if ok else f"  [MISS] {desc}: {info}"
        print(status)
        (result.ml_ok if ok else result.ml_missing).append(f"{mod} ({info})")
        if not ok:
            result.errors.append(f"CRITICAL: {mod} is not installed — {desc}")

    # ── Intel / DirectML ─────────────────────────────────────────────────
    print("\n-- Intel / DirectML Dependencies --------------------------------------")
    for mod, desc in INTEL_DEPS:
        ok, info = check_import(mod)
        status = f"  [OK]   {desc}: {info}" if ok else f"  [MISS] {desc}: {info}"
        print(status)
        (result.intel_ok if ok else result.intel_missing).append(f"{mod} ({info})")
        if not ok:
            result.warnings.append(
                f"WARNING: {mod} not installed — Intel GPU acceleration unavailable. "
                f"Install with: pip install torch-directml"
            )

    # ── NVIDIA-only audit ────────────────────────────────────────────────
    print("\n-- NVIDIA-Only Audit (should NOT be present on Intel) -----------------")
    for mod, desc in NVIDIA_ONLY:
        ok, info = check_import(mod)
        if ok:
            status = f"  [WARN] {desc}: {info} — REMOVE (will crash on Intel)"
            result.nvidia_present.append(f"{mod} ({info})")
            result.warnings.append(
                f"WARNING: {mod} is installed but is NVIDIA-only. "
                f"It may cause import errors on Intel. Remove with: pip uninstall {mod}"
            )
        else:
            status = f"  [OK]   {desc}: not installed (correct for Intel)"
            result.nvidia_absent.append(mod)
        print(status)

    # ── Torch details ────────────────────────────────────────────────────
    print("\n-- PyTorch Configuration ----------------------------------------------")
    try:
        import torch
        cuda_compiled = torch.version.cuda or "None"
        cuda_available = torch.cuda.is_available()
        result.torch_info = {
            "version": torch.__version__,
            "cuda_compiled": cuda_compiled,
            "cuda_available": cuda_available,
        }
        print(f"  Version       : {torch.__version__}")
        print(f"  CUDA compiled : {cuda_compiled}")
        print(f"  CUDA available: {cuda_available}")

        # Check if torch has CUDA in the version string (wrong for Intel)
        if "+cu" in torch.__version__:
            result.warnings.append(
                f"WARNING: PyTorch {torch.__version__} is a CUDA build. "
                f"For Intel, install the CPU build: "
                f"pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu"
            )
            print(f"  [WARN] CUDA build detected in version string — consider CPU build for Intel")

        # Check DirectML
        try:
            import torch_directml
            dml_name = torch_directml.device_name(0)
            result.torch_info["directml_device"] = dml_name
            print(f"  DirectML      : {dml_name}")

            # Smoke test
            t = torch.tensor([1.0], device=torch_directml.device())
            r = (t * 2.0).item()
            del t
            print(f"  DML smoke test: PASS (1.0 * 2.0 = {r})")
            result.torch_info["directml_smoke_test"] = "pass"
        except ImportError:
            print(f"  DirectML      : not installed")
            result.torch_info["directml_device"] = None
        except Exception as e:
            print(f"  DirectML      : FAILED ({e})")
            result.torch_info["directml_smoke_test"] = f"fail: {e}"

    except ImportError:
        print("  [FAIL] PyTorch not installed!")
        result.torch_info = {"error": "not installed"}

    # ── Summary ──────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    total_issues = len(result.errors)
    total_warnings = len(result.warnings)

    if total_issues == 0 and total_warnings == 0:
        print("  RESULT: ALL CHECKS PASSED")
    elif total_issues == 0:
        print(f"  RESULT: PASSED with {total_warnings} warning(s)")
    else:
        print(f"  RESULT: {total_issues} CRITICAL issue(s), {total_warnings} warning(s)")

    for e in result.errors:
        print(f"    {e}")
    for w in result.warnings:
        print(f"    {w}")
    print("=" * 60)

    return result


def main():
    result = run_audit()

    if "--json" in sys.argv:
        out_path = Path("audit_report.json")
        report = {
            "python_version": sys.version,
            "core_ok": result.core_ok,
            "core_missing": result.core_missing,
            "ml_ok": result.ml_ok,
            "ml_missing": result.ml_missing,
            "intel_ok": result.intel_ok,
            "intel_missing": result.intel_missing,
            "nvidia_present_warning": result.nvidia_present,
            "nvidia_absent_ok": result.nvidia_absent,
            "torch_info": result.torch_info,
            "errors": result.errors,
            "warnings": result.warnings,
        }
        out_path.write_text(json.dumps(report, indent=2))
        print(f"\nAudit report written to {out_path}")

    # Exit code
    if result.errors:
        sys.exit(1)
    elif result.warnings:
        sys.exit(2)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
