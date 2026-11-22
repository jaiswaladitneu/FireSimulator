"""The simulation grid: a landscape of cells held as NumPy arrays."""
from __future__ import annotations

import numpy as np

from .cell import CellState, FuelType

MAX_SIDE = 400  # safety cap on grid dimension


class Grid:
    """A width x height grid of cells.

    Cell properties are stored as parallel NumPy arrays of shape (height, width)
    so the per-tick update can be vectorized rather than looping cell by cell.
    The arrays are indexed ``[y, x]`` (row, column).

    Attributes:
        width: Number of columns (cells along x), between 1 and ``MAX_SIDE`` (400).
        height: Number of rows (cells along y), between 1 and ``MAX_SIDE`` (400).
        state: ``int8`` array of ``CellState`` codes; every cell starts ``UNBURNED``.
        fuel: ``FuelType`` code per cell (default: ``GRASS`` everywhere, ``int8``).
        moisture: Fuel moisture per cell (default 0.10, ``float32``); the spread models
            multiply a cell's flammability by ``1 - moisture``.
        elevation: Relative terrain height per cell, without a unit (default 0, ``float32``);
            fire spreads faster uphill.
        fuel_remaining: Fuel left per cell (``float32``): 1.0 in every burnable cell and 0
            where the fuel is ``FuelType.NONE``. A burning cell uses it up and becomes
            ``BURNED`` when it reaches 0.
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
        """Create a grid where every cell is unburned.

        Arrays passed in are stored as given (not copied) and should have shape
        ``(height, width)``.

        Args:
            width: Number of columns (cells along x), between 1 and ``MAX_SIDE`` (400).
            height: Number of rows (cells along y), between 1 and ``MAX_SIDE`` (400).
            fuel: ``FuelType`` code per cell; None fills the grid with ``GRASS``.
            moisture: Fuel moisture per cell; None uses 0.10 everywhere.
            elevation: Relative terrain height per cell; None makes the terrain flat (0).

        Raises:
            ValueError: When ``width`` or ``height`` is outside 1..``MAX_SIDE``.
        """
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
        """Tell whether a cell coordinate lies inside the grid.

        Args:
            x: Column index.
            y: Row index.

        Returns:
            True if ``0 <= x < width`` and ``0 <= y < height``.
        """
        return 0 <= x < self.width and 0 <= y < self.height

    def get_state(self, x: int, y: int) -> CellState:
        """Return the state of one cell.

        The coordinate is not bounds-checked; use ``in_bounds`` first.

        Args:
            x: Column index.
            y: Row index.

        Returns:
            The cell's ``CellState``.
        """
        return CellState(int(self.state[y, x]))

    def ignite(self, x: int, y: int) -> None:
        """Set a burnable cell alight (used for ignition points).

        The cell becomes ``BURNING`` whatever its current state. Coordinates outside the grid
        and cells whose fuel is ``FuelType.NONE`` are ignored.

        Args:
            x: Column index.
            y: Row index.
        """
        if self.in_bounds(x, y) and self.fuel[y, x] != FuelType.NONE:
            self.state[y, x] = CellState.BURNING

    def counts(self) -> dict[str, int]:
        """Number of cells in each state, keyed by lowercase state name.

        Returns:
            Dict mapping ``"unburned"``, ``"igniting"``, ``"burning"``, ``"burned"`` and
            ``"suppressed"`` to the number of cells in that state.
        """
        return {s.name.lower(): int(np.count_nonzero(self.state == s)) for s in CellState}
