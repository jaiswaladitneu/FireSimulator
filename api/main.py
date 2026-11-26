"""FastAPI application: scenario management and playback control (Epic E2).

This is the control surface other components and the UI use. It wraps the
simulation (a Facade over the engine and, for towns, the city layer) and keeps
scenarios in a repository. A single active session is held for simplicity.

City scenarios add the incident-command features: the town map, people at risk,
priorities, fire-crew dispatch, and an incident history (Epic E6) that records
every finished city incident for the admin dashboard.

Module state: ``scenarios`` keeps the saved scenarios in memory, and ``incidents`` keeps the
incident history in ``data/incidents.json`` under the repository folder (set the
``FIRESIM_INCIDENTS_FILE`` environment variable to use another file, or to an empty value or
``:memory:`` to keep it in memory). A re-entrant lock lets one request at a time touch the
live session. Every route is also served under ``/api`` (``ApiPrefixMiddleware``), and the
built UI is served from ``/`` when ``FIRESIM_STATIC_DIR`` names an existing folder
(``mount_ui``).
"""
from __future__ import annotations

import os
import threading
import time
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Literal

import numpy as np
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.types import ASGIApp, Receive, Scope, Send

from engine import Scenario, SimState
from engine.cell import FuelType
from engine.landuse import landuse_from_fuel
from engine.scenario import IgnitionPoint
from engine.session import Session, create_session
from messaging import TOPIC_SNAPSHOT, EventPublisher, InMemoryBus
from persistence import (
    IncidentRecord,
    InMemoryIncidentRepository,
    InMemoryScenarioRepository,
    InMemorySnapshotRepository,
    JsonFileIncidentRepository,
    JsonFileSnapshotRepository,
    ScenarioRecord,
    SnapshotArchiver,
)

app = FastAPI(title="Fire Simulator API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", "http://127.0.0.1:5173",   # Vite dev server
        "http://localhost:4173", "http://127.0.0.1:4173",   # Vite preview
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ApiPrefixMiddleware:
    """ASGI middleware that serves ``/api/<path>`` as ``/<path>``.

    The UI always calls the API under ``/api``. In development the Vite proxy strips
    the prefix; when this app serves the built UI itself (the Docker image), this
    middleware does the same, so one UI build works in both setups.

    Attributes:
        app: The wrapped ASGI application.
    """

    def __init__(self, app: ASGIApp) -> None:
        """Wrap an ASGI application.

        Args:
            app: The ASGI application to call with the rewritten request.
        """
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Strip a leading ``/api`` from HTTP request paths, then call the wrapped app.

        Args:
            scope: ASGI connection scope; ``path`` and ``raw_path`` are rewritten.
            receive: ASGI receive channel, passed through unchanged.
            send: ASGI send channel, passed through unchanged.
        """
        path = scope.get("path", "")
        if scope["type"] == "http" and (path == "/api" or path.startswith("/api/")):
            path = path[4:] or "/"
            scope = {**scope, "path": path, "raw_path": path.encode()}
        await self.app(scope, receive, send)


app.add_middleware(ApiPrefixMiddleware)


def _incident_repository():
    """JSON file by default (history survives restarts); ':memory:' for tests."""
    default = Path(__file__).resolve().parent.parent / "data" / "incidents.json"
    path = os.environ.get("FIRESIM_INCIDENTS_FILE", str(default))
    if path in ("", ":memory:"):
        return InMemoryIncidentRepository()
    return JsonFileIncidentRepository(path)


def _snapshot_repository():
    """In-memory by default; set ``FIRESIM_SNAPSHOTS_FILE`` to persist snapshots to a file."""
    path = os.environ.get("FIRESIM_SNAPSHOTS_FILE", "")
    if path in ("", ":memory:"):
        return InMemorySnapshotRepository()
    return JsonFileSnapshotRepository(path)


# How often the live run saves a full-state snapshot (ticks); 0 disables periodic snapshots.
SNAPSHOT_EVERY = int(os.environ.get("FIRESIM_SNAPSHOT_EVERY", "25"))

scenarios = InMemoryScenarioRepository()
incidents = _incident_repository()
snapshots = _snapshot_repository()
_session: Session | None = None
_started_at: float = 0.0
_recorded_id: str | None = None
_lock = threading.RLock()   # one request at a time touches the live session


class IgnitionPointIn(BaseModel):
    """A cell where the fire starts, as given in a scenario request.

    Attributes:
        x: Column index of the cell (x grows to the east).
        y: Row index of the cell (y grows to the south).
        tick: Tick of the ignition (default 0); it is stored with the scenario, but every
            point is ignited when the simulation is built.
    """
    x: int
    y: int
    tick: int = 0


class ScenarioIn(BaseModel):
    """Request body of ``POST /scenarios``: the parameters of a new scenario.

    Attributes:
        name: Display name of the scenario.
        width: Map width in cells (1 to 400, default 200; city maps need at least 48).
        height: Map height in cells (1 to 400, default 200; city maps need at least 48).
        seed: Random seed (default 0); the same parameters and seed reproduce the same run.
        wind_direction: Direction the wind blows toward, in degrees clockwise from north
            (default 90, east).
        wind_speed: Wind speed in km/h (default 15).
        ignition_points: Cells where the fire starts; points outside the map or with nothing
            to burn are ignored. A city scenario without any gets a default point upwind of
            the town.
        map_type: ``"wildland"`` (default) or ``"city"`` (a town with people and fire crews).
        hour: Local hour the incident starts (0 to 23, default 14); in city scenarios it
            drives how many people are in each building.
        crews: Number of fire crews (0 to 12, default 4); city scenarios only.
        auto_dispatch: Whether crews dispatch themselves to the top priorities from the start
            (default False); city scenarios only.
    """
    name: str
    width: int = Field(default=200, ge=1, le=400)
    height: int = Field(default=200, ge=1, le=400)
    seed: int = 0
    wind_direction: float = 90.0
    wind_speed: float = 15.0
    ignition_points: list[IgnitionPointIn] = Field(default_factory=list)
    map_type: Literal["wildland", "city"] = "wildland"
    hour: int = Field(default=14, ge=0, le=23)
    crews: int = Field(default=4, ge=0, le=12)
    auto_dispatch: bool = False


class SpeedIn(BaseModel):
    """Request body of ``POST /simulation/speed``.

    Attributes:
        speed: Playback speed, 0.25 to 16.0 (the UI requests this many ticks per second).
    """
    speed: float = Field(ge=0.25, le=16.0)


class CellIn(BaseModel):
    """A grid cell to ignite or suppress.

    Attributes:
        x: Column index (x grows to the east).
        y: Row index (y grows to the south).
    """
    x: int
    y: int


class SuppressIn(BaseModel):
    """Request body of ``POST /simulation/suppress``.

    Attributes:
        cells: Cells to suppress on the next tick (default: none).
    """
    cells: list[CellIn] = Field(default_factory=list)


class DispatchIn(BaseModel):
    """Request body of ``POST /simulation/dispatch``.

    Attributes:
        asset_id: Asset to protect: its ``id`` in the ``assets`` of ``GET /simulation/map``.
    """
    asset_id: int


class AutoDispatchIn(BaseModel):
    """Request body of ``POST /simulation/auto-dispatch``.

    Attributes:
        enabled: True to turn automatic crew dispatch on, False to turn it off.
    """
    enabled: bool


class BatchIn(BaseModel):
    """Request body of ``POST /incidents/simulate``: a batch of headless city incidents.

    Attributes:
        count: Number of incidents to run (1 to 20, default 5).
        size: Side of each square town map, in cells (48 to 128, default 80).
        max_ticks: Tick limit per run (50 to 3000, default 800); a run still burning at the
            limit is recorded with outcome ``"time_limit"``.
        seed: Seed for drawing the run conditions; None (default) draws new ones every time.
    """
    count: int = Field(default=5, ge=1, le=20)
    size: int = Field(default=80, ge=48, le=128)
    max_ticks: int = Field(default=800, ge=50, le=3000)
    seed: int | None = None


def _to_scenario(body: ScenarioIn) -> Scenario:
    """Convert a scenario request body into an engine ``Scenario`` with a new id."""
    return Scenario(
        name=body.name, width=body.width, height=body.height, seed=body.seed,
        wind_direction=body.wind_direction, wind_speed=body.wind_speed,
        ignition_points=[IgnitionPoint(p.x, p.y, p.tick) for p in body.ignition_points],
        map_type=body.map_type, hour=body.hour, crews=body.crews,
        auto_dispatch=body.auto_dispatch,
    )


def _build(sc: Scenario, *, publisher=None, snapshot_every: int = 0) -> Session:
    """Build a session for a scenario; a ``ValueError`` from the engine becomes HTTP 422.

    Args:
        sc: The scenario to build.
        publisher: Optional event publisher wired into the engine (see ``create_session``).
        snapshot_every: Periodic snapshot interval in ticks (see ``create_session``).
    """
    try:
        return create_session(sc, publisher=publisher, snapshot_every=snapshot_every)
    except ValueError as exc:   # e.g. a city map smaller than the minimum size
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _build_live(sc: Scenario) -> Session:
    """Build the live session with event publishing and snapshot archiving wired in.

    The engine publishes fire events on an in-memory bus and emits a full-state snapshot
    every ``SNAPSHOT_EVERY`` ticks; a ``SnapshotArchiver`` subscribed to the snapshot topic
    saves each one under the scenario id, so the live run's snapshots are kept for resync.

    Args:
        sc: The scenario to build.

    Returns:
        The live ``Session`` (its engine already wired to the bus and archiver).
    """
    bus = InMemoryBus()
    bus.subscribe(TOPIC_SNAPSHOT, SnapshotArchiver(snapshots, sc.id).handle)
    return _build(sc, publisher=EventPublisher(bus), snapshot_every=SNAPSHOT_EVERY)


@app.get("/health")
def health() -> dict:
    """Report that the API is up.

    A liveness check; it does not touch the simulation.

    \f
    Returns:
        ``{"status": "ok"}``.
    """
    return {"status": "ok"}


# ---- scenarios ----------------------------------------------------------
@app.post("/scenarios", status_code=201)
def create_scenario(body: ScenarioIn) -> dict:
    """Create a scenario and make it the active simulation.

    Builds the map and engine and replaces any previous live session; the new simulation
    starts idle at tick 0, and its run counts as a new incident. The scenario is also saved
    so it can be listed and replayed. A city scenario without ignition points gets a default
    ignition upwind of the town, and the saved scenario keeps the points actually used.

    \f
    Args:
        body: Parameters of the new scenario.

    Returns:
        ``{"id": <scenario id>, "name": <scenario name>}``, with status 201.

    Raises:
        HTTPException: 422 if the engine rejects the scenario, e.g. a city map with a side
            shorter than 48 cells; nothing is saved and the live session is kept.
    """
    global _session, _started_at, _recorded_id
    sc = _to_scenario(body)
    session = _build_live(sc)
    payload = body.model_dump()
    # Store the actual ignition points (a city scenario may have had a default chosen).
    payload["ignition_points"] = [asdict(p) for p in sc.ignition_points]
    with _lock:
        scenarios.save(ScenarioRecord(id=sc.id, name=sc.name, payload=payload))
        _session, _started_at, _recorded_id = session, time.time(), None
    return {"id": sc.id, "name": sc.name}


@app.get("/scenarios")
def list_scenarios() -> list[dict]:
    """List the saved scenarios.

    Scenarios are kept in memory, so the list starts empty after an API restart.

    \f
    Returns:
        One dict per scenario, in creation order, with ``id``, ``name`` and ``payload`` (the
        parameters the scenario was created with).
    """
    return [asdict(r) for r in scenarios.all()]


@app.get("/scenarios/{scenario_id}")
def get_scenario(scenario_id: str) -> dict:
    """Get one saved scenario.

    Returns its id, its name and the parameters it was created with.

    \f
    Args:
        scenario_id: Id returned by ``POST /scenarios``.

    Returns:
        The scenario as ``{"id", "name", "payload"}``.

    Raises:
        HTTPException: 404 if no scenario has this id.
    """
    rec = scenarios.find(scenario_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="scenario not found")
    return asdict(rec)


@app.delete("/scenarios/{scenario_id}", status_code=204)
def delete_scenario(scenario_id: str) -> None:
    """Delete a saved scenario.

    Only the saved record is removed; a live simulation built from it keeps running.
    Responds with 204 No Content.

    \f
    Args:
        scenario_id: Id of the scenario to delete.

    Raises:
        HTTPException: 404 if no scenario has this id.
    """
    if not scenarios.delete(scenario_id):
        raise HTTPException(status_code=404, detail="scenario not found")


@app.get("/scenarios/{scenario_id}/replay")
def replay_scenario(
    scenario_id: str,
    max_ticks: int = Query(default=2000, ge=1, le=10000),
) -> dict:
    """Deterministically replay a saved scenario and return its per-tick timeline.

    Runs are reproducible (seeded RNG + procedural map), so a saved scenario
    replays to the exact same sequence of states without the original live
    session. Each frame is the cell-state counts at that tick (plus people and
    buildings for city scenarios).

    The replay uses only the saved parameters (including ignitions added before the first
    tick); spot fires, dispatches, suppression and auto-dispatch changes made during the
    live run are not replayed.

    \f
    Args:
        scenario_id: Id of the saved scenario.
        max_ticks: Maximum number of ticks to simulate (1 to 10000, default 2000).

    Returns:
        A dict with ``scenario_id``; ``ticks`` (ticks simulated); ``final_state``
        (``"completed"`` if the fire went out, ``"running"`` if ``max_ticks`` was reached
        first); and ``frames``, one for each tick from 0 to ``ticks``, each with ``tick`` and
        ``counts`` (cells per state) plus, for city scenarios, ``city`` with ``at_risk``,
        ``casualties``, ``evacuated`` and ``buildings_destroyed``.

    Raises:
        HTTPException: 404 if no scenario has this id; 422 if the engine rejects the saved
            scenario.
    """
    rec = scenarios.find(scenario_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="scenario not found")
    session = _build(_to_scenario(ScenarioIn(**rec.payload)))
    eng, city = session.engine, session.city

    def frame() -> dict:
        f = {"tick": eng.tick, "counts": eng.counts()}
        if city is not None:
            p, b = city.population(), city.buildings()
            f["city"] = {"at_risk": p["at_risk"], "casualties": p["casualties"],
                         "evacuated": p["evacuated"], "buildings_destroyed": b["destroyed"]}
        return f

    frames = [frame()]
    eng.start()
    while eng.state == SimState.RUNNING and eng.tick < max_ticks:
        eng.advance()
        frames.append(frame())
    return {
        "scenario_id": scenario_id,
        "ticks": eng.tick,
        "final_state": eng.state.value,
        "frames": frames,
    }


@app.get("/scenarios/{scenario_id}/snapshots")
def list_snapshots(scenario_id: str, full: bool = Query(default=False)) -> dict:
    """List the full-state snapshots saved for a scenario during its live run.

    The live run saves a snapshot every ``SNAPSHOT_EVERY`` ticks (Epic E6), so a client can
    see the saved resync points for a scenario and, with ``full=true``, fetch their grid
    states.

    \f
    Args:
        scenario_id: Id of the scenario whose snapshots to list.
        full: When true, include each snapshot's ``state`` (``height`` rows of cell-state
            codes); when false (default) return only ``tick`` and ``timestamp``.

    Returns:
        ``{"scenario_id", "count", "snapshots"}`` where each snapshot has ``tick`` and
        ``timestamp`` (and ``state`` when ``full`` is true), ordered by tick.
    """
    with _lock:
        saved = snapshots.find_by_scenario(scenario_id)
    out = []
    for s in saved:
        row = {"tick": s.tick, "timestamp": s.timestamp}
        if full:
            row["state"] = s.state
        out.append(row)
    return {"scenario_id": scenario_id, "count": len(out), "snapshots": out}


# ---- playback -----------------------------------------------------------
def _require_session() -> Session:
    """Return the active session; raise HTTP 409 if no scenario has been created yet."""
    if _session is None:
        raise HTTPException(status_code=409, detail="no active scenario; create one first")
    return _session


def _require_city(session: Session):
    """Return the session's city layer; raise HTTP 409 if it is a wildland scenario."""
    if session.city is None:
        raise HTTPException(status_code=409, detail="the active scenario is not a city scenario")
    return session.city


@app.post("/simulation/play")
def play() -> dict:
    """Start or resume the active simulation.

    An idle or paused simulation becomes running; in any other state nothing changes.
    Playing does not advance time by itself: each ``POST /simulation/tick`` then advances
    one tick.

    \f
    Returns:
        The live state payload (same shape as ``GET /simulation/state``).

    Raises:
        HTTPException: 409 if there is no active scenario.
    """
    with _lock:
        s = _require_session()
        s.engine.start()
        return _state_payload(s)


@app.post("/simulation/pause")
def pause() -> dict:
    """Pause the active simulation.

    A running simulation becomes paused; in any other state nothing changes.

    \f
    Returns:
        The live state payload (same shape as ``GET /simulation/state``).

    Raises:
        HTTPException: 409 if there is no active scenario.
    """
    with _lock:
        s = _require_session()
        s.engine.pause()
        return _state_payload(s)


@app.post("/simulation/step")
def step() -> dict:
    """Advance the active simulation by exactly one tick and leave it paused.

    Works from idle, paused or running and does nothing once the incident is completed. If
    the fire goes out on this tick the simulation completes instead, and a city incident is
    recorded in the incident history.

    \f
    Returns:
        The live state payload (same shape as ``GET /simulation/state``).

    Raises:
        HTTPException: 409 if there is no active scenario.
    """
    with _lock:
        s = _require_session()
        s.engine.step()
        _maybe_record(s)
        return _state_payload(s)


@app.post("/simulation/tick")
def tick() -> dict:
    """Advance the active simulation by one tick if it is running.

    Clients call this repeatedly to play the simulation (the UI paces the calls by the
    playback speed); when the simulation is not running nothing changes. When the fire goes
    out, a city incident is recorded in the incident history.

    \f
    Returns:
        The live state payload (same shape as ``GET /simulation/state``).

    Raises:
        HTTPException: 409 if there is no active scenario.
    """
    with _lock:
        s = _require_session()
        if s.engine.state == SimState.RUNNING:
            s.engine.advance()
            _maybe_record(s)
        return _state_payload(s)


@app.post("/simulation/reset")
def reset() -> dict:
    """Reset the active simulation to its initial condition.

    Goes back to tick 0 in the idle state with the starting fire (including ignitions added
    before the first tick) and re-seeds the random generator; spot fires and queued
    suppression are discarded. City scenarios also reset people, crews and the event log.
    The next run is recorded as a new incident.

    \f
    Returns:
        The live state payload (same shape as ``GET /simulation/state``).

    Raises:
        HTTPException: 409 if there is no active scenario.
    """
    global _started_at, _recorded_id
    with _lock:
        s = _require_session()
        s.engine.reset()
        _started_at, _recorded_id = time.time(), None
        return _state_payload(s)


@app.post("/simulation/speed")
def speed(body: SpeedIn) -> dict:
    """Set the playback speed of the active simulation.

    The value is stored and reported as ``speed`` in the state payload. The server does not
    advance time on its own; the UI uses the speed as the number of ticks to request per
    second.

    \f
    Args:
        body: The new speed (0.25 to 16.0).

    Returns:
        The live state payload (same shape as ``GET /simulation/state``).

    Raises:
        HTTPException: 409 if there is no active scenario.
    """
    with _lock:
        s = _require_session()
        s.engine.set_speed(body.speed)
        return _state_payload(s)


@app.get("/simulation/state")
def state() -> dict:
    """Get the live state of the active simulation.

    Every ``/simulation`` endpoint except ``GET /simulation/map`` returns this same payload.

    \f
    Returns:
        A dict with ``state`` (``"idle"``, ``"running"``, ``"paused"`` or ``"completed"``),
        ``tick``, ``speed``, ``counts`` (number of cells per state: ``unburned``,
        ``igniting``, ``burning``, ``burned``, ``suppressed``), ``grid`` (``height`` rows of
        ``width`` cell-state codes: 0 unburned, 1 igniting, 2 burning, 3 burned,
        4 suppressed), ``map_type``, ``scenario`` (``id`` and ``name``), ``wind``
        (``direction`` the wind blows toward, in degrees from north, and ``speed`` in km/h),
        ``incident_id`` (id of this run's history record, or None until it is recorded) and
        ``city`` (for city scenarios the town's dynamic state: clock, population and
        building totals, per-asset arrays, priorities, crews, recent events and hazards;
        None for wildland).

    Raises:
        HTTPException: 409 if there is no active scenario.
    """
    with _lock:
        return _state_payload(_require_session())


@app.get("/simulation/resync")
def resync() -> dict:
    """Return the latest full-state snapshot of the active simulation, for a late join.

    A client that connects or reconnects mid-run uses this to resync to the current fire
    without replaying from the start. It returns the newest snapshot saved during the run (one
    is saved every ``SNAPSHOT_EVERY`` ticks); before the first one is saved it falls back to
    the engine's current state, so it always returns a usable grid.

    \f
    Returns:
        A dict with ``scenario`` (``id`` and ``name``), ``tick``, ``state`` (``height`` rows
        of cell-state codes, same coding as ``GET /simulation/state``'s ``grid``) and
        ``source`` (``"snapshot"`` for a saved snapshot, ``"live"`` for the engine fallback).

    Raises:
        HTTPException: 409 if there is no active scenario.
    """
    with _lock:
        s = _require_session()
        saved = snapshots.find_by_scenario(s.scenario.id)
        scenario = {"id": s.scenario.id, "name": s.scenario.name}
        if saved:
            latest = saved[-1]
            return {"scenario": scenario, "tick": latest.tick, "state": latest.state,
                    "source": "snapshot"}
        snap = s.engine.snapshot()
        return {"scenario": scenario, "tick": snap["tick"], "state": snap["state"],
                "source": "live"}


@app.get("/simulation/map")
def simulation_map() -> dict:
    """The static map (land use, fuel, elevation, assets). Fetch once per scenario.

    Wildland maps have no assets, fire station, crews or asset kinds, and their land use is
    derived from the fuel layer.

    \f
    Returns:
        A dict with ``map_type``, ``width``, ``height``, ``cell_size_m`` (10), ``landuse``,
        ``fuel`` and ``elevation`` (``height`` rows of ``width`` values: land-use codes,
        fuel codes and elevation rounded to 3 decimals), ``assets`` (one dict per building,
        park or road segment with ``id``, ``kind``, ``name``, ``street``, ``x``, ``y``,
        ``w``, ``h``, ``floors``, ``capacity``, ``parts`` and ``occupants0``, the people
        present at the start), ``station`` (``{"x", "y"}`` of the fire station, or None),
        ``crews`` (``id`` and ``name`` of each crew), ``hour`` and ``kinds`` (label,
        vulnerability and hazard of each asset kind).

    Raises:
        HTTPException: 409 if there is no active scenario.
    """
    with _lock:
        s = _require_session()
        if s.city is not None:
            return s.city.static_payload()
        g = s.engine.grid
        return {
            "map_type": "wildland", "width": g.width, "height": g.height, "cell_size_m": 10,
            "landuse": landuse_from_fuel(g.fuel).tolist(), "fuel": g.fuel.tolist(),
            "elevation": np.round(g.elevation, 3).tolist(), "assets": [], "station": None,
            "crews": [], "hour": s.scenario.hour, "kinds": {},
        }


@app.post("/simulation/ignite")
def ignite(body: CellIn) -> dict:
    """Start a fire at a cell. Before the first tick it becomes part of the scenario.

    At tick 0 the cell is added to the scenario's ignition points, so resets and replays
    keep it; later it is a spot fire, which a reset removes.

    \f
    Args:
        body: The cell to ignite.

    Returns:
        The live state payload (same shape as ``GET /simulation/state``).

    Raises:
        HTTPException: 409 if there is no active scenario or the incident is closed (reset
            first); 422 if the cell is outside the map or has nothing to burn.
    """
    with _lock:
        s = _require_session()
        eng = s.engine
        if not eng.grid.in_bounds(body.x, body.y):
            raise HTTPException(status_code=422, detail="cell is outside the map")
        if eng.grid.fuel[body.y, body.x] == FuelType.NONE:
            raise HTTPException(status_code=422, detail="nothing to burn at this cell")
        if eng.state == SimState.COMPLETED:
            raise HTTPException(status_code=409, detail="incident is closed; reset first")
        if eng.tick == 0:
            eng.ignite(body.x, body.y)
            s.scenario.ignition_points.append(IgnitionPoint(body.x, body.y))
            rec = scenarios.find(s.scenario.id)
            if rec is not None:
                rec.payload["ignition_points"] = [asdict(p) for p in s.scenario.ignition_points]
        else:
            eng.spot_fire(body.x, body.y)
        if s.city is not None:
            s.city.refresh()
        return _state_payload(s)


@app.post("/simulation/suppress")
def suppress(body: SuppressIn) -> dict:
    """Queue suppression on cells (same effect as a bus suppression command).

    The cells are treated on the next tick: those inside the map that are unburned,
    igniting or burning become suppressed, the others are ignored. The returned state does
    not show them yet.

    \f
    Args:
        body: The cells to suppress.

    Returns:
        The live state payload (same shape as ``GET /simulation/state``).

    Raises:
        HTTPException: 409 if there is no active scenario.
    """
    with _lock:
        s = _require_session()
        s.engine.apply_suppression([(c.x, c.y) for c in body.cells])
        return _state_payload(s)


@app.post("/simulation/dispatch")
def dispatch(body: DispatchIn) -> dict:
    """Send the nearest available fire crew to an asset.

    City scenarios only. The nearest free crew (city-block distance) travels there, then
    works at the asset for a limited number of ticks, suppressing fire in and around it and
    helping people get out.

    \f
    Args:
        body: The asset to protect.

    Returns:
        The live state payload (same shape as ``GET /simulation/state``).

    Raises:
        HTTPException: 404 if the asset does not exist; 409 if there is no active scenario,
            it is not a city scenario, the incident is closed or no crew is available.
    """
    with _lock:
        s = _require_session()
        city = _require_city(s)
        if not 0 <= body.asset_id < len(city.assets):
            raise HTTPException(status_code=404, detail="asset not found")
        if s.engine.state == SimState.COMPLETED:
            raise HTTPException(status_code=409, detail="incident is closed")
        if city.dispatch(body.asset_id) is None:
            raise HTTPException(status_code=409, detail="no crews available")
        city.refresh()
        return _state_payload(s)


@app.post("/simulation/auto-dispatch")
def auto_dispatch(body: AutoDispatchIn) -> dict:
    """Turn automatic crew dispatch on or off.

    City scenarios only. While it is on, before every tick the most urgent assets that no
    crew is assigned to get the nearest free crew, in priority order; low-priority assets
    are skipped. The change is written to the incident's event log.

    \f
    Args:
        body: Whether automatic dispatch should be on.

    Returns:
        The live state payload (same shape as ``GET /simulation/state``).

    Raises:
        HTTPException: 409 if there is no active scenario or it is not a city scenario.
    """
    with _lock:
        s = _require_session()
        _require_city(s).set_auto_dispatch(body.enabled)
        return _state_payload(s)


@app.post("/simulation/end")
def end_incident() -> dict:
    """Close the incident now and record it in the history (city scenarios).

    The simulation becomes completed whatever its state. A city incident that has run at
    least one tick and is not recorded yet is saved with outcome ``"stopped"``, and its id
    appears as ``incident_id`` in the returned state. Wildland scenarios are only stopped.

    \f
    Returns:
        The live state payload (same shape as ``GET /simulation/state``).

    Raises:
        HTTPException: 409 if there is no active scenario.
    """
    global _recorded_id
    with _lock:
        s = _require_session()
        s.engine.stop()
        if s.city is not None and _recorded_id is None and s.engine.tick > 0:
            _recorded_id = _record(s, "stopped", "live", _started_at).id
        return _state_payload(s)


def _state_payload(s: Session) -> dict:
    """Build the live state payload returned by ``GET /simulation/state`` and the controls."""
    eng = s.engine
    return {
        "state": eng.state.value,
        "tick": eng.tick,
        "speed": eng.speed,
        "counts": eng.counts(),
        "grid": eng.grid.state.tolist(),
        "map_type": s.scenario.map_type,
        "scenario": {"id": s.scenario.id, "name": s.scenario.name},
        "wind": {"direction": eng.wind.direction_deg, "speed": eng.wind.speed},
        "incident_id": _recorded_id,
        "city": s.city.dynamic_payload() if s.city is not None else None,
    }


# ---- incident history (admin dashboard) -----------------------------------
def _params(s: Session) -> dict:
    """Collect the scenario parameters stored with an incident record."""
    sc = s.scenario
    return {
        "map_type": sc.map_type, "width": sc.width, "height": sc.height, "seed": sc.seed,
        "wind_direction": sc.wind_direction, "wind_speed": sc.wind_speed, "hour": sc.hour,
        "crews": sc.crews,
        "auto_dispatch": s.city.response.auto if s.city is not None else False,
        "ignition_points": [asdict(p) for p in sc.ignition_points],
    }


def _record(s: Session, outcome: str, source: str, started_at: float) -> IncidentRecord:
    """Save a city session's incident to the history and return the new record."""
    rec = IncidentRecord(
        id=str(uuid.uuid4()), name=s.scenario.name, scenario_id=s.scenario.id,
        source=source, outcome=outcome, started_at=started_at, ended_at=time.time(),
        ticks=s.engine.tick, params=_params(s), summary=s.city.incident_summary(),
    )
    with _lock:
        incidents.save(rec)
    return rec


def _maybe_record(s: Session) -> None:
    """Record a city incident once, when its fire is out."""
    global _recorded_id
    if (s.city is not None and _recorded_id is None and s.engine.state == SimState.COMPLETED
            and s.engine.tick > 0):
        _recorded_id = _record(s, "extinguished", "live", _started_at).id


_COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


@app.get("/incidents")
def list_incidents() -> list[dict]:
    """List the incident history, newest first.

    Each entry is a brief record without the per-tick timeline and key events; get them
    with ``GET /incidents/{incident_id}``.

    \f
    Returns:
        One dict per incident (``IncidentRecord.brief``) with ``id``, ``name``,
        ``scenario_id``, ``source``, ``outcome``, ``started_at``, ``ended_at``, ``ticks``,
        ``params`` and ``summary`` (without ``timeline`` and ``key_events``).
    """
    with _lock:
        return [r.brief() for r in incidents.all()]


@app.get("/incidents/{incident_id}")
def get_incident(incident_id: str) -> dict:
    """Get one incident from the history, including its timeline and key events.

    Returns the full record: run parameters, outcome and the complete summary (people,
    buildings, losses, key events and the per-tick timeline).

    \f
    Args:
        incident_id: Id of the incident.

    Returns:
        The full ``IncidentRecord`` as a dict: the same keys as a ``GET /incidents`` entry,
        with the complete ``summary``.

    Raises:
        HTTPException: 404 if no incident has this id.
    """
    with _lock:
        rec = incidents.find(incident_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="incident not found")
    return asdict(rec)


@app.delete("/incidents/{incident_id}", status_code=204)
def delete_incident(incident_id: str) -> None:
    """Delete one incident from the history.

    Responds with 204 No Content.

    \f
    Args:
        incident_id: Id of the incident to delete.

    Raises:
        HTTPException: 404 if no incident has this id.
    """
    with _lock:
        if not incidents.delete(incident_id):
            raise HTTPException(status_code=404, detail="incident not found")


@app.delete("/incidents")
def clear_incidents() -> dict:
    """Delete every incident from the history.

    Returns how many incidents were deleted.

    \f
    Returns:
        ``{"deleted": <number of incidents deleted>}``.
    """
    with _lock:
        return {"deleted": incidents.clear()}


@app.post("/incidents/simulate", status_code=201)
def simulate_incidents(body: BatchIn) -> list[dict]:
    """Run city incidents headless with varied conditions and record them.

    Each run is a real simulation (random seed, wind, time of day, crews and
    response mode); the parameters are stored, so every run can be replayed.

    The conditions are drawn from a generator seeded with ``seed``: repeating a request with
    the same seed and settings gives runs with the same conditions and outcomes, and without
    a seed every request differs. The live simulation is not affected.

    \f
    Args:
        body: Number of runs, town size, tick limit per run and optional seed.

    Returns:
        One brief record per run, in run order (same shape as the ``GET /incidents``
        entries), each with source ``"simulated"`` and outcome ``"extinguished"`` or
        ``"time_limit"``; the response status is 201.

    Raises:
        HTTPException: 422 if the engine rejects a generated scenario.
    """
    rng = np.random.default_rng(body.seed)
    out = []
    for _ in range(body.count):
        wind_dir = float(rng.choice([0, 45, 90, 135, 180, 225, 270, 315]))
        wind_speed = float(np.round(rng.uniform(8, 38)))
        hour = int(rng.choice([2, 7, 10, 13, 15, 18, 21, 23]))
        sc = Scenario(
            name=f"{_COMPASS[int(wind_dir) // 45]} wind {wind_speed:.0f} km/h at {hour:02d}:00",
            width=body.size, height=body.size, seed=int(rng.integers(0, 1_000_000)),
            wind_direction=wind_dir, wind_speed=wind_speed, map_type="city", hour=hour,
            crews=int(rng.integers(2, 7)), auto_dispatch=bool(rng.random() < 0.6),
        )
        started = time.time()
        s = _build(sc)
        s.engine.run(body.max_ticks)
        outcome = "extinguished" if s.engine.state == SimState.COMPLETED else "time_limit"
        out.append(_record(s, outcome, "simulated", started).brief())
    return out


# ---- built UI (packaged image) --------------------------------------------
def mount_ui(application: FastAPI, directory: str | os.PathLike[str]) -> bool:
    """Serve a built UI (the ``frontend/dist`` folder) from the root of an app.

    Call it after every API route is registered: the mount answers only the paths
    the routes do not, and ``html=True`` serves ``index.html`` for ``/``.

    Args:
        application: The FastAPI app to mount the UI on.
        directory: Folder that holds the built UI (``index.html`` and ``assets/``).

    Returns:
        True if the folder exists and was mounted, False if it was skipped.
    """
    if not directory or not Path(directory).is_dir():
        return False
    application.mount("/", StaticFiles(directory=directory, html=True), name="ui")
    return True


# The Docker image sets FIRESIM_STATIC_DIR, so one container serves the API and the UI.
mount_ui(app, os.environ.get("FIRESIM_STATIC_DIR", ""))
