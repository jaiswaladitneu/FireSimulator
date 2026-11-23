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

    Attributes:
        direction_deg: Direction the wind blows toward, in degrees clockwise from North
            (default 0).
        speed: Wind speed in km/h (default 0, calm air).
        speed_norm: ``speed`` as a fraction of ``WIND_SATURATION_KMH`` (40 km/h), clamped to
            0..1 (read-only).
    """
    direction_deg: float = 0.0
    speed: float = 0.0

    def vector(self) -> tuple[float, float]:
        """Unit vector in (east, north) pointing where the wind blows toward.

        It depends only on ``direction_deg``, not on ``speed``.

        Returns:
            The ``(east, north)`` components ``(sin(direction), cos(direction))``; for
            example about ``(1.0, 0.0)`` for a wind blowing toward the east (90 degrees).
        """
        rad = math.radians(self.direction_deg)
        return (math.sin(rad), math.cos(rad))

    @property
    def speed_norm(self) -> float:
        """Speed normalized to roughly 0..1.

        The value is ``speed / WIND_SATURATION_KMH`` clamped to the range 0..1, so any speed
        of 40 km/h or more gives 1.0.
        """
        return max(0.0, min(1.0, self.speed / WIND_SATURATION_KMH))
