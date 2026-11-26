"""Messaging tests: versioned event publishing and the suppression listener (E3)."""
from engine import SimulationEngine
from engine.cell import CellState
from engine.grid import Grid
from messaging.bus import InMemoryBus
from messaging.events import (
    TOPIC_EXTINGUISHED,
    TOPIC_SNAPSHOT,
    TOPIC_SPREAD,
    TOPIC_STATE,
    TOPIC_SUPPRESSION,
)
from messaging.listener import SuppressionListener
from messaging.publisher import EventPublisher
from persistence import InMemorySnapshotRepository, SnapshotArchiver


def _engine() -> SimulationEngine:
    grid = Grid(10, 10)
    grid.ignite(5, 5)
    return SimulationEngine(grid, seed=1)


def test_publisher_emits_versioned_state_events():
    bus = InMemoryBus()
    eng = _engine()
    eng.publisher = EventPublisher(bus)

    eng.start()
    eng.advance()

    topics = [topic for topic, _ in bus.published]
    assert TOPIC_STATE in topics
    assert all(payload.get("version") == "1" for _, payload in bus.published)


def test_engine_emits_periodic_snapshot_events_for_resync():
    bus = InMemoryBus()
    eng = _engine()
    eng.publisher = EventPublisher(bus)
    eng.snapshot_every = 2

    eng.start()
    for _ in range(5):          # ticks 1..5
        eng.advance()

    snaps = [payload for topic, payload in bus.published if topic == TOPIC_SNAPSHOT]
    assert [s["tick"] for s in snaps] == [2, 4]            # every 2nd tick
    assert len(snaps[0]["state"]) == 10 and len(snaps[0]["state"][0]) == 10


def test_no_snapshot_events_when_interval_is_zero():
    bus = InMemoryBus()
    eng = _engine()
    eng.publisher = EventPublisher(bus)        # snapshot_every defaults to 0
    eng.start()
    eng.advance()
    assert not any(topic == TOPIC_SNAPSHOT for topic, _ in bus.published)


def test_snapshot_archiver_persists_snapshot_events_to_repo():
    repo = InMemorySnapshotRepository()
    bus = InMemoryBus()
    bus.subscribe(TOPIC_SNAPSHOT, SnapshotArchiver(repo, "scenX").handle)
    eng = _engine()
    eng.publisher = EventPublisher(bus)
    eng.snapshot_every = 2

    eng.start()
    for _ in range(4):          # ticks 1..4 -> snapshots at 2 and 4
        eng.advance()

    saved = repo.find_by_scenario("scenX")
    assert [s.tick for s in saved] == [2, 4]
    assert all(s.scenario_id == "scenX" for s in saved)
    assert len(saved[0].state) == 10


def test_suppression_listener_applies_cells_to_engine():
    bus = InMemoryBus()
    eng = _engine()
    listener = SuppressionListener(bus, eng)

    # An external component asks us to suppress a burning cell.
    eng.grid.ignite(2, 2)
    bus.publish(TOPIC_SUPPRESSION, {"tick": 0, "cells": [{"x": 2, "y": 2}]})
    assert listener.received == 1

    # Suppression is queued and takes effect on the next tick.
    eng.start()
    eng.advance()
    assert eng.grid.get_state(2, 2) == CellState.SUPPRESSED


def test_suppression_listener_ignores_empty_payload():
    bus = InMemoryBus()
    listener = SuppressionListener(bus, _engine())
    bus.publish(TOPIC_SUPPRESSION, {"cells": []})
    assert listener.received == 0


def test_publisher_uses_one_versioned_topic_per_event_type():
    bus = InMemoryBus()
    pub = EventPublisher(bus)
    pub.publish_spread(3, {"burning": 4})
    pub.publish_extinguished(9)
    pub.publish_snapshot(5, [[0, 2], [3, 0]])

    (t1, spread), (t2, out), (t3, snap) = bus.published
    assert (t1, t2, t3) == (TOPIC_SPREAD, TOPIC_EXTINGUISHED, TOPIC_SNAPSHOT)
    assert spread["tick"] == 3 and spread["counts"] == {"burning": 4}
    assert out == {"tick": 9, "version": "1", "timestamp": out["timestamp"]}
    assert snap["state"] == [[0, 2], [3, 0]] and snap["version"] == "1"
