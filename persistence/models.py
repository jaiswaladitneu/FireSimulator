"""Persistence models.

Plain dataclasses stored by the repositories in ``persistence.repositories``.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class Snapshot:
    """A full-state snapshot (Memento) for replay and late-join resync.

    Attributes:
        scenario_id: Id of the scenario the snapshot belongs to.
        tick: Simulation tick at which the snapshot was taken.
        state: Cell-state codes of the whole grid as a list of rows (e.g. the ``state`` of
            ``SimulationEngine.snapshot()``).
        timestamp: Wall-clock time the snapshot was created, in epoch seconds.
    """
    scenario_id: str
    tick: int
    state: list = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)


@dataclass
class ScenarioRecord:
    """A saved scenario: its id, its name and the parameters it was created with.

    Attributes:
        id: Unique scenario id (``Scenario.id``).
        name: Display name of the scenario.
        payload: Scenario parameters as a plain dict. The API stores the ``ScenarioIn``
            request body here, with the ignition points actually used, so the scenario can
            be rebuilt and replayed.
    """
    id: str
    name: str
    payload: dict = field(default_factory=dict)


@dataclass
class IncidentRecord:
    """One finished (or stopped) city incident, for the admin dashboard's history.

    Attributes:
        id: Unique incident id.
        name: Display name (the scenario name).
        scenario_id: Id of the scenario that was run.
        source: ``"live"`` (run in the command center) or ``"simulated"`` (batch run).
        outcome: ``"extinguished"``, ``"stopped"`` or ``"time_limit"``.
        started_at: Wall-clock time the run started, in epoch seconds.
        ended_at: Wall-clock time the run ended and was recorded, in epoch seconds.
        ticks: Ticks simulated (simulated minutes).
        params: Scenario parameters of the run (map size, seed, wind, hour, crews, ...).
        summary: Results: people, buildings, timeline, key events and more. ``timeline``
            and ``key_events`` are the heavy parts that ``brief`` leaves out.
    """
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
        """The record without its heavy parts (timeline, events) for list views.

        Returns:
            A new dict with the record's fields (``id``, ``name``, ``scenario_id``,
            ``source``, ``outcome``, ``started_at``, ``ended_at``, ``ticks``, ``params``,
            ``summary``) in which ``summary`` has no ``timeline`` or ``key_events`` key.
        """
        summary = {k: v for k, v in self.summary.items() if k not in ("timeline", "key_events")}
        return {
            "id": self.id, "name": self.name, "scenario_id": self.scenario_id,
            "source": self.source, "outcome": self.outcome, "started_at": self.started_at,
            "ended_at": self.ended_at, "ticks": self.ticks, "params": self.params,
            "summary": summary,
        }
