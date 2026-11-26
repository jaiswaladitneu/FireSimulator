"""PostgreSQL-backed repositories (Epic E6).

Implements the scenario, snapshot and incident repository ports on PostgreSQL, so the
history survives restarts and can be shared by several API instances. The repositories keep
the same interfaces as the in-memory and JSON-file ones, so nothing in the domain changes;
``PostgresStore`` opens one connection, creates the schema if needed and hands out the three
repositories. JSON fields are stored as text (``json.dumps``) and parsed on read, so the
mapping does not depend on a driver's JSON handling.

The driver (``psycopg``) is imported lazily, so this module loads even where it is not
installed; a connection can also be injected (used by the tests).
"""
from __future__ import annotations

import json
from collections.abc import Callable

from .models import IncidentRecord, ScenarioRecord, Snapshot

SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS scenarios (
        seq        bigserial PRIMARY KEY,
        id         text UNIQUE NOT NULL,
        name       text NOT NULL,
        payload    text NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS snapshots (
        seq          bigserial PRIMARY KEY,
        scenario_id  text NOT NULL,
        tick         integer NOT NULL,
        state        text NOT NULL,
        ts           double precision NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS incidents (
        id          text PRIMARY KEY,
        name        text NOT NULL,
        scenario_id text NOT NULL,
        source      text NOT NULL,
        outcome     text NOT NULL,
        started_at  double precision NOT NULL,
        ended_at    double precision NOT NULL,
        ticks       integer NOT NULL,
        params      text NOT NULL,
        summary     text NOT NULL
    )
    """,
)


def _default_connect(dsn: str):
    """Open a PostgreSQL connection with ``psycopg`` (imported lazily)."""
    import psycopg
    return psycopg.connect(dsn)


class PostgresScenarioRepository:
    """``ScenarioRepository`` stored in the ``scenarios`` table."""

    def __init__(self, conn) -> None:
        """Use an open database connection.

        Args:
            conn: A DB-API connection (``psycopg``).
        """
        self._conn = conn

    def save(self, record: ScenarioRecord) -> None:
        """Insert or replace a scenario record (upsert on ``id``).

        Args:
            record: The record to store.
        """
        with self._conn.cursor() as cur:
            cur.execute(
                "INSERT INTO scenarios (id, name, payload) VALUES (%s, %s, %s) "
                "ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, payload = EXCLUDED.payload",
                (record.id, record.name, json.dumps(record.payload)),
            )
        self._conn.commit()

    def find(self, scenario_id: str) -> ScenarioRecord | None:
        """Look up a scenario record by id.

        Args:
            scenario_id: Id of the scenario.

        Returns:
            The record, or None if no record has this id.
        """
        with self._conn.cursor() as cur:
            cur.execute("SELECT id, name, payload FROM scenarios WHERE id = %s", (scenario_id,))
            row = cur.fetchone()
        return _scenario(row) if row else None

    def all(self) -> list[ScenarioRecord]:
        """List every scenario record in creation order.

        Returns:
            All stored records, oldest first.
        """
        with self._conn.cursor() as cur:
            cur.execute("SELECT id, name, payload FROM scenarios ORDER BY seq")
            rows = cur.fetchall()
        return [_scenario(r) for r in rows]

    def delete(self, scenario_id: str) -> bool:
        """Delete a scenario record.

        Args:
            scenario_id: Id of the scenario to delete.

        Returns:
            True if a record was deleted, False if no record had this id.
        """
        with self._conn.cursor() as cur:
            cur.execute("DELETE FROM scenarios WHERE id = %s", (scenario_id,))
            deleted = cur.rowcount
        self._conn.commit()
        return deleted > 0


class PostgresSnapshotRepository:
    """``SnapshotRepository`` stored in the ``snapshots`` table."""

    def __init__(self, conn) -> None:
        """Use an open database connection.

        Args:
            conn: A DB-API connection (``psycopg``).
        """
        self._conn = conn

    def save(self, snapshot: Snapshot) -> None:
        """Store a snapshot under its ``scenario_id``.

        Args:
            snapshot: The snapshot to store.
        """
        with self._conn.cursor() as cur:
            cur.execute(
                "INSERT INTO snapshots (scenario_id, tick, state, ts) VALUES (%s, %s, %s, %s)",
                (snapshot.scenario_id, snapshot.tick, json.dumps(snapshot.state),
                 snapshot.timestamp),
            )
        self._conn.commit()

    def find_by_scenario(self, scenario_id: str) -> list[Snapshot]:
        """List the snapshots saved for a scenario, ordered by tick.

        Args:
            scenario_id: Id of the scenario.

        Returns:
            The scenario's snapshots ordered by tick; empty if it has none.
        """
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT scenario_id, tick, state, ts FROM snapshots "
                "WHERE scenario_id = %s ORDER BY tick",
                (scenario_id,),
            )
            rows = cur.fetchall()
        return [Snapshot(scenario_id=r[0], tick=r[1], state=json.loads(r[2]), timestamp=r[3])
                for r in rows]


class PostgresIncidentRepository:
    """``IncidentRepository`` stored in the ``incidents`` table."""

    def __init__(self, conn) -> None:
        """Use an open database connection.

        Args:
            conn: A DB-API connection (``psycopg``).
        """
        self._conn = conn

    def save(self, record: IncidentRecord) -> None:
        """Insert or replace an incident record (upsert on ``id``).

        Args:
            record: The record to store.
        """
        with self._conn.cursor() as cur:
            cur.execute(
                "INSERT INTO incidents (id, name, scenario_id, source, outcome, started_at, "
                "ended_at, ticks, params, summary) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, "
                "scenario_id = EXCLUDED.scenario_id, source = EXCLUDED.source, "
                "outcome = EXCLUDED.outcome, started_at = EXCLUDED.started_at, "
                "ended_at = EXCLUDED.ended_at, ticks = EXCLUDED.ticks, "
                "params = EXCLUDED.params, summary = EXCLUDED.summary",
                (record.id, record.name, record.scenario_id, record.source, record.outcome,
                 record.started_at, record.ended_at, record.ticks,
                 json.dumps(record.params), json.dumps(record.summary)),
            )
        self._conn.commit()

    def find(self, incident_id: str) -> IncidentRecord | None:
        """Look up an incident record by id.

        Args:
            incident_id: Id of the incident.

        Returns:
            The record, or None if no record has this id.
        """
        with self._conn.cursor() as cur:
            cur.execute(f"SELECT {_INCIDENT_COLS} FROM incidents WHERE id = %s", (incident_id,))
            row = cur.fetchone()
        return _incident(row) if row else None

    def all(self) -> list[IncidentRecord]:
        """List every incident record, newest first.

        Returns:
            All stored records, the latest ``ended_at`` first.
        """
        with self._conn.cursor() as cur:
            cur.execute(f"SELECT {_INCIDENT_COLS} FROM incidents ORDER BY ended_at DESC")
            rows = cur.fetchall()
        return [_incident(r) for r in rows]

    def delete(self, incident_id: str) -> bool:
        """Delete an incident record.

        Args:
            incident_id: Id of the incident to delete.

        Returns:
            True if a record was deleted, False if no record had this id.
        """
        with self._conn.cursor() as cur:
            cur.execute("DELETE FROM incidents WHERE id = %s", (incident_id,))
            deleted = cur.rowcount
        self._conn.commit()
        return deleted > 0

    def clear(self) -> int:
        """Delete every incident record.

        Returns:
            The number of records deleted.
        """
        with self._conn.cursor() as cur:
            cur.execute("DELETE FROM incidents")
            deleted = cur.rowcount
        self._conn.commit()
        return deleted


_INCIDENT_COLS = ("id, name, scenario_id, source, outcome, started_at, ended_at, ticks, "
                  "params, summary")


def _scenario(row) -> ScenarioRecord:
    """Build a ``ScenarioRecord`` from a ``(id, name, payload)`` row."""
    return ScenarioRecord(id=row[0], name=row[1], payload=json.loads(row[2]))


def _incident(row) -> IncidentRecord:
    """Build an ``IncidentRecord`` from a row in ``_INCIDENT_COLS`` order."""
    return IncidentRecord(
        id=row[0], name=row[1], scenario_id=row[2], source=row[3], outcome=row[4],
        started_at=row[5], ended_at=row[6], ticks=row[7],
        params=json.loads(row[8]), summary=json.loads(row[9]),
    )


class PostgresStore:
    """Opens one PostgreSQL connection, ensures the schema, and hands out the repositories.

    Attributes:
        conn: The open database connection.
        scenarios: ``PostgresScenarioRepository`` on this connection.
        snapshots: ``PostgresSnapshotRepository`` on this connection.
        incidents: ``PostgresIncidentRepository`` on this connection.
    """

    def __init__(self, dsn: str, *, connect: Callable[[str], object] | None = None) -> None:
        """Connect, create the schema if needed, and build the repositories.

        Args:
            dsn: PostgreSQL connection string, e.g. ``postgresql://user:pw@host/db``.
            connect: Optional factory returning a connection (for tests); by default it
                connects with ``psycopg``.
        """
        self.conn = (connect or _default_connect)(dsn)
        self._ensure_schema()
        self.scenarios = PostgresScenarioRepository(self.conn)
        self.snapshots = PostgresSnapshotRepository(self.conn)
        self.incidents = PostgresIncidentRepository(self.conn)

    def _ensure_schema(self) -> None:
        """Create the tables if they do not exist."""
        with self.conn.cursor() as cur:
            for statement in SCHEMA:
                cur.execute(statement)
        self.conn.commit()

    def close(self) -> None:
        """Close the database connection."""
        self.conn.close()
