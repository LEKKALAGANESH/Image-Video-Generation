"""
AuraGen — SSE (Server-Sent Events) connection manager.

Replaces the WebSocket manager for **unidirectional** server-to-client
streaming.  Each client is identified by a ``client_id`` and receives
events through an ``asyncio.Queue`` that the SSE endpoint drains.

All outbound events are JSON-encoded dicts with the structure::

    id: <monotonic-counter>
    data: {"type": "progress"|"complete"|"error"|..., "job_id": "...", ...}

The SSE spec keepalive (lines starting with ``:``) is handled by the
endpoint generator, not by this manager.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("auragen.sse")


@dataclass
class SSEClient:
    """Represents a single SSE subscriber."""

    client_id: str
    queue: asyncio.Queue  # type: asyncio.Queue[dict[str, Any]]
    connected_at: float = field(default_factory=time.time)
    last_event_id: int = 0


class SSEManager:
    """Manages SSE client connections and broadcasts events.

    Thread-safe for the async event loop — all public methods are
    plain-async or synchronous and only touch ``dict`` (GIL-protected).
    """

    def __init__(self) -> None:
        self._clients: dict[str, SSEClient] = {}
        self._event_counter: int = 0

    # ── lifecycle ─────────────────────────────────────────────────────────

    def connect(self, client_id: str) -> SSEClient:
        """Register a new SSE client.

        If a client with the same *client_id* already exists it is
        silently replaced (the old queue is abandoned — the endpoint
        generator will detect disconnection via ``request.is_disconnected``).
        """
        client = SSEClient(
            client_id=client_id,
            queue=asyncio.Queue(maxsize=100),
        )
        self._clients[client_id] = client
        logger.info(
            "SSE client connected: %s (total: %d)",
            client_id,
            len(self._clients),
        )
        return client

    def disconnect(self, client_id: str) -> None:
        """Remove an SSE client from the registry."""
        if client_id in self._clients:
            del self._clients[client_id]
            logger.info(
                "SSE client disconnected: %s (total: %d)",
                client_id,
                len(self._clients),
            )

    # ── messaging ─────────────────────────────────────────────────────────

    async def broadcast(self, data: dict[str, Any]) -> None:
        """Send an event to **all** connected SSE clients.

        If a client's queue is full (slow consumer), the event is
        silently dropped for that client — we do not disconnect them.
        """
        self._event_counter += 1
        event = {"id": self._event_counter, **data}

        for client_id, client in list(self._clients.items()):
            try:
                client.queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning(
                    "SSE queue full for %s, dropping event", client_id
                )

    async def send_to(self, client_id: str, data: dict[str, Any]) -> None:
        """Send an event to a **specific** SSE client."""
        client = self._clients.get(client_id)
        if client is None:
            return
        self._event_counter += 1
        event = {"id": self._event_counter, **data}
        try:
            client.queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning("SSE queue full for %s", client_id)

    # ── introspection ─────────────────────────────────────────────────────

    @property
    def active_connections(self) -> int:
        """Return the number of active SSE clients."""
        return len(self._clients)


# Module-level singleton used throughout the application.
sse_manager = SSEManager()
