from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)

CITY = {"name": "Town Burn", "width": 56, "height": 56, "seed": 2, "wind_direction": 90,
        "wind_speed": 30, "map_type": "city", "hour": 13, "crews": 3}


def new_city(**overrides) -> str:
    res = client.post("/scenarios", json={**CITY, **overrides})
    assert res.status_code == 201
    return res.json()["id"]


def test_city_scenario_exposes_map_and_people():
    new_city()
    m = client.get("/simulation/map").json()
    assert m["map_type"] == "city" and m["assets"] and len(m["landuse"]) == 56
    st = client.get("/simulation/state").json()
    assert st["map_type"] == "city"
    assert st["wind"] == {"direction": 90, "speed": 30}
    assert st["city"]["population"]["total"] > 0
    assert len(st["city"]["assets"]["status"]) == len(m["assets"])


def test_city_requires_minimum_size():
    assert client.post("/scenarios", json={**CITY, "width": 30, "height": 30}).status_code == 422


def test_dispatch_and_auto_dispatch():
    new_city()
    houses = [a for a in client.get("/simulation/map").json()["assets"] if a["kind"] == "house"]
    res = client.post("/simulation/dispatch", json={"asset_id": houses[0]["id"]})
    assert res.status_code == 200
    assert any(c["status"] == "en_route" and c["target"] == houses[0]["id"]
               for c in res.json()["city"]["crews"])
    assert client.post("/simulation/dispatch", json={"asset_id": 10**6}).status_code == 404
    res = client.post("/simulation/auto-dispatch", json={"enabled": True})
    assert res.json()["city"]["auto_dispatch"] is True


def test_ignite_validates_cells():
    new_city()
    assets = client.get("/simulation/map").json()["assets"]
    road = next(a for a in assets if a["kind"] == "road")
    res = client.post("/simulation/ignite", json={"x": road["x"], "y": road["y"]})
    assert res.status_code == 422
    house = next(a for a in assets if a["kind"] == "house")
    res = client.post("/simulation/ignite", json={"x": house["x"], "y": house["y"]})
    assert res.status_code == 200
    assert res.json()["counts"]["burning"] >= 2      # default ignition + the new one


def test_finished_city_incident_is_recorded():
    client.delete("/incidents")
    new_city(name="Recorded Burn")
    client.post("/simulation/play")
    st = {}
    for _ in range(2000):
        st = client.post("/simulation/tick").json()
        if st["state"] == "completed":
            break
    assert st["state"] == "completed" and st["incident_id"]
    listed = client.get("/incidents").json()
    assert listed[0]["id"] == st["incident_id"] and listed[0]["name"] == "Recorded Burn"
    assert listed[0]["outcome"] == "extinguished"
    assert "timeline" not in listed[0]["summary"]
    full = client.get(f"/incidents/{st['incident_id']}").json()
    assert len(full["summary"]["timeline"]) > 1
    assert full["summary"]["population"]["total"] > 0


def test_end_records_a_stopped_incident():
    new_city(name="Stopped Burn")
    client.post("/simulation/play")
    for _ in range(5):
        client.post("/simulation/tick")
    st = client.post("/simulation/end").json()
    assert st["state"] == "completed" and st["incident_id"]
    rec = client.get(f"/incidents/{st['incident_id']}").json()
    assert rec["outcome"] == "stopped" and rec["ticks"] == 5


def test_batch_simulation_and_history_management():
    client.delete("/incidents")
    batch = {"count": 2, "size": 48, "max_ticks": 300, "seed": 1}
    res = client.post("/incidents/simulate", json=batch)
    assert res.status_code == 201 and len(res.json()) == 2
    ids = [r["id"] for r in res.json()]
    assert {r["id"] for r in client.get("/incidents").json()} == set(ids)
    assert client.delete(f"/incidents/{ids[0]}").status_code == 204
    assert client.get(f"/incidents/{ids[0]}").status_code == 404
    assert client.delete("/incidents").json() == {"deleted": 1}


def test_city_replay_is_deterministic():
    sid = new_city(name="Replay Town")
    a = client.get(f"/scenarios/{sid}/replay", params={"max_ticks": 120}).json()
    b = client.get(f"/scenarios/{sid}/replay", params={"max_ticks": 120}).json()
    assert a == b and "city" in a["frames"][-1]


def test_wildland_scenario_has_no_city_layer():
    client.post("/scenarios", json={"name": "Wild", "width": 20, "height": 20, "seed": 1,
                                    "ignition_points": [{"x": 10, "y": 10}]})
    assert client.get("/simulation/state").json()["city"] is None
    assert client.get("/simulation/map").json()["map_type"] == "wildland"
    assert client.post("/simulation/dispatch", json={"asset_id": 0}).status_code == 409
