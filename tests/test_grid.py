import numpy as np

from engine import CellState, FuelType, Grid


def test_grid_starts_unburned():
    g = Grid(10, 8)
    assert g.width == 10 and g.height == 8
    assert g.state.shape == (8, 10)
    assert np.all(g.state == CellState.UNBURNED)
    assert g.counts()["unburned"] == 80


def test_ignite_sets_burning():
    g = Grid(5, 5)
    g.ignite(2, 3)
    assert g.get_state(2, 3) == CellState.BURNING
    assert g.counts()["burning"] == 1


def test_non_fuel_cell_does_not_ignite():
    fuel = np.full((3, 3), FuelType.NONE, dtype=np.int8)
    g = Grid(3, 3, fuel=fuel)
    g.ignite(1, 1)
    assert g.get_state(1, 1) == CellState.UNBURNED


def test_grid_size_is_validated():
    import pytest

    with pytest.raises(ValueError):
        Grid(0, 10)
