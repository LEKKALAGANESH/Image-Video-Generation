"""
AuraGen Smoke Test — GPU/Device Diagnostics
Agent 1: Hardware & Backend Auditor
"""

import sys
import os

# Ensure backend is on sys.path
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

print("=" * 70)
print("  AuraGen GPU / Device Smoke Test")
print("=" * 70)

# ── 1. PyTorch basics ────────────────────────────────────────────────────
import torch

print(f"\n[1] PyTorch version   : {torch.__version__}")
print(f"    CUDA compiled     : {torch.version.cuda or 'N/A'}")
print(f"    cuDNN available   : {torch.backends.cudnn.is_available()}")
print(f"    CUDA available    : {torch.cuda.is_available()}")

if torch.cuda.is_available():
    print(f"    CUDA device count : {torch.cuda.device_count()}")
    print(f"    CUDA device name  : {torch.cuda.get_device_name(0)}")
    props = torch.cuda.get_device_properties(0)
    vram = props.total_mem // (1024 * 1024)
    print(f"    VRAM              : {vram} MB")
else:
    print("    CUDA              : NOT available")

# ── 2. DirectML check ───────────────────────────────────────────────────
print("\n[2] DirectML probe:")
try:
    import torch_directml
    dml_device = torch_directml.device()
    dml_name = torch_directml.device_name(0)
    # Quick tensor test
    t = torch.tensor([1.0, 2.0, 3.0], device=dml_device)
    result = (t * 2.0).cpu().tolist()
    print(f"    torch_directml    : INSTALLED")
    print(f"    Device name       : {dml_name}")
    print(f"    Device object     : {dml_device}")
    print(f"    Tensor smoke test : [1,2,3]*2 = {result}  (PASS)")
    directml_ok = True
except ImportError:
    print("    torch_directml    : NOT INSTALLED")
    directml_ok = False
except Exception as e:
    print(f"    torch_directml    : ERROR — {e}")
    directml_ok = False

# ── 3. GPU diagnostics module ──────────────────────────────────────────
print("\n[3] AuraGen gpu_diagnostics.run_diagnostics():")
try:
    from core.gpu_diagnostics import run_diagnostics
    diag = run_diagnostics()
    d = diag.to_dict()
    for k, v in d.items():
        if k == "warnings":
            print(f"    {k:22s}: {v}")
        else:
            print(f"    {k:22s}: {v}")
except Exception as e:
    print(f"    ERROR: {e}")
    import traceback
    traceback.print_exc()

# ── 4. Effective device for AuraGen ────────────────────────────────────
print("\n[4] Effective backend decision:")
if torch.cuda.is_available():
    effective = "cuda"
    print(f"    Will use           : CUDA (NVIDIA GPU)")
elif directml_ok:
    effective = "privateuseone"
    print(f"    Will use           : DirectML (privateuseone) — {dml_name}")
else:
    effective = "cpu"
    print(f"    Will use           : CPU (no GPU acceleration)")

# ── 5. dtype resolution ───────────────────────────────────────────────
print("\n[5] dtype resolution for effective device:")
try:
    from inference.dtype_utils import resolve_dtype
    dtype = resolve_dtype(effective)
    print(f"    resolve_dtype('{effective}') = {dtype}")
except Exception as e:
    print(f"    ERROR: {e}")

print("\n" + "=" * 70)
print("  Smoke test complete.")
print("=" * 70)
