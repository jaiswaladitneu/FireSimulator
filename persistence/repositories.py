"""Repository ports and in-memory implementations.

The ``Protocol`` classes are the ports (GoF Repository) that define the storage contract;
the ``InMemory*`` classes implement them with dicts, and ``JsonFileIncidentRepository``
also writes the incident history to a JSON file.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import asdict
from pathlib import Path
from typing import Protocol

from .models import IncidentRecord, ScenarioRecord, Snapshot


class ScenarioRepository(Protocol):
    """Storage port for saved scenarios (GoF Repository), keyed by ``ScenarioRecord.id``."""

    def save(self, record: ScenarioRecord) -> None:
        """Store a scenario record, replacing any record with the same id.

        Args:
            record: The record to store.
        """
        ...

    def find(self, scenario_id: str) -> ScenarioRecord | None:
        """Look up a scenario record by id.

        Args:
            scenario_id: Id of the scenario.

        Returns:
            The record, or None if no record has this id.
        """
        ...

    def all(self) -> list[ScenarioRecord]:
        """List every stored scenario record.

        Returns:
            All stored records.
        """
        ...

    def delete(self, scenario_id: str) -> bool:
        """Delete a scenario record.

        Args:
            scenario_id: Id of the scenario to delete.

        Returns:
            True if a record was deleted, False if no record had this id.
        """
        ...


class SnapshotRepository(Protocol):
    """Storage port for grid-state snapshots (GoF Repository), grouped by scenario."""

    def save(self, snapshot: Snapshot) -> None:
        """Store a snapshot under its ``scenario_id``.

        Args:
            snapshot: The snapshot to store.
        """
        ...

    def find_by_scenario(self, scenario_id: str) -> list[Snapshot]:
        """List the snapshots saved for a scenario.

        Args:
            scenario_id: Id of the scenario.

        Returns:
            The scenario's snapshots ordered by tick; empty if it has none.
        """
        ...


class InMemoryScenarioRepository:
    """``ScenarioRepository`` that keeps the records in a dict in process memory.

    Records are lost when the process exits.
    """

    def __init__(self) -> None:
        """Create an empty repository."""
        self._store: dict[str, ScenarioRecord] = {}

    def save(self, record: ScenarioRecord) -> None:
        """Store a scenario record, replacing any record with the same id.

        Args:
            record: The record to store.
        """
        self._store[record.id] = record

    def find(self, scenario_id: str) -> ScenarioRecord | None:
        """Look up a scenario record by id.

        Args:
            scenario_id: Id of the scenario.

        Returns:
            The record, or None if no record has this id.
        """
        return self._store.get(scenario_id)

    def all(self) -> list[ScenarioRecord]:
        """List every stored scenario record.

        Returns:
            A new list of all records, in the order their ids were first saved.
        """
        return list(self._store.values())

    def delete(self, scenario_id: str) -> bool:
        """Delete a scenario record.

        Args:
            scenario_id: Id of the scenario to delete.

        Returns:
            True if a record was deleted, False if no record had this id.
        """
        return self._store.pop(scenario_id, None) is not None


class InMemorySnapshotRepository:
    """``SnapshotRepository`` that keeps snapshots in process memory, grouped by scenario id.

    Snapshots are lost when the process exits.
    """

    def __init__(self) -> None:
        """Create an empty repository."""
        self._store: dict[str, list[Snapshot]] = {}

    def save(self, snapshot: Snapshot) -> None:
        """Append a snapshot to the list of its scenario.

        Args:
            snapshot: The snapshot to store, filed under ``snapshot.scenario_id``.
        """
        self._store.setdefault(snapshot.scenario_id, []).append(snapshot)

    def find_by_scenario(self, scenario_id: str) -> list[Snapshot]:
        """List the snapshots saved for a scenario.

        Args:
            scenario_id: Id of the scenario.

        Returns:
            A new list of the scenario's snapshots sorted by ``tick`` (snapshots with the
            same tick keep their save order); empty if it has none.
        """
        return sorted(self._store.get(scenario_id, []), key=lambda s: s.tick)


class JsonFileSnapshotRepository(InMemorySnapshotRepository):
    """Snapshots kept in a JSON file so they survive API restarts (for resync and replay).

    Like ``JsonFileIncidentRepository``: writes go to a temporary file that atomically
    replaces the real one, and an unreadable file is moved aside
    (``*.corrupt-<time>.json``) rather than silently overwritten. The file holds a JSON array
    with one object per snapshot (the ``Snapshot`` fields); reads are served from memory.

    Attributes:
        path: Location of the JSON file.
    """

    def __init__(self, path: str | os.PathLike) -> None:
        """Open the snapshot store at ``path``, loading the snapshots already in the file.

        If the file is not valid JSON or holds rows that do not match ``Snapshot``, the store
        starts empty and the file is renamed to ``<stem>.corrupt-<epoch seconds>.json`` in the
        same folder. A missing file (and its folder) is created on the first write.

        Args:
            path: Path of the JSON file.
        """
        super().__init__()
        self.path = Path(path)
        if self.path.exists():
            try:
                for row in json.loads(self.path.read_text(encoding="utf-8")):
                    snap = Snapshot(**row)
                    self._store.setdefault(snap.scenario_id, []).append(snap)
            except (ValueError, TypeError):
                self._store.clear()
                self.path.replace(self.path.with_name(f"{self.path.stem}.corrupt-{int(time.time())}.json"))

    def _flush(self) -> None:
        """Write every snapshot to a temporary file, then atomically replace the JSON file."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        rows = [asdict(s) for snaps in self._store.values() for s in snaps]
        tmp.write_text(json.dumps(rows), encoding="utf-8")
        os.replace(tmp, self.path)

    def save(self, snapshot: Snapshot) -> None:
        """Append a snapshot to its scenario's list, then rewrite the file.

        Args:
            snapshot: The snapshot to store, filed under ``snapshot.scenario_id``.
        """
        super().save(snapshot)
        self._flush()


class IncidentRepository(Protocol):
    """Storage port for the incident history (GoF Repository), keyed by ``IncidentRecord.id``.

    Implemented by ``InMemoryIncidentRepository`` and ``JsonFileIncidentRepository``.
    """

    def save(self, record: IncidentRecord) -> None:
        """Store an incident record, replacing any record with the same id.

        Args:
            record: The record to store.
        """
        ...

    def find(self, incident_id: str) -> IncidentRecord | None:
        """Look up an incident record by id.

        Args:
            incident_id: Id of the incident.

        Returns:
            The record, or None if no record has this id.
        """
        ...

    def all(self) -> list[IncidentRecord]:
        """List every stored incident record, newest first.

        Returns:
            All stored records, the latest ``ended_at`` first.
        """
        ...

    def delete(self, incident_id: str) -> bool:
        """Delete an incident record.

        Args:
            incident_id: Id of the incident to delete.

        Returns:
            True if a record was deleted, False if no record had this id.
        """
        ...

    def clear(self) -> int:
        """Delete every incident record.

        Returns:
            The number of records deleted.
        """
        ...


class InMemoryIncidentRepository:
    """``IncidentRepository`` that keeps the incident history in a dict in process memory.

    Records are lost when the process exits; ``JsonFileIncidentRepository`` builds on this
    class to keep them in a file.
    """

    def __init__(self) -> None:
        """Create an empty history."""
        self._store: dict[str, IncidentRecord] = {}

    def save(self, record: IncidentRecord) -> None:
        """Store an incident record, replacing any record with the same id.

        Args:
            record: The record to store.
        """
        self._store[record.id] = record

    def find(self, incident_id: str) -> IncidentRecord | None:
        """Look up an incident record by id.

        Args:
            incident_id: Id of the incident.

        Returns:
            The record, or None if no record has this id.
        """
        return self._store.get(incident_id)

    def all(self) -> list[IncidentRecord]:
        """Newest first.

        Returns:
            A new list of all records sorted by ``ended_at``, latest first.
        """
        return sorted(self._store.values(), key=lambda r: r.ended_at, reverse=True)

    def delete(self, incident_id: str) -> bool:
        """Delete an incident record.

        Args:
            incident_id: Id of the incident to delete.

        Returns:
            True if a record was deleted, False if no record had this id.
        """
        return self._store.pop(incident_id, None) is not None

    def clear(self) -> int:
        """Delete every incident record.

        Returns:
            The number of records deleted.
        """
        n = len(self._store)
        self._store.clear()
        return n


class JsonFileIncidentRepository(InMemoryIncidentRepository):
    """Incident history kept in a JSON file so it survives API restarts.

    Writes go to a temporary file that atomically replaces the real one, so a crash
    mid-write never leaves a half-written history. An unreadable file is moved
    aside (``*.corrupt-<time>.json``) rather than silently overwritten.

    The file holds a JSON array with one object per record (the ``IncidentRecord`` fields);
    every change rewrites the whole file. Reads are served from memory.

    Attributes:
        path: Location of the JSON file.
    """

    def __init__(self, path: str | os.PathLike) -> None:
        """Open the history stored at ``path``, loading the records already in the file.

        If the file is not valid JSON or holds rows that do not match ``IncidentRecord``,
        the history starts empty and the file is renamed to
        ``<stem>.corrupt-<epoch seconds>.json`` in the same folder. A missing file (and its
        folder) is created on the first write.

        Args:
            path: Path of the JSON file.
        """
        super().__init__()
        self.path = Path(path)
        if self.path.exists():
            try:
                for row in json.loads(self.path.read_text(encoding="utf-8")):
                    record = IncidentRecord(**row)
                    self._store[record.id] = record
            except (ValueError, TypeError):
                self._store.clear()
                self.path.replace(self.path.with_name(f"{self.path.stem}.corrupt-{int(time.time())}.json"))

    def _flush(self) -> None:
        """Write every record to a temporary file, then atomically replace the JSON file."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps([asdict(r) for r in self._store.values()]), encoding="utf-8")
        os.replace(tmp, self.path)

    def save(self, record: IncidentRecord) -> None:
        """Store an incident record, then rewrite the file.

        Args:
            record: The record to store; it replaces any record with the same id.
        """
        super().save(record)
        self._flush()

    def delete(self, incident_id: str) -> bool:
        """Delete an incident record; the file is rewritten only if one was removed.

        Args:
            incident_id: Id of the incident to delete.

        Returns:
            True if a record was deleted, False if no record had this id.
        """
        removed = super().delete(incident_id)
        if removed:
            self._flush()
        return removed

    def clear(self) -> int:
        """Delete every incident record and rewrite the file as an empty list.

        Returns:
            The number of records deleted.
        """
        n = super().clear()
        self._flush()
        return n
