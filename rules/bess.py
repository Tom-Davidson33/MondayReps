"""
BESS 2-cycle rule.

A second cycle is only worth it when BOTH the morning and evening spreads clear the
threshold — i.e. there's a genuine arb on both peaks. Pure function: numbers in,
verdict out. No hidden state.
"""
from __future__ import annotations
from contracts import BessRec, Signal
import config


def evaluate(am_spread: float, pm_spread: float, days: str = "Thu & Fri") -> BessRec:
    thr = config.BESS_SPREAD_THRESHOLD
    two_cycle = am_spread >= thr and pm_spread >= thr
    one_cycle = (am_spread >= thr) ^ (pm_spread >= thr)
    verdict = "RUN 2 CYCLES" if two_cycle else ("1 CYCLE" if one_cycle else "HOLD")
    return BessRec(fired=two_cycle, am_spread=am_spread, pm_spread=pm_spread,
                   threshold=thr, verdict=verdict, days=days if two_cycle else "")


def signal(rec: BessRec) -> Signal | None:
    if not rec.fired:
        return None
    return Signal("BESS 2-CYCLE", "info",
                  f"{rec.days} — both AM (${rec.am_spread:.0f}) and PM (${rec.pm_spread:.0f}) "
                  f"spreads clear the ${rec.threshold:.0f}/MWh 2-cycle threshold.")
