"""The simulation grid: a landscape of cells held as NumPy arrays."""
from __future__ import annotations

import numpy as np

from .cell import CellState, FuelType

MAX_SIDE = 400  # safety cap on grid dimension


class Grid:
    """A width x height grid of cells.

    Cell properties are stored as parallel NumPy arrays of shape (height, width)
    so the per-tick update can be vectorized rather than looping cell by cell.
    """

    def __init__(
        self,
        width: int,
        height: int,
        *,
        fuel: np.ndarray | None = None,
        moisture: np.ndarray | None = None,
        elevation: np.ndarray | None = None,
    ) -> None:
        if not (1 <= width <= MAX_SIDE and 1 <= height <= MAX_SIDE):
            raise ValueError(f"grid size must be within 1..{MAX_SIDE}")
        self.width = width
        self.height = height
        shape = (height, width)
        self.state = np.full(shape, CellState.UNBURNED, dtype=np.int8)
        self.fuel = fuel if fuel is not None else np.full(shape, FuelType.GRASS, dtype=np.int8)
        self.moisture = moisture if moisture is not None else np.full(shape, 0.10, dtype=np.float32)
        self.elevation = elevation if elevation is not None else np.zeros(shape, dtype=np.float32)
        # 1.0 of fuel in every burnable cell, 0 where there is nothing to burn.
        self.fuel_remaining = (self.fuel != FuelType.NONE).astype(np.float32)

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def get_state(self, x: int, y: int) -> CellState:
        return CellState(int(self.state[y, x]))

    def ignite(self, x: int, y: int) -> None:
        """Set a burnable cell alight (used for ignition points)."""
        if self.in_bounds(x, y) and self.fuel[y, x] != FuelType.NONE:
            self.state[y, x] = CellState.BURNING

    def counts(self) -> dict[str, int]:
        """Number of cells in each state, keyed by lowercase state name."""
        return {s.name.lower(): int(np.count_nonzero(self.state == s)) for s in CellState}
