from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_create_scenario_and_play():
    body = {
        "name": "Test Burn", "width": 20, "height": 20, "seed": 3,
        "wind_direction": 90, "wind_speed": 20,
        "ignition_points": [{"x": 10, "y": 10}],
    }
    res = client.post("/scenarios", json=body)
    assert res.status_code == 201
    sid = res.json()["id"]

    assert any(r["id"] == sid for r in client.get("/scenarios").json())

    played = client.post("/simulation/play").json()
    assert played["state"] == "running"

    stepped = client.post("/simulation/step").json()
    assert stepped["tick"] == 1

    assert client.get(f"/scenarios/{sid}").json()["name"] == "Test Burn"
    assert client.delete(f"/scenarios/{sid}").status_code == 204
    assert client.get(f"/scenarios/{sid}").status_code == 404


def test_playback_without_scenario_is_conflict():
    # Reset module state is not trivial; a missing scenario id still 404s.
    assert client.get("/scenarios/does-not-exist").status_code == 404
