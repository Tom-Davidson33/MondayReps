"""
Electricity (NEM).

Outages    : TESTER.STPASA_DUIDAVAILABILITY + DUDETAIL (capacity) + DUDETAILSUMMARY
             (region) + GENUNITS (name/fuel). Latest run from STPASA_CASESOLUTION.
             Per-unit rows where forward PASA availability sits well below capacity.
Constraints: TESTER.DISPATCHCONSTRAINT — recently binding IDs as a watch proxy
             (there's no forward per-constraint table in the repos; flagged).
Δ vs last week: diff current outage DUIDs against a local snapshot in out/.
All tables/columns lifted from your price_drivers.py / data_fetcher.py.
"""
from __future__ import annotations
import json

import pandas as pd

import config
from connections import q
from contracts import Outage, Constraint

# Per-unit forward outages from the latest STPASA case
_SQL_OUTAGES = """
SELECT DD.STATIONNAME, DAU.DUID, DDET.REGIONID,
       DC.REGISTEREDCAPACITY,
       MIN(TRUNC(DAU.INTERVAL_DATETIME)) AS FROM_DATE,
       MAX(TRUNC(DAU.INTERVAL_DATETIME)) AS TO_DATE,
       MIN(DAU.GENERATION_PASA_AVAILABILITY) AS MIN_AVAIL
FROM TESTER.STPASA_DUIDAVAILABILITY DAU
JOIN TESTER.GENUNITS DD ON DAU.DUID = DD.GENSETID
JOIN TESTER.DUDETAILSUMMARY DDET
     ON DAU.DUID = DDET.DUID
     AND DAU.INTERVAL_DATETIME BETWEEN DDET.START_DATE AND DDET.END_DATE
JOIN (
    SELECT DUID, REGISTEREDCAPACITY FROM TESTER.DUDETAIL
    WHERE (DUID, LASTCHANGED) IN (
        SELECT DUID, MAX(LASTCHANGED) FROM TESTER.DUDETAIL GROUP BY DUID
    ) AND DISPATCHTYPE = 'GENERATOR'
) DC ON DAU.DUID = DC.DUID
WHERE DAU.RUN_DATETIME = (SELECT MAX(RUN_DATETIME) FROM TESTER.STPASA_CASESOLUTION)
  AND DAU.INTERVAL_DATETIME BETWEEN TRUNC(SYSDATE) AND TRUNC(SYSDATE) + 7
  AND DC.REGISTEREDCAPACITY > 30
  AND DAU.GENERATION_PASA_AVAILABILITY < DC.REGISTEREDCAPACITY * 0.5
GROUP BY DD.STATIONNAME, DAU.DUID, DDET.REGIONID, DC.REGISTEREDCAPACITY
ORDER BY DC.REGISTEREDCAPACITY DESC
"""

# Recently binding constraints (last 3 days) as a watch list
_SQL_CONSTR = """
SELECT CONSTRAINTID, COUNT(*) AS BIND_CT, MAX(ABS(MARGINALVALUE)) AS MAXMV
FROM TESTER.DISPATCHCONSTRAINT
WHERE SETTLEMENTDATE >= TRUNC(SYSDATE) - 3
  AND INTERVENTION = 0
  AND ABS(NVL(MARGINALVALUE, 0)) > 0
GROUP BY CONSTRAINTID
ORDER BY MAXMV DESC
FETCH FIRST 6 ROWS ONLY
"""


def _snapshot_path():
    config.SNAPSHOT_DIR.mkdir(exist_ok=True)
    return config.SNAPSHOT_DIR / "nem_outage_snapshot.json"


def read_outages() -> list[Outage]:
    df = q("me_market", _SQL_OUTAGES)

    # Δ vs last week
    prev = set()
    p = _snapshot_path()
    if p.exists():
        try:
            prev = set(json.loads(p.read_text()))
        except Exception:
            prev = set()
    current = set(df["DUID"].tolist())
    try:
        p.write_text(json.dumps(sorted(current)))
    except Exception:
        pass

    out: list[Outage] = []
    for _, r in df.iterrows():
        frm = pd.to_datetime(r["FROM_DATE"]); to = pd.to_datetime(r["TO_DATE"])
        is_new = r["DUID"] not in prev
        out.append(Outage(
            asset=str(r["STATIONNAME"] or r["DUID"]),
            region=str(r["REGIONID"] or ""),
            window=f"{frm:%a %d}\u2013{to:%a %d}",
            mw=f"{float(r['REGISTEREDCAPACITY']):.0f}",
            delta="new" if is_new else "ongoing",
            delta_dir="up" if is_new else "flat",
        ))
    return out


def read_constraints() -> list[Constraint]:
    df = q("me_market", _SQL_CONSTR)
    out: list[Constraint] = []
    for _, r in df.iterrows():
        out.append(Constraint(
            cid=str(r["CONSTRAINTID"]),
            note=f"bound {int(r['BIND_CT'])}x in last 3 days (max shadow "
                 f"${float(r['MAXMV']):,.0f}). Watch if it re-binds.",
            severity="watch",
        ))
    return out
