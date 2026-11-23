from persistence import IncidentRecord, JsonFileIncidentRepository


def _record(rid: str = "a", ended: float = 2.0) -> IncidentRecord:
    return IncidentRecord(
        id=rid, name="Burn", scenario_id="s", source="live", outcome="extinguished",
        started_at=1.0, ended_at=ended, ticks=10, params={"seed": 1},
        summary={"timeline": [{"t": 0}], "key_events": [], "population": {"total": 3}},
    )


def test_json_repository_survives_a_restart(tmp_path):
    path = tmp_path / "incidents.json"
    JsonFileIncidentRepository(path).save(_record())
    again = JsonFileIncidentRepository(path)
    assert again.find("a") == _record()
    assert "timeline" not in again.find("a").brief()["summary"]
    assert again.delete("a")
    assert JsonFileIncidentRepository(path).all() == []


def test_history_is_newest_first(tmp_path):
    repo = JsonFileIncidentRepository(tmp_path / "incidents.json")
    repo.save(_record("old", ended=1.0))
    repo.save(_record("new", ended=5.0))
    assert [r.id for r in repo.all()] == ["new", "old"]
    assert repo.clear() == 2 and repo.all() == []


def test_corrupt_file_is_moved_aside(tmp_path):
    path = tmp_path / "incidents.json"
    path.write_text("{not json", encoding="utf-8")
    repo = JsonFileIncidentRepository(path)
    assert repo.all() == []
    assert not path.exists()
    assert list(tmp_path.glob("incidents.corrupt-*.json"))
