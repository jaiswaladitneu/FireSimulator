"""Fire Simulator — simulation engine core (Epics E1, E4).

Models the fire on a grid of cells and advances it in discrete ticks.
See the package modules: cell, grid, wind, spread, map_gen, scenario, engine.
"""
from .cell import CellState, FuelType
from .engine import SimState, SimulationEngine
from .grid import Grid
from .map_gen import MapGenerator
from .scenario import IgnitionPoint, Scenario
from .spread import PhysicsSpreadModel, SpreadModel
from .wind import Wind

__all__ = [
    "CellState", "FuelType", "Grid", "Wind", "SpreadModel", "PhysicsSpreadModel",
    "Scenario", "IgnitionPoint", "MapGenerator", "SimulationEngine", "SimState",
]
