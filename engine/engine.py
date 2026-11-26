"""The simulation engine (Epic E1).

Advances the fire one discrete tick at a time. Its lifecycle (Idle -> Running
<-> Paused -> Completed) matches the simulation state-machine diagram, and a
seeded RNG makes every run reproducible.
"""
from __future__ import annotations

from enum import StrEnum
from typing import Protocol

import numpy as np

from .cell import FUEL_BURN_RATE, CellState
from .grid import Grid
from .map_gen import MapGenerator
from .scenario import Scenario
from .spread import PhysicsSpreadModel, SpreadModel
from .wind import Wind


class SimState(StrEnum):
    """Lifecycle state of a ``SimulationEngine``.

    The values are lowercase strings (e.g. ``"running"``), as reported to API clients.

    Attributes:
        IDLE: Just created or reset; waiting to start.
        RUNNING: Playing; ``run()`` advances ticks only in this state.
        PAUSED: Paused by ``pause()`` or after a single ``step()``.
        COMPLETED: The fire is out (no burning or igniting cell after a tick) or the run was
            ended with ``stop()``; only ``reset()`` leaves this state.
    """
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"


class TickObserver(Protocol):
    """Something that reacts to the engine's tick loop (GoF Observer).

    ``before_tick`` runs at the start of every tick (it may queue suppression),
    ``after_tick`` after the fire has advanced, and ``on_reset`` after a reset.
    The engine never needs to know what the observer is (e.g. the city layer).
    """

    def before_tick(self, engine: SimulationEngine) -> None:
        """React to the start of a tick, before the fire advances.

        Suppression queued here with ``engine.apply_suppression`` is applied in the same tick.

        Args:
            engine: The engine that is advancing.
        """
        ...

    def after_tick(self, engine: SimulationEngine) -> None:
        """React after the fire has advanced and ``engine.tick`` has been incremented.

        It runs before the engine checks whether the fire is out, so ``engine.state`` does
        not yet show that the fire went out during this tick.

        Args:
            engine: The engine that has advanced.
        """
        ...

    def on_reset(self, engine: SimulationEngine) -> None:
        """React to the engine being reset to its initial condition.

        Args:
            engine: The engine that was reset.
        """
        ...


class SimulationEngine:
    """Seeded, fixed-step fire simulation on a ``Grid``.

    Each ``advance()`` moves the fire one tick using a ``SpreadModel`` strategy (default
    ``PhysicsSpreadModel``) and a random generator seeded with ``seed``, so runs are
    reproducible. Registered ``TickObserver`` objects are notified before and after every
    tick and after a reset (Observer). Playback follows the ``SimState`` lifecycle.

    Attributes:
        grid: The grid being simulated; ``advance()`` updates its ``state`` and
            ``fuel_remaining``.
        wind: Wind used by the spread model.
        seed: Seed of the random generator; ``reset()`` re-seeds with it.
        spread_model: The ``SpreadModel`` strategy that gives per-cell ignition
            probabilities.
        publisher: Optional event publisher, or None. After every tick it receives
            ``publish_state_update(tick, counts)``, plus ``publish_extinguished(tick)`` when
            that tick leaves the engine ``COMPLETED``.
        tick: Number of ticks advanced since creation or the last ``reset()``.
        speed: Playback speed set by ``set_speed`` (0.25..16, default 1.0). The engine only
            stores it for clients that pace playback; it does not change ``advance()``.
        state: Current ``SimState`` (``IDLE`` at creation).
    """

    def __init__(
        self,
        grid: Grid,
        wind: Wind | None = None,
        *,
        seed: int = 0,
        spread_model: SpreadModel | None = None,
        publisher=None,
        snapshot_every: int = 0,
    ) -> None:
        """Create an engine in the ``IDLE`` state at tick 0.

        The grid's current cell states and remaining fuel are saved as the initial condition
        that ``reset()`` restores, and per-cell burn rates are looked up from ``grid.fuel``
        (``FUEL_BURN_RATE``) once, here.

        Args:
            grid: The grid to simulate; the engine modifies it in place.
            wind: Wind for the spread model; None means calm air (``Wind()``).
            seed: Seed for the random generator that decides which cells ignite.
            spread_model: Spread strategy; None means ``PhysicsSpreadModel()``.
            publisher: Optional object with ``publish_state_update(tick, counts)`` and
                ``publish_extinguished(tick)`` methods, such as ``messaging.EventPublisher``;
                None disables event publishing.
            snapshot_every: Publish a full-state ``SnapshotEvent`` every this many ticks (via
                ``publisher.publish_snapshot``) so a late-joining subscriber can resync; 0
                (default) disables periodic snapshots. It has no effect without a publisher.
        """
        self.grid = grid
        self.wind = wind or Wind()
        self.seed = seed
        self.spread_model = spread_model or PhysicsSpreadModel()
        self.publisher = publisher
        self.snapshot_every = snapshot_every
        self.tick = 0
        self.speed = 1.0
        self.state = SimState.IDLE
        self._rng = np.random.default_rng(seed)
        self._pending: list[tuple[int, int]] = []
        self._observers: list[TickObserver] = []
        self._burn_rate = np.zeros(grid.fuel.shape, dtype=np.float32)
        for ft, val in FUEL_BURN_RATE.items():
            self._burn_rate[grid.fuel == ft] = val
        self._save_initial()

    def add_observer(self, observer: TickObserver) -> None:
        """Register an observer of the tick loop.

        Observers are called in the order they were added.

        Args:
            observer: Object implementing ``TickObserver`` (for example ``CityModel``).
        """
        self._observers.append(observer)

    # ---- construction ---------------------------------------------------
    @classmethod
    def from_scenario(
        cls, sc: Scenario, *, publisher=None, snapshot_every: int = 0,
    ) -> SimulationEngine:
        """Build an engine for a wildland scenario.

        The map comes from ``MapGenerator`` (scenario size and seed) and the wind from the
        scenario, and every ignition point is set alight as part of the initial condition.
        The default spread model is used and the city settings are ignored; use
        ``create_session`` for city scenarios.

        Args:
            sc: The scenario; its ``width``, ``height``, ``seed``, wind and
                ``ignition_points`` are used.
            publisher: Optional event publisher (see the constructor).
            snapshot_every: Periodic snapshot interval in ticks (see the constructor).

        Returns:
            A new engine in the ``IDLE`` state at tick 0.
        """
        grid = MapGenerator.generate(sc.width, sc.height, sc.seed)
        eng = cls(grid, Wind(sc.wind_direction, sc.wind_speed), seed=sc.seed,
                  publisher=publisher, snapshot_every=snapshot_every)
        for p in sc.ignition_points:
            eng.ignite(p.x, p.y)
        return eng

    def _save_initial(self) -> None:
        """Save the current cell states and fuel as the condition ``reset()`` restores."""
        self._initial_state = self.grid.state.copy()
        self._initial_fuel = self.grid.fuel_remaining.copy()

    def ignite(self, x: int, y: int) -> None:
        """Set a cell alight as part of the initial condition.

        After ``Grid.ignite``, the whole current grid is saved as the condition ``reset()``
        restores, so call this before the first tick; use ``spot_fire`` once the run has
        started. Cells outside the grid or without fuel are not ignited.

        Args:
            x: Column index.
            y: Row index.
        """
        self.grid.ignite(x, y)
        self._save_initial()  # ignition points are part of the initial condition

    def spot_fire(self, x: int, y: int) -> None:
        """Start a new fire mid-run without changing the initial condition.

        Cells outside the grid or without fuel are not ignited (see ``Grid.ignite``).

        Args:
            x: Column index.
            y: Row index.
        """
        self.grid.ignite(x, y)

    # ---- playback controls ---------------------------------------------
    def start(self) -> None:
        """Start or resume the run.

        Moves ``IDLE`` or ``PAUSED`` to ``RUNNING``; does nothing in other states. It does
        not advance a tick by itself: call ``advance()`` or ``run()``.
        """
        if self.state in (SimState.IDLE, SimState.PAUSED):
            self.state = SimState.RUNNING

    def pause(self) -> None:
        """Pause the run.

        Moves ``RUNNING`` to ``PAUSED``; does nothing in other states.
        """
        if self.state == SimState.RUNNING:
            self.state = SimState.PAUSED

    def set_speed(self, speed: float) -> None:
        """Set the playback speed.

        Args:
            speed: Requested speed; converted to ``float`` and clamped to 0.25..16.
        """
        self.speed = max(0.25, min(16.0, float(speed)))

    def step(self) -> None:
        """Advance exactly one tick and settle in the Paused state.

        Does nothing once the run is ``COMPLETED``. If the fire goes out during this tick,
        the engine ends ``COMPLETED`` instead of ``PAUSED``.
        """
        if self.state == SimState.COMPLETED:
            return
        self.advance()
        if self.state == SimState.RUNNING:
            self.state = SimState.PAUSED
        elif self.state == SimState.IDLE:
            self.state = SimState.PAUSED

    def stop(self) -> None:
        """End the run now (e.g. the incident commander closes the incident).

        Sets the state to ``COMPLETED`` from any state; only ``reset()`` leaves it. No event
        is published.
        """
        self.state = SimState.COMPLETED

    def reset(self) -> None:
        """Restore the initial condition and return to ``IDLE`` at tick 0.

        Restores the cell states and remaining fuel saved at construction or by the last
        ``ignite()``, re-seeds the random generator with ``seed`` (so the fire replays the
        same way), drops queued suppression and then calls each observer's ``on_reset``.
        Wind and speed are kept.
        """
        self.grid.state = self._initial_state.copy()
        self.grid.fuel_remaining = self._initial_fuel.copy()
        self._rng = np.random.default_rng(self.seed)
        self._pending.clear()
        self.tick = 0
        self.state = SimState.IDLE
        for obs in self._observers:
            obs.on_reset(self)

    def apply_suppression(self, cells: list[tuple[int, int]]) -> None:
        """Queue suppression; applied on the next tick (reacts to other components).

        During the next ``advance()``, after the fire has spread and burned, each listed cell
        inside the grid that is unburned, igniting or burning becomes ``SUPPRESSED``; other
        cells are ignored.

        Args:
            cells: ``(x, y)`` cell coordinates; the values are converted to ``int``.
        """
        self._pending.extend((int(x), int(y)) for x, y in cells)

    # ---- the tick -------------------------------------------------------
    def advance(self) -> None:
        """Advance the simulation by one tick.

        The steps, in order:

        1. Call each observer's ``before_tick``.
        2. Turn ``IGNITING`` cells into ``BURNING``.
        3. Ask the spread model for ignition probabilities and set each ``UNBURNED`` cell to
           ``IGNITING`` when its random draw falls below its probability.
        4. Burn fuel in ``BURNING`` cells at their fuel's burn rate; cells with no fuel left
           become ``BURNED``.
        5. Apply queued suppression (see ``apply_suppression``).
        6. Increment ``tick`` and call each observer's ``after_tick``.
        7. Set the state to ``COMPLETED`` if no cell is burning or igniting.
        8. If a publisher is set, publish the tick's cell counts, a full-state snapshot every
           ``snapshot_every`` ticks (for resync), and, when the engine is ``COMPLETED``, the
           extinguished event.

        It does not check ``state``: callers such as ``run()`` and ``step()`` decide when to
        tick.
        """
        for obs in self._observers:
            obs.before_tick(self)
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
        for obs in self._observers:
            obs.after_tick(self)

        # 5. Completion when no fire remains.
        active = np.any((g.state == CellState.BURNING) | (g.state == CellState.IGNITING))
        if not active:
            self.state = SimState.COMPLETED

        if self.publisher is not None:
            self.publisher.publish_state_update(self.tick, g.counts())
            if self.snapshot_every and self.tick % self.snapshot_every == 0:
                self.publisher.publish_snapshot(self.tick, g.state.tolist())
            if self.state == SimState.COMPLETED:
                self.publisher.publish_extinguished(self.tick)

    def run(self, max_ticks: int = 10_000) -> int:
        """Run until the fire is out or max_ticks is reached; returns ticks run.

        An ``IDLE`` engine is started first. Ticks are advanced only while the state is
        ``RUNNING``, so a ``PAUSED`` or ``COMPLETED`` engine runs no ticks.

        Args:
            max_ticks: Maximum number of ticks to advance in this call.

        Returns:
            The number of ticks advanced by this call.
        """
        if self.state == SimState.IDLE:
            self.start()
        ran = 0
        while self.state == SimState.RUNNING and ran < max_ticks:
            self.advance()
            ran += 1
        return ran

    # ---- state ----------------------------------------------------------
    def counts(self) -> dict[str, int]:
        """Count the cells in each state.

        Returns:
            Same as ``Grid.counts``: each lowercase state name (``"unburned"``,
            ``"igniting"``, ``"burning"``, ``"burned"``, ``"suppressed"``) mapped to its
            number of cells.
        """
        return self.grid.counts()

    def snapshot(self) -> dict:
        """A Memento of the current state, for persistence / replay / resync.

        Returns:
            Dict with ``"tick"`` (the current tick) and ``"state"`` (the cell-state codes as
            nested lists: ``height`` rows of ``width`` ints).
        """
        return {"tick": self.tick, "state": self.grid.state.tolist()}
