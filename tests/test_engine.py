import numpy as np

from engine import CellState, Grid, Scenario, SimState, SimulationEngine
from engine.scenario import IgnitionPoint
from messaging.bus import InMemoryBus
from messaging.events import TOPIC_EXTINGUISHED, TOPIC_STATE
from messaging.publisher import EventPublisher


def _ignited_engine(seed=0):
    g = Grid(25, 25)
    eng = SimulationEngine(g, seed=seed)
    eng.ignite(12, 12)
    return eng


def test_lifecycle_transitions():
    eng = _ignited_engine()
    assert eng.state == SimState.IDLE
    eng.start()
    assert eng.state == SimState.RUNNING
    eng.pause()
    assert eng.state == SimState.PAUSED
    eng.start()
    assert eng.state == SimState.RUNNING


def test_step_advances_one_tick_and_pauses():
    eng = _ignited_engine()
    eng.step()
    assert eng.tick == 1
    assert eng.state == SimState.PAUSED


def test_fire_spreads_then_completes():
    eng = _ignited_engine()
    ticks = eng.run(max_ticks=2000)
    assert ticks > 0
    assert eng.state == SimState.COMPLETED
    counts = eng.counts()
    assert counts["burned"] > 1          # the fire spread beyond the ignition cell
    assert counts["burning"] == 0        # nothing left burning
    assert counts["igniting"] == 0


def test_runs_are_reproducible_with_same_seed():
    a = SimulationEngine.from_scenario(
        Scenario("s", width=30, height=30, seed=7, ignition_points=[IgnitionPoint(15, 15)])
    )
    b = SimulationEngine.from_scenario(
        Scenario("s", width=30, height=30, seed=7, ignition_points=[IgnitionPoint(15, 15)])
    )
    a.run(max_ticks=50)
    b.run(max_ticks=50)
    assert np.array_equal(a.grid.state, b.grid.state)


def test_reset_restores_initial_state():
    eng = _ignited_engine()
    eng.run(max_ticks=50)
    eng.reset()
    assert eng.tick == 0
    assert eng.state == SimState.IDLE
    assert eng.counts()["burning"] == 1  # back to just the ignition cell


def test_suppression_stops_cells_burning():
    g = Grid(9, 9)
    eng = SimulationEngine(g, seed=1)
    eng.ignite(4, 4)
    eng.apply_suppression([(4, 4)])
    eng.advance()
    assert eng.grid.get_state(4, 4) == CellState.SUPPRESSED


def test_closed_incident_ignores_step_and_start():
    eng = _ignited_engine()
    eng.stop()
    eng.step()
    eng.start()
    assert eng.state == SimState.COMPLETED
    assert eng.tick == 0


def test_speed_is_clamped_to_the_supported_range():
    eng = _ignited_engine()
    eng.set_speed(100)
    assert eng.speed == 16.0
    eng.set_speed(0)
    assert eng.speed == 0.25


def test_snapshot_is_a_memento_of_tick_and_cells():
    eng = _ignited_engine()
    eng.step()
    snap = eng.snapshot()
    assert snap["tick"] == 1
    assert snap["state"] == eng.grid.state.tolist()


def test_publisher_announces_when_the_fire_is_out():
    bus = InMemoryBus()
    eng = _ignited_engine()
    eng.publisher = EventPublisher(bus)
    eng.run(max_ticks=2000)
    topics = [topic for topic, _ in bus.published]
    assert eng.state == SimState.COMPLETED
    assert topics[-1] == TOPIC_EXTINGUISHED
    assert topics.count(TOPIC_STATE) == eng.tick   # one state update per tick
