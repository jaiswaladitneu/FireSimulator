"""API tests for live-run snapshotting and resync (E6, issues #27 and #30)."""
from fastapi.testclient import TestClient

import api.main as main
from api.main import app
from persistence import InMemorySnapshotRepository, JsonFileSnapshotRepository

client = TestClient(app)


def test_snapshot_repository_factory_honours_the_env_var(tmp_path, monkeypatch):
    monkeypatch.delenv("FIRESIM_SNAPSHOTS_FILE", raising=False)
    assert isinstance(main._snapshot_repository(), InMemorySnapshotRepository)
    monkeypatch.setenv("FIRESIM_SNAPSHOTS_FILE", str(tmp_path / "s.json"))
    assert isinstance(main._snapshot_repository(), JsonFileSnapshotRepository)

CITY = {"name": "Snapshot Town", "width": 56, "height": 56, "seed": 2,
        "wind_direction": 90, "wind_speed": 30, "map_type": "city", "hour": 13, "crews": 3}


def test_live_run_saves_snapshots_and_resync_returns_the_latest(monkeypatch):
    monkeypatch.setattr(main, "SNAPSHOT_EVERY", 3)      # snapshot every 3 ticks for a fast test
    sid = client.post("/scenarios", json=CITY).json()["id"]

    client.post("/simulation/play")
    last = {}
    for _ in range(7):
        last = client.post("/simulation/tick").json()
        if last["state"] == "completed":
            break

    listed = client.get(f"/scenarios/{sid}/snapshots").json()
    assert listed["scenario_id"] == sid and listed["count"] >= 1
    assert listed["snapshots"][0]["tick"] == 3              # first saved at tick 3
    assert "state" not in listed["snapshots"][0]            # brief by default

    full = client.get(f"/scenarios/{sid}/snapshots", params={"full": "true"}).json()
    assert len(full["snapshots"][0]["state"]) == 56         # one row per grid row

    r = client.get("/simulation/resync").json()
    assert r["source"] == "snapshot" and r["scenario"]["id"] == sid
    assert r["tick"] == listed["snapshots"][-1]["tick"]     # the newest snapshot
    assert len(r["state"]) == 56 and len(r["state"][0]) == 56


def test_resync_falls_back_to_live_state_before_the_first_snapshot(monkeypatch):
    monkeypatch.setattr(main, "SNAPSHOT_EVERY", 1000)       # none will be saved in this run
    client.post("/scenarios", json={**CITY, "name": "Fresh Town"})

    r = client.get("/simulation/resync").json()
    assert r["source"] == "live" and r["tick"] == 0
    assert len(r["state"]) == 56


def test_snapshots_endpoint_is_empty_for_an_unknown_scenario():
    listed = client.get("/scenarios/never-created/snapshots").json()
    assert listed == {"scenario_id": "never-created", "count": 0, "snapshots": []}
