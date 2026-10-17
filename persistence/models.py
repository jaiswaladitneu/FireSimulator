"""Persistence models."""
from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class Snapshot:
    """A full-state snapshot (Memento) for replay and late-join resync."""
    scenario_id: str
    tick: int
    state: list = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)


@dataclass
class ScenarioRecord:
    id: str
    name: str
    payload: dict = field(default_factory=dict)
