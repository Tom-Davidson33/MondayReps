"""
Orchestration + freshness gate.

Enforces the dependency chain you flagged:
    GPG Nelder-Mead  ->  Godfather full run  ->  render
Godfather is only triggered once NM is confirmed fresh (NM feeds the gas demand
picture). If either can't be made fresh, we return all_fresh=False and the caller
applies config.STALE_POLICY — the report never silently ships stale numbers.
"""
from __future__ import annotations
from datetime import datetime

import config
from contracts import (ReportContext, FreshnessStamp)
from freshness import ensure_fresh
from sources import models, weather, nem, gas
from rules import bess, synergen, gas_trades, bluf


def _safe_read(name: str, reader, default):
    """
    Read one report section without letting a single source/DSN issue kill the
    whole render. The freshness banner/stale draft policy still tells the desk to
    review; this keeps --no-send useful while DB aliases or upstream commands are
    being fixed.
    """
    try:
        return reader()
    except Exception as exc:
        print(f"[source:{name}] unavailable: {exc}")
        return default


def _gate() -> FreshnessStamp:
    """Run the ordered freshness chain. Returns a stamp describing the outcome."""
    # 1) GPG Nelder-Mead first
    f = config.FRESHNESS["gpg_nm"]
    nm_ok, nm_ts = ensure_fresh(
        "gpg_nm", models.gpg_nm_last_updated, models.gpg_nm_trigger_run,
        f["max_age"], f["poll"], f["timeout"])

    gf_ok, gf_ts = False, None
    if nm_ok:
        # 2) Godfather only after NM is fresh (dependency respected)
        g = config.FRESHNESS["godfather"]
        gf_ok, gf_ts = ensure_fresh(
            "godfather", models.godfather_last_updated, models.godfather_trigger_run,
            g["max_age"], g["poll"], g["timeout"])
    else:
        print("[gate] skipping Godfather — NM not fresh")

    all_fresh = nm_ok and gf_ok
    detail = (f"NM {'OK' if nm_ok else 'STALE'} · Godfather {'OK' if gf_ok else 'STALE'}")
    return FreshnessStamp(nm_ts, gf_ts, all_fresh, detail)


def build_context(week_label: str, week_start: str) -> ReportContext:
    stamp = _gate()
    # Desk-safe "data current as at" — the effective pipeline time, no tool names.
    eff = stamp.godfather_updated or stamp.gpg_nm_updated or datetime.now()
    data_as_at = eff.strftime("%H:%M, %a %d %b")

    # ---- gather section data (deterministic sources only) ----
    wx = _safe_read("weather", weather.read_weather, [])
    outages = _safe_read("nem_outages", nem.read_outages, [])
    constraints = _safe_read("constraints", nem.read_constraints, [])
    lng = _safe_read("lng_outages", gas.read_lng_outages, [])
    curve = _safe_read("curve", models.read_curve, [])
    pelican = _safe_read("pelican", models.read_pelican,
                         models.empty_pelican("Forecast unavailable — review source logs."))
    pelican_daily = _safe_read("pelican_daily", models.read_pelican_daily, [])

    # ---- run rules ----
    # BESS spread still needs a VIC power-price forecast source (not in repos) — left
    # as an input. Synergen now uses the REAL forecast SA1 price (RRP_MAX) from the
    # Pelican daily model, which is the STPASA-demand-scaled reserve-gap implied price.
    bess_rec = bess.evaluate(am_spread=config.BESS_AM_SPREAD, pm_spread=config.BESS_PM_SPREAD)
    if pelican_daily:
        syn_rec = synergen.evaluate([(d.label, d.rrp_max) for d in pelican_daily])
    else:
        syn_rec = synergen.evaluate([])
    gt_rec = gas_trades.evaluate(curve, pelican)

    # ---- BLUF from fired signals ----
    calls = bluf.assemble(
        synergen.signal(syn_rec),
        gas_trades.signal(gt_rec, pelican),
        bess.signal(bess_rec),
    )

    # ---- charts (email-safe PNGs, base64-embedded) ----
    curve_png = pelican_png = ""
    try:
        import charts
        if curve:
            curve_png = charts.curve_chart(curve)
        if pelican_daily:
            pelican_png = charts.pelican_chart(pelican_daily)
    except Exception as e:  # never let a chart failure kill the report
        print(f"[charts] skipped: {e}")

    return ReportContext(
        week_label=week_label, week_start=week_start,
        generated_ts=datetime.now().strftime("%H:%M AEST, %a %d %b"),
        is_stale=not stamp.all_fresh, freshness=stamp, data_as_at=data_as_at,
        bluf=calls, weather=wx, nem_outages=outages, constraints=constraints,
        lng_outages=lng, curve=curve, pelican_daily=pelican_daily,
        curve_png=curve_png, pelican_png=pelican_png,
        bess=bess_rec, pelican=pelican, synergen=syn_rec, gas_trades=gt_rec,
        wind_bar_scale=config.WIND_BAR_SCALE_MW, gas_curve_scale=config.GAS_CURVE_BAR_SCALE,
    )
