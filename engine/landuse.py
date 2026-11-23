"""Land use layer (Epic E4 — Environment & Map Modeling).

Land use says what a cell *is* (road, house, park, ...), while the fuel layer says
how it burns. City maps set both; wildland maps derive land use from fuel so the
UI can render every map the same way.
"""
from __future__ import annotations

from enum import IntEnum

import numpy as np

from .cell import FuelType


class LandUse(IntEnum):
    """What a cell is (road, house, park, ...), as a code in a land-use layer.

    City maps store the layer in ``CityMap.landuse``; wildland maps derive it with
    ``landuse_from_fuel``. How a cell burns comes from its ``FuelType``, not its land use.

    Attributes:
        WATER: River or pond (``landuse_from_fuel`` also maps fuel-free cells here); nothing
            burns.
        ROAD: Street or highway; nothing burns.
        PAVED: Parking lot, plaza or station apron; nothing burns.
        GRASS: Open wild grassland.
        SHRUB: Shrubland.
        FOREST: Forest.
        LAWN: Yard or school field.
        PARK: Park grounds.
        HOUSE: House.
        COMMERCIAL: Shop, office or other commercial building.
        SCHOOL: School building.
        HOSPITAL: Hospital building.
        FUEL_STATION: Fuel station (kiosk and pump canopy).
        BATTERY: Battery-storage site (containers and control building).
        FIRE_STATION: Fire station building.
    """
    WATER = 0
    ROAD = 1
    PAVED = 2          # parking lots, plazas, station aprons
    GRASS = 3          # open wild grassland
    SHRUB = 4
    FOREST = 5
    LAWN = 6           # yards, school fields
    PARK = 7
    HOUSE = 8
    COMMERCIAL = 9
    SCHOOL = 10
    HOSPITAL = 11
    FUEL_STATION = 12
    BATTERY = 13
    FIRE_STATION = 14


def landuse_from_fuel(fuel: np.ndarray) -> np.ndarray:
    """Land use for a wildland map, derived from its fuel layer.

    Args:
        fuel: Array of ``FuelType`` codes (usually ``Grid.fuel``).

    Returns:
        An ``int8`` array of ``LandUse`` codes with the same shape as ``fuel``: ``NONE``
        becomes ``WATER``, ``SHRUB`` becomes ``SHRUB``, ``FOREST`` becomes ``FOREST`` and
        every other fuel becomes ``GRASS``.
    """
    lu = np.full(fuel.shape, LandUse.GRASS, dtype=np.int8)
    lu[fuel == FuelType.NONE] = LandUse.WATER
    lu[fuel == FuelType.SHRUB] = LandUse.SHRUB
    lu[fuel == FuelType.FOREST] = LandUse.FOREST
    return lu
