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
    """Blur a 2-D array once with ``_SMOOTH_KERNEL`` (borders repeat the edge values)."""
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
        """Generate a reproducible wildland grid from a seed.

        The same arguments always give the same grid. Elevation is random noise smoothed
        ``smoothing`` times and rescaled to 0..1. Each cell's fuel is drawn independently as
        ``GRASS``, ``SHRUB`` or ``FOREST`` with probabilities 0.45, 0.33 and 0.22, and its
        moisture is uniform in 0.10..0.30.

        Args:
            width: Number of columns (cells along x).
            height: Number of rows (cells along y).
            seed: Seed for the NumPy random generator.
            smoothing: Number of smoothing passes over the elevation noise; more passes give
                smoother terrain.

        Returns:
            A new ``Grid`` with ``fuel``, ``moisture`` and ``elevation`` filled in and every
            cell unburned.
        """
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
