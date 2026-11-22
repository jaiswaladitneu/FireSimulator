"""The API as packaged in the Docker image: /api prefix and the built UI."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.main import app, mount_ui


def test_api_prefix_is_stripped():
    client = TestClient(app)
    assert client.get("/api/health").json() == {"status": "ok"}
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/api/scenarios/does-not-exist").status_code == 404


def test_mount_ui_serves_index_and_keeps_api_routes(tmp_path):
    (tmp_path / "index.html").write_text("<!doctype html><title>FireSim UI</title>", "utf-8")
    ui_app = FastAPI()

    @ui_app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    assert mount_ui(ui_app, tmp_path) is True
    client = TestClient(ui_app)
    assert "FireSim UI" in client.get("/").text
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/missing.js").status_code == 404


def test_mount_ui_skips_a_missing_folder(tmp_path):
    assert mount_ui(FastAPI(), tmp_path / "missing") is False
    assert mount_ui(FastAPI(), "") is False
