"""Messaging & interoperability (Epic E3).

The domain depends on the ``MessageBus`` port (Adapter pattern); ``InMemoryBus``
is used for tests and local runs, and a NATS adapter plugs in behind the same
port in production. Events are published on versioned JSON topics so other
Fireforce6 components can build against a stable contract.
"""
from .bus import InMemoryBus, MessageBus
from .events import (
    TOPIC_EXTINGUISHED,
    TOPIC_IGNITION,
    TOPIC_SNAPSHOT,
    TOPIC_SPREAD,
    TOPIC_STATE,
    TOPIC_SUPPRESSION,
    ExtinguishedEvent,
    SnapshotEvent,
    StateUpdateEvent,
)
from .publisher import EventPublisher

__all__ = [
    "MessageBus", "InMemoryBus", "EventPublisher",
    "StateUpdateEvent", "ExtinguishedEvent", "SnapshotEvent",
    "TOPIC_IGNITION", "TOPIC_SPREAD", "TOPIC_STATE",
    "TOPIC_EXTINGUISHED", "TOPIC_SNAPSHOT", "TOPIC_SUPPRESSION",
]
