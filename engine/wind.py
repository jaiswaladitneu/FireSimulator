"""Wind model."""
from __future__ import annotations

import math
from dataclasses import dataclass

#: Wind speed (km/h) at which the wind factor saturates.
WIND_SATURATION_KMH = 40.0


@dataclass
class Wind:
    """Wind as a direction the wind blows *toward* and a speed in km/h.

    direction_deg is measured clockwise from North (0 = N, 90 = E, 180 = S).
    """
    direction_deg: float = 0.0
    speed: float = 0.0

    def vector(self) -> tuple[float, float]:
        """Unit vector in (east, north) pointing where the wind blows toward."""
        rad = math.radians(self.direction_deg)
        return (math.sin(rad), math.cos(rad))

    @property
    def speed_norm(self) -> float:
        """Speed normalized to roughly 0..1."""
        return max(0.0, min(1.0, self.speed / WIND_SATURATION_KMH))
