"""FastAPI application: scenario management and playback control (Epic E2).

This is the control surface other components and the UI use. It wraps the
simulation engine (a Facade) and keeps scenarios in a repository. A single
active engine is held for simplicity in this scaffold.
"""
from __future__ import annotations

from dataclasses import asdict

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from engine import Scenario, SimState, SimulationEngine
from engine.scenario import IgnitionPoint
from persistence import InMemoryScenarioRepository, ScenarioRecord

app = FastAPI(title="Fire Simulator API", version="0.1.0")

scenarios = InMemoryScenarioRepository()
_engine: SimulationEngine | None = None


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


class SpeedIn(BaseModel):
    speed: float = Field(ge=0.25, le=16.0)


def _to_scenario(body: ScenarioIn) -> Scenario:
    return Scenario(
        name=body.name, width=body.width, height=body.height, seed=body.seed,
        wind_direction=body.wind_direction, wind_speed=body.wind_speed,
        ignition_points=[IgnitionPoint(p.x, p.y, p.tick) for p in body.ignition_points],
    )


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


# ---- scenarios ----------------------------------------------------------
@app.post("/scenarios", status_code=201)
def create_scenario(body: ScenarioIn) -> dict:
    sc = _to_scenario(body)
    scenarios.save(ScenarioRecord(id=sc.id, name=sc.name, payload=body.model_dump()))
    global _engine
    _engine = SimulationEngine.from_scenario(sc)
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
    session. Each frame is the cell-state counts at that tick.
    """
    rec = scenarios.find(scenario_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="scenario not found")
    eng = SimulationEngine.from_scenario(_to_scenario(ScenarioIn(**rec.payload)))
    frames = [{"tick": eng.tick, "counts": eng.counts()}]
    eng.start()
    while eng.state == SimState.RUNNING and eng.tick < max_ticks:
        eng.advance()
        frames.append({"tick": eng.tick, "counts": eng.counts()})
    return {
        "scenario_id": scenario_id,
        "ticks": eng.tick,
        "final_state": eng.state.value,
        "frames": frames,
    }


# ---- playback -----------------------------------------------------------
def _require_engine() -> SimulationEngine:
    if _engine is None:
        raise HTTPException(status_code=409, detail="no active scenario; create one first")
    return _engine


@app.post("/simulation/play")
def play() -> dict:
    eng = _require_engine()
    eng.start()
    return _state_payload(eng)


@app.post("/simulation/pause")
def pause() -> dict:
    eng = _require_engine()
    eng.pause()
    return _state_payload(eng)


@app.post("/simulation/step")
def step() -> dict:
    eng = _require_engine()
    eng.step()
    return _state_payload(eng)


@app.post("/simulation/reset")
def reset() -> dict:
    eng = _require_engine()
    eng.reset()
    return _state_payload(eng)


@app.post("/simulation/speed")
def speed(body: SpeedIn) -> dict:
    eng = _require_engine()
    eng.set_speed(body.speed)
    return _state_payload(eng)


@app.get("/simulation/state")
def state() -> dict:
    return _state_payload(_require_engine())


def _state_payload(eng: SimulationEngine) -> dict:
    return {"state": eng.state.value, "tick": eng.tick, "speed": eng.speed, "counts": eng.counts()}
