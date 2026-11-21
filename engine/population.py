"""People in the town: who is where, and how they respond to fire.

Each asset kind has a profile:

* **presence** — fraction of an asset's capacity on site at each hour of the day
  (a school is full at 10:00 and empty at 22:00; homes are the opposite);
* **vulnerability** — how much one person at risk weighs in the priority score
  (hospital patients and schoolchildren cannot evacuate unaided);
* **evac_rate** — fraction of the people still inside who get out per tick once
  an evacuation is ordered;
* **harm_rate** — fraction of the people still inside harmed per tick while the
  asset is fully on fire (scaled by how much of it is burning);
* **hazard** — extra priority for sites that make a fire worse (fuel, batteries);
* **delay** — ticks between the evacuation order and people actually leaving
  (warning reaching them, gathering family, organising patients); doubled at night
  for homes because residents are asleep;
* **stay_fraction** — share of people who cannot leave without help (elderly or
  disabled residents, bed-bound patients). Only a fire crew on scene rescues them.

The numbers are planning-level estimates for a training simulation, not
calibrated casualty predictions.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class KindProfile:
    label: str
    presence: tuple[float, ...]   # 24 values, index = hour of day
    vulnerability: float
    evac_rate: float
    harm_rate: float
    hazard: float = 0.0
    trapped_fraction: float = 0.6  # share of those still inside lost if it is destroyed
    reason: str = ""
    delay: int = 1                 # ticks from evacuation order to people leaving
    stay_fraction: float = 0.0     # share who cannot leave without a crew's help


def _hours(*spans: tuple[int, int, float]) -> tuple[float, ...]:
    """Build a 24-hour presence curve from (start_hour, end_hour_inclusive, value) spans."""
    curve = [0.0] * 24
    for start, end, value in spans:
        for h in range(start, end + 1):
            curve[h] = value
    return tuple(curve)


PROFILES: dict[str, KindProfile] = {
    "house": KindProfile(
        "House",
        _hours((0, 6, 0.95), (7, 7, 0.80), (8, 8, 0.55), (9, 15, 0.35), (16, 16, 0.50),
               (17, 17, 0.65), (18, 21, 0.85), (22, 23, 0.93)),
        vulnerability=1.0, evac_rate=0.22, harm_rate=0.25, reason="residents at home",
        delay=3, stay_fraction=0.07,
    ),
    "commercial": KindProfile(
        "Shop / office",
        _hours((0, 6, 0.02), (7, 8, 0.30), (9, 11, 0.60), (12, 13, 0.85), (14, 16, 0.65),
               (17, 18, 0.80), (19, 20, 0.50), (21, 21, 0.25), (22, 23, 0.05)),
        vulnerability=0.9, evac_rate=0.30, harm_rate=0.20, reason="shoppers and staff",
        delay=2,
    ),
    "school": KindProfile(
        "School",
        _hours((0, 6, 0.01), (7, 7, 0.30), (8, 14, 0.95), (15, 15, 0.50), (16, 17, 0.15),
               (18, 23, 0.02)),
        vulnerability=1.8, evac_rate=0.20, harm_rate=0.18, reason="children on site",
        delay=2,
    ),
    "hospital": KindProfile(
        "Hospital",
        _hours((0, 7, 0.85), (8, 20, 0.95), (21, 23, 0.88)),
        vulnerability=2.2, evac_rate=0.05, harm_rate=0.12,
        reason="patients with limited mobility", delay=4, stay_fraction=0.30,
    ),
    "fuel_station": KindProfile(
        "Fuel station",
        _hours((0, 5, 0.25), (6, 6, 0.60), (7, 9, 0.85), (10, 15, 0.60), (16, 18, 0.85),
               (19, 22, 0.55), (23, 23, 0.30)),
        vulnerability=1.0, evac_rate=0.50, harm_rate=0.35, hazard=150.0,
        reason="fuel tanks: explosion risk",
    ),
    "battery_storage": KindProfile(
        "Battery storage",
        _hours((0, 6, 0.35), (7, 18, 0.90), (19, 23, 0.35)),
        vulnerability=1.0, evac_rate=0.50, harm_rate=0.35, hazard=120.0,
        reason="lithium batteries: thermal runaway and toxic smoke",
    ),
    "fire_station": KindProfile(
        "Fire station",
        _hours((0, 23, 0.90)),
        vulnerability=0.3, evac_rate=0.50, harm_rate=0.10, reason="response base",
    ),
    "park": KindProfile(
        "Park",
        _hours((0, 5, 0.01), (6, 8, 0.20), (9, 11, 0.45), (12, 17, 0.70), (18, 20, 0.40),
               (21, 23, 0.08)),
        vulnerability=0.8, evac_rate=0.30, harm_rate=0.08, trapped_fraction=0.2,
        reason="visitors in open space",
    ),
    "road": KindProfile(
        "Road",
        _hours((0, 5, 0.08), (6, 6, 0.35), (7, 9, 0.95), (10, 15, 0.55), (16, 18, 0.95),
               (19, 21, 0.45), (22, 23, 0.18)),
        vulnerability=0.7, evac_rate=0.35, harm_rate=0.04, trapped_fraction=0.0,
        reason="people in vehicles", delay=0,
    ),
}

NIGHT_HOURS = (23, 0, 1, 2, 3, 4, 5)   # residents asleep: home evacuation delay doubles

KINDS: list[str] = list(PROFILES)
KIND_INDEX: dict[str, int] = {k: i for i, k in enumerate(KINDS)}
# Kinds whose damage counts as a "building" in statistics.
BUILDING_KINDS = ("house", "commercial", "school", "hospital", "fuel_station",
                  "battery_storage", "fire_station")


def presence(kind: str, hour: int) -> float:
    """Fraction of an asset's capacity on site at the given hour (0-23)."""
    return PROFILES[kind].presence[int(hour) % 24]
