"""Repository ports and in-memory implementations."""
from __future__ import annotations

import json
import os
import time
from dataclasses import asdict
from pathlib import Path
from typing import Protocol

from .models import IncidentRecord, ScenarioRecord, Snapshot


class ScenarioRepository(Protocol):
    def save(self, record: ScenarioRecord) -> None: ...
    def find(self, scenario_id: str) -> ScenarioRecord | None: ...
    def all(self) -> list[ScenarioRecord]: ...
    def delete(self, scenario_id: str) -> bool: ...


class SnapshotRepository(Protocol):
    def save(self, snapshot: Snapshot) -> None: ...
    def find_by_scenario(self, scenario_id: str) -> list[Snapshot]: ...


class InMemoryScenarioRepository:
    def __init__(self) -> None:
        self._store: dict[str, ScenarioRecord] = {}

    def save(self, record: ScenarioRecord) -> None:
        self._store[record.id] = record

    def find(self, scenario_id: str) -> ScenarioRecord | None:
        return self._store.get(scenario_id)

    def all(self) -> list[ScenarioRecord]:
        return list(self._store.values())

    def delete(self, scenario_id: str) -> bool:
        return self._store.pop(scenario_id, None) is not None


class InMemorySnapshotRepository:
    def __init__(self) -> None:
        self._store: dict[str, list[Snapshot]] = {}

    def save(self, snapshot: Snapshot) -> None:
        self._store.setdefault(snapshot.scenario_id, []).append(snapshot)

    def find_by_scenario(self, scenario_id: str) -> list[Snapshot]:
        return sorted(self._store.get(scenario_id, []), key=lambda s: s.tick)


class IncidentRepository(Protocol):
    def save(self, record: IncidentRecord) -> None: ...
    def find(self, incident_id: str) -> IncidentRecord | None: ...
    def all(self) -> list[IncidentRecord]: ...
    def delete(self, incident_id: str) -> bool: ...
    def clear(self) -> int: ...


class InMemoryIncidentRepository:
    def __init__(self) -> None:
        self._store: dict[str, IncidentRecord] = {}

    def save(self, record: IncidentRecord) -> None:
        self._store[record.id] = record

    def find(self, incident_id: str) -> IncidentRecord | None:
        return self._store.get(incident_id)

    def all(self) -> list[IncidentRecord]:
        """Newest first."""
        return sorted(self._store.values(), key=lambda r: r.ended_at, reverse=True)

    def delete(self, incident_id: str) -> bool:
        return self._store.pop(incident_id, None) is not None

    def clear(self) -> int:
        n = len(self._store)
        self._store.clear()
        return n


class JsonFileIncidentRepository(InMemoryIncidentRepository):
    """Incident history kept in a JSON file so it survives API restarts.

    Writes go to a temporary file that atomically replaces the real one, so a crash
    mid-write never leaves a half-written history. An unreadable file is moved
    aside (``*.corrupt-<time>.json``) rather than silently overwritten.
    """

    def __init__(self, path: str | os.PathLike) -> None:
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
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps([asdict(r) for r in self._store.values()]), encoding="utf-8")
        os.replace(tmp, self.path)

    def save(self, record: IncidentRecord) -> None:
        super().save(record)
        self._flush()

    def delete(self, incident_id: str) -> bool:
        removed = super().delete(incident_id)
        if removed:
            self._flush()
        return removed

    def clear(self) -> int:
        n = super().clear()
        self._flush()
        return n
