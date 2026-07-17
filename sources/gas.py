"""
Gas — LNG / supply outages.
Source: GSH.GAS_MEDIUM_TERM_CAP_OUTLOOK joined to GSH.GAS_FACILITY_SUMMARY.
Query lifted verbatim from your Godfather price_drivers.py (the MT capacity outlook).
"""
from __future__ import annotations
import pandas as pd

from connections import q
from contracts import LngOutage

_SQL = """
SELECT
    FS.FACILITYNAME,
    O.FROMGASDATE,
    O.TOGASDATE,
    O.OUTLOOKQUANTITY,
    O.DESCRIPTION
FROM GSH.GAS_MEDIUM_TERM_CAP_OUTLOOK O
LEFT JOIN (
    SELECT DISTINCT FACILITYID, FACILITYNAME FROM GSH.GAS_FACILITY_SUMMARY
) FS ON FS.FACILITYID = O.FACILITYID
WHERE O.ACTIVEFLAG = 1
  AND O.DISABLEDDATETIME IS NULL
  AND O.TOGASDATE >= TRUNC(SYSDATE)
  AND O.FROMGASDATE < O.TOGASDATE
  AND (O.DESCRIPTION IS NULL OR O.DESCRIPTION != 'Production')
  AND O.FROMGASDATE <= TRUNC(SYSDATE) + 7
ORDER BY O.FROMGASDATE
"""


def read_lng_outages() -> list[LngOutage]:
    df = q("gas_market", _SQL)
    out: list[LngOutage] = []
    for _, r in df.iterrows():
        frm = pd.to_datetime(r["FROMGASDATE"])
        to = pd.to_datetime(r["TOGASDATE"])
        qty = r["OUTLOOKQUANTITY"]
        out.append(LngOutage(
            facility=str(r["FACILITYNAME"] or "Unknown"),
            kind="Planned",
            window=f"{frm:%a %d}\u2013{to:%a %d}",
            tj_day=f"{float(qty):.0f}" if pd.notna(qty) else "\u2014",
            note=str(r["DESCRIPTION"] or "capacity reduction"),
            note_dir="down",
        ))
    return out
