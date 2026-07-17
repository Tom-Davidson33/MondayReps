"""
Gas trade timing.

Cheapest curve day = buy, dearest = sell. If Pelican is running hard, bias the call
to pre-buying the cheapest day that lands *before* the burn window.
"""
from __future__ import annotations
from contracts import GasTradeRec, CurvePoint, PelicanRec, Signal
import config


def evaluate(curve: list[CurvePoint], pelican: PelicanRec) -> GasTradeRec:
    if not curve:
        return GasTradeRec(buy_day="n/a", buy_price=0.0,
                           sell_day="n/a", sell_price=0.0, rationale="no curve data")
    buy = min(curve, key=lambda c: c.price)
    sell = max(curve, key=lambda c: c.price)
    running_hard = pelican.tj_day >= config.PELICAN_HARD_RUN_TJ
    rationale = ("pre-buy for Pelican burn" if running_hard else "curve extremes")
    return GasTradeRec(buy_day=buy.label, buy_price=buy.price,
                       sell_day=sell.label, sell_price=sell.price, rationale=rationale)


def signal(rec: GasTradeRec, pelican: PelicanRec) -> Signal | None:
    if rec.buy_day == "n/a" or pelican.tj_day < config.PELICAN_HARD_RUN_TJ:
        return None
    return Signal("GAS BUY", "opportunity",
                  f"Buy {rec.buy_day.split()[0]} ahead of Pelican run — implied curve is "
                  f"cheapest {rec.buy_day.split()[0]} (${rec.buy_price:.2f}/GJ) before the lift.")
