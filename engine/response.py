"""Fire crews: the response resources the incident commander dispatches.

Crews start at the fire station, travel to a target asset, then for a fixed
number of ticks suppress a limited number of cells per tick around it: first
fire inside the asset, then fire close to it, then a wet line next to the fire,
then the structure itself (pre-wetting). Capacity is deliberately limited so the
commander has to prioritise.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from .cell import CellState, FuelType

if TYPE_CHECKING:  # pragma: no cover
    from .city import CityModel
    from .grid import Grid

CREW_NAMES = ["Engine 1", "Engine 2", "Ladder 1", "Engine 3", "Rescue 1", "Engine 4",
              "Tanker 1", "Engine 5", "Brush 1", "Engine 6", "Ladder 2", "Engine 7"]
MAX_CREWS = len(CREW_NAMES)


@dataclass
class Crew:
    id: int
    name: str
    x: float
    y: float
    status: str = "available"       # available | en_route | working
    target: int | None = None
    origin: tuple[float, float] = (0.0, 0.0)
    travel_total: int = 0
    travel_left: int = 0
    work_left: int = 0
    assignment_cells: int = 0
    cells_suppressed: int = 0
    dispatches: int = 0

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "status": self.status, "target": self.target,
            "x": round(self.x, 2), "y": round(self.y, 2), "eta": self.travel_left,
            "work_left": self.work_left, "cells_suppressed": self.cells_suppressed,
        }


def _dilate(m: np.ndarray) -> np.ndarray:
    g = m.copy()
    g[1:, :] |= m[:-1, :]
    g[:-1, :] |= m[1:, :]
    g[:, 1:] |= m[:, :-1]
    g[:, :-1] |= m[:, 1:]
    g[1:, 1:] |= m[:-1, :-1]
    g[1:, :-1] |= m[:-1, 1:]
    g[:-1, 1:] |= m[1:, :-1]
    g[:-1, :-1] |= m[1:, 1:]
    return g


class ResponseManager:
    SPEED = 5.0       # cells travelled per tick
    WORK_TICKS = 14   # ticks a crew works at a target before it is released
    CAPACITY = 7      # cells a crew can treat per tick
    RADIUS = 3        # working radius around the target (cells)

    def __init__(self, n_crews: int, station: tuple[int, int], auto: bool = False) -> None:
        self.n = max(0, min(MAX_CREWS, int(n_crews)))
        self.station = station
        self.auto = auto
        self.reset()

    def reset(self) -> None:
        sx, sy = self.station
        self.crews = [Crew(i, CREW_NAMES[i], sx + 0.5, sy + 0.5) for i in range(self.n)]
        self.dispatch_count = 0
        self.cells_suppressed = 0

    def targeted(self) -> set[int]:
        return {c.target for c in self.crews if c.status != "available" and c.target is not None}

    def working_targets(self) -> set[int]:
        return {c.target for c in self.crews if c.status == "working" and c.target is not None}

    def available(self) -> int:
        return sum(1 for c in self.crews if c.status == "available")

    def dispatch(self, asset_id: int, city: CityModel) -> Crew | None:
        """Send the nearest available crew to an asset; ``None`` if every crew is busy."""
        free = [c for c in self.crews if c.status == "available"]
        if not free:
            return None
        asset = city.assets[asset_id]
        ax, ay = asset.center
        crew = min(free, key=lambda c: abs(c.x - ax) + abs(c.y - ay))
        trip = abs(crew.x - ax) + abs(crew.y - ay)
        crew.status, crew.target = "en_route", asset_id
        crew.origin = (crew.x, crew.y)
        crew.travel_total = crew.travel_left = max(1, math.ceil(trip / self.SPEED))
        crew.assignment_cells = 0
        crew.dispatches += 1
        self.dispatch_count += 1
        city.log("dispatch", f"{crew.name} dispatched to {asset.name} (ETA {crew.travel_left} min)",
                 asset_id, "info")
        return crew

    def step(self, city: CityModel, grid: Grid) -> list[tuple[int, int]]:
        """Advance every crew one tick; returns the cells to suppress this tick."""
        if self.auto:
            self._auto_assign(city)
        cells: list[tuple[int, int]] = []
        taken: set[tuple[int, int]] = set()
        for crew in self.crews:
            if crew.status == "en_route":
                asset = city.assets[crew.target]
                tx, ty = asset.center
                crew.travel_left -= 1
                f = 1.0 - crew.travel_left / crew.travel_total
                crew.x = crew.origin[0] + (tx - crew.origin[0]) * f
                crew.y = crew.origin[1] + (ty - crew.origin[1]) * f
                if crew.travel_left <= 0:
                    crew.status, crew.work_left = "working", self.WORK_TICKS
                    city.log("arrival", f"{crew.name} on scene at {asset.name}",
                             crew.target, "info")
            elif crew.status == "working":
                asset = city.assets[crew.target]
                picked = [c for c in self._pick_cells(city, grid, crew.target) if c not in taken]
                picked = picked[: self.CAPACITY]
                taken.update(picked)
                cells.extend(picked)
                crew.assignment_cells += len(picked)
                crew.cells_suppressed += len(picked)
                self.cells_suppressed += len(picked)
                crew.work_left -= 1
                idle = not picked and city.dist[crew.target] > city.ALERT_R
                if crew.work_left <= 0 or idle:
                    city.log("cleared", f"{crew.name} cleared {asset.name} "
                             f"({crew.assignment_cells} cells treated)", crew.target, "info")
                    crew.status, crew.target, crew.work_left = "available", None, 0
        return cells

    def _auto_assign(self, city: CityModel) -> None:
        targeted = self.targeted()
        for p in city.priorities:
            if self.available() == 0:
                break
            if p["id"] in targeted or p["level"] == "low":
                continue
            if self.dispatch(p["id"], city) is not None:
                targeted.add(p["id"])

    def _pick_cells(self, city: CityModel, grid: Grid, asset_id: int) -> list[tuple[int, int]]:
        a = city.assets[asset_id]
        r = self.RADIUS
        x0, y0 = max(0, a.x - r), max(0, a.y - r)
        x1, y1 = min(grid.width, a.x + a.w + r), min(grid.height, a.y + a.h + r)
        st = grid.state[y0:y1, x0:x1]
        fuel = grid.fuel[y0:y1, x0:x1]
        own = city.asset_id[y0:y1, x0:x1] == asset_id
        active = (st == CellState.IGNITING) | (st == CellState.BURNING)

        tier = np.full(st.shape, 99, dtype=np.int16)
        tier[active] = 1
        tier[active & own] = 0
        if active.any() or city.dist[asset_id] <= city.THREAT_R:
            unburned = (st == CellState.UNBURNED) & (fuel != FuelType.NONE)
            tier[unburned & _dilate(active) & (tier == 99)] = 2
            tier[unburned & own & (tier == 99)] = 3
        cand = tier < 99
        if not cand.any():
            return []
        yy, xx = np.mgrid[y0:y1, x0:x1]
        cx, cy = a.center
        d = np.hypot(xx + 0.5 - cx, yy + 0.5 - cy)
        order = np.lexsort((d[cand], tier[cand]))
        keep = order[: self.CAPACITY * 3]
        xs, ys = xx[cand][keep], yy[cand][keep]
        return [(int(x), int(y)) for x, y in zip(xs, ys, strict=True)]
