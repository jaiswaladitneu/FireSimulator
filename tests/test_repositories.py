"""Repositories: scenario CRUD and snapshot (Memento) storage, in memory and on file (E6)."""
from persistence import (
    InMemoryScenarioRepository,
    InMemorySnapshotRepository,
    JsonFileSnapshotRepository,
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


def test_json_snapshot_repository_persists_across_reopen(tmp_path):
    path = tmp_path / "snaps.json"
    repo = JsonFileSnapshotRepository(path)
    repo.save(Snapshot(scenario_id="s1", tick=10, state=[[1, 2]]))
    repo.save(Snapshot(scenario_id="s1", tick=5, state=[[0]]))
    repo.save(Snapshot(scenario_id="s2", tick=7))

    reopened = JsonFileSnapshotRepository(path)
    assert [s.tick for s in reopened.find_by_scenario("s1")] == [5, 10]
    assert reopened.find_by_scenario("s1")[1].state == [[1, 2]]
    assert [s.tick for s in reopened.find_by_scenario("s2")] == [7]


def test_json_snapshot_repository_recovers_from_corrupt_file(tmp_path):
    path = tmp_path / "snaps.json"
    path.write_text("not valid json", encoding="utf-8")

    repo = JsonFileSnapshotRepository(path)        # moves the bad file aside, starts empty
    assert repo.find_by_scenario("s1") == []
    assert list(tmp_path.glob("snaps.corrupt-*.json"))

    repo.save(Snapshot(scenario_id="s1", tick=1))
    assert path.exists()
