"""NATS adapter tests: the sync MessageBus bridge over an async client (E3, issue #25).

The bridge is exercised with an in-process fake NATS client, so the tests need no server.
``test_nats_bus_roundtrip_against_a_live_server`` runs the real adapter and is skipped unless
``FIRESIM_NATS_URL`` points at a running NATS server.
"""
import json
import os
import time
from types import SimpleNamespace

import pytest

import api.main as main
from messaging import TOPIC_EXTINGUISHED, EventPublisher, InMemoryBus
from messaging.nats_bus import NatsBus


class _FakeNats:
    """Minimal async NATS client that routes messages in-process (stands in for nats-py)."""

    def __init__(self) -> None:
        self._subs: dict[str, list] = {}
        self.published: list[tuple[str, bytes]] = []

    async def publish(self, subject: str, data: bytes) -> None:
        self.published.append((subject, data))
        for cb in self._subs.get(subject, []):
            await cb(SimpleNamespace(subject=subject, data=data))

    async def subscribe(self, subject: str, cb=None):
        self._subs.setdefault(subject, []).append(cb)
        return SimpleNamespace(subject=subject)

    async def drain(self) -> None:
        self._subs.clear()


def _fake_bus() -> tuple[NatsBus, _FakeNats]:
    fake = _FakeNats()

    async def connect(_servers: str) -> _FakeNats:
        return fake

    return NatsBus("nats://fake:4222", connect=connect), fake


def test_nats_bus_delivers_published_messages_to_subscribers():
    bus, _ = _fake_bus()
    got = []
    bus.subscribe("fire.state.v1", got.append)
    bus.publish("fire.state.v1", {"tick": 3, "counts": {"burning": 2}})
    bus.close()
    assert got == [{"tick": 3, "counts": {"burning": 2}}]


def test_nats_bus_encodes_payloads_as_json_bytes():
    bus, fake = _fake_bus()
    bus.publish("fire.snapshot.v1", {"tick": 1, "state": [[0, 2]]})
    bus.close()
    subject, data = fake.published[0]
    assert subject == "fire.snapshot.v1"
    assert json.loads(data.decode()) == {"tick": 1, "state": [[0, 2]]}


def test_event_publisher_works_over_the_nats_adapter():
    bus, _ = _fake_bus()
    got = []
    bus.subscribe(TOPIC_EXTINGUISHED, got.append)
    EventPublisher(bus).publish_extinguished(42)
    bus.close()
    assert got and got[0]["tick"] == 42


def test_make_bus_selects_the_adapter_from_the_environment(monkeypatch):
    created = {}

    class _FakeBus:
        def __init__(self, url):
            created["url"] = url

    monkeypatch.setattr(main, "NatsBus", _FakeBus)
    monkeypatch.setenv("FIRESIM_NATS_URL", "nats://host:4222")
    assert isinstance(main._make_bus(), _FakeBus) and created["url"] == "nats://host:4222"

    monkeypatch.delenv("FIRESIM_NATS_URL")
    assert isinstance(main._make_bus(), InMemoryBus)


@pytest.mark.skipif(
    not os.environ.get("FIRESIM_NATS_URL"),
    reason="set FIRESIM_NATS_URL to run against a live NATS server",
)
def test_nats_bus_roundtrip_against_a_live_server():
    bus = NatsBus(os.environ["FIRESIM_NATS_URL"])
    got = []
    bus.subscribe("fire.test.v1", got.append)
    bus.publish("fire.test.v1", {"tick": 7})
    time.sleep(0.3)
    bus.close()
    assert {"tick": 7} in got
