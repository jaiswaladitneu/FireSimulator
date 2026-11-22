"""Suppression listener (Epic E3).

Other Fireforce6 components (e.g. the suppression / tactics service) publish
suppression commands on the message bus. This listener subscribes to that topic
and applies the requested cells to the running engine, closing the loop between
the fire model and the rest of the system.

It depends only on the ``MessageBus`` port and on anything exposing
``apply_suppression``, so it stays decoupled from the concrete bus and engine.
"""
from __future__ import annotations

from .bus import MessageBus
from .events import TOPIC_SUPPRESSION


class SuppressionListener:
    """Subscribes to suppression commands and forwards them to the engine.

    Expected payload shape (JSON on ``TOPIC_SUPPRESSION``)::

        {"tick": <int>, "cells": [{"x": <int>, "y": <int>}, ...]}

    ``cells`` is required; any other fields are ignored so the contract can grow.
    Cells without ``x`` or ``y`` are skipped, and a command with no valid cells does
    nothing. ``SimulationEngine.apply_suppression`` queues the cells for its next tick.

    Attributes:
        bus: The message bus the listener is subscribed to.
        engine: Receiver of the cells: any object with an ``apply_suppression(cells)``
            method, e.g. a ``SimulationEngine``.
        received: Total number of cells forwarded to the engine so far.
    """

    def __init__(self, bus: MessageBus, engine) -> None:
        """Subscribe to ``TOPIC_SUPPRESSION`` on the bus.

        Args:
            bus: Message bus to listen on.
            engine: Object whose ``apply_suppression`` method receives a list of ``(x, y)``
                integer tuples.
        """
        self.bus = bus
        self.engine = engine
        self.received = 0
        bus.subscribe(TOPIC_SUPPRESSION, self._on_suppression)

    def _on_suppression(self, payload: dict) -> None:
        """Forward the valid cells of one suppression command to the engine."""
        cells = [
            (int(c["x"]), int(c["y"]))
            for c in payload.get("cells", [])
            if "x" in c and "y" in c
        ]
        if cells:
            self.engine.apply_suppression(cells)
            self.received += len(cells)
