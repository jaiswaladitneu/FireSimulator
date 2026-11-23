"""Persistence & replay (Epic E6).

Repository interfaces (GoF Repository) abstract storage so the domain is
storage-agnostic. In-memory implementations are used for tests and local runs;
PostgreSQL-backed implementations can plug in behind the same interfaces.

``JsonFileIncidentRepository`` keeps the incident history in a JSON file so it survives
restarts. The models are ``Snapshot`` (a Memento of the grid state), ``ScenarioRecord`` and
``IncidentRecord``.
"""
from .models import IncidentRecord, ScenarioRecord, Snapshot
from .repositories import (
    IncidentRepository,
    InMemoryIncidentRepository,
    InMemoryScenarioRepository,
    InMemorySnapshotRepository,
    JsonFileIncidentRepository,
    ScenarioRepository,
    SnapshotRepository,
)

__all__ = [
    "Snapshot", "ScenarioRecord", "IncidentRecord",
    "ScenarioRepository", "SnapshotRepository", "IncidentRepository",
    "InMemoryScenarioRepository", "InMemorySnapshotRepository",
    "InMemoryIncidentRepository", "JsonFileIncidentRepository",
]
