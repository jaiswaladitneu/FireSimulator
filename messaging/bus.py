"""Message bus port (Adapter pattern) and an in-memory implementation.

``Handler`` is the type of a subscriber callback: it receives the payload dict of each
message published on the topic it subscribed to and returns nothing.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

Handler = Callable[[dict], None]


class MessageBus(Protocol):
    """Port through which the simulator publishes and receives messages (Adapter pattern).

    ``EventPublisher`` and ``SuppressionListener`` depend only on this interface, so any bus
    implementation can be plugged in behind it; ``InMemoryBus`` is the one provided here.
    Messages are plain dicts sent on named topics.
    """

    def publish(self, topic: str, payload: dict) -> None:
        """Publish a message on a topic.

        Args:
            topic: Topic name, e.g. ``TOPIC_STATE`` (``"fire.state.v1"``).
            payload: Message body as a plain dict.
        """
        ...

    def subscribe(self, topic: str, handler: Handler) -> None:
        """Register a handler for every message later published on a topic.

        Args:
            topic: Topic name to listen to.
            handler: Callback that receives the payload dict of each message.
        """
        ...


class InMemoryBus:
    """A synchronous in-process bus for tests and local runs.

    Implements the ``MessageBus`` port with a list of handlers per topic; ``publish`` calls
    the handlers immediately, in the caller's thread.

    Attributes:
        published: Every ``(topic, payload)`` pair published so far, oldest first.
    """

    def __init__(self) -> None:
        """Create a bus with no subscribers and no published messages."""
        self._subs: dict[str, list[Handler]] = {}
        self.published: list[tuple[str, dict]] = []

    def publish(self, topic: str, payload: dict) -> None:
        """Record a message, then pass it to every handler subscribed to its topic.

        Handlers run synchronously, in the order they subscribed. A message on a topic
        without subscribers is only recorded.

        Args:
            topic: Topic name.
            payload: Message body; every handler receives this same dict.
        """
        self.published.append((topic, payload))
        for handler in self._subs.get(topic, []):
            handler(payload)

    def subscribe(self, topic: str, handler: Handler) -> None:
        """Add a handler for a topic.

        Args:
            topic: Topic name.
            handler: Callback that receives each payload published on ``topic``.
        """
        self._subs.setdefault(topic, []).append(handler)
