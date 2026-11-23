"""REST API edge cases: playback controls and every documented error status (E2)."""
import pytest
from fastapi.testclient import TestClient

import api.main as main
from engine.cell import CellState

client = TestClient(main.app)

WILD = {"name": "Edge Burn", "width": 20, "height": 20, "seed": 3, "wind_direction": 90,
        "wind_speed": 10, "ignition_points": [{"x": 10, "y": 10}]}
CITY = {"name": "Edge Town", "width": 56, "height": 56, "seed": 2, "map_type": "city",
        "hour": 13, "crews": 3}


def new_scenario(body: dict) -> str:
    res = client.post("/scenarios", json=body)
    assert res.status_code == 201
    return res.json()["id"]


@pytest.mark.parametrize("method, path", [
    ("post", "/simulation/play"), ("post", "/simulation/pause"), ("post", "/simulation/step"),
    ("post", "/simulation/tick"), ("post", "/simulation/reset"), ("get", "/simulation/state"),
    ("get", "/simulation/map"), ("post", "/simulation/end"),
])
def test_playback_without_a_scenario_is_a_conflict(monkeypatch, method, path):
    monkeypatch.setattr(main, "_session", None)
    res = getattr(client, method)(path)
    assert res.status_code == 409
    assert "no active scenario" in res.json()["detail"]


@pytest.mark.parametrize("body", [
    {**WILD, "width": 0},                               # below the minimum size
    {**WILD, "height": 401},                            # above the maximum size
    {**WILD, "map_type": "desert"},                     # unknown map type
    {**WILD, "hour": 24},                               # hour of day out of range
    {k: v for k, v in WILD.items() if k != "name"},     # name is required
])
def test_invalid_scenarios_are_rejected(body):
    assert client.post("/scenarios", json=body).status_code == 422


def test_playback_controls_follow_the_engine_lifecycle():
    new_scenario(WILD)
    assert client.get("/simulation/state").json()["state"] == "idle"
    assert client.post("/simulation/play").json()["state"] == "running"
    paused = client.post("/simulation/pause").json()
    assert paused["state"] == "paused"
    assert client.post("/simulation/tick").json()["tick"] == paused["tick"]  # no tick when paused
    stepped = client.post("/simulation/step").json()
    assert stepped["tick"] == paused["tick"] + 1 and stepped["state"] == "paused"
    assert client.post("/simulation/speed", json={"speed": 4}).json()["speed"] == 4
    assert client.post("/simulation/speed", json={"speed": 32}).status_code == 422
    reset = client.post("/simulation/reset").json()
    assert reset["state"] == "idle" and reset["tick"] == 0


def test_ignite_spot_fires_and_closed_incidents():
    new_scenario(WILD)
    assert client.post("/simulation/ignite", json={"x": 99, "y": 0}).status_code == 422
    fuel = client.get("/simulation/map").json()["fuel"]
    x, y = next((x, y) for y, row in enumerate(fuel) for x, f in enumerate(row)
                if f and abs(x - 10) + abs(y - 10) > 8)
    client.post("/simulation/play")
    client.post("/simulation/tick")
    spot = client.post("/simulation/ignite", json={"x": x, "y": y})
    assert spot.status_code == 200 and spot.json()["grid"][y][x] == CellState.BURNING
    client.post("/simulation/end")
    closed = client.post("/simulation/ignite", json={"x": x, "y": y})
    assert closed.status_code == 409


def test_suppression_is_applied_on_the_next_tick():
    new_scenario(WILD)
    client.post("/simulation/suppress", json={"cells": [{"x": 10, "y": 10}]})
    assert client.post("/simulation/step").json()["grid"][10][10] == CellState.SUPPRESSED


def test_dispatch_needs_a_free_crew_and_an_open_incident():
    new_scenario({**CITY, "crews": 0})
    house = next(a for a in client.get("/simulation/map").json()["assets"] if a["kind"] == "house")
    res = client.post("/simulation/dispatch", json={"asset_id": house["id"]})
    assert res.status_code == 409 and res.json()["detail"] == "no crews available"
    client.post("/simulation/end")
    res = client.post("/simulation/dispatch", json={"asset_id": house["id"]})
    assert res.status_code == 409 and res.json()["detail"] == "incident is closed"


def test_auto_dispatch_needs_a_city_scenario():
    new_scenario(WILD)
    assert client.post("/simulation/auto-dispatch", json={"enabled": True}).status_code == 409


def test_unknown_incidents_are_not_found():
    assert client.get("/incidents/does-not-exist").status_code == 404
    assert client.delete("/incidents/does-not-exist").status_code == 404


@pytest.mark.parametrize("max_ticks", [0, 10_001])
def test_replay_tick_limit_is_validated(max_ticks):
    sid = new_scenario(WILD)
    res = client.get(f"/scenarios/{sid}/replay", params={"max_ticks": max_ticks})
    assert res.status_code == 422
