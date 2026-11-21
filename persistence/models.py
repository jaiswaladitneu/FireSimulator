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


@dataclass
class IncidentRecord:
    """One finished (or stopped) city incident, for the admin dashboard's history."""
    id: str
    name: str
    scenario_id: str
    source: str             # "live" (run in the command center) | "simulated" (batch run)
    outcome: str            # "extinguished" | "stopped" | "time_limit"
    started_at: float       # wall-clock epoch seconds
    ended_at: float
    ticks: int              # simulated minutes
    params: dict = field(default_factory=dict)    # scenario parameters
    summary: dict = field(default_factory=dict)   # people, buildings, timeline, key events

    def brief(self) -> dict:
        """The record without its heavy parts (timeline, events) for list views."""
        summary = {k: v for k, v in self.summary.items() if k not in ("timeline", "key_events")}
        return {
            "id": self.id, "name": self.name, "scenario_id": self.scenario_id,
            "source": self.source, "outcome": self.outcome, "started_at": self.started_at,
            "ended_at": self.ended_at, "ticks": self.ticks, "params": self.params,
            "summary": summary,
        }
