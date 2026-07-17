"""
BLUF assembler. Collects the Signals that actually fired and orders them so the
sharpest risk is read first. Only fired rules appear — no filler lines.
"""
from __future__ import annotations
from contracts import Signal

_ORDER = {"high": 0, "opportunity": 1, "info": 2, "watch": 3}


def assemble(*signals: Signal | None, extra_watch: list[Signal] | None = None) -> list[Signal]:
    live = [s for s in signals if s is not None]
    if extra_watch:
        live += extra_watch
    return sorted(live, key=lambda s: _ORDER.get(s.severity, 9))
