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
    scenario: Scenario
    engine: SimulationEngine
    city: CityModel | None = None


def default_ignition(city: CityMap, wind: Wind) -> IgnitionPoint:
    """A burnable wildland cell upwind of the town, so the fire runs toward it."""
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


def create_session(sc: Scenario, *, publisher=None) -> Session:
    """Build the session. For a city scenario without ignition points, a default
    upwind ignition is chosen and written back to ``sc.ignition_points``."""
    if sc.map_type != "city":
        return Session(sc, SimulationEngine.from_scenario(sc, publisher=publisher))
    cmap = CityMapGenerator.generate(sc.width, sc.height, sc.seed)
    wind = Wind(sc.wind_direction, sc.wind_speed)
    eng = SimulationEngine(cmap.grid, wind, seed=sc.seed, spread_model=UrbanSpreadModel(),
                           publisher=publisher)
    if not sc.ignition_points:
        sc.ignition_points = [default_ignition(cmap, wind)]
    for p in sc.ignition_points:
        eng.ignite(p.x, p.y)
    city = CityModel(cmap, hour=sc.hour, crews=sc.crews, auto_dispatch=sc.auto_dispatch,
                     seed=sc.seed)
    city.attach(eng)
    return Session(sc, eng, city)
