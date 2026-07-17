"""
Synergen peaker rule.

Arm if any forecast evening peak clears the price trigger. Collects the qualifying
days so the desk knows exactly when to stand up.
"""
from __future__ import annotations
from contracts import SynergenRec, Signal
import config


def evaluate(exp_peaks: list[tuple[str, float]]) -> SynergenRec:
    """exp_peaks: [(day_label, expected_peak_price), ...]"""
    trig = config.SYNERGEN_PRICE_TRIGGER
    hits = [(d, p) for d, p in exp_peaks if p >= trig]
    fired = len(hits) > 0
    days = " & ".join(d.split()[0] for d, _ in hits) + " PM" if fired else ""
    return SynergenRec(fired=fired, trigger=trig, peaks=exp_peaks,
                       verdict="STANDBY / ARM" if fired else "NO RUN", days=days)


def signal(rec: SynergenRec) -> Signal | None:
    if not rec.fired:
        return None
    return Signal("SYNERGEN", "high",
                  f"Standby {rec.days} — STPASA implies ≥${rec.trigger:.0f} evening caps "
                  f"under low-wind, cold peaks.")
