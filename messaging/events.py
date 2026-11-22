"""Versioned fire events published on the message bus.

Every topic name ends in a version suffix and every event carries a ``version`` field, so
the message contract can evolve without breaking subscribers. Topics:

* ``TOPIC_STATE`` (``fire.state.v1``): ``StateUpdateEvent``; an engine with a publisher
  attached sends one after every tick.
* ``TOPIC_SPREAD`` (``fire.spread.v1``): ``StateUpdateEvent`` sent by
  ``EventPublisher.publish_spread``.
* ``TOPIC_EXTINGUISHED`` (``fire.extinguished.v1``): ``ExtinguishedEvent``; an engine with
  a publisher attached sends it on the tick the fire goes out.
* ``TOPIC_SNAPSHOT`` (``fire.snapshot.v1``): ``SnapshotEvent`` with the full grid state.
* ``TOPIC_IGNITION`` (``fire.ignition.v1``): defined for ignition events;
  ``EventPublisher`` has no method that publishes on it.
* ``TOPIC_SUPPRESSION`` (``sim.suppression.v1``): inbound suppression commands from other
  components, handled by ``SuppressionListener``.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field

# Versioned topic names — bump the suffix to evolve the contract safely.
TOPIC_IGNITION = "fire.ignition.v1"
TOPIC_SPREAD = "fire.spread.v1"
TOPIC_STATE = "fire.state.v1"
TOPIC_EXTINGUISHED = "fire.extinguished.v1"
TOPIC_SNAPSHOT = "fire.snapshot.v1"
TOPIC_SUPPRESSION = "sim.suppression.v1"


@dataclass
class FireEvent:
    """Base class of the versioned events published on the message bus.

    Attributes:
        tick: Simulation tick the event refers to.
        version: Version of the event contract (``"1"``), included in every payload.
        timestamp: Wall-clock time the event was created, in epoch seconds.
    """
    tick: int
    version: str = "1"
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        """Convert the event to a plain dict for publishing.

        Returns:
            A dict with one entry per dataclass field, including the fields a subclass adds
            (built with ``dataclasses.asdict``).
        """
        return asdict(self)


@dataclass
class StateUpdateEvent(FireEvent):
    """Cell counts at a tick, published on ``TOPIC_STATE`` or ``TOPIC_SPREAD``.

    Also has the ``tick``, ``version`` and ``timestamp`` fields of ``FireEvent``.

    Attributes:
        counts: Number of cells in each state, keyed by state name (the engine sends
            ``Grid.counts()``: ``unburned``, ``igniting``, ``burning``, ``burned``,
            ``suppressed``).
    """
    counts: dict = field(default_factory=dict)


@dataclass
class ExtinguishedEvent(FireEvent):
    """Signals that the fire is out; published on ``TOPIC_EXTINGUISHED``.

    Carries only the ``tick``, ``version`` and ``timestamp`` fields of ``FireEvent``.
    """
    pass


@dataclass
class SnapshotEvent(FireEvent):
    """Full grid state at a tick, published on ``TOPIC_SNAPSHOT``.

    Also has the ``tick``, ``version`` and ``timestamp`` fields of ``FireEvent``.

    Attributes:
        state: Cell-state codes of the whole grid as a list of rows (e.g.
            ``grid.state.tolist()``).
    """
    state: list = field(default_factory=list)
