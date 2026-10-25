"""Messaging tests: versioned event publishing and the suppression listener (E3)."""
from engine import SimulationEngine
from engine.cell import CellState
from engine.grid import Grid
from messaging.bus import InMemoryBus
from messaging.events import TOPIC_STATE, TOPIC_SUPPRESSION
from messaging.listener import SuppressionListener
from messaging.publisher import EventPublisher


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
