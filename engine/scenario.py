"""Scenario definition (Epic E2 — Scenario Management)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field


@dataclass
class IgnitionPoint:
    """A cell where the fire starts.

    Attributes:
        x: Column of the cell.
        y: Row of the cell.
        tick: Tick recorded with the point (default 0). The engine does not use it:
            ``SimulationEngine.from_scenario`` and ``create_session`` ignite every point
            before the first tick.
    """
    x: int
    y: int
    tick: int = 0


@dataclass
class Scenario:
    """Settings for one simulation run: map, wind, ignition points and city options.

    ``seed`` drives every random choice (the map, the fire spread and, in cities, building
    occupancy), so the same scenario always plays out the same way.

    Attributes:
        name: Human-readable name.
        width: Map width in cells (default 200); 1..400, and at least 48 for a city map.
        height: Map height in cells (default 200); 1..400, and at least 48 for a city map.
        seed: Seed for map generation and the engine's random generator (default 0).
        wind_direction: Direction the wind blows toward, in degrees clockwise from North
            (0 = N, 90 = E; default 90).
        wind_speed: Wind speed in km/h (default 15).
        ignition_points: Cells set alight before the first tick. For a city scenario without
            any, ``create_session`` picks one upwind of the town and stores it here.
        id: Unique identifier; a random UUID4 string by default.
        map_type: ``"wildland"`` (default) for procedural terrain, or ``"city"`` for a
            procedural town with people and fire crews.
        hour: Local hour of day (0-23) when the incident starts (default 14); in city
            scenarios it drives building occupancy.
        crews: Number of fire engines available in city scenarios (default 4).
        auto_dispatch: Whether crews self-assign to the top priorities in city scenarios
            (default False).
    """
    name: str
    width: int = 200
    height: int = 200
    seed: int = 0
    wind_direction: float = 90.0   # degrees, 0 = N, 90 = E
    wind_speed: float = 15.0       # km/h
    ignition_points: list[IgnitionPoint] = field(default_factory=list)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    # City scenarios (map_type="city") add a town, its people and fire crews.
    map_type: str = "wildland"     # "wildland" | "city"
    hour: int = 14                 # local time the incident starts (drives occupancy)
    crews: int = 4                 # fire engines available
    auto_dispatch: bool = False    # crews self-assign to the top priorities
