"""Live-state cache (Epic E6): the latest state of each run, for fast reads and resync.

``StateCache`` is the port (GoF Repository/Adapter). ``InMemoryStateCache`` keeps the latest
state in a process dict; ``RedisStateCache`` stores it in Redis so the current state of a
running incident is shared across API instances and survives a restart. The cache is
optional — the simulator runs on the in-memory cache by default.
"""
from __future__ import annotations

import json
from typing import Protocol


class StateCache(Protocol):
    """Port for caching the latest live state of each scenario, keyed by scenario id."""

    def put(self, scenario_id: str, state: dict) -> None:
        """Store the latest state for a scenario, replacing any previous value.

        Args:
            scenario_id: Id of the scenario the state belongs to.
            state: The live state payload (as returned by ``GET /simulation/state``).
        """
        ...

    def get(self, scenario_id: str) -> dict | None:
        """Return the cached latest state for a scenario, or None if there is none.

        Args:
            scenario_id: Id of the scenario.

        Returns:
            The cached state payload, or None.
        """
        ...


class InMemoryStateCache:
    """``StateCache`` that keeps the latest state per scenario in a process dict.

    Values are lost when the process exits; use ``RedisStateCache`` to share them.
    """

    def __init__(self) -> None:
        """Create an empty cache."""
        self._store: dict[str, dict] = {}

    def put(self, scenario_id: str, state: dict) -> None:
        """Store the latest state for a scenario.

        Args:
            scenario_id: Id of the scenario.
            state: The live state payload.
        """
        self._store[scenario_id] = state

    def get(self, scenario_id: str) -> dict | None:
        """Return the cached state for a scenario, or None.

        Args:
            scenario_id: Id of the scenario.

        Returns:
            The cached state payload, or None if the scenario has none.
        """
        return self._store.get(scenario_id)


class RedisStateCache:
    """``StateCache`` backed by Redis, so the live state is shared and survives a restart.

    State is stored as JSON under ``firesim:state:<scenario_id>`` with a time-to-live, so a
    stale run's state expires on its own.

    Attributes:
        ttl: Seconds each cached state lives before Redis expires it.
    """

    def __init__(
        self, url: str = "redis://127.0.0.1:6379/0", *, client=None, ttl: int = 3600,
    ) -> None:
        """Connect to Redis (or use an injected client) and set the entry lifetime.

        Args:
            url: Redis URL, e.g. ``redis://host:6379/0``.
            client: Optional Redis client to use instead of connecting (for tests).
            ttl: Seconds each cached state lives before it expires.
        """
        if client is None:
            import redis
            client = redis.Redis.from_url(url)
        self._r = client
        self.ttl = ttl

    @staticmethod
    def _key(scenario_id: str) -> str:
        """Return the Redis key a scenario's state is stored under."""
        return f"firesim:state:{scenario_id}"

    def put(self, scenario_id: str, state: dict) -> None:
        """Store the latest state as JSON with the configured TTL.

        Args:
            scenario_id: Id of the scenario.
            state: The live state payload.
        """
        self._r.set(self._key(scenario_id), json.dumps(state), ex=self.ttl)

    def get(self, scenario_id: str) -> dict | None:
        """Return the cached state for a scenario, or None if absent or expired.

        Args:
            scenario_id: Id of the scenario.

        Returns:
            The cached state payload, or None.
        """
        raw = self._r.get(self._key(scenario_id))
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode()
        return json.loads(raw)
