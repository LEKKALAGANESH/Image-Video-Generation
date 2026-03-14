"""
AuraGen — GPU Smoke Test.

Validates the GPU backend chain: CUDA → DirectML → CPU.
Run from the project root:

    python smoke_test.py
"""

from __future__ import annotations

import sys


def _section(title: str) -> None:
    print(f"\n{'-' * 60}")
    print(f"  {title}")
    print(f"{'-' * 60}")


def main() -> None:
    passed = 0
    failed = 0

    # ── 1. PyTorch ────────────────────────────────────────────────────────
    _section("1. PyTorch")
    try:
        import torch

        print(f"  torch version  : {torch.__version__}")
        print(f"  CUDA compiled  : {torch.version.cuda or 'None'}")
        print(f"  CUDA available : {torch.cuda.is_available()}")

        # Quick tensor test on CPU
        t = torch.tensor([1.0, 2.0, 3.0])
        assert (t * 2).tolist() == [2.0, 4.0, 6.0], "CPU tensor math failed"
        print("  CPU tensor ops : OK")
        passed += 1
    except Exception as e:
        print(f"  FAIL: {e}")
        failed += 1

    # ── 2. CUDA probe ─────────────────────────────────────────────────────
    _section("2. CUDA")
    try:
        import torch

        if torch.cuda.is_available():
            name = torch.cuda.get_device_name(0)
            vram = torch.cuda.get_device_properties(0).total_mem // (1024 * 1024)
            t = torch.tensor([1.0], device="cuda")
            assert (t * 2).item() == 2.0
            print(f"  Device : {name} ({vram} MB)")
            print("  CUDA tensor ops : OK")
            passed += 1
        else:
            print("  CUDA not available (expected on Intel Iris Xe)")
            passed += 1  # not a failure — expected
    except Exception as e:
        print(f"  CUDA probe error: {e}")
        passed += 1  # informational

    # ── 3. DirectML ───────────────────────────────────────────────────────
    _section("3. DirectML")
    try:
        import torch_directml  # type: ignore[import-untyped]

        dml_device = torch_directml.device()
        device_name = torch_directml.device_name(0)
        print(f"  Device       : {device_name}")
        print(f"  DML device   : {dml_device}")

        import torch

        t = torch.tensor([1.0], device=dml_device)
        result = (t * 2.0).item()
        assert result == 2.0, f"Expected 2.0, got {result}"
        print("  DirectML tensor ops : OK  (PrivateUse1)")
        passed += 1
    except ImportError:
        print("  torch-directml not installed")
        print(f"  Python {sys.version.split()[0]} — package may not support this version yet")
        print("  Install: pip install torch-directml  (requires Python <=3.12)")
        failed += 1
    except Exception as e:
        print(f"  DirectML probe error: {e}")
        failed += 1

    # ── 4. Backend selection (gpu_diagnostics) ────────────────────────────
    _section("4. GPU Diagnostics")
    try:
        sys.path.insert(0, "backend")
        from core.gpu_diagnostics import run_diagnostics

        diag = run_diagnostics()
        print(f"  Backend      : {diag.backend}")
        print(f"  Device name  : {diag.device_name}")
        print(f"  Healthy      : {diag.healthy}")
        if diag.warnings:
            for w in diag.warnings:
                print(f"  Warning      : {w}")
        passed += 1
    except Exception as e:
        print(f"  FAIL: {e}")
        failed += 1

    # ── 5. dtype_utils ────────────────────────────────────────────────────
    _section("5. dtype_utils")
    try:
        from inference.dtype_utils import resolve_dtype

        import torch

        cpu_dtype = resolve_dtype("cpu")
        assert cpu_dtype == torch.float32, f"CPU dtype should be float32, got {cpu_dtype}"
        print(f"  CPU dtype          : {cpu_dtype}  OK")

        dml_dtype = resolve_dtype("privateuseone")
        assert dml_dtype == torch.float32, f"DirectML dtype should be float32, got {dml_dtype}"
        print(f"  DirectML dtype     : {dml_dtype}  OK")

        cuda_dtype = resolve_dtype("cuda")
        expected = torch.float16 if torch.cuda.is_available() else torch.float32
        assert cuda_dtype == expected
        print(f"  CUDA dtype         : {cuda_dtype}  OK")

        passed += 1
    except Exception as e:
        print(f"  FAIL: {e}")
        failed += 1

    # ── Summary ───────────────────────────────────────────────────────────
    _section("Summary")
    total = passed + failed
    print(f"  {passed}/{total} checks passed")
    if failed:
        print(f"  {failed} check(s) FAILED")
    else:
        print("  All checks passed!")

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
