"""Cell state and fuel definitions.

The grid stores cell properties as NumPy arrays (see grid.py); these enums give
the integer codes stored in those arrays and the per-fuel physical constants.
"""
from enum import IntEnum


class CellState(IntEnum):
    """Lifecycle of a single cell (matches the cell state-machine diagram)."""
    UNBURNED = 0
    IGNITING = 1
    BURNING = 2
    BURNED = 3
    SUPPRESSED = 4


class FuelType(IntEnum):
    NONE = 0
    GRASS = 1
    SHRUB = 2
    FOREST = 3


# How readily each fuel ignites (0..1) and how fast it is consumed per tick.
FUEL_FLAMMABILITY = {
    FuelType.NONE: 0.0,
    FuelType.GRASS: 0.90,
    FuelType.SHRUB: 0.60,
    FuelType.FOREST: 0.40,
}
FUEL_BURN_RATE = {
    FuelType.NONE: 0.0,
    FuelType.GRASS: 0.50,
    FuelType.SHRUB: 0.25,
    FuelType.FOREST: 0.12,
}
