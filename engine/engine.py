"""The simulation engine (Epic E1).

Advances the fire one discrete tick at a time. Its lifecycle (Idle -> Running
<-> Paused -> Completed) matches the simulation state-machine diagram, and a
seeded RNG makes every run reproducible.
"""
from __future__ import annotations

from enum import StrEnum

import numpy as np

from .cell import FUEL_BURN_RATE, CellState
from .grid import Grid
from .map_gen import MapGenerator
from .scenario import Scenario
from .spread import PhysicsSpreadModel, SpreadModel
from .wind import Wind


class SimState(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"


class SimulationEngine:
    def __init__(
        self,
        grid: Grid,
        wind: Wind | None = None,
        *,
        seed: int = 0,
        spread_model: SpreadModel | None = None,
        publisher=None,
    ) -> None:
        self.grid = grid
        self.wind = wind or Wind()
        self.seed = seed
        self.spread_model = spread_model or PhysicsSpreadModel()
        self.publisher = publisher
        self.tick = 0
        self.speed = 1.0
        self.state = SimState.IDLE
        self._rng = np.random.default_rng(seed)
        self._pending: list[tuple[int, int]] = []
        self._burn_rate = np.zeros(grid.fuel.shape, dtype=np.float32)
        for ft, val in FUEL_BURN_RATE.items():
            self._burn_rate[grid.fuel == ft] = val
        self._save_initial()

    # ---- construction ---------------------------------------------------
    @classmethod
    def from_scenario(cls, sc: Scenario, *, publisher=None) -> SimulationEngine:
        grid = MapGenerator.generate(sc.width, sc.height, sc.seed)
        eng = cls(grid, Wind(sc.wind_direction, sc.wind_speed), seed=sc.seed, publisher=publisher)
        for p in sc.ignition_points:
            eng.ignite(p.x, p.y)
        return eng

    def _save_initial(self) -> None:
        self._initial_state = self.grid.state.copy()
        self._initial_fuel = self.grid.fuel_remaining.copy()

    def ignite(self, x: int, y: int) -> None:
        self.grid.ignite(x, y)
        self._save_initial()  # ignition points are part of the initial condition

    # ---- playback controls ---------------------------------------------
    def start(self) -> None:
        if self.state in (SimState.IDLE, SimState.PAUSED):
            self.state = SimState.RUNNING

    def pause(self) -> None:
        if self.state == SimState.RUNNING:
            self.state = SimState.PAUSED

    def set_speed(self, speed: float) -> None:
        self.speed = max(0.25, min(16.0, float(speed)))

    def step(self) -> None:
        """Advance exactly one tick and settle in the Paused state."""
        if self.state == SimState.COMPLETED:
            return
        self.advance()
        if self.state == SimState.RUNNING:
            self.state = SimState.PAUSED
        elif self.state == SimState.IDLE:
            self.state = SimState.PAUSED

    def reset(self) -> None:
        self.grid.state = self._initial_state.copy()
        self.grid.fuel_remaining = self._initial_fuel.copy()
        self._rng = np.random.default_rng(self.seed)
        self._pending.clear()
        self.tick = 0
        self.state = SimState.IDLE

    def apply_suppression(self, cells: list[tuple[int, int]]) -> None:
        """Queue suppression; applied on the next tick (reacts to other components)."""
        self._pending.extend((int(x), int(y)) for x, y in cells)

    # ---- the tick -------------------------------------------------------
    def advance(self) -> None:
        g = self.grid

        # 1. Cells that started igniting last tick are now burning.
        g.state[g.state == CellState.IGNITING] = CellState.BURNING

        # 2. Burning cells spread to unburned neighbours.
        prob = self.spread_model.ignition_probability(g, self.wind)
        unburned = g.state == CellState.UNBURNED
        draws = self._rng.random(g.state.shape)
        g.state[unburned & (draws < prob)] = CellState.IGNITING

        # 3. Burning cells consume fuel; exhausted ones burn out.
        burning = g.state == CellState.BURNING
        g.fuel_remaining[burning] -= self._burn_rate[burning]
        g.state[burning & (g.fuel_remaining <= 0.0)] = CellState.BURNED

        # 4. Apply any queued suppression actions.
        for x, y in self._pending:
            if g.in_bounds(x, y) and g.state[y, x] in (
                CellState.UNBURNED, CellState.IGNITING, CellState.BURNING,
            ):
                g.state[y, x] = CellState.SUPPRESSED
        self._pending.clear()

        self.tick += 1

        # 5. Completion when no fire remains.
        active = np.any((g.state == CellState.BURNING) | (g.state == CellState.IGNITING))
        if not active:
            self.state = SimState.COMPLETED

        if self.publisher is not None:
            self.publisher.publish_state_update(self.tick, g.counts())
            if self.state == SimState.COMPLETED:
                self.publisher.publish_extinguished(self.tick)

    def run(self, max_ticks: int = 10_000) -> int:
        """Run until the fire is out or max_ticks is reached; returns ticks run."""
        if self.state == SimState.IDLE:
            self.start()
        ran = 0
        while self.state == SimState.RUNNING and ran < max_ticks:
            self.advance()
            ran += 1
        return ran

    # ---- state ----------------------------------------------------------
    def counts(self) -> dict[str, int]:
        return self.grid.counts()

    def snapshot(self) -> dict:
        """A Memento of the current state, for persistence / replay / resync."""
        return {"tick": self.tick, "state": self.grid.state.tolist()}
