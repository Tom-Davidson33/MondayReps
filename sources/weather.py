"""
Weather & renewables.

EDD / min / max  : WEATHERZONE.WEATHER_DAILY_FORECASTS (latest ISSUETIME per VALIDTIME)
Wind / solar MW  : TESTER.STPASA_REGIONSOLUTION (SS_WIND_UIGF, SS_SOLAR_UIGF, latest run)
Both queries are lifted from your Godfather price_drivers.py.
"""
from __future__ import annotations
from datetime import date, timedelta

import pandas as pd

import config
from connections import q
from contracts import WeatherDay

# forward EDD / temps for the week ahead, Melbourne station
_SQL_WX = """
SELECT TRUNC(VALIDTIME) AS GAS_DATE, TMAX, TMIN, EDD
FROM WEATHERZONE.WEATHER_DAILY_FORECASTS
WHERE (TRUNC(VALIDTIME), ISSUETIME) IN (
    SELECT TRUNC(VALIDTIME), MAX(ISSUETIME)
    FROM WEATHERZONE.WEATHER_DAILY_FORECASTS
    WHERE STATIONID = :station
      AND TRUNC(VALIDTIME) BETWEEN TRUNC(SYSDATE) AND TRUNC(SYSDATE) + 7
    GROUP BY TRUNC(VALIDTIME)
)
AND STATIONID = :station
ORDER BY VALIDTIME ASC
"""

# forward wind/solar MW from the latest STPASA run: sum across portfolio regions
# per interval, then average the intervals within each day (a straight SUM over
# the ~48 daily intervals would inflate MW by ~48x)
_SQL_RENEW = """
WITH per_interval AS (
    SELECT TRUNC(INTERVAL_DATETIME) AS GAS_DATE,
           SUM(SS_WIND_UIGF)  AS WIND_MW,
           SUM(SS_SOLAR_UIGF) AS SOLAR_MW
    FROM TESTER.STPASA_REGIONSOLUTION
    WHERE RUN_DATETIME = (SELECT MAX(RUN_DATETIME) FROM TESTER.STPASA_REGIONSOLUTION)
      AND REGIONID IN ({regions})
      AND INTERVAL_DATETIME > SYSDATE
      AND INTERVAL_DATETIME <= SYSDATE + 8
    GROUP BY TRUNC(INTERVAL_DATETIME), INTERVAL_DATETIME
)
SELECT GAS_DATE, AVG(WIND_MW) AS WIND_MW, AVG(SOLAR_MW) AS SOLAR_MW
FROM per_interval GROUP BY GAS_DATE ORDER BY GAS_DATE
"""


def read_weather() -> list[WeatherDay]:
    wx = q("gas_market", _SQL_WX, {"station": config.MELBOURNE_STATION})

    reg_binds = {f"r{i}": r for i, r in enumerate(config.WEATHER_REGIONS)}
    reg_sql = ",".join(f":{k}" for k in reg_binds)
    try:
        rn = q("me_market", _SQL_RENEW.format(regions=reg_sql), reg_binds)
    except Exception as exc:
        # MEMARKET/TNS problems should not erase the gas-market weather rows.
        # Render EDD/min/max and leave wind/solar at 0 until MEMARKET is fixed.
        print(f"[weather] renewables unavailable: {exc}")
        rn = pd.DataFrame(columns=["GAS_DATE", "WIND_MW", "SOLAR_MW"])

    wx["GAS_DATE"] = pd.to_datetime(wx["GAS_DATE"])
    rn["GAS_DATE"] = pd.to_datetime(rn["GAS_DATE"])
    df = wx.merge(rn, on="GAS_DATE", how="left").sort_values("GAS_DATE")

    out: list[WeatherDay] = []
    for _, r in df.iterrows():
        out.append(WeatherDay(
            label=r["GAS_DATE"].strftime("%a %d"),
            edd=round(float(r["EDD"]), 1) if pd.notna(r["EDD"]) else 0.0,
            tmin=round(float(r["TMIN"]), 1) if pd.notna(r["TMIN"]) else 0.0,
            tmax=round(float(r["TMAX"]), 1) if pd.notna(r["TMAX"]) else 0.0,
            wind_mw=int(r["WIND_MW"]) if pd.notna(r.get("WIND_MW")) else 0,
            solar_mw=int(r["SOLAR_MW"]) if pd.notna(r.get("SOLAR_MW")) else 0,
        ))
    return out
