"""In-memory repositories: scenario CRUD and snapshot (Memento) storage (E6)."""
from persistence import (
    InMemoryScenarioRepository,
    InMemorySnapshotRepository,
    ScenarioRecord,
    Snapshot,
)


def test_scenario_repository_crud():
    repo = InMemoryScenarioRepository()
    rec = ScenarioRecord(id="a", name="Burn", payload={"seed": 1})
    repo.save(rec)
    assert repo.find("a") == rec and repo.all() == [rec]
    assert repo.delete("a") is True
    assert repo.delete("a") is False and repo.find("a") is None


def test_snapshots_come_back_in_tick_order_per_scenario():
    repo = InMemorySnapshotRepository()
    for tick in (30, 10, 20):
        repo.save(Snapshot(scenario_id="s1", tick=tick, state=[[tick]]))
    repo.save(Snapshot(scenario_id="s2", tick=5))
    assert [s.tick for s in repo.find_by_scenario("s1")] == [10, 20, 30]
    assert [s.tick for s in repo.find_by_scenario("s2")] == [5]
    assert repo.find_by_scenario("unknown") == []
