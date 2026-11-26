"""PostgreSQL repository tests (E6, issue #29).

The repositories are exercised against an in-process fake connection that records the SQL and
returns programmed rows, so the tests need no database. The live roundtrip test runs the real
``psycopg`` path and is skipped unless ``FIRESIM_DATABASE_URL`` is set.
"""
import json
import os
from types import SimpleNamespace

import pytest

import api.main as main
from persistence import InMemoryScenarioRepository, PostgresStore
from persistence.models import IncidentRecord, ScenarioRecord, Snapshot


class _FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.rowcount = 0
        self._rows = []

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False

    def execute(self, sql, params=None):
        self.conn.executed.append((sql, params))
        verb = sql.strip().split(None, 1)[0].upper()
        if verb == "SELECT":
            self._rows = self.conn.select_queue.pop(0) if self.conn.select_queue else []
        elif verb in ("DELETE", "INSERT", "UPDATE"):
            self.rowcount = self.conn.rowcount_queue.pop(0) if self.conn.rowcount_queue else 1

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class _FakeConn:
    def __init__(self):
        self.executed = []
        self.select_queue = []      # one row-list popped per SELECT
        self.rowcount_queue = []    # one int popped per write
        self.commits = 0
        self.closed = False

    def cursor(self):
        return _FakeCursor(self)

    def commit(self):
        self.commits += 1

    def close(self):
        self.closed = True


def _store() -> tuple[PostgresStore, _FakeConn]:
    conn = _FakeConn()
    return PostgresStore("postgresql://fake/db", connect=lambda _dsn: conn), conn


def _last(conn, verb):
    return next((row for row in reversed(conn.executed)
                 if row[0].strip().upper().startswith(verb)), None)


def test_store_creates_the_schema_on_connect():
    _store_obj, conn = _store()
    creates = [sql for sql, _ in conn.executed if sql.strip().upper().startswith("CREATE TABLE")]
    assert len(creates) == 3 and conn.commits >= 1
    assert {"scenarios", "snapshots", "incidents"} <= {w for sql in creates for w in sql.split()}


def test_scenario_repository_roundtrip():
    store, conn = _store()
    store.scenarios.save(ScenarioRecord(id="a", name="Burn", payload={"seed": 1}))
    sql, params = _last(conn, "INSERT")
    assert "scenarios" in sql and params[0] == "a" and params[1] == "Burn"
    assert json.loads(params[2]) == {"seed": 1}

    conn.select_queue.append([("a", "Burn", '{"seed": 1}')])
    assert store.scenarios.find("a") == ScenarioRecord(id="a", name="Burn", payload={"seed": 1})

    conn.select_queue.append([])
    assert store.scenarios.find("missing") is None

    conn.select_queue.append([("a", "Burn", "{}"), ("b", "Two", "{}")])
    assert [r.id for r in store.scenarios.all()] == ["a", "b"]

    conn.rowcount_queue.append(1)
    assert store.scenarios.delete("a") is True
    conn.rowcount_queue.append(0)
    assert store.scenarios.delete("a") is False


def test_snapshot_repository_roundtrip():
    store, conn = _store()
    store.snapshots.save(Snapshot(scenario_id="s", tick=5, state=[[0, 1]], timestamp=1.5))
    sql, params = _last(conn, "INSERT")
    assert "snapshots" in sql and params[0] == "s" and params[1] == 5 and params[3] == 1.5
    assert json.loads(params[2]) == [[0, 1]]

    conn.select_queue.append([("s", 5, "[[0, 1]]", 1.5), ("s", 10, "[[2]]", 2.0)])
    snaps = store.snapshots.find_by_scenario("s")
    assert [x.tick for x in snaps] == [5, 10] and snaps[0].state == [[0, 1]]


def test_incident_repository_roundtrip():
    store, conn = _store()
    rec = IncidentRecord(id="i", name="N", scenario_id="s", source="live",
                         outcome="extinguished", started_at=1.0, ended_at=2.0, ticks=3,
                         params={"a": 1}, summary={"x": 2})
    store.incidents.save(rec)
    sql, params = _last(conn, "INSERT")
    assert "incidents" in sql and params[0] == "i"
    assert json.loads(params[8]) == {"a": 1} and json.loads(params[9]) == {"x": 2}

    row = ("i", "N", "s", "live", "extinguished", 1.0, 2.0, 3, '{"a": 1}', '{"x": 2}')
    conn.select_queue.append([row])
    assert store.incidents.find("i") == rec
    conn.select_queue.append([row])
    assert len(store.incidents.all()) == 1

    conn.rowcount_queue.append(1)
    assert store.incidents.delete("i") is True
    conn.rowcount_queue.append(4)
    assert store.incidents.clear() == 4
    store.close()
    assert conn.closed is True


def test_make_repositories_selects_postgres_from_the_environment(monkeypatch):
    monkeypatch.setattr(main, "PostgresStore",
                        lambda url: SimpleNamespace(scenarios="S", incidents="I", snapshots="N"))
    monkeypatch.setenv("FIRESIM_DATABASE_URL", "postgresql://host/db")
    assert main._make_repositories() == ("S", "I", "N")

    monkeypatch.delenv("FIRESIM_DATABASE_URL")
    scenarios, _incidents, _snapshots = main._make_repositories()
    assert isinstance(scenarios, InMemoryScenarioRepository)


@pytest.mark.skipif(
    not os.environ.get("FIRESIM_DATABASE_URL"),
    reason="set FIRESIM_DATABASE_URL to run against a live PostgreSQL server",
)
def test_postgres_store_roundtrip_against_a_live_db():
    store = PostgresStore(os.environ["FIRESIM_DATABASE_URL"])
    store.incidents.clear()
    store.scenarios.save(ScenarioRecord(id="live-a", name="Live", payload={"seed": 9}))
    assert store.scenarios.find("live-a").payload == {"seed": 9}
    store.snapshots.save(Snapshot(scenario_id="live-a", tick=3, state=[[1]]))
    assert store.snapshots.find_by_scenario("live-a")[0].tick == 3
    assert store.scenarios.delete("live-a") is True
    store.close()
