"""Publishes fire events to the bus (Observer / publish-subscribe)."""
from __future__ import annotations

from .bus import MessageBus
from .events import (
    TOPIC_EXTINGUISHED,
    TOPIC_SNAPSHOT,
    TOPIC_SPREAD,
    TOPIC_STATE,
    ExtinguishedEvent,
    SnapshotEvent,
    StateUpdateEvent,
)


class EventPublisher:
    def __init__(self, bus: MessageBus) -> None:
        self.bus = bus

    def publish_state_update(self, tick: int, counts: dict) -> None:
        self.bus.publish(TOPIC_STATE, StateUpdateEvent(tick=tick, counts=counts).to_dict())

    def publish_spread(self, tick: int, counts: dict) -> None:
        self.bus.publish(TOPIC_SPREAD, StateUpdateEvent(tick=tick, counts=counts).to_dict())

    def publish_extinguished(self, tick: int) -> None:
        self.bus.publish(TOPIC_EXTINGUISHED, ExtinguishedEvent(tick=tick).to_dict())

    def publish_snapshot(self, tick: int, state: list) -> None:
        self.bus.publish(TOPIC_SNAPSHOT, SnapshotEvent(tick=tick, state=state).to_dict())
