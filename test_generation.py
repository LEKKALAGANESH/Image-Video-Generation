"""
AuraGen — End-to-end generation test.

Tests both image (FLUX.1-schnell) and video (Wan 2.1 → CogVideoX fallback)
generation through the API endpoints.

Usage:
    1. Start the backend:  cd backend && python main.py
    2. Run this script:    python test_generation.py

Expects the server at http://localhost:8000.
"""

from __future__ import annotations

import sys
import time

import httpx

BASE = "http://localhost:8000"
TIMEOUT = 300.0  # 5 min max per job


def poll_job(client: httpx.Client, job_id: str, label: str) -> bool:
    """Poll a job until completed or failed. Returns True on success."""
    print(f"  [{label}] Polling job {job_id[:12]}...")
    start = time.monotonic()

    while time.monotonic() - start < TIMEOUT:
        r = client.get(f"{BASE}/api/jobs/{job_id}")
        r.raise_for_status()
        data = r.json()
        status = data["status"]
        progress = data.get("progress", 0)

        if status == "completed":
            result_url = data.get("result_url", "")
            elapsed = time.monotonic() - start
            print(f"  [{label}] COMPLETED in {elapsed:.1f}s -> {result_url}")
            return True
        elif status == "failed":
            error = data.get("error", "unknown")
            print(f"  [{label}] FAILED: {error}")
            return False

        print(f"  [{label}] {status} {progress}%", end="\r")
        time.sleep(2.0)

    print(f"  [{label}] TIMEOUT after {TIMEOUT}s")
    return False


def test_image(client: httpx.Client) -> bool:
    """Test image generation with FLUX.1-schnell."""
    print("\n=== IMAGE TEST (FLUX.1-schnell) ===")
    print("  Submitting image generation request...")

    r = client.post(f"{BASE}/api/generate/image", json={
        "prompt": "A golden retriever sitting in a sunlit meadow, photorealistic",
        "width": 512,
        "height": 512,
        "num_steps": 4,
        "guidance_scale": 0.0,
    })

    if r.status_code == 202:
        job_id = r.json()["job_id"]
        print(f"  Job accepted: {job_id[:12]}...")
        return poll_job(client, job_id, "IMAGE")
    else:
        print(f"  Submit failed: {r.status_code} {r.text[:200]}")
        return False


def test_video(client: httpx.Client) -> bool:
    """Test video generation (Wan 2.1 primary, CogVideoX fallback)."""
    print("\n=== VIDEO TEST (Wan 2.1 -> CogVideoX fallback) ===")
    print("  Submitting video generation request...")

    r = client.post(f"{BASE}/api/generate/video", json={
        "prompt": "A cat walking across a table, smooth motion",
        "width": 480,
        "height": 320,
        "num_frames": 17,
        "num_steps": 20,
        "guidance_scale": 5.0,
    })

    if r.status_code == 202:
        job_id = r.json()["job_id"]
        print(f"  Job accepted: {job_id[:12]}...")
        return poll_job(client, job_id, "VIDEO")
    else:
        print(f"  Submit failed: {r.status_code} {r.text[:200]}")
        return False


def main() -> int:
    print("AuraGen Generation Test")
    print("=" * 50)

    # Check server is running
    with httpx.Client(timeout=10.0) as client:
        try:
            r = client.get(f"{BASE}/api/health")
            r.raise_for_status()
            health = r.json()
            print(f"Server: {health.get('status', '?')} (v{health.get('version', '?')})")
        except Exception as e:
            print(f"ERROR: Cannot reach server at {BASE}: {e}")
            print("Start the backend first: cd backend && python main.py")
            return 1

        # Check GPU health
        try:
            r = client.get(f"{BASE}/api/health-check")
            gpu = r.json().get("gpu", {})
            print(f"GPU: {gpu.get('backend', '?')} — {gpu.get('device_name', '?')}")
        except Exception:
            print("GPU health check unavailable")

    # Run tests with longer timeout
    with httpx.Client(timeout=TIMEOUT) as client:
        img_ok = test_image(client)
        vid_ok = test_video(client)

    # Summary
    print("\n" + "=" * 50)
    print(f"  Image (FLUX.1-schnell):            {'PASS' if img_ok else 'FAIL'}")
    print(f"  Video (Wan 2.1 / CogVideoX):       {'PASS' if vid_ok else 'FAIL'}")
    print("=" * 50)

    return 0 if (img_ok and vid_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
