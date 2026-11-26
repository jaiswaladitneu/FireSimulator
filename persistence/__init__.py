"""Persistence & replay (Epic E6).

Repository interfaces (GoF Repository) abstract storage so the domain is
storage-agnostic. In-memory implementations are used for tests and local runs;
PostgreSQL-backed implementations can plug in behind the same interfaces.

``JsonFileIncidentRepository`` keeps the incident history in a JSON file so it survives
restarts. The models are ``Snapshot`` (a Memento of the grid state), ``ScenarioRecord`` and
``IncidentRecord``.
"""
from .cache import InMemoryStateCache, RedisStateCache, StateCache
from .models import IncidentRecord, ScenarioRecord, Snapshot
from .postgres import (
    PostgresIncidentRepository,
    PostgresScenarioRepository,
    PostgresSnapshotRepository,
    PostgresStore,
)
from .recorder import SnapshotArchiver
from .repositories import (
    IncidentRepository,
    InMemoryIncidentRepository,
    InMemoryScenarioRepository,
    InMemorySnapshotRepository,
    JsonFileIncidentRepository,
    JsonFileSnapshotRepository,
    ScenarioRepository,
    SnapshotRepository,
)

__all__ = [
    "Snapshot", "ScenarioRecord", "IncidentRecord",
    "ScenarioRepository", "SnapshotRepository", "IncidentRepository",
    "InMemoryScenarioRepository", "InMemorySnapshotRepository",
    "InMemoryIncidentRepository", "JsonFileIncidentRepository",
    "JsonFileSnapshotRepository", "SnapshotArchiver",
    "StateCache", "InMemoryStateCache", "RedisStateCache",
    "PostgresStore", "PostgresScenarioRepository",
    "PostgresSnapshotRepository", "PostgresIncidentRepository",
]
