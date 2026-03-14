"""
AuraGen — WebSocket connection manager.

Maintains a registry of active WebSocket connections keyed by ``client_id``
and provides helpers for targeted or broadcast messaging.

All outbound messages are JSON-encoded dicts with the structure::

    {
        "type": "progress" | "complete" | "error",
        "job_id": "<uuid>",
        "data": { ... }
    }
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger("auragen.ws")


class ConnectionManager:
    """Thread-safe manager for WebSocket connections."""

    def __init__(self) -> None:
        # client_id  ->  WebSocket instance
        self._connections: dict[str, WebSocket] = {}
        self._lock = asyncio.Lock()

    # ── lifecycle ─────────────────────────────────────────────────────────

    async def connect(self, websocket: WebSocket, client_id: str) -> None:
        """Accept a new WebSocket and register it under *client_id*.

        If a connection with the same *client_id* already exists it is
        silently replaced (the old socket is closed first).
        """
        await websocket.accept()
        async with self._lock:
            old = self._connections.get(client_id)
            if old is not None:
                try:
                    await old.close(code=1000, reason="Replaced by new connection")
                except Exception:
                    pass
            self._connections[client_id] = websocket
        logger.info("WebSocket connected: %s (total: %d)", client_id, len(self._connections))

    async def disconnect(self, client_id: str) -> None:
        """Remove *client_id* from the registry."""
        async with self._lock:
            ws = self._connections.pop(client_id, None)
        if ws is not None:
            try:
                await ws.close()
            except Exception:
                pass
        logger.info("WebSocket disconnected: %s (total: %d)", client_id, len(self._connections))

    # ── messaging ─────────────────────────────────────────────────────────

    async def send_personal(self, message: dict[str, Any], client_id: str) -> None:
        """Send a JSON message to a single client."""
        async with self._lock:
            ws = self._connections.get(client_id)
        if ws is None:
            return
        try:
            await ws.send_text(json.dumps(message))
        except Exception:
            logger.warning("Failed to send to %s — removing connection", client_id)
            await self.disconnect(client_id)

    async def broadcast(self, message: dict[str, Any]) -> None:
        """Send a JSON message to **all** connected clients.

        Dead connections are silently removed.

        Automatically injects chunk-size metadata (``chunk_bytes``,
        ``server_ts``) so the frontend can measure real transfer speed.
        """
        import datetime

        # Inject chunk metadata for bandwidth measurement
        enriched = {
            **message,
            "server_ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        payload = json.dumps(enriched)
        enriched["chunk_bytes"] = len(payload.encode("utf-8"))
        # Re-serialize with the final byte count
        payload = json.dumps(enriched)

        async with self._lock:
            clients = list(self._connections.items())

        dead: list[str] = []

        for client_id, ws in clients:
            try:
                await ws.send_text(payload)
            except Exception:
                logger.warning("Broadcast failed for %s — will remove", client_id)
                dead.append(client_id)

        # Clean up any broken connections.
        for cid in dead:
            await self.disconnect(cid)

    # ── introspection ─────────────────────────────────────────────────────

    @property
    def active_count(self) -> int:
        """Return the number of active connections."""
        return len(self._connections)


# Module-level singleton used throughout the application.
manager = ConnectionManager()
