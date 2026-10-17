"""Scenario definition (Epic E2 — Scenario Management)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field


@dataclass
class IgnitionPoint:
    x: int
    y: int
    tick: int = 0


@dataclass
class Scenario:
    name: str
    width: int = 200
    height: int = 200
    seed: int = 0
    wind_direction: float = 90.0   # degrees, 0 = N, 90 = E
    wind_speed: float = 15.0       # km/h
    ignition_points: list[IgnitionPoint] = field(default_factory=list)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
