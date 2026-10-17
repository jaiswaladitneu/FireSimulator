"""Fire-spread model (GoF Strategy).

The engine depends on the ``SpreadModel`` protocol, not on a concrete model, so
the spread algorithm can be swapped (e.g. for richer physics) without touching
the engine. ``PhysicsSpreadModel`` is the default: a vectorized, physics-lite
model driven by fuel, moisture, wind and slope.
"""
from __future__ import annotations

from typing import Protocol

import numpy as np

from .cell import FUEL_FLAMMABILITY, CellState
from .grid import Grid
from .wind import Wind

# 8-neighbourhood offsets as (dy, dx) in (row, col).
NEIGHBORS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]

BASE_P = 0.28   # base per-neighbour ignition probability
WIND_K = 1.4    # strength of the wind effect
SLOPE_K = 0.6   # strength of the slope effect
MAX_P = 0.98    # cap so ignition is never certain


def _shift(a: np.ndarray, dy: int, dx: int) -> np.ndarray:
    """Return a copy of ``a`` shifted by (dy, dx) with zero fill (no wrap)."""
    r = np.zeros_like(a)
    h, w = a.shape
    sy0, sy1 = max(0, -dy), min(h, h - dy)
    sx0, sx1 = max(0, -dx), min(w, w - dx)
    dy0, dx0 = max(0, dy), max(0, dx)
    r[dy0:dy0 + (sy1 - sy0), dx0:dx0 + (sx1 - sx0)] = a[sy0:sy1, sx0:sx1]
    return r


class SpreadModel(Protocol):
    def ignition_probability(self, grid: Grid, wind: Wind) -> np.ndarray:
        """Per-cell probability of igniting this tick (shape = grid shape)."""
        ...


class PhysicsSpreadModel:
    """Default spread strategy."""

    def ignition_probability(self, grid: Grid, wind: Wind) -> np.ndarray:
        burning = (grid.state == CellState.BURNING).astype(np.float32)

        # Susceptibility of each destination cell from its fuel and moisture.
        flam = np.zeros(grid.fuel.shape, dtype=np.float32)
        for ft, val in FUEL_FLAMMABILITY.items():
            flam[grid.fuel == ft] = val
        suscept = np.clip(flam * (1.0 - grid.moisture), 0.0, 1.0)

        we, wn = wind.vector()
        ws = wind.speed_norm
        elev = grid.elevation
        no_ignite = np.ones(grid.state.shape, dtype=np.float32)

        for dy, dx in NEIGHBORS:
            # A burning neighbour sitting at offset (dy, dx) from the cell.
            nb = _shift(burning, -dy, -dx)
            if not nb.any():
                continue
            # Spread direction (neighbour -> cell) in (east, north), normalized.
            mag = (dy * dy + dx * dx) ** 0.5
            se, sn = (-dx) / mag, (dy) / mag
            alignment = we * se + wn * sn            # -1..1
            wind_factor = np.clip(1.0 + WIND_K * ws * alignment, 0.1, 3.0)
            # Uphill spread is faster: cell elevation minus neighbour elevation.
            delev = elev - _shift(elev, -dy, -dx)
            slope_factor = np.clip(1.0 + SLOPE_K * np.tanh(delev / 0.2), 0.3, 2.0)

            p = np.clip(BASE_P * suscept * wind_factor * slope_factor, 0.0, MAX_P)
            no_ignite *= 1.0 - p * nb

        return 1.0 - no_ignite
