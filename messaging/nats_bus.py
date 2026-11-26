"""NATS adapter for the ``MessageBus`` port (Epic E3, Adapter pattern).

``nats-py`` is asyncio-only, but the ``MessageBus`` port (and ``EventPublisher`` /
``SuppressionListener`` built on it) is synchronous. ``NatsBus`` bridges the two: it runs a
private event loop in a background thread and schedules each ``publish`` / ``subscribe`` onto
it, blocking for the result. Messages travel as JSON bytes on the same versioned topics as
``InMemoryBus``, so other Fireforce6 components can exchange events with the simulator over a
real NATS server without any domain code changing.
"""
from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import Awaitable, Callable

from .bus import Handler

DEFAULT_SERVERS = "nats://127.0.0.1:4222"


async def _default_connect(servers: str):
    """Connect to NATS with ``nats-py`` (imported lazily so the module loads without it)."""
    import nats
    return await nats.connect(servers)


class NatsBus:
    """``MessageBus`` adapter backed by a NATS server.

    Implements the synchronous ``publish`` / ``subscribe`` port over the asynchronous
    ``nats-py`` client by owning an event loop on a daemon thread. Handler callbacks run on
    that loop thread.

    Attributes:
        servers: The NATS server URL(s) the adapter connected to.
    """

    def __init__(
        self,
        servers: str = DEFAULT_SERVERS,
        *,
        connect: Callable[[str], Awaitable] | None = None,
    ) -> None:
        """Connect to NATS and start the background loop.

        Args:
            servers: NATS server URL(s), e.g. ``"nats://host:4222"``.
            connect: Optional coroutine factory used to obtain the client (for tests); by
                default it connects with ``nats-py``.
        """
        self.servers = servers
        self._connect = connect or _default_connect
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()
        self._nc = self._run(self._connect(servers))

    def _run(self, coro: Awaitable):
        """Run a coroutine on the background loop from the calling thread and return its result."""
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result()

    def publish(self, topic: str, payload: dict) -> None:
        """Publish a message as JSON bytes on a topic.

        Args:
            topic: Topic (NATS subject), e.g. ``"fire.state.v1"``.
            payload: Message body as a plain dict; sent as UTF-8 JSON.
        """
        self._run(self._nc.publish(topic, json.dumps(payload).encode()))

    def subscribe(self, topic: str, handler: Handler) -> None:
        """Subscribe a handler to a topic; it receives each message's decoded dict payload.

        Args:
            topic: Topic (NATS subject) to listen to.
            handler: Callback invoked (on the loop thread) with each message's dict payload.
        """
        async def _cb(msg) -> None:
            handler(json.loads(msg.data.decode()))

        self._run(self._nc.subscribe(topic, cb=_cb))

    def close(self) -> None:
        """Drain the connection and stop the background loop."""
        try:
            self._run(self._nc.drain())
        finally:
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(timeout=2.0)
