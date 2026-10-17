"""Message bus port (Adapter pattern) and an in-memory implementation."""
from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

Handler = Callable[[dict], None]


class MessageBus(Protocol):
    def publish(self, topic: str, payload: dict) -> None: ...
    def subscribe(self, topic: str, handler: Handler) -> None: ...


class InMemoryBus:
    """A synchronous in-process bus for tests and local runs."""

    def __init__(self) -> None:
        self._subs: dict[str, list[Handler]] = {}
        self.published: list[tuple[str, dict]] = []

    def publish(self, topic: str, payload: dict) -> None:
        self.published.append((topic, payload))
        for handler in self._subs.get(topic, []):
            handler(payload)

    def subscribe(self, topic: str, handler: Handler) -> None:
        self._subs.setdefault(topic, []).append(handler)
