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
    """A fire crew that the incident commander sends to an asset.

    Its ``status`` cycles ``available`` -> ``en_route`` -> ``working`` -> ``available``.

    Attributes:
        id: Crew index (0-based), its position in ``ResponseManager.crews``.
        name: Radio name from ``CREW_NAMES`` (e.g. ``"Engine 1"``).
        x: Position along x, in cells. Crews start at the centre of the station cell and stay
            where they finished their last job.
        y: Position along y, in cells.
        status: ``"available"``, ``"en_route"`` or ``"working"``.
        target: Id of the asset the crew is assigned to; ``None`` when available.
        origin: Position ``(x, y)`` the current trip started from.
        travel_total: Ticks the current trip takes (at least 1).
        travel_left: Ticks left until arrival (reported as ``eta``).
        work_left: Ticks of work left at the target before the crew is released.
        assignment_cells: Cells treated during the current assignment.
        cells_suppressed: Cells treated since the crew was created.
        dispatches: Number of times the crew has been dispatched.
    """
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
        """Serialise the crew for the live city payload.

        Returns:
            A dict with ``id``, ``name``, ``status``, ``target``, ``x`` and ``y`` (rounded to
            2 decimals), ``eta`` (ticks left travelling), ``work_left`` and
            ``cells_suppressed``.
        """
        return {
            "id": self.id, "name": self.name, "status": self.status, "target": self.target,
            "x": round(self.x, 2), "y": round(self.y, 2), "eta": self.travel_left,
            "work_left": self.work_left, "cells_suppressed": self.cells_suppressed,
        }


def _dilate(m: np.ndarray) -> np.ndarray:
    """Grow a 2-D boolean mask by one cell in all eight directions."""
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
    """The fire crews of a city incident: dispatch, travel and suppression work.

    Each tick ``step`` moves en-route crews toward their target asset and lets working crews
    treat up to ``CAPACITY`` cells around it. With ``auto`` set, free crews are also sent to
    the most urgent priorities without waiting for the commander.

    Attributes:
        SPEED: Cells a crew travels per tick.
        WORK_TICKS: Ticks a crew works at a target before it is released.
        CAPACITY: Cells a crew can treat per tick.
        RADIUS: Working radius (cells) around the target asset's site.
        n: Number of crews (0 to ``MAX_CREWS``).
        station: Cell ``(x, y)`` of the fire station, where the crews start.
        auto: Whether free crews are dispatched automatically each tick.
        crews: The crews, indexed by crew id.
        dispatch_count: Dispatches since the last reset.
        cells_suppressed: Cells treated by all crews since the last reset.
    """
    SPEED = 5.0       # cells travelled per tick
    WORK_TICKS = 14   # ticks a crew works at a target before it is released
    CAPACITY = 7      # cells a crew can treat per tick
    RADIUS = 3        # working radius around the target (cells)

    def __init__(self, n_crews: int, station: tuple[int, int], auto: bool = False) -> None:
        """Create the crews, all available at the fire station.

        Args:
            n_crews: Number of crews; clamped to 0..``MAX_CREWS`` (12).
            station: Cell ``(x, y)`` where the crews start.
            auto: Start with automatic dispatch enabled.
        """
        self.n = max(0, min(MAX_CREWS, int(n_crews)))
        self.station = station
        self.auto = auto
        self.reset()

    def reset(self) -> None:
        """Replace the crews with fresh, available ones at the station and zero the totals."""
        sx, sy = self.station
        self.crews = [Crew(i, CREW_NAMES[i], sx + 0.5, sy + 0.5) for i in range(self.n)]
        self.dispatch_count = 0
        self.cells_suppressed = 0

    def targeted(self) -> set[int]:
        """Return the assets that have a crew assigned.

        Returns:
            Ids of the assets with a crew en route or working.
        """
        return {c.target for c in self.crews if c.status != "available" and c.target is not None}

    def working_targets(self) -> set[int]:
        """Return the assets where a crew is working on scene.

        Returns:
            Ids of the assets with a crew in the ``"working"`` state.
        """
        return {c.target for c in self.crews if c.status == "working" and c.target is not None}

    def available(self) -> int:
        """Count the crews that are free to dispatch.

        Returns:
            Number of crews whose status is ``"available"``.
        """
        return sum(1 for c in self.crews if c.status == "available")

    def dispatch(self, asset_id: int, city: CityModel) -> Crew | None:
        """Send the nearest available crew to an asset; ``None`` if every crew is busy.

        The nearest crew has the shortest city-block distance from its current position to
        the asset's centre. The trip takes that distance divided by ``SPEED``, rounded up (at
        least 1 tick). The dispatch is written to the city's event log.

        Args:
            asset_id: Id of the target asset (index into ``city.assets``).
            city: The city model that holds the asset and the event log.

        Returns:
            The dispatched crew, now ``"en_route"``, or ``None`` if no crew is available.
        """
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
        """Advance every crew one tick; returns the cells to suppress this tick.

        With ``auto`` set, free crews are first dispatched to the top priorities (any level
        but ``low``) that have no crew yet. En-route crews move in a straight line toward the
        asset's centre and start ``WORK_TICKS`` ticks of work on arrival. Each working crew
        picks up to ``CAPACITY`` cells within ``RADIUS`` of the asset's site: fire on the
        asset first, then other fire; if that area has fire or the asset is within
        ``city.THREAT_R`` of it, also unburned fuel next to the fire and then the asset's own
        unburned fuel (pre-wetting). Within each tier, cells nearer the asset's centre come
        first. A crew is released when its work time is over, or when it finds nothing to
        treat and the fire is farther than ``city.ALERT_R`` from the asset. Arrivals and
        releases are written to the city's event log.

        Args:
            city: The city model (assets, fire distances, priorities and event log).
            grid: The fire grid whose cell states and fuel are read.

        Returns:
            The ``(x, y)`` cells to suppress; no cell is listed twice.
        """
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
        """Send free crews down the priority list, skipping covered and ``low`` entries."""
        targeted = self.targeted()
        for p in city.priorities:
            if self.available() == 0:
                break
            if p["id"] in targeted or p["level"] == "low":
                continue
            if self.dispatch(p["id"], city) is not None:
                targeted.add(p["id"])

    def _pick_cells(self, city: CityModel, grid: Grid, asset_id: int) -> list[tuple[int, int]]:
        """Rank the cells to treat around an asset, best first (at most ``3 * CAPACITY``)."""
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
