"""
Data contract. The Jinja template renders ONLY what is in ReportContext — nothing
is invented downstream. Every field here is produced by a source adapter or a rule.
This is the boundary that keeps the report honest.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime


# ---- weather ----------------------------------------------------------------
@dataclass
class WeatherDay:
    label: str          # "Mon 13"
    edd: float
    tmin: float
    tmax: float
    wind_mw: int
    solar_mw: int


# ---- electricity ------------------------------------------------------------
@dataclass
class Outage:
    asset: str
    region: str
    window: str
    mw: str
    delta: str          # "new" | "unchanged" | "returned early" | ...
    delta_dir: str      # "up" | "down" | "flat"  -> drives colour


@dataclass
class Constraint:
    cid: str            # e.g. "V::S_HEYWOOD"
    note: str
    severity: str       # "watch" | "info"


# ---- gas --------------------------------------------------------------------
@dataclass
class LngOutage:
    facility: str
    kind: str           # "Planned" | "Maint." | "Unplanned"
    window: str
    tj_day: str
    note: str
    note_dir: str       # "up" | "down" | "flat"


@dataclass
class CurvePoint:
    label: str          # "Wed 15"
    price: float        # $/GJ
    is_min: bool = False
    is_max: bool = False


@dataclass
class PelicanDay:
    label: str          # "Wed 15"
    tj: float           # daily gas usage TJ
    reason: str         # dominant RUN_REASON (ECONOMIC/NSCAS/SSM/OFF)
    rrp_avg: float      # implied SA1 price $/MWh
    rrp_max: float


# ---- recommendations --------------------------------------------------------
@dataclass
class Signal:
    """A BLUF line. Only emitted when a rule fires."""
    tag: str            # "SYNERGEN"
    severity: str       # "high" | "opportunity" | "watch" | "info"
    headline: str


@dataclass
class BessRec:
    fired: bool
    am_spread: float
    pm_spread: float
    threshold: float
    verdict: str        # "RUN 2 CYCLES" | "1 CYCLE" | "HOLD"
    days: str


@dataclass
class PelicanRec:
    tj_day: float
    mw: float
    peak_days: str
    note: str


@dataclass
class SynergenRec:
    fired: bool
    trigger: float
    peaks: list          # list[tuple[str, float]]  (day, exp price)
    verdict: str         # "STANDBY / ARM" | "NO RUN"
    days: str


@dataclass
class GasTradeRec:
    buy_day: str
    buy_price: float
    sell_day: str
    sell_price: float
    rationale: str


# ---- freshness --------------------------------------------------------------
@dataclass
class FreshnessStamp:
    gpg_nm_updated: datetime | None
    godfather_updated: datetime | None
    all_fresh: bool
    detail: str          # human-readable status for the footer / alert


# ---- top-level context ------------------------------------------------------
@dataclass
class ReportContext:
    week_label: str
    week_start: str
    generated_ts: str
    is_stale: bool
    freshness: FreshnessStamp
    data_as_at: str = ""          # desk-safe "data current as at" timestamp (no tool names)
    bluf: list = field(default_factory=list)           # list[Signal]
    weather: list = field(default_factory=list)         # list[WeatherDay]
    nem_outages: list = field(default_factory=list)     # list[Outage]
    constraints: list = field(default_factory=list)     # list[Constraint]
    lng_outages: list = field(default_factory=list)     # list[LngOutage]
    curve: list = field(default_factory=list)           # list[CurvePoint]
    pelican_daily: list = field(default_factory=list)    # list[PelicanDay]
    curve_png: str = ""                                  # base64 data URI
    pelican_png: str = ""                                # base64 data URI
    bess: BessRec = None
    pelican: PelicanRec = None
    synergen: SynergenRec = None
    gas_trades: GasTradeRec = None
    # config echoed for the template's bar-chart scaling
    wind_bar_scale: float = 3000.0
    gas_curve_scale: float = 14.0
