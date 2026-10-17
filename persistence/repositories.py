"""Repository ports and in-memory implementations."""
from __future__ import annotations

from typing import Protocol

from .models import ScenarioRecord, Snapshot


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
