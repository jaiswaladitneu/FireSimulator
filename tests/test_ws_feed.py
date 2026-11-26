"""WebSocket live-feed tests (E5, issue #36)."""
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import api.main as main
from api.main import app

client = TestClient(app)

CITY = {"name": "Feed Town", "width": 56, "height": 56, "seed": 2, "wind_direction": 90,
        "wind_speed": 30, "map_type": "city", "hour": 13, "crews": 3}


def test_ws_streams_server_driven_frames_live():
    client.post("/scenarios", json=CITY)
    client.post("/simulation/speed", json={"speed": 16})     # fast frames for the test
    client.post("/simulation/play")

    with client.websocket_connect("/simulation/ws") as ws:
        first = ws.receive_json()
        assert first["tick"] == 0 and first["state"] == "running"   # resync on connect
        ticks = [ws.receive_json()["tick"] for _ in range(4)]

    assert ticks == sorted(ticks)          # frames arrive in order
    assert ticks[-1] >= 4                   # the server advanced the run on its own


def test_ws_is_served_under_the_api_prefix():
    client.post("/scenarios", json=CITY)
    with client.websocket_connect("/api/simulation/ws") as ws:
        frame = ws.receive_json()
    assert "tick" in frame and "grid" in frame


def test_ws_closes_when_there_is_no_active_scenario(monkeypatch):
    monkeypatch.setattr(main, "_session", None)
    with client.websocket_connect("/simulation/ws") as ws, pytest.raises(WebSocketDisconnect):
        ws.receive_json()
