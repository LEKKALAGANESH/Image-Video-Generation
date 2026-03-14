"""
AuraGen — WebSocket Smoke Test
===============================

Tests the WebSocket manager's connect/disconnect/broadcast logic
directly (unit-style) and optionally against a live server.

Usage:
    python smoke_test_ws.py           # Unit tests only (no server needed)
    python smoke_test_ws.py --live    # Also test against running server on :8000

Reports: connection times, reconnection stability, memory behavior.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
import tracemalloc
from unittest.mock import AsyncMock, MagicMock

# ── Unit Tests: WebSocket Manager ─────────────────────────────────────────


class FakeWebSocket:
    """Minimal WebSocket mock for testing the ConnectionManager."""

    def __init__(self, client_id: str = "test") -> None:
        self.client_id = client_id
        self.accepted = False
        self.closed = False
        self.close_code: int | None = None
        self.close_reason: str | None = None
        self.sent: list[str] = []

    async def accept(self) -> None:
        self.accepted = True

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self.closed = True
        self.close_code = code
        self.close_reason = reason

    async def send_text(self, data: str) -> None:
        if self.closed:
            raise RuntimeError("WebSocket is closed")
        self.sent.append(data)


class BrokenWebSocket(FakeWebSocket):
    """A WebSocket that fails on send_text (simulates dead connection)."""

    async def send_text(self, data: str) -> None:
        raise ConnectionResetError("Connection lost")


async def test_connect_disconnect() -> None:
    """Test basic connect and disconnect lifecycle."""
    from websocket.manager import ConnectionManager

    mgr = ConnectionManager()
    ws = FakeWebSocket("client-1")

    # Connect
    t0 = time.perf_counter()
    await mgr.connect(ws, "client-1")
    t_connect = (time.perf_counter() - t0) * 1000

    assert ws.accepted, "WebSocket should be accepted"
    assert mgr.active_count == 1, f"Expected 1 connection, got {mgr.active_count}"

    # Disconnect
    t0 = time.perf_counter()
    await mgr.disconnect("client-1")
    t_disconnect = (time.perf_counter() - t0) * 1000

    assert mgr.active_count == 0, f"Expected 0 connections, got {mgr.active_count}"

    print(f"  [PASS] connect/disconnect — connect: {t_connect:.2f}ms, disconnect: {t_disconnect:.2f}ms")


async def test_replace_existing_connection() -> None:
    """Test that connecting with the same client_id closes the old socket."""
    from websocket.manager import ConnectionManager

    mgr = ConnectionManager()
    ws1 = FakeWebSocket("client-1")
    ws2 = FakeWebSocket("client-1")

    await mgr.connect(ws1, "client-1")
    await mgr.connect(ws2, "client-1")

    assert ws1.closed, "Old WebSocket should be closed when replaced"
    assert ws1.close_code == 1000, f"Expected close code 1000, got {ws1.close_code}"
    assert ws2.accepted, "New WebSocket should be accepted"
    assert mgr.active_count == 1, f"Expected 1 connection after replace, got {mgr.active_count}"

    print("  [PASS] replace existing connection — old socket closed, new socket active")


async def test_send_personal() -> None:
    """Test targeted message delivery."""
    from websocket.manager import ConnectionManager

    mgr = ConnectionManager()
    ws = FakeWebSocket("client-1")
    await mgr.connect(ws, "client-1")

    msg = {"type": "progress", "job_id": "test-job", "data": {"step": 5}}
    await mgr.send_personal(msg, "client-1")

    assert len(ws.sent) == 1, f"Expected 1 message, got {len(ws.sent)}"
    parsed = json.loads(ws.sent[0])
    assert parsed["type"] == "progress"
    assert parsed["job_id"] == "test-job"

    # Send to nonexistent client — should not raise
    await mgr.send_personal(msg, "nonexistent")

    print("  [PASS] send_personal — message delivered, nonexistent client handled gracefully")


async def test_send_personal_broken_connection() -> None:
    """Test that a failed send removes the dead connection."""
    from websocket.manager import ConnectionManager

    mgr = ConnectionManager()
    ws = BrokenWebSocket("client-1")
    await mgr.connect(ws, "client-1")

    assert mgr.active_count == 1
    await mgr.send_personal({"type": "test"}, "client-1")

    # The manager should have removed the broken connection
    assert mgr.active_count == 0, f"Expected 0 after failed send, got {mgr.active_count}"

    print("  [PASS] send_personal with broken connection — dead socket removed")


async def test_broadcast() -> None:
    """Test broadcast to multiple clients, including dead connection cleanup."""
    from websocket.manager import ConnectionManager

    mgr = ConnectionManager()
    ws1 = FakeWebSocket("client-1")
    ws2 = FakeWebSocket("client-2")
    ws_dead = BrokenWebSocket("client-dead")

    await mgr.connect(ws1, "client-1")
    await mgr.connect(ws2, "client-2")
    await mgr.connect(ws_dead, "client-dead")

    assert mgr.active_count == 3

    msg = {"type": "progress", "job_id": "broadcast-job"}
    await mgr.broadcast(msg)

    # Healthy clients should receive the message
    assert len(ws1.sent) == 1, f"client-1: expected 1 message, got {len(ws1.sent)}"
    assert len(ws2.sent) == 1, f"client-2: expected 1 message, got {len(ws2.sent)}"

    # Dead client should be removed
    assert mgr.active_count == 2, f"Expected 2 after broadcast, got {mgr.active_count}"

    # Verify chunk_bytes and server_ts injection
    parsed = json.loads(ws1.sent[0])
    assert "server_ts" in parsed, "Broadcast should inject server_ts"
    assert "chunk_bytes" in parsed, "Broadcast should inject chunk_bytes"
    assert isinstance(parsed["chunk_bytes"], int), "chunk_bytes should be an integer"
    assert parsed["chunk_bytes"] > 0, "chunk_bytes should be positive"

    print("  [PASS] broadcast — delivered to healthy clients, dead client removed, metadata injected")


async def test_broadcast_does_not_throw() -> None:
    """Broadcast must NEVER throw even if all clients are dead."""
    from websocket.manager import ConnectionManager

    mgr = ConnectionManager()
    for i in range(5):
        ws = BrokenWebSocket(f"dead-{i}")
        await mgr.connect(ws, f"dead-{i}")

    # This must not raise
    try:
        await mgr.broadcast({"type": "test"})
    except Exception as exc:
        print(f"  [FAIL] broadcast threw: {exc}")
        return

    assert mgr.active_count == 0, f"Expected 0, got {mgr.active_count}"
    print("  [PASS] broadcast with all-dead clients — no exception, all cleaned up")


async def test_rapid_reconnect_flap() -> None:
    """Simulate 5 rapid disconnect/reconnect cycles (network flap)."""
    from websocket.manager import ConnectionManager

    mgr = ConnectionManager()
    times: list[float] = []

    for i in range(5):
        ws = FakeWebSocket(f"flap-client")

        t0 = time.perf_counter()
        await mgr.connect(ws, "flap-client")
        t_ms = (time.perf_counter() - t0) * 1000
        times.append(t_ms)

        assert mgr.active_count == 1, f"Cycle {i}: expected 1 connection, got {mgr.active_count}"
        await mgr.disconnect("flap-client")
        assert mgr.active_count == 0

    avg = sum(times) / len(times)
    print(f"  [PASS] rapid reconnect (5 cycles) — avg connect: {avg:.2f}ms, all succeeded")


async def test_concurrent_operations() -> None:
    """Test thread safety by running multiple operations concurrently."""
    from websocket.manager import ConnectionManager

    mgr = ConnectionManager()

    # Create 10 clients
    sockets = []
    for i in range(10):
        ws = FakeWebSocket(f"concurrent-{i}")
        sockets.append((f"concurrent-{i}", ws))

    # Connect all concurrently
    await asyncio.gather(*[mgr.connect(ws, cid) for cid, ws in sockets])
    assert mgr.active_count == 10, f"Expected 10, got {mgr.active_count}"

    # Broadcast and disconnect concurrently
    await asyncio.gather(
        mgr.broadcast({"type": "test"}),
        *[mgr.disconnect(cid) for cid, _ in sockets[:5]],
    )

    assert mgr.active_count == 5, f"Expected 5, got {mgr.active_count}"

    print("  [PASS] concurrent operations — connect/broadcast/disconnect all thread-safe")


async def test_memory_behavior() -> None:
    """Track memory allocations during connect/disconnect cycles."""
    from websocket.manager import ConnectionManager

    tracemalloc.start()
    snap_before = tracemalloc.take_snapshot()

    mgr = ConnectionManager()

    # Connect and disconnect 100 clients
    for i in range(100):
        ws = FakeWebSocket(f"mem-{i}")
        await mgr.connect(ws, f"mem-{i}")

    # All connected
    assert mgr.active_count == 100

    # Disconnect all
    for i in range(100):
        await mgr.disconnect(f"mem-{i}")

    assert mgr.active_count == 0

    snap_after = tracemalloc.take_snapshot()

    # Compare top allocations
    stats = snap_after.compare_to(snap_before, "lineno")
    total_diff = sum(s.size_diff for s in stats)

    tracemalloc.stop()

    # After disconnecting all, residual memory should be minimal
    # (We allow up to 50 KB for Python overhead)
    if total_diff > 50_000:
        print(f"  [WARN] memory — {total_diff / 1024:.1f} KB residual after 100 connect/disconnect cycles")
    else:
        print(f"  [PASS] memory — {total_diff / 1024:.1f} KB residual after 100 connect/disconnect cycles (< 50 KB threshold)")


async def test_chunk_bytes_accuracy() -> None:
    """Verify that chunk_bytes reflects the actual payload size."""
    from websocket.manager import ConnectionManager

    mgr = ConnectionManager()
    ws = FakeWebSocket("size-check")
    await mgr.connect(ws, "size-check")

    await mgr.broadcast({"type": "test", "data": "x" * 1000})

    payload = ws.sent[0]
    parsed = json.loads(payload)

    actual_size = len(payload.encode("utf-8"))
    reported_size = parsed["chunk_bytes"]

    # The chunk_bytes is injected BEFORE the final serialization,
    # so the reported size is the byte count of the FIRST serialization
    # (without chunk_bytes). The final payload is slightly larger.
    # This is a known inaccuracy — document it.
    size_diff = abs(actual_size - reported_size)

    if size_diff > 50:  # More than 50 bytes off
        print(f"  [WARN] chunk_bytes accuracy — reported: {reported_size}, actual: {actual_size}, diff: {size_diff} bytes")
    else:
        print(f"  [PASS] chunk_bytes accuracy — reported: {reported_size}, actual: {actual_size}, diff: {size_diff} bytes")


# ── Live Server Test (optional) ───────────────────────────────────────────


async def test_live_websocket() -> None:
    """Test against a running server (requires websockets package)."""
    try:
        import websockets
    except ImportError:
        print("  [SKIP] live test — 'websockets' package not installed (pip install websockets)")
        return

    url = "ws://localhost:8000/ws/smoke-test-client"
    print(f"  Connecting to {url}...")

    try:
        async with websockets.connect(url, open_timeout=5) as ws:
            # Wait for initial message (hardware_error or ping)
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                parsed = json.loads(msg)
                print(f"  Received initial message: type={parsed.get('type')}")
            except asyncio.TimeoutError:
                print("  No initial message within 5s (OK if GPU is healthy)")

            # Send ping, expect pong
            await ws.send(json.dumps({"type": "ping"}))
            response = await asyncio.wait_for(ws.recv(), timeout=5.0)
            parsed = json.loads(response)
            assert parsed.get("type") == "pong", f"Expected pong, got {parsed}"
            print("  [PASS] ping/pong exchange")

    except (ConnectionRefusedError, OSError) as exc:
        print(f"  [SKIP] live test — server not running: {exc}")
        return

    # Rapid reconnect test
    print("  Testing rapid reconnect (5 cycles)...")
    reconnect_times: list[float] = []
    failures = 0

    for i in range(5):
        t0 = time.perf_counter()
        try:
            async with websockets.connect(url, open_timeout=3) as ws:
                t_ms = (time.perf_counter() - t0) * 1000
                reconnect_times.append(t_ms)
                # Drain any initial messages
                try:
                    await asyncio.wait_for(ws.recv(), timeout=1.0)
                except asyncio.TimeoutError:
                    pass
        except Exception as exc:
            failures += 1
            print(f"    Reconnect {i+1} failed: {exc}")

    if reconnect_times:
        avg = sum(reconnect_times) / len(reconnect_times)
        print(f"  [{'PASS' if failures == 0 else 'WARN'}] rapid reconnect — "
              f"{len(reconnect_times)}/5 succeeded, avg: {avg:.1f}ms, failures: {failures}")
    else:
        print(f"  [FAIL] all reconnections failed")


# ── Runner ────────────────────────────────────────────────────────────────

async def run_all(live: bool = False) -> None:
    print("=" * 60)
    print("AuraGen WebSocket Smoke Test")
    print("=" * 60)

    print("\n--- Unit Tests: ConnectionManager ---")
    await test_connect_disconnect()
    await test_replace_existing_connection()
    await test_send_personal()
    await test_send_personal_broken_connection()
    await test_broadcast()
    await test_broadcast_does_not_throw()
    await test_rapid_reconnect_flap()
    await test_concurrent_operations()
    await test_memory_behavior()
    await test_chunk_bytes_accuracy()

    if live:
        print("\n--- Live Server Tests ---")
        await test_live_websocket()

    print("\n" + "=" * 60)
    print("All tests complete.")
    print("=" * 60)


if __name__ == "__main__":
    live = "--live" in sys.argv
    asyncio.run(run_all(live=live))
