"""Fire Simulator — simulation engine core (Epics E1, E4).

Models the fire on a grid of cells and advances it in discrete ticks.
See the package modules: cell, grid, wind, spread, map_gen, scenario, engine,
and for towns: landuse, city_gen, population, response, city, session.
"""
from .cell import CellState, FuelType
from .city import CityModel
from .city_gen import Asset, CityMap, CityMapGenerator, Part
from .engine import SimState, SimulationEngine, TickObserver
from .grid import Grid
from .landuse import LandUse
from .map_gen import MapGenerator
from .scenario import IgnitionPoint, Scenario
from .session import Session, create_session
from .spread import PhysicsSpreadModel, SpreadModel, UrbanSpreadModel
from .wind import Wind

__all__ = [
    "CellState", "FuelType", "Grid", "Wind", "SpreadModel", "PhysicsSpreadModel",
    "UrbanSpreadModel", "Scenario", "IgnitionPoint", "MapGenerator", "SimulationEngine",
    "SimState", "TickObserver", "LandUse", "CityMapGenerator", "CityMap", "Asset", "Part",
    "CityModel", "Session", "create_session",
]
