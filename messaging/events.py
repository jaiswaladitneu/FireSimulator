"""Versioned fire events published on the message bus."""
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
    tick: int
    version: str = "1"
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class StateUpdateEvent(FireEvent):
    counts: dict = field(default_factory=dict)


@dataclass
class ExtinguishedEvent(FireEvent):
    pass


@dataclass
class SnapshotEvent(FireEvent):
    state: list = field(default_factory=list)
