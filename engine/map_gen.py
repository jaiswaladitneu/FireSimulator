"""Procedural map generation (Epic E4).

Generates reproducible terrain (elevation), fuel distribution and moisture from a
seed, so a scenario always plays out the same way without any external data.
"""
from __future__ import annotations

import numpy as np

from .cell import FuelType
from .grid import Grid

_SMOOTH_KERNEL = np.array([[1, 2, 1], [2, 4, 2], [1, 2, 1]], dtype=np.float32)
_SMOOTH_KERNEL /= _SMOOTH_KERNEL.sum()


def _smooth(a: np.ndarray) -> np.ndarray:
    pad = np.pad(a, 1, mode="edge")
    out = np.zeros_like(a)
    for dy in range(3):
        for dx in range(3):
            out += _SMOOTH_KERNEL[dy, dx] * pad[dy:dy + a.shape[0], dx:dx + a.shape[1]]
    return out


class MapGenerator:
    """Factory for procedurally generated grids."""

    @staticmethod
    def generate(width: int, height: int, seed: int = 0, *, smoothing: int = 6) -> Grid:
        rng = np.random.default_rng(seed)
        elev = rng.random((height, width)).astype(np.float32)
        for _ in range(smoothing):
            elev = _smooth(elev)
        span = float(np.ptp(elev)) or 1.0
        elev = (elev - elev.min()) / span

        fuel = rng.choice(
            [int(FuelType.GRASS), int(FuelType.SHRUB), int(FuelType.FOREST)],
            size=(height, width),
            p=[0.45, 0.33, 0.22],
        ).astype(np.int8)
        moisture = np.clip(0.10 + 0.20 * rng.random((height, width)), 0.0, 1.0).astype(np.float32)
        return Grid(width, height, fuel=fuel, moisture=moisture, elevation=elev)
