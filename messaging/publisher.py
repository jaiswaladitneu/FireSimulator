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
    """Publishes the simulator's fire events on a message bus (Observer / publish-subscribe).

    Each method wraps its arguments in a versioned event and publishes the event's
    ``to_dict()`` on the matching topic. A ``SimulationEngine`` given a publisher calls
    ``publish_state_update`` after every tick and ``publish_extinguished`` when the fire
    goes out.

    Attributes:
        bus: The ``MessageBus`` the events are published on.
    """

    def __init__(self, bus: MessageBus) -> None:
        """Create a publisher for a bus.

        Args:
            bus: The message bus to publish on.
        """
        self.bus = bus

    def publish_state_update(self, tick: int, counts: dict) -> None:
        """Publish a ``StateUpdateEvent`` on ``TOPIC_STATE``.

        Args:
            tick: Tick the counts belong to.
            counts: Number of cells in each state, keyed by state name.
        """
        self.bus.publish(TOPIC_STATE, StateUpdateEvent(tick=tick, counts=counts).to_dict())

    def publish_spread(self, tick: int, counts: dict) -> None:
        """Publish a ``StateUpdateEvent`` on ``TOPIC_SPREAD``.

        Args:
            tick: Tick the counts belong to.
            counts: Number of cells in each state, keyed by state name.
        """
        self.bus.publish(TOPIC_SPREAD, StateUpdateEvent(tick=tick, counts=counts).to_dict())

    def publish_extinguished(self, tick: int) -> None:
        """Publish an ``ExtinguishedEvent`` on ``TOPIC_EXTINGUISHED``.

        Args:
            tick: Tick at which the fire went out.
        """
        self.bus.publish(TOPIC_EXTINGUISHED, ExtinguishedEvent(tick=tick).to_dict())

    def publish_snapshot(self, tick: int, state: list) -> None:
        """Publish a ``SnapshotEvent`` with the full grid state on ``TOPIC_SNAPSHOT``.

        Args:
            tick: Tick the snapshot was taken at.
            state: Cell-state codes of the whole grid as a list of rows.
        """
        self.bus.publish(TOPIC_SNAPSHOT, SnapshotEvent(tick=tick, state=state).to_dict())
