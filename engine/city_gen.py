"""Procedural town generator (Epic E4 — Environment & Map Modeling).

Builds a reproducible town from a seed: a street grid with named roads and
highways, residential lots, a commercial strip on Main St, schools, a hospital,
parks with ponds, fuel stations, a battery-storage site and a fire station, all
inside forested hills crossed by a river (a wildland-urban interface).

Every building, park and road segment becomes an :class:`Asset` with a capacity
(people) so the city layer can estimate lives at risk. Each asset's physical
structures are :class:`Part` boxes that the 3-D view draws.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

import numpy as np

from .cell import FuelType
from .grid import Grid
from .landuse import LandUse, landuse_from_fuel
from .map_gen import _smooth

CELL_SIZE_M = 10   # one cell is roughly 10 m x 10 m
MIN_SIDE = 48      # smallest grid that fits a town

_H_NAMES = ["Pine St", "Oak Ave", "Elm St", "Maple Ave", "Cedar St", "Birch Ln", "Walnut St",
            "Spruce Ave", "Willow St", "Aspen Rd", "Chestnut St", "Hickory Ave", "Poplar St",
            "Laurel Ave", "Juniper St", "Magnolia Ave", "Sycamore St", "Alder Rd"]
_V_NAMES = ["Lincoln Ave", "Washington Blvd", "Jefferson St", "Franklin Ave", "Madison St",
            "Adams Ave", "Jackson St", "Monroe Ave", "Hamilton St", "Grant Ave", "Taylor St",
            "Pierce Ave"]
_SCHOOLS = ["Maple Elementary School", "Lincoln Middle School", "Riverside High School",
            "Oakwood Elementary School", "Westview Academy", "Hillcrest Elementary School"]
_HOSPITALS = ["St. Mary's General Hospital", "Mercy Medical Center", "Valley Regional Hospital"]
_PARKS = ["Willow Park", "Memorial Park", "Central Green", "Cedar Grove Park", "Lakeside Park",
          "Hillside Park"]
_SHOPS = ["Market", "Pharmacy", "Cafe", "Hardware Store", "Bakery", "Bank", "Diner",
          "Bookstore", "Grocery", "Laundromat", "Post Office", "Pizzeria", "Florist", "Gym",
          "Dental Clinic", "Barber Shop", "Toy Store", "Pet Shop", "Deli", "Office Building",
          "Insurance Office", "Library", "Daycare", "Restaurant"]

Rect = tuple[int, int, int, int]   # x0, y0, x1, y1 (end-exclusive)


@dataclass
class Part:
    """One physical structure of an asset (drawn as a box in the 3-D view).

    Attributes:
        x: First column of the box.
        y: First row of the box.
        w: Width in cells (along x).
        h: Depth in cells (along y).
        height: Height in storeys; may be fractional (e.g. 1.6 for a gym).
        style: Kind of structure: ``house``, ``shop``, ``school``, ``gym``, ``hospital``,
            ``wing``, ``kiosk``, ``canopy``, ``container`` or ``firestation``.
    """
    x: int
    y: int
    w: int
    h: int
    height: float   # in storeys
    # house, shop, school, gym, hospital, wing, kiosk, canopy, container, firestation
    style: str


@dataclass
class Asset:
    """Something people use and responders protect: a building, a park or a road segment.

    The site rectangle (``x``, ``y``, ``w``, ``h``) can be larger than the cells the asset
    occupies in ``CityMap.asset_id`` (e.g. a school's buildings inside its block).

    Attributes:
        id: Index in ``CityMap.assets``; the value its cells hold in ``CityMap.asset_id``.
        kind: Asset kind, a key of ``population.PROFILES``: ``house``, ``commercial``,
            ``school``, ``hospital``, ``fuel_station``, ``battery_storage``,
            ``fire_station``, ``park`` or ``road``.
        name: Display name (a street address for a home, the street name for a road segment).
        x: First column of the site.
        y: First row of the site.
        w: Site width in cells.
        h: Site height in cells.
        capacity: Most people on site at once; the occupants at the start are drawn from it.
        floors: Number of storeys.
        street: Street the asset is on (empty for the fire station).
        parts: Structures drawn by the 3-D view (empty for parks and roads).
        center: Centre ``(x, y)`` of the site, in cells.
    """
    id: int
    kind: str
    name: str
    x: int
    y: int
    w: int
    h: int
    capacity: int
    floors: int = 1
    street: str = ""
    parts: list[Part] = field(default_factory=list)

    @property
    def center(self) -> tuple[float, float]:
        """Centre ``(x, y)`` of the site rectangle, in cells (fractional)."""
        return (self.x + self.w / 2.0, self.y + self.h / 2.0)

    def to_dict(self) -> dict:
        """Serialise the asset to a JSON-ready dict.

        Returns:
            A dict with ``id``, ``kind``, ``name``, ``street``, ``x``, ``y``, ``w``, ``h``,
            ``floors``, ``capacity`` and ``parts`` (one dict of ``Part`` fields per part).
        """
        return {
            "id": self.id, "kind": self.kind, "name": self.name, "street": self.street,
            "x": self.x, "y": self.y, "w": self.w, "h": self.h,
            "floors": self.floors, "capacity": self.capacity,
            "parts": [asdict(p) for p in self.parts],
        }


@dataclass
class CityMap:
    """A generated town: its fire grid, land use, assets and fire-crew base.

    Product of ``CityMapGenerator.generate``. Cell arrays have shape ``(H, W)`` and are
    indexed ``[y, x]``.

    Attributes:
        grid: Fire grid of the town, with the generator's fuel, moisture and elevation.
        landuse: ``LandUse`` code of every cell.
        asset_id: Index into ``assets`` of the asset on every cell, or -1.
        assets: Every building, park and road segment, indexed by ``Asset.id``.
        station: Cell ``(x, y)`` where fire crews are based.
        town: Town rectangle ``(x0, y0, x1, y1)``, end-exclusive; wildland surrounds it.
        seed: Seed the town was generated from.
    """
    grid: Grid
    landuse: np.ndarray        # (H, W) LandUse codes
    asset_id: np.ndarray       # (H, W) index into ``assets`` or -1
    assets: list[Asset]
    station: tuple[int, int]   # cell where fire crews are based
    town: Rect
    seed: int


@dataclass
class _Block:
    """Street block between two roads each way; ``row``/``col`` index it in the street grid."""
    x0: int
    y0: int
    x1: int
    y1: int
    row: int
    col: int

    @property
    def w(self) -> int:
        return self.x1 - self.x0

    @property
    def h(self) -> int:
        return self.y1 - self.y0

    @property
    def center(self) -> tuple[float, float]:
        return ((self.x0 + self.x1) / 2.0, (self.y0 + self.y1) / 2.0)


def _overlaps(a: Rect, b: Rect) -> bool:
    """Tell whether two end-exclusive rectangles overlap."""
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


class CityMapGenerator:
    """Factory for procedurally generated towns."""

    @staticmethod
    def generate(width: int, height: int, seed: int = 0) -> CityMap:
        """Generate a town on a ``width`` x ``height`` grid of cells.

        The same size and seed always give the same town.

        Args:
            width: Grid width in cells; at least ``MIN_SIDE`` (48) and at most the grid limit
                ``grid.MAX_SIDE`` (400), otherwise ``ValueError`` is raised.
            height: Grid height in cells; same limits as ``width``.
            seed: Seed of the random number generator.

        Returns:
            The generated town.
        """
        return _Builder(width, height, seed).build()


class _Builder:
    """Step-by-step builder of one town from a seed (used by ``CityMapGenerator``)."""

    def __init__(self, width: int, height: int, seed: int) -> None:
        if width < MIN_SIDE or height < MIN_SIDE:
            raise ValueError(f"city maps need at least {MIN_SIDE} x {MIN_SIDE} cells")
        self.W, self.H, self.seed = width, height, seed
        self.rng = np.random.default_rng(seed)
        shape = (height, width)
        self.lu = np.full(shape, LandUse.GRASS, dtype=np.int8)
        self.fuel = np.full(shape, FuelType.GRASS, dtype=np.int8)
        self.moist = np.full(shape, 0.15, dtype=np.float32)
        self.elev = np.zeros(shape, dtype=np.float32)
        self.aid = np.full(shape, -1, dtype=np.int32)
        self.assets: list[Asset] = []
        mx, my = max(8, round(width * 0.15)), max(8, round(height * 0.15))
        self.town: Rect = (mx, my, width - mx, height - my)
        self.station = (mx, my)
        self._house_numbers: dict[str, int] = {}
        self._shop_names = list(self.rng.permutation(_SHOPS))

    # ---- helpers ---------------------------------------------------------
    def _paint(self, rect: Rect, lu: LandUse, fuel: FuelType, moisture: float) -> None:
        """Set land use, fuel and moisture over a rectangle, clipped to the grid."""
        x0, y0, x1, y1 = rect
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(self.W, x1), min(self.H, y1)
        if x0 >= x1 or y0 >= y1:
            return
        self.lu[y0:y1, x0:x1] = lu
        self.fuel[y0:y1, x0:x1] = fuel
        self.moist[y0:y1, x0:x1] = moisture

    def _add(self, kind: str, name: str, site: Rect, capacity: int, *, floors: int = 1,
             street: str = "", parts: list[Part] | None = None,
             cells: list[Rect] | None = None) -> Asset:
        """Register an asset; ``cells`` are the rects it occupies (default: the site)."""
        x0, y0, x1, y1 = site
        asset = Asset(len(self.assets), kind, name, x0, y0, x1 - x0, y1 - y0,
                      int(capacity), floors, street, parts or [])
        for cx0, cy0, cx1, cy1 in cells or [site]:
            self.aid[max(0, cy0):min(self.H, cy1), max(0, cx0):min(self.W, cx1)] = asset.id
        self.assets.append(asset)
        return asset

    def _house_number(self, street: str) -> int:
        n = self._house_numbers.get(street, 2 + 2 * int(self.rng.integers(0, 6)))
        self._house_numbers[street] = n + 2 + 2 * int(self.rng.random() < 0.3)
        return n

    def _shop_name(self) -> str:
        if not self._shop_names:
            self._shop_names = list(self.rng.permutation(_SHOPS))
        return str(self._shop_names.pop())

    # ---- build ------------------------------------------------------------
    def build(self) -> CityMap:
        """Run every construction step and return the finished town."""
        self._terrain()
        self._wildland()
        self._roads()
        self._river()
        self._blocks()
        self._road_assets()
        grid = Grid(self.W, self.H, fuel=self.fuel, moisture=self.moist, elevation=self.elev)
        return CityMap(grid, self.lu, self.aid, self.assets, self.station, self.town, self.seed)

    def _terrain(self) -> None:
        """Hills around a flat valley floor where the town sits."""
        raw = self.rng.random((self.H, self.W)).astype(np.float32)
        for _ in range(8):
            raw = _smooth(raw)
        raw = (raw - raw.min()) / (float(np.ptp(raw)) or 1.0)
        x0, y0, x1, y1 = self.town
        yy, xx = np.mgrid[0:self.H, 0:self.W]
        dx = np.maximum(np.maximum(x0 - xx, xx - (x1 - 1)), 0)
        dy = np.maximum(np.maximum(y0 - yy, yy - (y1 - 1)), 0)
        t = np.clip(np.hypot(dx, dy) / 10.0, 0.0, 1.0)
        blend = t * t * (3.0 - 2.0 * t)
        self.elev = (0.10 + blend * (0.15 + 0.75 * raw)).astype(np.float32)
        self._outside = blend > 0.0

    def _wildland(self) -> None:
        """Grass in the lowlands, shrub on the slopes, forest on the hills."""
        veg = self.rng.random((self.H, self.W)).astype(np.float32)
        for _ in range(4):
            veg = _smooth(veg)
        veg = (veg - veg.min()) / (float(np.ptp(veg)) or 1.0)
        v = 0.55 * self.elev + 0.45 * veg
        wild = self._outside
        q1, q2 = np.quantile(v[wild], [0.33, 0.62]) if wild.any() else (0.4, 0.6)
        fuel = np.full(v.shape, FuelType.GRASS, dtype=np.int8)
        fuel[v > q1] = FuelType.SHRUB
        fuel[v > q2] = FuelType.FOREST
        self.fuel[:] = fuel
        self.lu[:] = landuse_from_fuel(fuel)
        self.moist[:] = (0.08 + 0.17 * self.rng.random(v.shape)).astype(np.float32)

    def _roads(self) -> None:
        """Lay the street grid and highways, name the streets and record the blocks."""
        x0, y0, x1, y1 = self.town
        tw, th = x1 - x0, y1 - y0
        ncols = max(2, round((tw - 2) / 17))
        nrows = max(2, round((th - 2) / 9))
        self.vx = [x0 + round(i * (tw - 2) / ncols) for i in range(ncols + 1)]
        self.hy = [y0 + round(j * (th - 2) / nrows) for j in range(nrows + 1)]
        self.vw = [2] * (ncols + 1)
        self.hw = [2 if (j % 2 == 0 or j == nrows) else 1 for j in range(nrows + 1)]
        self.ncols, self.nrows = ncols, nrows

        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        inner_h = [j for j in range(1, nrows) if self.hw[j] == 2] or list(range(nrows + 1))
        self.main_j = min(inner_h, key=lambda j: abs(self.hy[j] + 1 - cy))
        inner_v = list(range(1, ncols)) or list(range(ncols + 1))
        self.main_i = min(inner_v, key=lambda i: abs(self.vx[i] + 1 - cx))

        h_names = list(self.rng.permutation(_H_NAMES))
        v_names = list(self.rng.permutation(_V_NAMES))
        self.h_names = [str(h_names[j % len(h_names)]) for j in range(nrows + 1)]
        self.v_names = [str(v_names[i % len(v_names)]) for i in range(ncols + 1)]
        self.h_names[self.main_j] = "Main St"
        self.v_names[self.main_i] = "Central Ave"

        for i, x in enumerate(self.vx):
            self._paint((x, y0, x + self.vw[i], y1), LandUse.ROAD, FuelType.NONE, 0.0)
        for j, y in enumerate(self.hy):
            self._paint((x0, y, x1, y + self.hw[j]), LandUse.ROAD, FuelType.NONE, 0.0)
        # Highways leave town along Main St (Hwy 9) and Central Ave (Ridge Rd).
        my, mx = self.hy[self.main_j], self.vx[self.main_i]
        self.highways = [
            ((0, my, x0, my + 2), "Hwy 9"), ((x1, my, self.W, my + 2), "Hwy 9"),
            ((mx, 0, mx + 2, y0), "Ridge Rd"), ((mx, y1, mx + 2, self.H), "Ridge Rd"),
        ]
        for rect, _ in self.highways:
            self._paint(rect, LandUse.ROAD, FuelType.NONE, 0.0)

        self.blocks: list[_Block] = []
        for j in range(nrows):
            by0, by1 = self.hy[j] + self.hw[j], self.hy[j + 1]
            for i in range(ncols):
                bx0, bx1 = self.vx[i] + self.vw[i], self.vx[i + 1]
                if bx1 - bx0 >= 6 and by1 - by0 >= 4:
                    self.blocks.append(_Block(bx0, by0, bx1, by1, j, i))

    def _river(self) -> None:
        """A river meanders through the hills south of town; roads cross on bridges."""
        y1 = self.town[3]
        gap = self.H - y1
        if gap < 6:
            return
        base = y1 + gap / 2.0
        amp = max(1.0, gap / 5.0)
        freq = float(self.rng.uniform(1.5, 2.5)) * 2.0 * math.pi / self.W
        phase = float(self.rng.uniform(0.0, 2.0 * math.pi))
        river = np.zeros(self.lu.shape, dtype=bool)
        for x in range(self.W):
            yc = base + amp * math.sin(freq * x + phase)
            for y in range(round(yc - 1), round(yc + 1) + 1):
                if 0 <= y < self.H and self.lu[y, x] != LandUse.ROAD:
                    river[y, x] = True
        self.lu[river] = LandUse.WATER
        self.fuel[river] = FuelType.NONE
        self.moist[river] = 1.0
        # Carve a shallow valley so the river sits below its banks.
        near = river.copy()
        for d in range(1, 4):
            grown = near.copy()
            grown[1:, :] |= near[:-1, :]
            grown[:-1, :] |= near[1:, :]
            grown[:, 1:] |= near[:, :-1]
            grown[:, :-1] |= near[:, 1:]
            ring = grown & ~near
            self.elev[ring] = np.minimum(self.elev[ring], 0.12 + 0.07 * d)
            near = grown
        self.elev[river] = np.minimum(self.elev[river], 0.08)

    # ---- blocks -----------------------------------------------------------
    def _blocks(self) -> None:
        """Give every block a use (homes, shops, schools, ...) and build its contents."""
        blocks = self.blocks
        tx0, ty0, tx1, ty1 = self.town
        cx, cy = (tx0 + tx1) / 2.0, (ty0 + ty1) / 2.0

        def dist(b: _Block) -> float:
            return math.hypot(b.center[0] - cx, b.center[1] - cy)

        order = sorted(blocks, key=dist)
        kind: dict[int, str] = {}   # id(block) -> kind
        n = len(blocks)

        def free(cands: list[_Block]) -> list[_Block]:
            return [b for b in cands if id(b) not in kind]

        def pick(cands: list[_Block], count: int, min_sep: float) -> list[_Block]:
            chosen: list[_Block] = []
            for b in cands:
                if all(math.hypot(b.center[0] - c.center[0], b.center[1] - c.center[1]) >= min_sep
                       for c in chosen):
                    chosen.append(b)
                    if len(chosen) == count:
                        break
            return chosen

        hospital = next((b for b in order if b.w >= 10 and b.h >= 6), order[0])
        kind[id(hospital)] = "hospital"

        main_rows = (self.main_j - 1, self.main_j)
        for b in free([b for b in order if b.row in main_rows])[:max(1, round(n / 7))]:
            kind[id(b)] = "commercial"

        edge_rows, edge_cols = (0, self.nrows - 1), (0, self.ncols - 1)
        outer = free([b for b in order if b.row in edge_rows or b.col in edge_cols])
        corners = [b for b in outer if b.row in edge_rows and b.col in edge_cols]
        battery_pool = corners or outer or free(order)
        if battery_pool:
            battery = battery_pool[int(self.rng.integers(len(battery_pool)))]
            kind[id(battery)] = "battery"

        max_d = max(dist(b) for b in blocks) or 1.0
        # Schools sit at a middle distance from the centre (a little randomness for variety).
        jitter = {id(b): float(self.rng.random()) * 4 for b in blocks}
        mid = sorted(free(order), key=lambda b: abs(dist(b) - 0.55 * max_d) + jitter[id(b)])
        for b in pick([b for b in mid if b.h >= 6] or mid, 2 if n >= 14 else 1, 18.0):
            kind[id(b)] = "school"
        park_pool = free(order)
        self.rng.shuffle(park_pool)
        for b in pick(park_pool, 2 if n >= 12 else 1, 16.0):
            kind[id(b)] = "park"
        for b in blocks:
            kind.setdefault(id(b), "residential")

        # Corner facilities carved out of residential/commercial blocks.
        reserved: dict[int, list[tuple[str, Rect]]] = {}
        host_kinds = ("residential", "commercial")

        def corner_rect(b: _Block, tx: float, ty: float, w: int = 5, h: int = 4) -> Rect:
            w, h = min(w, b.w), min(h, b.h)
            x = b.x0 if abs(b.x0 - tx) <= abs(b.x1 - tx) else b.x1 - w
            y = b.y0 if abs(b.y0 - ty) <= abs(b.y1 - ty) else b.y1 - h
            return (x, y, x + w, y + h)

        hosts = [b for b in order if kind[id(b)] in host_kinds]
        if hosts:
            fs = hosts[0]
            reserved.setdefault(id(fs), []).append(("fire_station", corner_rect(fs, cx, cy)))

        my = self.hy[self.main_j] + 1
        entries = [(float(tx0), float(my)), (float(tx1), float(my))]
        used = {id(hosts[0])} if hosts else set()
        for ex, ey in entries:
            cands = [b for b in blocks if kind[id(b)] in host_kinds and id(b) not in used]
            if not cands:
                break
            b = min(cands, key=lambda b: math.hypot(b.center[0] - ex, b.center[1] - ey))
            used.add(id(b))
            reserved.setdefault(id(b), []).append(("fuel_station", corner_rect(b, ex, ey)))

        school_names = list(self.rng.permutation(_SCHOOLS))
        park_names = list(self.rng.permutation(_PARKS))
        for b in blocks:
            k = kind[id(b)]
            res = [r for _, r in reserved.get(id(b), [])]
            if k == "residential":
                self._fill_residential(b, res)
            elif k == "commercial":
                self._fill_commercial(b, res)
            elif k == "school":
                self._fill_school(b, str(school_names.pop()))
            elif k == "hospital":
                self._fill_hospital(b, str(self.rng.choice(_HOSPITALS)))
            elif k == "park":
                self._fill_park(b, str(park_names.pop()), pond=len(park_names) % 2 == 1)
            elif k == "battery":
                self._fill_battery(b)
            for fk, rect in reserved.get(id(b), []):
                if fk == "fire_station":
                    self._fill_fire_station(rect)
                else:
                    self._fill_fuel_station(rect, self._facing_street(b, rect))

    def _facing_street(self, b: _Block, rect: Rect) -> str:
        return self.h_names[b.row] if rect[1] == b.y0 else self.h_names[b.row + 1]

    def _fill_residential(self, b: _Block, reserved: list[Rect]) -> None:
        self._paint((b.x0, b.y0, b.x1, b.y1), LandUse.LAWN, FuelType.GRASS, 0.45)
        hh = 2
        setback = 1 if b.h >= 8 else 0
        rows = [(b.y0 + setback, self.h_names[b.row])]
        if b.h >= 5:
            rows.append((b.y1 - setback - hh, self.h_names[b.row + 1]))
        for y, street in rows:
            x = b.x0 + int(self.rng.integers(0, 2))
            while x + 2 <= b.x1:
                hw = 3 if (self.rng.random() < 0.25 and x + 3 <= b.x1) else 2
                rect = (x, y, x + hw, y + hh)
                if not any(_overlaps(rect, r) for r in reserved) and self.rng.random() > 0.07:
                    self._add_house(rect, street)
                x += hw + 1 + int(self.rng.random() < 0.15)
        # Backyard trees and hedges (fuel that links one yard to the next).
        sub = (slice(b.y0, b.y1), slice(b.x0, b.x1))
        yard = self.lu[sub] == LandUse.LAWN
        r = self.rng.random(yard.shape)
        fuel = self.fuel[sub]
        fuel[yard & (r < 0.14)] = FuelType.FOREST
        fuel[yard & (r >= 0.14) & (r < 0.24)] = FuelType.SHRUB

    def _add_house(self, rect: Rect, street: str) -> None:
        floors = 1 if self.rng.random() < 0.6 else 2
        cap = int(self.rng.choice([1, 2, 3, 4, 5, 6], p=[0.12, 0.28, 0.22, 0.22, 0.11, 0.05]))
        self._paint(rect, LandUse.HOUSE, FuelType.STRUCTURE, 0.05)
        x0, y0, x1, y1 = rect
        self._add("house", f"{self._house_number(street)} {street}", rect, cap, floors=floors,
                  street=street, parts=[Part(x0, y0, x1 - x0, y1 - y0, float(floors), "house")])

    def _fill_commercial(self, b: _Block, reserved: list[Rect]) -> None:
        self._paint((b.x0, b.y0, b.x1, b.y1), LandUse.PAVED, FuelType.NONE, 0.0)
        depth = 3 if b.h >= 7 else 2
        rows = [(b.y0, self.h_names[b.row])]
        if b.h >= 2 * depth + 1:
            rows.append((b.y1 - depth, self.h_names[b.row + 1]))
        for y, street in rows:
            x = b.x0
            while x + 3 <= b.x1:
                sw = min(int(self.rng.integers(3, 5)), b.x1 - x)
                rect = (x, y, x + sw, y + depth)
                if not any(_overlaps(rect, r) for r in reserved):
                    floors = int(self.rng.choice([1, 2, 3], p=[0.45, 0.35, 0.20]))
                    fuel = FuelType.STRUCTURE if floors <= 2 else FuelType.MASONRY
                    self._paint(rect, LandUse.COMMERCIAL, fuel, 0.05)
                    self._add("commercial", f"{street} {self._shop_name()}", rect,
                              int(self.rng.integers(12, 61)), floors=floors, street=street,
                              parts=[Part(x, y, sw, depth, float(floors), "shop")])
                x += sw + int(self.rng.random() < 0.3)

    def _fill_school(self, b: _Block, name: str) -> None:
        self._paint((b.x0, b.y0, b.x1, b.y1), LandUse.LAWN, FuelType.GRASS, 0.50)
        mw, mh = min(b.w - 2, 10), (3 if b.h >= 7 else 2)
        my = b.y0 + 1 if b.h >= 7 else b.y0
        main = (b.x0 + 1, my, b.x0 + 1 + mw, my + mh)
        parts = [Part(main[0], main[1], mw, mh, 2.0, "school")]
        cells = [main]
        if b.h >= 7 and b.w >= 8:
            gym = (b.x1 - 5, b.y1 - 3, b.x1 - 1, b.y1 - 1)
            if not _overlaps(gym, main):
                parts.append(Part(gym[0], gym[1], 4, 2, 1.6, "gym"))
                cells.append(gym)
            self._paint((b.x0 + 1, b.y1 - 3, b.x0 + 4, b.y1 - 1), LandUse.PAVED, FuelType.NONE, 0.0)
        for rect in cells:
            self._paint(rect, LandUse.SCHOOL, FuelType.MASONRY, 0.05)
        self._add("school", name, (b.x0, b.y0, b.x1, b.y1), int(self.rng.integers(320, 681)),
                  floors=2, street=self.h_names[b.row], parts=parts, cells=cells)

    def _fill_hospital(self, b: _Block, name: str) -> None:
        self._paint((b.x0, b.y0, b.x1, b.y1), LandUse.PAVED, FuelType.NONE, 0.0)
        mw, mh = min(b.w - 4, 8), min(b.h - 2, 5)
        mx, my = b.x0 + 2, b.y0 + (b.h - mh) // 2
        main = (mx, my, mx + mw, my + mh)
        parts = [Part(mx, my, mw, mh, 5.0, "hospital")]
        cells = [main]
        if b.x1 - main[2] >= 4 and mh >= 3:
            wing = (main[2], my + 1, min(main[2] + 3, b.x1 - 1), my + mh - 1)
            parts.append(Part(wing[0], wing[1], wing[2] - wing[0], wing[3] - wing[1], 2.5, "wing"))
            cells.append(wing)
        for rect in cells:
            self._paint(rect, LandUse.HOSPITAL, FuelType.MASONRY, 0.05)
        self._add("hospital", name, (b.x0, b.y0, b.x1, b.y1), int(self.rng.integers(260, 461)),
                  floors=5, street=self.h_names[b.row], parts=parts, cells=cells)

    def _fill_park(self, b: _Block, name: str, pond: bool) -> None:
        site = (b.x0, b.y0, b.x1, b.y1)
        self._paint(site, LandUse.PARK, FuelType.GRASS, 0.40)
        sub = (slice(b.y0, b.y1), slice(b.x0, b.x1))
        yy, xx = np.mgrid[b.y0:b.y1, b.x0:b.x1]
        trees = np.zeros(yy.shape, dtype=bool)
        for _ in range(max(2, (b.w * b.h) // 25)):
            tx = self.rng.uniform(b.x0, b.x1)
            ty = self.rng.uniform(b.y0, b.y1)
            r = self.rng.uniform(1.2, 2.4)
            trees |= np.hypot(xx + 0.5 - tx, yy + 0.5 - ty) <= r
        trees &= self.rng.random(trees.shape) < 0.85
        self.fuel[sub][trees] = FuelType.FOREST
        midy, midx = (b.y0 + b.y1) // 2, (b.x0 + b.x1) // 2
        self._paint((b.x0, midy, b.x1, midy + 1), LandUse.PAVED, FuelType.NONE, 0.0)
        self._paint((midx, b.y0, midx + 1, b.y1), LandUse.PAVED, FuelType.NONE, 0.0)
        if pond and b.w >= 10 and b.h >= 6:
            pcx = b.x0 + b.w * 0.3
            pcy = b.y0 + b.h * 0.3
            rx, ry = max(1.5, b.w / 6.0), max(1.2, b.h / 5.0)
            water = ((xx + 0.5 - pcx) / rx) ** 2 + ((yy + 0.5 - pcy) / ry) ** 2 <= 1.0
            self.lu[sub][water] = LandUse.WATER
            self.fuel[sub][water] = FuelType.NONE
            self.moist[sub][water] = 1.0
        self._add("park", name, site, int(self.rng.integers(40, 141)), street=self.h_names[b.row])

    def _fill_battery(self, b: _Block) -> None:
        site = (b.x0, b.y0, b.x1, b.y1)
        self._paint(site, LandUse.GRASS, FuelType.GRASS, 0.15)   # dry grass around the fence
        pad = (b.x0 + 1, b.y0 + 1, b.x1 - 1, b.y1 - 1)
        self._paint(pad, LandUse.PAVED, FuelType.NONE, 0.0)
        parts: list[Part] = []
        cells: list[Rect] = []
        control = (pad[0], pad[1], pad[0] + 2, pad[1] + 2)
        self._paint(control, LandUse.BATTERY, FuelType.STRUCTURE, 0.05)
        parts.append(Part(control[0], control[1], 2, 2, 1.0, "kiosk"))
        cells.append(control)
        y = pad[1]
        while y + 1 <= pad[3] - 1:
            x = pad[0] + 3 if y < control[3] else pad[0]
            while x + 3 <= pad[2]:
                rect = (x, y, x + 3, y + 1)
                self._paint(rect, LandUse.BATTERY, FuelType.HAZMAT, 0.0)
                parts.append(Part(x, y, 3, 1, 1.0, "container"))
                cells.append(rect)
                x += 4
            y += 2
        self._add("battery_storage", "Ridgeview Battery Storage", site,
                  int(self.rng.integers(2, 5)), street=self.h_names[b.row],
                  parts=parts, cells=cells)

    def _fill_fuel_station(self, rect: Rect, street: str) -> None:
        x0, y0, x1, y1 = rect
        self._paint(rect, LandUse.PAVED, FuelType.NONE, 0.0)
        kiosk = (x0, y0, min(x0 + 2, x1), min(y0 + 2, y1))
        canopy = (max(x1 - 3, x0), max(y1 - 2, y0), x1, y1)
        self._paint(kiosk, LandUse.FUEL_STATION, FuelType.STRUCTURE, 0.05)
        self._paint(canopy, LandUse.FUEL_STATION, FuelType.HAZMAT, 0.0)
        def part(r: Rect, height: float, style: str) -> Part:
            return Part(r[0], r[1], r[2] - r[0], r[3] - r[1], height, style)

        parts = [part(kiosk, 1.0, "kiosk"), part(canopy, 1.3, "canopy")]
        self._add("fuel_station", f"{street} Fuel Station", rect, int(self.rng.integers(4, 13)),
                  street=street, parts=parts, cells=[kiosk, canopy])

    def _fill_fire_station(self, rect: Rect) -> None:
        x0, y0, x1, y1 = rect
        self._paint(rect, LandUse.PAVED, FuelType.NONE, 0.0)
        bw, bh = min(4, x1 - x0), min(3, y1 - y0)
        bld = (x0, y0, x0 + bw, y0 + bh)
        self._paint(bld, LandUse.FIRE_STATION, FuelType.MASONRY, 0.05)
        self._add("fire_station", "Fire Station 1", rect, int(self.rng.integers(8, 15)),
                  parts=[Part(x0, y0, bw, bh, 1.6, "firestation")], cells=[bld])
        self.station = (min(x0 + 1, x1 - 1), y1 - 1)

    def _road_assets(self) -> None:
        """Register road segments and 12-cell highway sections as ``road`` assets."""
        def capacity(rect: Rect, factor: float) -> int:
            cells = (rect[2] - rect[0]) * (rect[3] - rect[1])
            return max(2, round(cells * 0.45 * factor))

        busy = {"Main St": 1.6, "Central Ave": 1.6}
        for j, y in enumerate(self.hy):
            street = self.h_names[j]
            for i in range(self.ncols):
                x0 = self.vx[i]
                x1 = self.vx[i + 1] if i < self.ncols - 1 else self.vx[i + 1] + self.vw[i + 1]
                rect = (x0, y, x1, y + self.hw[j])
                cap = capacity(rect, busy.get(street, 1.0))
                self._add("road", street, rect, cap, street=street)
        for i, x in enumerate(self.vx):
            street = self.v_names[i]
            for j in range(self.nrows):
                y0, y1 = self.hy[j] + self.hw[j], self.hy[j + 1]
                if y1 > y0:
                    rect = (x, y0, x + self.vw[i], y1)
                    cap = capacity(rect, busy.get(street, 1.0))
                    self._add("road", street, rect, cap, street=street)
        for (x0, y0, x1, y1), street in self.highways:
            horizontal = (x1 - x0) >= (y1 - y0)
            length = (x1 - x0) if horizontal else (y1 - y0)
            for s in range(0, length, 12):
                e = min(length, s + 12)
                rect = (x0 + s, y0, x0 + e, y1) if horizontal else (x0, y0 + s, x1, y0 + e)
                if rect[2] > rect[0] and rect[3] > rect[1]:
                    self._add("road", street, rect, capacity(rect, 0.8), street=street)
