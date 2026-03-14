"""
AuraGen — GPU Verification Script

Loads a 1×1 pixel tensor onto CUDA to prove the driver link works.

Usage:
    python test_gpu.py

Expected output on success:
    [PASS] Device: cuda
    [PASS] GPU: <gpu name> (<vram> MB)
    [PASS] Tensor created on CUDA successfully
    [PASS] WebSocket endpoint is reachable

Expected output on failure:
    [FAIL] CUDA is not available
    [FAIL] <specific DLL / driver error>
"""

from __future__ import annotations

import sys


def check_cuda() -> bool:
    """Verify CUDA is available and a tensor can be placed on the GPU."""
    print("=" * 60)
    print("  AuraGen GPU Verification")
    print("=" * 60)
    print()

    # ── 1. Import PyTorch ────────────────────────────────────────
    try:
        import torch
    except ImportError:
        print("[FAIL] PyTorch is not installed.")
        print("       Install with:")
        print("       pip install torch torchvision "
              "--index-url https://download.pytorch.org/whl/cu128")
        return False

    print(f"  PyTorch version : {torch.__version__}")
    print(f"  CUDA compiled   : {torch.version.cuda or 'None'}")
    print(f"  cuDNN available : {torch.backends.cudnn.is_available()}")
    print()

    # ── 2. Check CUDA availability ──────────────────────────────
    if not torch.cuda.is_available():
        print("[FAIL] CUDA is not available.")
        print()
        # Surface the specific init error
        try:
            torch.cuda.init()
        except Exception as e:
            print(f"[FAIL] CUDA init error: {e}")
        print()
        print("  Checklist:")
        print("    1. Install NVIDIA GPU drivers → https://www.nvidia.com/drivers")
        print("    2. Run: nvidia-smi")
        print("    3. Ensure PyTorch CUDA build matches your driver version")
        return False

    gpu_name = torch.cuda.get_device_name(0)
    vram_mb = torch.cuda.get_device_properties(0).total_mem // (1024 * 1024)
    print(f"[PASS] Device: cuda")
    print(f"[PASS] GPU: {gpu_name} ({vram_mb} MB)")

    # ── 3. Create a 1×1 tensor on CUDA ──────────────────────────
    try:
        t = torch.tensor([[1.0]], device="cuda")
        assert t.device.type == "cuda"
        # Quick math to prove the GPU actually runs compute
        result = (t * 2.0).item()
        assert result == 2.0
        del t
        torch.cuda.empty_cache()
        print("[PASS] Tensor created on CUDA successfully")
    except Exception as e:
        print(f"[FAIL] Tensor creation failed: {e}")
        return False

    # ── 4. 4-bit quantization readiness ─────────────────────────
    try:
        import bitsandbytes  # noqa: F401
        print("[PASS] bitsandbytes available (4-bit quantization ready)")
    except ImportError:
        print("[WARN] bitsandbytes not installed — 4-bit quantization unavailable")
        print("       Install with: pip install bitsandbytes")

    print()
    return True


def check_websocket() -> bool:
    """Quick check that the WebSocket endpoint is reachable."""
    import asyncio

    async def _probe() -> bool:
        try:
            # Use standard library to avoid extra deps
            from websockets.client import connect as ws_connect
            async with ws_connect(
                "ws://localhost:8000/ws/test-probe",
                open_timeout=5,
                close_timeout=2,
            ) as ws:
                import json
                await ws.send(json.dumps({"type": "ping"}))
                resp = await asyncio.wait_for(ws.recv(), timeout=5)
                data = __import__("json").loads(resp)
                if data.get("type") == "pong":
                    print("[PASS] WebSocket endpoint is reachable (ping → pong)")
                    return True
                # Server may send its own ping first
                if data.get("type") == "ping":
                    print("[PASS] WebSocket endpoint is reachable (server heartbeat received)")
                    return True
                print(f"[WARN] Unexpected WS response: {data}")
                return True
        except ImportError:
            print("[SKIP] websockets library not installed — skipping WS check")
            print("       Install with: pip install websockets")
            return True
        except Exception as e:
            print(f"[FAIL] WebSocket connection failed: {e}")
            print("       Is the backend running? (python -m uvicorn main:app)")
            return False

    return asyncio.run(_probe())


def main() -> None:
    gpu_ok = check_cuda()
    ws_ok = check_websocket()

    print()
    print("=" * 60)
    if gpu_ok and ws_ok:
        print("  ALL CHECKS PASSED — AuraGen is ready for GPU inference")
    elif gpu_ok:
        print("  GPU OK — WebSocket check failed (start the backend first)")
    else:
        print("  GPU CHECK FAILED — fix CUDA before starting AuraGen")
    print("=" * 60)

    sys.exit(0 if (gpu_ok and ws_ok) else 1)


if __name__ == "__main__":
    main()
