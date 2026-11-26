"""Live-state cache tests: in-memory and Redis-backed, plus the API wiring (E6, issue #32)."""
import json
import os

import pytest
from fastapi.testclient import TestClient

import api.main as main
from api.main import app
from persistence import InMemoryStateCache, RedisStateCache

client = TestClient(app)

CITY = {"name": "Cache Town", "width": 56, "height": 56, "seed": 2, "wind_direction": 90,
        "wind_speed": 30, "map_type": "city", "hour": 13, "crews": 3}


class _FakeRedis:
    """Minimal Redis client: stores values with their TTL (stands in for redis-py)."""

    def __init__(self) -> None:
        self.store: dict[str, object] = {}
        self.ttl: dict[str, int | None] = {}

    def set(self, key, value, ex=None) -> None:
        self.store[key] = value
        self.ttl[key] = ex

    def get(self, key):
        return self.store.get(key)


def test_in_memory_state_cache_put_get_and_miss():
    cache = InMemoryStateCache()
    assert cache.get("s1") is None
    cache.put("s1", {"tick": 4})
    assert cache.get("s1") == {"tick": 4}


def test_redis_state_cache_serializes_with_key_and_ttl():
    fake = _FakeRedis()
    cache = RedisStateCache(client=fake, ttl=120)
    cache.put("s1", {"tick": 7, "grid": [[0, 1]]})

    assert "firesim:state:s1" in fake.store
    assert fake.ttl["firesim:state:s1"] == 120
    assert json.loads(fake.store["firesim:state:s1"]) == {"tick": 7, "grid": [[0, 1]]}
    assert cache.get("s1") == {"tick": 7, "grid": [[0, 1]]}


def test_redis_state_cache_decodes_bytes_and_misses_to_none():
    fake = _FakeRedis()
    cache = RedisStateCache(client=fake)
    fake.store["firesim:state:s2"] = b'{"tick": 9}'      # real redis returns bytes
    assert cache.get("s2") == {"tick": 9}
    assert cache.get("absent") is None


def test_live_state_is_cached_and_readable_by_scenario_id():
    sid = client.post("/scenarios", json=CITY).json()["id"]
    live = client.get("/simulation/state").json()        # building the payload caches it
    cached = client.get(f"/simulation/cached/{sid}").json()
    assert cached["scenario"]["id"] == sid and cached["tick"] == live["tick"]
    assert client.get("/simulation/cached/never-created").status_code == 404


def test_state_payload_survives_a_cache_outage(monkeypatch):
    client.post("/scenarios", json=CITY)

    class _BrokenCache:
        def put(self, *_a):
            raise RuntimeError("cache down")

        def get(self, *_a):
            return None

    monkeypatch.setattr(main, "state_cache", _BrokenCache())
    assert client.get("/simulation/state").status_code == 200   # cache error is swallowed


def test_make_state_cache_selects_redis_from_the_environment(monkeypatch):
    captured = {}

    class _FakeRedisCache:
        def __init__(self, url):
            captured["url"] = url

    monkeypatch.setattr(main, "RedisStateCache", _FakeRedisCache)
    monkeypatch.setenv("FIRESIM_REDIS_URL", "redis://host:6379/0")
    assert isinstance(main._make_state_cache(), _FakeRedisCache)
    assert captured["url"] == "redis://host:6379/0"

    monkeypatch.delenv("FIRESIM_REDIS_URL")
    assert isinstance(main._make_state_cache(), InMemoryStateCache)


@pytest.mark.skipif(
    not os.environ.get("FIRESIM_REDIS_URL"),
    reason="set FIRESIM_REDIS_URL to run against a live Redis server",
)
def test_redis_state_cache_roundtrip_against_a_live_server():
    cache = RedisStateCache(os.environ["FIRESIM_REDIS_URL"], ttl=30)
    cache.put("test-scenario", {"tick": 11})
    assert cache.get("test-scenario") == {"tick": 11}
