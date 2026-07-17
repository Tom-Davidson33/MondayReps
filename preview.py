"""
Preview the report layout WITHOUT a database — uses representative sample data.
    python preview.py         # writes out/tom_monday_report.html and opens it
Use this to iterate on the look. run_report.py is the real, DB-backed pipeline.
"""
from __future__ import annotations
import datetime as dt, webbrowser
from pathlib import Path
import pandas as pd

import connections
def _fake_q(alias, sql, params=None):
    s = sql.upper()
    if "WEATHER_DAILY_FORECASTS" in s:
        return pd.DataFrame({"GAS_DATE":pd.date_range("2026-07-13",periods=7),
            "TMAX":[11,10,12,9,9,12,13],"TMIN":[3,2,4,1,2,3,4],"EDD":[18,20,17,21,21,17,15]})
    if "STPASA_REGIONSOLUTION" in s:
        return pd.DataFrame({"GAS_DATE":pd.date_range("2026-07-13",periods=7),
            "WIND_MW":[1840,1120,2410,640,760,1980,2230],"SOLAR_MW":[1020,940,1180,880,910,1240,1300]})
    if "GAS_MEDIUM_TERM_CAP_OUTLOOK" in s:
        return pd.DataFrame({"FACILITYNAME":["QCLNG T2","Longford"],
            "FROMGASDATE":[pd.Timestamp("2026-07-14"),pd.Timestamp("2026-07-13")],
            "TOGASDATE":[pd.Timestamp("2026-07-15"),pd.Timestamp("2026-07-16")],
            "OUTLOOKQUANTITY":[300,180],"DESCRIPTION":["Maintenance","Maintenance"]})
    if "STPASA_DUIDAVAILABILITY" in s:
        return pd.DataFrame({"STATIONNAME":["Loy Yang A","Bayswater"],"DUID":["LYA2","BW03"],
            "REGIONID":["VIC1","NSW1"],"REGISTEREDCAPACITY":[530,660],
            "FROM_DATE":[pd.Timestamp("2026-07-13")]*2,"TO_DATE":[pd.Timestamp("2026-07-16")]*2,
            "MIN_AVAIL":[0,0]})
    if "DISPATCHCONSTRAINT" in s:
        return pd.DataFrame({"CONSTRAINTID":["V::S_HEYWOOD"],"BIND_CT":[12],"MAXMV":[250.0]})
    return pd.DataFrame()

connections.q = _fake_q
import sources.weather, sources.nem, sources.gas
sources.weather.q = _fake_q; sources.nem.q = _fake_q; sources.gas.q = _fake_q
import sources.models as M
def _fake_parquet(p):
    s = str(p).lower()
    if "pelican_daily" in s:
        return pd.DataFrame({"GAS_DATE":pd.date_range("2026-07-13",periods=7),
            "PP_TJ":[14,9,22,31,28,12,10],
            "RUN_REASON":["NSCAS","OFF","ECONOMIC","ECONOMIC","SSM","NSCAS","OFF"],
            "RRP_AVG":[95,60,140,320,180,90,70],
            "RRP_MAX":[210,120,640,1180,1040,150,110]})
    if "gpg" in s:
        return pd.DataFrame({"GAS_DATE":pd.date_range("2026-07-13",periods=7),"REGION":["SA1"]*7,
                             "FORECAST_TJ":[32,28,35,40,38,30,29]})
    return pd.DataFrame()
M.pd.read_parquet = _fake_parquet
# GSH curve comes via connections.q now:
def _fake_q_curve(alias, sql, params=None):
    if "DELIV_DATE" in sql or "GSH_TRADE" in sql.upper() or "VWAP" in sql.upper():
        return pd.DataFrame({"DELIV_DATE":pd.date_range("2026-07-13",periods=7),
            "VWAP":[11.8,11.55,11.2,12.9,13.4,12.1,11.7]})
    return _fake_q(alias, sql, params)
connections.q = _fake_q_curve
M.gpg_nm_last_updated = lambda: dt.datetime.now()
M.godfather_last_updated = lambda: dt.datetime.now()

import orchestrate, render
ctx = orchestrate.build_context("Mon 13 – Sun 19 Jul 2026", "13 Jul 2026")
path = render.render_to_file(ctx)
print("preview ->", path)
try: webbrowser.open(f"file://{Path(path).resolve()}")
except Exception: pass
