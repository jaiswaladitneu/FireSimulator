"""City layer: people, risk and response on top of the fire grid.

``CityModel`` observes the engine (GoF Observer). After every tick it works out,
for every asset (building, park, road segment):

* its **status** — safe, threatened, burning, damaged, destroyed or blocked (roads);
* how far the nearest fire is;
* its **people** — still inside, evacuated, or casualties (estimated);
* a **priority score** so responders protect lives first, then hazards.

Before every tick it lets the fire crews act (their suppression is applied by the
engine in the same tick). Fuel stations explode the first time they burn, and
battery sites go into thermal runaway, both of which feed back into the fire.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from .cell import CellState, FuelType
from .city_gen import CELL_SIZE_M, CityMap
from .population import BUILDING_KINDS, KIND_INDEX, KINDS, NIGHT_HOURS, PROFILES, presence
from .response import ResponseManager

if TYPE_CHECKING:  # pragma: no cover
    from .engine import SimulationEngine
    from .grid import Grid

STATUS_NAMES = ["safe", "threatened", "burning", "damaged", "destroyed", "blocked"]
SAFE, THREATENED, BURNING, DAMAGED, DESTROYED, BLOCKED = range(6)
LEVELS = ["critical", "high", "medium", "low"]   # priority levels, most urgent first

HA_PER_CELL = (CELL_SIZE_M * CELL_SIZE_M) / 10_000.0
_HOUSE = KIND_INDEX["house"]
_ROAD = KIND_INDEX["road"]
_PARK = KIND_INDEX["park"]
_BUILDING_IDX = [KIND_INDEX[k] for k in BUILDING_KINDS]
_CRITICAL_KINDS = {KIND_INDEX[k] for k in ("school", "hospital", "fuel_station", "battery_storage")}


def _dilate(m: np.ndarray) -> np.ndarray:
    g = m.copy()
    g[1:, :] |= m[:-1, :]
    g[:-1, :] |= m[1:, :]
    g[:, 1:] |= m[:, :-1]
    g[:, :-1] |= m[:, 1:]
    g[1:, 1:] |= m[:-1, :-1]
    g[1:, :-1] |= m[:-1, 1:]
    g[:-1, 1:] |= m[1:, :-1]
    g[:-1, :-1] |= m[1:, 1:]
    return g


def chebyshev_distance(mask: np.ndarray, max_d: int) -> np.ndarray:
    """Distance (in cells, 8-neighbour steps) to the nearest True cell, capped at max_d + 1."""
    dist = np.full(mask.shape, max_d + 1, dtype=np.int16)
    if not mask.any():
        return dist
    dist[mask] = 0
    reached = mask.copy()
    frontier = mask
    for d in range(1, max_d + 1):
        new = _dilate(frontier) & ~reached
        if not new.any():
            break
        dist[new] = d
        reached |= new
        frontier = new
    return dist


def _plural(n: int, word: str, plural: str | None = None) -> str:
    return f"{n} {word if n == 1 else (plural or word + 's')}"


def _downsample(rows: list[dict], limit: int) -> list[dict]:
    if len(rows) <= limit:
        return list(rows)
    step = len(rows) / float(limit - 1)
    picked = [rows[min(len(rows) - 1, round(i * step))] for i in range(limit - 1)]
    return picked + [rows[-1]]


class CityModel:
    ALERT_R = 8      # evacuation is ordered when fire comes this close (cells)
    THREAT_R = 6     # asset counts as threatened within this distance
    D_MAX = 12       # distances beyond this are not tracked
    EXPLOSION_R = 3  # cells set alight around an exploding fuel station
    CREW_EVAC_BOOST = 0.15   # extra evacuation rate while a crew works at the asset
    RESCUE_RATE = 0.30       # share of people needing help that a crew gets out per tick
    MAX_EVENTS = 400

    def __init__(self, city: CityMap, *, hour: int = 14, crews: int = 4,
                 auto_dispatch: bool = False, seed: int = 0) -> None:
        self.map = city
        self.assets = city.assets
        self.asset_id = city.asset_id
        self.hour = int(hour) % 24
        self.n = n = len(self.assets)
        self.kind = np.array([KIND_INDEX[a.kind] for a in self.assets], dtype=np.int16)

        def per_kind(attr: str) -> np.ndarray:
            table = np.array([getattr(PROFILES[k], attr) for k in KINDS], dtype=np.float64)
            return table[self.kind]

        self.vuln = per_kind("vulnerability")
        self.evac_rate = per_kind("evac_rate")
        self.harm_rate = per_kind("harm_rate")
        self.hazard = per_kind("hazard")
        self.trapped_fraction = per_kind("trapped_fraction")
        self.capacity = np.array([a.capacity for a in self.assets], dtype=np.int64)
        pres = np.array([presence(a.kind, self.hour) for a in self.assets], dtype=np.float64)
        rng = np.random.default_rng(int(seed) * 7919 + self.hour)
        self.occ0 = rng.binomial(self.capacity, pres).astype(np.int64)
        # People who cannot leave without help, and how long each asset takes to react.
        self.stay0 = rng.binomial(self.occ0, per_kind("stay_fraction")).astype(np.int64)
        self.delay = per_kind("delay").astype(np.int64)
        if self.hour in NIGHT_HOURS:
            self.delay[self.kind == _HOUSE] *= 2

        flat = city.asset_id.ravel()
        self._valid = flat >= 0
        self._ids = flat[self._valid]
        fuel = city.grid.fuel.ravel()[self._valid]
        self._hazmat_cell = fuel == FuelType.HAZMAT
        self.burnable = np.bincount(self._ids[fuel != FuelType.NONE], minlength=n)
        self.has_fuel = self.burnable > 0
        self.is_fuel_station = self.kind == KIND_INDEX["fuel_station"]
        self.is_battery = self.kind == KIND_INDEX["battery_storage"]
        self.is_building = np.isin(self.kind, _BUILDING_IDX)
        self.centers = np.array([a.center for a in self.assets], dtype=np.float64).reshape(n, 2)
        self.response = ResponseManager(crews, city.station, auto_dispatch)
        self.engine: SimulationEngine | None = None
        self._reset_state()

    # ---- lifecycle --------------------------------------------------------
    def attach(self, engine: SimulationEngine) -> None:
        self.engine = engine
        engine.add_observer(self)
        self._update(engine.grid, advance=False)

    def _reset_state(self) -> None:
        n = self.n
        self.occ = self.occ0.copy()
        self.stay = self.stay0.copy()
        self.evac = np.zeros(n, dtype=np.int64)
        self.cas = np.zeros(n, dtype=np.int64)
        self.alerted = np.zeros(n, dtype=bool)
        self.alert_tick = np.full(n, -1, dtype=np.int64)
        self.needs_rescue = np.zeros(n, dtype=np.int64)
        self._announced_streets: set[str] = set()
        self._cas_pending = np.zeros(n, dtype=np.int64)          # casualties not yet reported
        self._house_pending = {"fire": 0, "destroyed": 0}       # house counts not yet reported
        self.status = np.zeros(n, dtype=np.int8)
        self.dist = np.full(n, self.D_MAX + 1, dtype=np.int16)
        self.n_burning = np.zeros(n, dtype=np.int64)
        self.burn_frac = np.zeros(n, dtype=np.float64)
        self.burned_frac = np.zeros(n, dtype=np.float64)
        self.at_risk = np.zeros(n, dtype=np.int64)
        self.exploded = np.zeros(n, dtype=bool)
        self.hazmat_fired = np.zeros(n, dtype=bool)
        self.events: list[dict] = []
        self.timeline: list[dict] = []
        self.priorities: list[dict] = []
        self.peak_at_risk = 0
        self.peak_burning_buildings = 0
        self.active_cells = 0
        self.burned_cells = 0
        self.response.reset()

    # ---- engine observer hooks ----------------------------------------------
    def before_tick(self, engine: SimulationEngine) -> None:
        cells = self.response.step(self, engine.grid)
        if cells:
            engine.apply_suppression(cells)

    def after_tick(self, engine: SimulationEngine) -> None:
        self._update(engine.grid, advance=True)

    def on_reset(self, engine: SimulationEngine) -> None:
        self._reset_state()
        self._update(engine.grid, advance=False)

    # ---- commands ------------------------------------------------------------
    def refresh(self) -> None:
        """Recompute statuses and priorities without advancing time (e.g. after a new ignition)."""
        if self.engine is not None:
            self._update(self.engine.grid, advance=False)

    def dispatch(self, asset_id: int):
        if not 0 <= asset_id < self.n:
            raise IndexError("unknown asset")
        return self.response.dispatch(asset_id, self)

    def set_auto_dispatch(self, enabled: bool) -> None:
        self.response.auto = bool(enabled)
        state = "enabled" if enabled else "disabled"
        self.log("auto", f"Automatic dispatch {state}", None, "info")

    # ---- helpers ---------------------------------------------------------------
    @property
    def tick(self) -> int:
        return self.engine.tick if self.engine is not None else 0

    def clock(self, tick: int | None = None) -> str:
        minutes = self.hour * 60 + (self.tick if tick is None else tick)
        return f"{(minutes // 60) % 24:02d}:{minutes % 60:02d}"

    def log(self, kind: str, message: str, asset_id: int | None, severity: str) -> None:
        self.events.append({
            "tick": self.tick, "clock": self.clock(), "type": kind, "message": message,
            "asset_id": asset_id, "severity": severity,
        })
        if len(self.events) > self.MAX_EVENTS:
            del self.events[: len(self.events) - self.MAX_EVENTS]

    # ---- the per-tick update -----------------------------------------------------
    def _update(self, grid: Grid, *, advance: bool) -> None:
        n = self.n
        state = grid.state
        active = (state == CellState.IGNITING) | (state == CellState.BURNING)
        sflat = state.ravel()[self._valid]
        aflat = active.ravel()[self._valid]
        ids = self._ids

        n_burning = np.bincount(ids[aflat], minlength=n)
        n_burned = np.bincount(ids[sflat == CellState.BURNED], minlength=n)
        hz_burning = np.bincount(ids[aflat & self._hazmat_cell], minlength=n)
        dfield = chebyshev_distance(active, self.D_MAX)
        dist = np.full(n, self.D_MAX + 1, dtype=np.int16)
        np.minimum.at(dist, ids, dfield.ravel()[self._valid])

        denom = np.maximum(self.burnable, 1)
        burn_frac = n_burning / denom
        burned_frac = n_burned / denom
        status = np.full(n, SAFE, dtype=np.int8)
        status[dist <= self.THREAT_R] = THREATENED
        status[~self.has_fuel & (dist <= 1)] = BLOCKED
        status[self.has_fuel & (burned_frac > 0)] = DAMAGED
        status[self.has_fuel & (burned_frac >= 0.5)] = DESTROYED
        status[n_burning > 0] = BURNING

        prev = self.status
        harm = np.zeros(n, dtype=np.int64)
        lost = np.zeros(n, dtype=bool)
        newly_alerted = np.zeros(n, dtype=bool)
        if advance:
            helped = np.zeros(n, dtype=bool)
            for t in self.response.working_targets():
                helped[t] = True
            alert_now = (dist <= self.ALERT_R) | (n_burning > 0)
            newly_alerted = alert_now & ~self.alerted & (self.occ > 0)
            self.alert_tick[alert_now & ~self.alerted] = self.tick
            self.alerted |= alert_now

            # Self-evacuation starts after the reaction delay; people who cannot
            # leave unaided are only got out by a crew working at the asset.
            evacuating = self.alerted & (self.occ > 0) & (status != DESTROYED)
            started = evacuating & (self.tick - self.alert_tick >= self.delay)
            rate = self.evac_rate + self.CREW_EVAC_BOOST * helped
            mobile = np.maximum(self.occ - self.stay, 0)
            out = np.where(started, np.minimum(mobile, np.ceil(mobile * rate)), 0).astype(np.int64)
            can_rescue = np.minimum(self.stay, np.ceil(self.stay * self.RESCUE_RATE))
            rescued = np.where(evacuating & helped, can_rescue, 0).astype(np.int64)
            self.stay -= rescued
            out += rescued
            self.occ -= out
            self.evac += out

            harm_frac = np.where(status == BURNING, self.harm_rate * burn_frac, 0.0)
            harm_frac += np.where(status == BLOCKED, self.harm_rate, 0.0)
            harm_frac *= np.where(helped, 0.5, 1.0)
            harm = np.floor(self.occ * harm_frac).astype(np.int64)

            # Fuel stations explode the first time their pumps or tanks burn.
            boom = self.is_fuel_station & (hz_burning > 0) & ~self.exploded
            for i in np.flatnonzero(boom):
                self.exploded[i] = True
                harm[i] += int(round((self.occ[i] - harm[i]) * 0.5))
                self._explode(grid, int(i))
            # Battery containers go into thermal runaway.
            runaway = self.is_battery & (hz_burning > 0) & ~self.hazmat_fired
            for i in np.flatnonzero(runaway):
                self.hazmat_fired[i] = True
                self.log("hazmat", f"Thermal runaway at {self.assets[i].name}: toxic smoke, "
                         "re-ignition risk. Shelter in place downwind.", int(i), "critical")
            self.hazmat_fired |= boom

            harm = np.minimum(harm, self.occ)
            self.occ -= harm
            self.cas += harm
            self.stay = np.minimum(self.stay, self.occ)

            lost = (status == DESTROYED) & (prev != DESTROYED) & (self.occ > 0)
            if lost.any():
                trapped = np.round(self.occ * self.trapped_fraction).astype(np.int64)
                self.cas[lost] += trapped[lost]
                self.evac[lost] += self.occ[lost] - trapped[lost]
                harm[lost] += trapped[lost]
                self.occ[lost] = 0
                self.stay[lost] = 0

        self.status = status
        self.dist = dist
        self.n_burning = n_burning
        self.burn_frac = burn_frac
        self.burned_frac = burned_frac
        self.active_cells = int(np.count_nonzero(active))
        self.burned_cells = int(np.count_nonzero(state == CellState.BURNED))

        at_risk_mask = ((dist <= self.ALERT_R) | (n_burning > 0)) & (status != DESTROYED)
        self.at_risk = np.where(at_risk_mask, self.occ, 0)
        self.needs_rescue = np.where(at_risk_mask, self.stay, 0)
        self._score(active)
        if advance:
            self._events(prev, status, newly_alerted, harm, lost)

        at_risk_total = int(self.at_risk.sum())
        bld_burning = int(np.count_nonzero(self.is_building & (status == BURNING)))
        self.peak_at_risk = max(self.peak_at_risk, at_risk_total)
        self.peak_burning_buildings = max(self.peak_burning_buildings, bld_burning)
        if self.timeline and self.timeline[-1]["t"] == self.tick:
            self.timeline.pop()   # a refresh at the same tick replaces that tick's row
        self.timeline.append({
            "t": self.tick,
            "burning": self.active_cells,
            "burned": self.burned_cells,
            "at_risk": at_risk_total,
            "casualties": int(self.cas.sum()),
            "evacuated": int(self.evac.sum()),
            "bld_burning": bld_burning,
            "bld_destroyed": int(np.count_nonzero(self.is_building & (status == DESTROYED))),
        })

    def _explode(self, grid: Grid, i: int) -> None:
        a = self.assets[i]
        r = self.EXPLOSION_R
        x0, y0 = max(0, a.x - r), max(0, a.y - r)
        x1, y1 = min(grid.width, a.x + a.w + r), min(grid.height, a.y + a.h + r)
        st = grid.state[y0:y1, x0:x1]
        catch = (st == CellState.UNBURNED) & (grid.fuel[y0:y1, x0:x1] != FuelType.NONE)
        st[catch] = CellState.IGNITING
        self.log("explosion", f"EXPLOSION at {a.name}: burning fuel thrown up to "
                 f"{r * CELL_SIZE_M} m, {int(catch.sum())} new spot fires", i, "critical")

    def _score(self, active: np.ndarray) -> None:
        dist = self.dist.astype(np.float64)
        burning_or_blocked = (self.n_burning > 0) | (self.status == BLOCKED)
        threat = np.clip((self.ALERT_R + 1 - dist) / (self.ALERT_R + 1), 0.0, 1.0)
        threat = np.where(burning_or_blocked, 1.0, threat)

        align = np.zeros(self.n)
        factor = np.ones(self.n)
        if self.engine is not None and active.any():
            ys, xs = np.nonzero(active)
            fx, fy = xs.mean() + 0.5, ys.mean() + 0.5
            we, wn = self.engine.wind.vector()
            ws = self.engine.wind.speed_norm
            vx = self.centers[:, 0] - fx
            vn = -(self.centers[:, 1] - fy)
            norm = np.hypot(vx, vn) + 1e-6
            align = (vx * we + vn * wn) / norm
            factor = 1.0 + 0.6 * ws * np.clip(align, 0.0, 1.0)

        alive = self.status != DESTROYED
        hazard = self.hazard * (~self.exploded) * alive
        # People who cannot self-evacuate count three times: only a crew can save them.
        lives = (self.at_risk + 2.0 * self.needs_rescue) * self.vuln
        score = threat * (lives + hazard) * factor * alive

        # Level first, then score: a burning home with someone inside always outranks
        # a merely threatened site, however large the site's score.
        on_fire_all = self.n_burning > 0
        hazard_close = (hazard > 0) & (self.dist <= 3)
        critical = (on_fire_all & (self.at_risk > 0)) | hazard_close | (score >= 250)
        level_code = np.where(critical, 0, np.where(score >= 80, 1, np.where(score >= 20, 2, 3)))
        cand = np.flatnonzero(score > 0)
        order = [int(i) for i in cand[np.lexsort((-score[cand], level_code[cand]))][:15]]

        crews_on: dict[int, list[str]] = {}
        for c in self.response.crews:
            if c.status != "available" and c.target is not None:
                crews_on.setdefault(c.target, []).append(c.name)

        items = []
        for i in order:
            a = self.assets[i]
            prof = PROFILES[a.kind]
            on_fire = bool(on_fire_all[i])
            level = LEVELS[int(level_code[i])]
            reasons = []
            if on_fire:
                reasons.append("On fire")
            elif self.status[i] == BLOCKED:
                reasons.append("Fire next to the road")
            else:
                reasons.append(f"Fire ~{int(self.dist[i]) * CELL_SIZE_M} m away")
            if self.at_risk[i] > 0:
                where = {"road": "in vehicles", "park": "in the park"}.get(a.kind, "inside")
                reasons.append(f"{_plural(int(self.at_risk[i]), 'person', 'people')} {where}")
                if self.needs_rescue[i] > 0:
                    reasons.append(f"{int(self.needs_rescue[i])} cannot evacuate without help")
                if prof.reason and a.kind not in ("road", "park", "house"):
                    reasons.append(prof.reason)
            elif prof.hazard > 0:
                reasons.append(prof.reason)
            if align[i] > 0.5:
                reasons.append("Downwind of the fire")
            items.append({
                "id": i, "kind": a.kind, "name": a.name, "status": STATUS_NAMES[self.status[i]],
                "level": level, "score": round(float(score[i]), 1), "at_risk": int(self.at_risk[i]),
                "needs_rescue": int(self.needs_rescue[i]),
                "distance_m": (int(self.dist[i]) * CELL_SIZE_M
                               if self.dist[i] <= self.D_MAX else None),
                "downwind": bool(align[i] > 0.5), "reasons": reasons, "crews": crews_on.get(i, []),
            })
        self.priorities = items

    def _events(self, prev: np.ndarray, status: np.ndarray, newly_alerted: np.ndarray,
                harm: np.ndarray, lost: np.ndarray) -> None:
        kind = self.kind
        houses = kind == _HOUSE
        roads = kind == _ROAD

        def named(mask: np.ndarray):
            return [int(i) for i in np.flatnonzero(mask & ~houses & ~roads)]

        def sev(i: int) -> str:
            return "critical" if int(kind[i]) in _CRITICAL_KINDS else "warning"

        # People on site when the alert went out = still inside + left during this tick.
        for i in named(newly_alerted):
            self.log("evacuation", f"Evacuation ordered: {self.assets[i].name} "
                     f"({int(self.occ[i] + self.evac[i])} people on site)", i, sev(i))
        h = newly_alerted & houses
        if h.any():
            residents = int(self.occ[h].sum() + self.evac[h].sum())
            self.log("evacuation", f"Evacuation ordered for {_plural(int(h.sum()), 'home')} "
                     f"({_plural(residents, 'resident')})", None, "warning")

        ignited = (status == BURNING) & (prev != BURNING) & (prev != DESTROYED)
        for i in named(ignited):
            self.log("fire", f"{self.assets[i].name} is on fire", i, "critical")
        destroyed = (status == DESTROYED) & (prev != DESTROYED)
        for i in named(destroyed):
            self.log("destroyed", f"{self.assets[i].name} destroyed", i, "critical")

        # House fires and losses are reported in 3-minute batches to keep the feed readable.
        pending = self._house_pending
        pending["fire"] += int((ignited & houses).sum())
        pending["destroyed"] += int((destroyed & houses).sum())
        if self.tick % 3 == 0:
            if pending["fire"]:
                self.log("fire", f"{_plural(pending['fire'], 'house')} caught fire",
                         None, "warning")
            if pending["destroyed"]:
                self.log("destroyed", f"{_plural(pending['destroyed'], 'house')} destroyed",
                         None, "critical")
            self._house_pending = {"fire": 0, "destroyed": 0}

        # Casualties: reported per site every 5 minutes, or at once if the site is lost
        # or the fire there ends.
        self._cas_pending += harm
        hot = np.where(roads, status == BLOCKED, status == BURNING)
        flush = (self._cas_pending > 0) & ((self.tick % 5 == 0) | lost | ~hot)

        def casualties(n: int) -> str:
            return _plural(int(n), "casualty", "casualties")

        for i in named(flush):
            self.log("casualties", f"{casualties(self._cas_pending[i])} (est.) at "
                     f"{self.assets[i].name}, {int(self.cas[i])} in total", i, "critical")
        for group, where in ((houses, "in burning homes"), (roads, "in vehicles cut off by fire")):
            g = flush & group
            if g.any():
                self.log("casualties", f"{casualties(self._cas_pending[g].sum())} (est.) {where}",
                         None, "critical")
        self._cas_pending[flush] = 0

        # Announce each street the first time fire cuts it.
        blocked = roads & (status == BLOCKED) & (prev != BLOCKED)
        for street in sorted({self.assets[i].street for i in np.flatnonzero(blocked)}):
            if street not in self._announced_streets:
                self._announced_streets.add(street)
                self.log("road", f"{street} blocked by fire", None, "warning")

    # ---- payloads ------------------------------------------------------------------
    def population(self) -> dict:
        danger = (self.status == BURNING) | (self.status == BLOCKED)
        return {
            "total": int(self.occ0.sum()),
            "present": int(self.occ.sum()),
            "at_risk": int(self.at_risk.sum()),
            "needs_rescue": int(self.needs_rescue.sum()),
            "in_danger": int(self.occ[danger].sum()),
            "evacuated": int(self.evac.sum()),
            "casualties": int(self.cas.sum()),
            "peak_at_risk": int(self.peak_at_risk),
        }

    def buildings(self) -> dict:
        b = self.is_building
        st = self.status
        return {
            "total": int(b.sum()),
            "threatened": int(np.count_nonzero(b & (st == THREATENED))),
            "burning": int(np.count_nonzero(b & (st == BURNING))),
            "damaged": int(np.count_nonzero(b & (st == DAMAGED))),
            "destroyed": int(np.count_nonzero(b & (st == DESTROYED))),
            "peak_burning": int(self.peak_burning_buildings),
        }

    def by_kind(self) -> dict:
        out = {}
        for k in KINDS:
            m = self.kind == KIND_INDEX[k]
            if not m.any():
                continue
            st = self.status[m]
            row = {"label": PROFILES[k].label, "total": int(m.sum())}
            for code, name in enumerate(STATUS_NAMES):
                row[name] = int(np.count_nonzero(st == code))
            row.update({
                "people": int(self.occ0[m].sum()),
                "present": int(self.occ[m].sum()),
                "at_risk": int(self.at_risk[m].sum()),
                "evacuated": int(self.evac[m].sum()),
                "casualties": int(self.cas[m].sum()),
            })
            out[k] = row
        return out

    def hazards(self) -> dict:
        return {
            "explosions": int(self.exploded.sum()),
            "battery_fires": int((self.hazmat_fired & self.is_battery).sum()),
        }

    def area_burned_ha(self) -> float:
        return round((self.burned_cells + self.active_cells) * HA_PER_CELL, 2)

    def static_payload(self) -> dict:
        g = self.map.grid
        assets = []
        for i, a in enumerate(self.assets):
            d = a.to_dict()
            d["occupants0"] = int(self.occ0[i])
            assets.append(d)
        return {
            "map_type": "city", "width": g.width, "height": g.height, "cell_size_m": CELL_SIZE_M,
            "landuse": self.map.landuse.tolist(), "fuel": g.fuel.tolist(),
            "elevation": np.round(g.elevation, 3).tolist(),
            "assets": assets,
            "station": {"x": self.map.station[0], "y": self.map.station[1]},
            "crews": [{"id": c.id, "name": c.name} for c in self.response.crews],
            "hour": self.hour,
            "kinds": {k: {"label": p.label, "vulnerability": p.vulnerability, "hazard": p.hazard}
                      for k, p in PROFILES.items()},
        }

    def dynamic_payload(self) -> dict:
        return {
            "clock": self.clock(), "hour": self.hour, "minutes": self.tick,
            "population": self.population(),
            "buildings": self.buildings(),
            "by_kind": self.by_kind(),
            "assets": {
                "status": self.status.tolist(),
                "occupants": self.occ.tolist(),
                "evacuated": self.evac.tolist(),
                "casualties": self.cas.tolist(),
                "at_risk": self.at_risk.tolist(),
                "needs_rescue": self.needs_rescue.tolist(),
                "burning": np.round(self.burn_frac, 2).tolist(),
                "burned": np.round(self.burned_frac, 2).tolist(),
                "dist": self.dist.tolist(),
            },
            "priorities": self.priorities,
            "crews": [c.to_dict() for c in self.response.crews],
            "crews_available": self.response.available(),
            "auto_dispatch": self.response.auto,
            "dispatches": self.response.dispatch_count,
            "cells_suppressed": self.response.cells_suppressed,
            "events": list(reversed(self.events[-40:])),
            "hazards": self.hazards(),
            "area_burned_ha": self.area_burned_ha(),
            "timeline": self.timeline[-1] if self.timeline else None,
        }

    def incident_summary(self) -> dict:
        """Everything the incident history keeps about this run."""
        critical = np.isin(self.kind, list(_CRITICAL_KINDS))
        destroyed = (self.status == DESTROYED) & self.is_building
        weight = self.cas * 1000 + destroyed * np.where(critical, 100, 1)
        order = np.argsort(-weight, kind="stable")
        losses = []
        for i in order[:8]:
            i = int(i)
            if self.cas[i] == 0 and self.status[i] != DESTROYED:
                continue
            losses.append({
                "name": self.assets[i].name, "kind": self.assets[i].kind,
                "casualties": int(self.cas[i]), "status": STATUS_NAMES[self.status[i]],
            })
        key = [e for e in self.events if e["severity"] == "critical"]
        return {
            "population": self.population(),
            "buildings": self.buildings(),
            "by_kind": self.by_kind(),
            "hazards": self.hazards(),
            "area_burned_ha": self.area_burned_ha(),
            "dispatches": self.response.dispatch_count,
            "cells_suppressed": self.response.cells_suppressed,
            "top_losses": losses[:5],
            "key_events": key[:60],
            "timeline": _downsample(self.timeline, 240),
        }
