"""Builds a ready-to-run simulation session from a scenario (GoF Factory/Facade).

A wildland scenario gives a plain engine. A city scenario gives an engine on a
procedural town with the urban spread model, plus the city layer (people, risk,
fire crews) attached to the engine as a tick observer.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .cell import FuelType
from .city import CityModel
from .city_gen import CityMap, CityMapGenerator
from .engine import SimulationEngine
from .scenario import IgnitionPoint, Scenario
from .spread import UrbanSpreadModel
from .wind import Wind


@dataclass
class Session:
    """A ready-to-run simulation built by ``create_session``.

    Attributes:
        scenario: The scenario the session was built from.
        engine: The engine that advances the fire.
        city: The city layer (people, risk, fire crews), attached to ``engine`` as a tick
            observer; None for wildland scenarios.
    """
    scenario: Scenario
    engine: SimulationEngine
    city: CityModel | None = None


def default_ignition(city: CityMap, wind: Wind) -> IgnitionPoint:
    """A burnable wildland cell upwind of the town, so the fire runs toward it.

    It picks the grass, shrub or forest cell outside the town (and outside a one-cell margin
    around it) that is nearest to a target point upwind of the town centre, at 0.75 times
    half the town's diagonal plus 5 cells.

    Args:
        city: The generated town; its ``town`` rectangle and ``grid`` are used.
        wind: The scenario's wind; only its direction matters.

    Returns:
        The chosen cell as an ``IgnitionPoint`` (tick 0), or the town centre if there is no
        such wildland cell.
    """
    x0, y0, x1, y1 = city.town
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    we, wn = wind.vector()
    ux, uy = -we, wn                       # upwind, in grid (x east, y south) coordinates
    reach = math.hypot(x1 - x0, y1 - y0) / 2.0 * 0.75 + 5
    tx, ty = cx + ux * reach, cy + uy * reach
    grid = city.grid
    yy, xx = np.mgrid[0:grid.height, 0:grid.width]
    outside = (xx < x0 - 1) | (xx >= x1 + 1) | (yy < y0 - 1) | (yy >= y1 + 1)
    ok = outside & np.isin(grid.fuel, [FuelType.GRASS, FuelType.SHRUB, FuelType.FOREST])
    if not ok.any():
        return IgnitionPoint(int(cx), int(cy))
    d = np.where(ok, np.hypot(xx + 0.5 - tx, yy + 0.5 - ty), np.inf)
    y, x = np.unravel_index(int(np.argmin(d)), d.shape)
    return IgnitionPoint(int(x), int(y))


def create_session(sc: Scenario, *, publisher=None, snapshot_every: int = 0) -> Session:
    """Build the session.

    A scenario whose ``map_type`` is not ``"city"`` gets a plain engine from
    ``SimulationEngine.from_scenario``. A city scenario gets an engine on a procedural town
    with ``UrbanSpreadModel`` and its ignition points set alight, plus a ``CityModel``
    attached to the engine as a tick observer. For a city scenario without ignition points,
    a default upwind ignition is chosen and written back to ``sc.ignition_points``.

    An out-of-range map size raises ``ValueError`` from the map generator or ``Grid`` (for
    example a city map smaller than 48 x 48 cells).

    Args:
        sc: The scenario to build; a city scenario may get a default ignition point.
        publisher: Optional event publisher passed to the engine (see
            ``SimulationEngine.publisher``); None disables event publishing.
        snapshot_every: Periodic snapshot interval in ticks passed to the engine (see
            ``SimulationEngine.snapshot_every``); 0 disables periodic snapshots.

    Returns:
        The new ``Session``; its ``city`` is None for wildland scenarios.
    """
    if sc.map_type != "city":
        return Session(sc, SimulationEngine.from_scenario(
            sc, publisher=publisher, snapshot_every=snapshot_every))
    cmap = CityMapGenerator.generate(sc.width, sc.height, sc.seed)
    wind = Wind(sc.wind_direction, sc.wind_speed)
    eng = SimulationEngine(cmap.grid, wind, seed=sc.seed, spread_model=UrbanSpreadModel(),
                           publisher=publisher, snapshot_every=snapshot_every)
    if not sc.ignition_points:
        sc.ignition_points = [default_ignition(cmap, wind)]
    for p in sc.ignition_points:
        eng.ignite(p.x, p.y)
    city = CityModel(cmap, hour=sc.hour, crews=sc.crews, auto_dispatch=sc.auto_dispatch,
                     seed=sc.seed)
    city.attach(eng)
    return Session(sc, eng, city)
