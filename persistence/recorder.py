"""Persists snapshot events from the message bus into a ``SnapshotRepository``.

``SnapshotArchiver`` is the subscriber that closes the loop between messaging and
persistence: an engine with a publisher emits a ``SnapshotEvent`` on ``TOPIC_SNAPSHOT``
every ``snapshot_every`` ticks, and an archiver subscribed to that topic saves each one, so
a run's snapshots survive for resync and replay (Epic E6).
"""
from __future__ import annotations

import time

from .models import Snapshot
from .repositories import SnapshotRepository


class SnapshotArchiver:
    """Saves snapshot events for one scenario into a ``SnapshotRepository``.

    Subscribe ``handle`` to ``TOPIC_SNAPSHOT`` on the bus the engine publishes to; every
    snapshot event published during the run is then stored under ``scenario_id``.

    Attributes:
        repo: The repository the snapshots are saved to.
        scenario_id: Id the snapshots are filed under.
        saved: Number of snapshots saved so far.
    """

    def __init__(self, repo: SnapshotRepository, scenario_id: str) -> None:
        """Create an archiver that files snapshots under ``scenario_id``.

        Args:
            repo: The ``SnapshotRepository`` to save snapshots to.
            scenario_id: Id to store each snapshot under.
        """
        self.repo = repo
        self.scenario_id = scenario_id
        self.saved = 0

    def handle(self, payload: dict) -> None:
        """Save one snapshot event's grid state.

        Args:
            payload: A ``SnapshotEvent`` as a dict, with at least ``tick`` and ``state`` (and
                optionally ``timestamp``), as published on ``TOPIC_SNAPSHOT``.
        """
        self.repo.save(Snapshot(
            scenario_id=self.scenario_id,
            tick=int(payload["tick"]),
            state=payload["state"],
            timestamp=float(payload.get("timestamp", time.time())),
        ))
        self.saved += 1
