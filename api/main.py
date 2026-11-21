"""FastAPI application: scenario management and playback control (Epic E2).

This is the control surface other components and the UI use. It wraps the
simulation (a Facade over the engine and, for towns, the city layer) and keeps
scenarios in a repository. A single active session is held for simplicity.

City scenarios add the incident-command features: the town map, people at risk,
priorities, fire-crew dispatch, and an incident history (Epic E6) that records
every finished city incident for the admin dashboard.
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
from pydantic import BaseModel, Field

from engine import Scenario, SimState
from engine.cell import FuelType
from engine.landuse import landuse_from_fuel
from engine.scenario import IgnitionPoint
from engine.session import Session, create_session
from persistence import (
    IncidentRecord,
    InMemoryIncidentRepository,
    InMemoryScenarioRepository,
    JsonFileIncidentRepository,
    ScenarioRecord,
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


def _incident_repository():
    """JSON file by default (history survives restarts); ':memory:' for tests."""
    default = Path(__file__).resolve().parent.parent / "data" / "incidents.json"
    path = os.environ.get("FIRESIM_INCIDENTS_FILE", str(default))
    if path in ("", ":memory:"):
        return InMemoryIncidentRepository()
    return JsonFileIncidentRepository(path)


scenarios = InMemoryScenarioRepository()
incidents = _incident_repository()
_session: Session | None = None
_started_at: float = 0.0
_recorded_id: str | None = None
_lock = threading.RLock()   # one request at a time touches the live session


class IgnitionPointIn(BaseModel):
    x: int
    y: int
    tick: int = 0


class ScenarioIn(BaseModel):
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
    speed: float = Field(ge=0.25, le=16.0)


class CellIn(BaseModel):
    x: int
    y: int


class SuppressIn(BaseModel):
    cells: list[CellIn] = Field(default_factory=list)


class DispatchIn(BaseModel):
    asset_id: int


class AutoDispatchIn(BaseModel):
    enabled: bool


class BatchIn(BaseModel):
    count: int = Field(default=5, ge=1, le=20)
    size: int = Field(default=80, ge=48, le=128)
    max_ticks: int = Field(default=800, ge=50, le=3000)
    seed: int | None = None


def _to_scenario(body: ScenarioIn) -> Scenario:
    return Scenario(
        name=body.name, width=body.width, height=body.height, seed=body.seed,
        wind_direction=body.wind_direction, wind_speed=body.wind_speed,
        ignition_points=[IgnitionPoint(p.x, p.y, p.tick) for p in body.ignition_points],
        map_type=body.map_type, hour=body.hour, crews=body.crews,
        auto_dispatch=body.auto_dispatch,
    )


def _build(sc: Scenario) -> Session:
    try:
        return create_session(sc)
    except ValueError as exc:   # e.g. a city map smaller than the minimum size
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


# ---- scenarios ----------------------------------------------------------
@app.post("/scenarios", status_code=201)
def create_scenario(body: ScenarioIn) -> dict:
    global _session, _started_at, _recorded_id
    sc = _to_scenario(body)
    session = _build(sc)
    payload = body.model_dump()
    # Store the actual ignition points (a city scenario may have had a default chosen).
    payload["ignition_points"] = [asdict(p) for p in sc.ignition_points]
    with _lock:
        scenarios.save(ScenarioRecord(id=sc.id, name=sc.name, payload=payload))
        _session, _started_at, _recorded_id = session, time.time(), None
    return {"id": sc.id, "name": sc.name}


@app.get("/scenarios")
def list_scenarios() -> list[dict]:
    return [asdict(r) for r in scenarios.all()]


@app.get("/scenarios/{scenario_id}")
def get_scenario(scenario_id: str) -> dict:
    rec = scenarios.find(scenario_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="scenario not found")
    return asdict(rec)


@app.delete("/scenarios/{scenario_id}", status_code=204)
def delete_scenario(scenario_id: str) -> None:
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


# ---- playback -----------------------------------------------------------
def _require_session() -> Session:
    if _session is None:
        raise HTTPException(status_code=409, detail="no active scenario; create one first")
    return _session


def _require_city(session: Session):
    if session.city is None:
        raise HTTPException(status_code=409, detail="the active scenario is not a city scenario")
    return session.city


@app.post("/simulation/play")
def play() -> dict:
    with _lock:
        s = _require_session()
        s.engine.start()
        return _state_payload(s)


@app.post("/simulation/pause")
def pause() -> dict:
    with _lock:
        s = _require_session()
        s.engine.pause()
        return _state_payload(s)


@app.post("/simulation/step")
def step() -> dict:
    with _lock:
        s = _require_session()
        s.engine.step()
        _maybe_record(s)
        return _state_payload(s)


@app.post("/simulation/tick")
def tick() -> dict:
    with _lock:
        s = _require_session()
        if s.engine.state == SimState.RUNNING:
            s.engine.advance()
            _maybe_record(s)
        return _state_payload(s)


@app.post("/simulation/reset")
def reset() -> dict:
    global _started_at, _recorded_id
    with _lock:
        s = _require_session()
        s.engine.reset()
        _started_at, _recorded_id = time.time(), None
        return _state_payload(s)


@app.post("/simulation/speed")
def speed(body: SpeedIn) -> dict:
    with _lock:
        s = _require_session()
        s.engine.set_speed(body.speed)
        return _state_payload(s)


@app.get("/simulation/state")
def state() -> dict:
    with _lock:
        return _state_payload(_require_session())


@app.get("/simulation/map")
def simulation_map() -> dict:
    """The static map (land use, fuel, elevation, assets). Fetch once per scenario."""
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
    """Start a fire at a cell. Before the first tick it becomes part of the scenario."""
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
    """Queue suppression on cells (same effect as a bus suppression command)."""
    with _lock:
        s = _require_session()
        s.engine.apply_suppression([(c.x, c.y) for c in body.cells])
        return _state_payload(s)


@app.post("/simulation/dispatch")
def dispatch(body: DispatchIn) -> dict:
    """Send the nearest available fire crew to an asset."""
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
    with _lock:
        s = _require_session()
        _require_city(s).set_auto_dispatch(body.enabled)
        return _state_payload(s)


@app.post("/simulation/end")
def end_incident() -> dict:
    """Close the incident now and record it in the history (city scenarios)."""
    global _recorded_id
    with _lock:
        s = _require_session()
        s.engine.stop()
        if s.city is not None and _recorded_id is None and s.engine.tick > 0:
            _recorded_id = _record(s, "stopped", "live", _started_at).id
        return _state_payload(s)


def _state_payload(s: Session) -> dict:
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
    sc = s.scenario
    return {
        "map_type": sc.map_type, "width": sc.width, "height": sc.height, "seed": sc.seed,
        "wind_direction": sc.wind_direction, "wind_speed": sc.wind_speed, "hour": sc.hour,
        "crews": sc.crews,
        "auto_dispatch": s.city.response.auto if s.city is not None else False,
        "ignition_points": [asdict(p) for p in sc.ignition_points],
    }


def _record(s: Session, outcome: str, source: str, started_at: float) -> IncidentRecord:
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
    with _lock:
        return [r.brief() for r in incidents.all()]


@app.get("/incidents/{incident_id}")
def get_incident(incident_id: str) -> dict:
    with _lock:
        rec = incidents.find(incident_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="incident not found")
    return asdict(rec)


@app.delete("/incidents/{incident_id}", status_code=204)
def delete_incident(incident_id: str) -> None:
    with _lock:
        if not incidents.delete(incident_id):
            raise HTTPException(status_code=404, detail="incident not found")


@app.delete("/incidents")
def clear_incidents() -> dict:
    with _lock:
        return {"deleted": incidents.clear()}


@app.post("/incidents/simulate", status_code=201)
def simulate_incidents(body: BatchIn) -> list[dict]:
    """Run city incidents headless with varied conditions and record them.

    Each run is a real simulation (random seed, wind, time of day, crews and
    response mode); the parameters are stored, so every run can be replayed.
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
