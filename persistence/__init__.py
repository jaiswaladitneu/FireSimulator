"""Persistence & replay (Epic E6).

Repository interfaces (GoF Repository) abstract storage so the domain is
storage-agnostic. In-memory implementations are used for tests and local runs;
PostgreSQL-backed implementations plug in behind the same interfaces.
"""
from .models import ScenarioRecord, Snapshot
from .repositories import (
    InMemoryScenarioRepository,
    InMemorySnapshotRepository,
    ScenarioRepository,
    SnapshotRepository,
)

__all__ = [
    "Snapshot", "ScenarioRecord",
    "ScenarioRepository", "SnapshotRepository",
    "InMemoryScenarioRepository", "InMemorySnapshotRepository",
]
