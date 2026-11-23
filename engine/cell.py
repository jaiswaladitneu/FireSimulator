"""Cell state and fuel definitions.

The grid stores cell properties as NumPy arrays (see grid.py); these enums give
the integer codes stored in those arrays and the per-fuel physical constants.
"""
from enum import IntEnum


class CellState(IntEnum):
    """Lifecycle of a single cell (matches the cell state-machine diagram).

    The values are the codes stored in ``Grid.state``. As the fire passes, a cell moves along
    ``UNBURNED -> IGNITING -> BURNING -> BURNED``; ``Grid.ignite`` sets a cell straight to
    ``BURNING``, and suppression turns an unburned, igniting or burning cell into ``SUPPRESSED``.

    Attributes:
        UNBURNED: Not on fire (the initial state); only these cells can be ignited by spread.
        IGNITING: Caught fire this tick; becomes ``BURNING`` at the start of the next tick. It
            does not spread fire or consume fuel yet.
        BURNING: On fire: can ignite its neighbours and consumes fuel every tick; becomes
            ``BURNED`` when its fuel runs out.
        BURNED: Burned out; its fuel is exhausted.
        SUPPRESSED: Suppression was applied; the cell stops burning and spreading fire can no
            longer ignite it.
    """
    UNBURNED = 0
    IGNITING = 1
    BURNING = 2
    BURNED = 3
    SUPPRESSED = 4


class FuelType(IntEnum):
    """Kind of fuel in a cell; the values are the codes stored in ``Grid.fuel``.

    The fuel sets how a cell burns through the per-fuel tables in this module:
    ``FUEL_FLAMMABILITY`` (how readily it ignites, 0..1), ``FUEL_BURN_RATE`` (fuel consumed per
    burning tick, where a burnable cell starts with 1.0) and ``FUEL_INTENSITY`` (relative heat
    output, used only by ``UrbanSpreadModel``).

    Attributes:
        NONE: Nothing to burn (e.g. water, roads, paving); such a cell never ignites.
        GRASS: Grass: the most flammable fuel and the quickest to burn out.
        SHRUB: Shrubs; between grass and forest in flammability and burn rate.
        FOREST: Forest; ignites less readily and burns longer than grass or shrubs.
        STRUCTURE: Wood-frame buildings (houses, small shops).
        MASONRY: Large concrete or brick buildings (schools, hospital); the hardest fuel to
            ignite.
        HAZMAT: Fuel pumps and tanks, lithium battery containers; burns hottest and longest.
    """
    NONE = 0
    GRASS = 1
    SHRUB = 2
    FOREST = 3
    STRUCTURE = 4   # wood-frame buildings (houses, small shops)
    MASONRY = 5     # large concrete/brick buildings (schools, hospital)
    HAZMAT = 6      # fuel pumps and tanks, lithium battery containers


# How readily each fuel ignites (0..1) and how fast it is consumed per tick.
FUEL_FLAMMABILITY = {
    FuelType.NONE: 0.0,
    FuelType.GRASS: 0.90,
    FuelType.SHRUB: 0.60,
    FuelType.FOREST: 0.40,
    FuelType.STRUCTURE: 0.55,
    FuelType.MASONRY: 0.22,
    FuelType.HAZMAT: 0.85,
}
FUEL_BURN_RATE = {
    FuelType.NONE: 0.0,
    FuelType.GRASS: 0.50,
    FuelType.SHRUB: 0.25,
    FuelType.FOREST: 0.12,
    FuelType.STRUCTURE: 0.07,
    FuelType.MASONRY: 0.05,
    FuelType.HAZMAT: 0.04,
}
# Relative heat output of a burning cell. Used only by the urban spread model;
# wildland fuels are 1.0 so they behave exactly as in the default model.
FUEL_INTENSITY = {
    FuelType.NONE: 0.0,
    FuelType.GRASS: 1.0,
    FuelType.SHRUB: 1.0,
    FuelType.FOREST: 1.0,
    FuelType.STRUCTURE: 1.3,
    FuelType.MASONRY: 1.15,
    FuelType.HAZMAT: 2.2,
}
