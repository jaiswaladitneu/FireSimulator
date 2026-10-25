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
    """

    def __init__(self, bus: MessageBus, engine) -> None:
        self.bus = bus
        self.engine = engine
        self.received = 0
        bus.subscribe(TOPIC_SUPPRESSION, self._on_suppression)

    def _on_suppression(self, payload: dict) -> None:
        cells = [
            (int(c["x"]), int(c["y"]))
            for c in payload.get("cells", [])
            if "x" in c and "y" in c
        ]
        if cells:
            self.engine.apply_suppression(cells)
            self.received += len(cells)
