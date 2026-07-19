"""
Model outputs feeding the report.

Pelican run : GPG_NM/models/gpg_forecast_latest.parquet (REGION='SA1').
              Columns written by GPG_NM main.py: GAS_DATE, REGION, FORECAST_TJ
              (and, on the combined path, GPG_TJ_PRED / GPG_MW_PRED).
Curve       : Godfather DWGM daily forecast. Godfather doesn't currently persist a
              daily curve file, so this reads GODFATHER_MODELS_DIR/dwgm_forecast_latest.parquet
              with columns GAS_DATE, PRICE ($/GJ). Add this 4-liner to the end of your
              Godfather run to produce it (result = model.forecast(...)):

                  df = result.to_dataframe()
                  df = df[df.SCHEDULE == "DAILY AVG"][["GAS_DATE", "FORECAST"]]
                  df = df.rename(columns={"FORECAST": "PRICE"})
                  df.to_parquet(GODFATHER_MODELS_DIR / "dwgm_forecast_latest.parquet", index=False)

Freshness readers/triggers below feed orchestrate.py's gate.
"""
from __future__ import annotations
import json
import shlex
import subprocess
from datetime import datetime
from typing import Optional

import pandas as pd

import config
from contracts import PelicanRec, CurvePoint


# ============================== GPG Nelder-Mead ==============================
def gpg_nm_last_updated() -> Optional[datetime]:
    if not config.GPG_META.exists():
        return None
    try:
        meta = json.loads(config.GPG_META.read_text())
        return datetime.strptime(meta["export_datetime"], "%Y-%m-%d %H:%M:%S")
    except Exception:
        return datetime.fromtimestamp(config.GPG_PARQUET.stat().st_mtime) \
            if config.GPG_PARQUET.exists() else None


def gpg_nm_trigger_run() -> None:
    """Run the upstream Pelican forecast command configured in .env."""
    if not str(config.GPG_NM_REPO_DIR):
        raise RuntimeError("GPG_NM_REPO_DIR is not set")
    subprocess.run(
        shlex.split(config.GPG_NM_COMMAND, posix=False),
        cwd=str(config.GPG_NM_REPO_DIR),
        check=True,
    )


def read_pelican() -> PelicanRec:
    try:
        df = pd.read_parquet(config.GPG_PARQUET)
    except (FileNotFoundError, OSError) as e:
        # missing model output must not kill the render — the freshness gate has
        # already flagged staleness; DRAFT_FLAGGED still wants a report out
        print(f"[models] pelican forecast unavailable: {e}")
        return PelicanRec(tj_day=0.0, mw=0.0, peak_days="—",
                          note="Forecast output missing — review before relying on this panel.")
    df["GAS_DATE"] = pd.to_datetime(df["GAS_DATE"])
    if "REGION" in df.columns:
        df = df[df["REGION"] == config.PELICAN_REGION]

    tj_col = "FORECAST_TJ" if "FORECAST_TJ" in df.columns else "GPG_TJ_PRED"
    fwd = df[df["GAS_DATE"] >= pd.Timestamp.today().normalize()].sort_values("GAS_DATE")

    tj = float(fwd[tj_col].mean()) if not fwd.empty else 0.0
    if "GPG_MW_PRED" in fwd.columns and not fwd.empty:
        mw = float(fwd["GPG_MW_PRED"].mean())
    else:
        mw = tj * 1000.0 / (config.GPG_HEAT_RATE * 24.0)  # TJ/day -> avg MW

    peak = fwd.nlargest(2, tj_col)["GAS_DATE"] if not fwd.empty else []
    peak_days = " & ".join(d.strftime("%a") for d in peak) + " PM" if len(peak) else "\u2014"

    return PelicanRec(tj_day=round(tj, 1), mw=round(mw, 0), peak_days=peak_days,
                      note="Nominate gas ahead of the peak burn window.")


# ================================ DWGM implied curve =========================
def godfather_last_updated() -> Optional[datetime]:
    if config.CURVE_PARQUET.exists():
        return datetime.fromtimestamp(config.CURVE_PARQUET.stat().st_mtime)
    return None


def godfather_trigger_run() -> None:
    """Run the upstream DWGM forecast command configured in .env."""
    if not str(config.GODFATHER_REPO_DIR):
        raise RuntimeError("GODFATHER_REPO_DIR is not set")
    subprocess.run(
        shlex.split(config.GODFATHER_COMMAND, posix=False),
        cwd=str(config.GODFATHER_REPO_DIR),
        check=True,
    )


def read_curve() -> list[CurvePoint]:
    """
    Read the DWGM implied gas price curve produced by the upstream forecast.

    Primary path is GODFATHER_MODELS_DIR/dwgm_forecast_latest.parquet with
    GAS_DATE + PRICE (or FORECAST). If that file is not available yet, fall back
    to the live GSH settled-trades VWAP curve so render-only previews still have
    a desk-safe curve panel.
    """
    if config.CURVE_PARQUET.exists():
        df = pd.read_parquet(config.CURVE_PARQUET)
        if "FORECAST" in df.columns and "PRICE" not in df.columns:
            df = df.rename(columns={"FORECAST": "PRICE"})
        df["GAS_DATE"] = pd.to_datetime(df["GAS_DATE"])
        df = (
            df[df["GAS_DATE"] >= pd.Timestamp.today().normalize()]
            .sort_values("GAS_DATE")
            .head(7)
        )
        if df.empty:
            return []
        lo, hi = df["PRICE"].min(), df["PRICE"].max()
        return [CurvePoint(r["GAS_DATE"].strftime("%a %d"), round(float(r["PRICE"]), 2),
                           is_min=(r["PRICE"] == lo), is_max=(r["PRICE"] == hi))
                for _, r in df.iterrows()]

    from connections import q
    import config as C
    sql = f"""
    SELECT TRUNC({C.GSH_TRADE_DATE_COL}) AS DELIV_DATE,
           SUM({C.GSH_TRADE_PRICE_COL} * {C.GSH_TRADE_QTY_COL})
             / NULLIF(SUM({C.GSH_TRADE_QTY_COL}), 0) AS VWAP
    FROM {C.GSH_TRADES_TABLE}
    WHERE TRUNC({C.GSH_TRADE_DATE_COL}) BETWEEN TRUNC(SYSDATE) AND TRUNC(SYSDATE) + 6
    GROUP BY TRUNC({C.GSH_TRADE_DATE_COL})
    ORDER BY DELIV_DATE
    """
    df = q("gas_market", sql)
    df["DELIV_DATE"] = pd.to_datetime(df["DELIV_DATE"])
    if df.empty:
        return []
    lo, hi = df["VWAP"].min(), df["VWAP"].max()
    return [CurvePoint(r["DELIV_DATE"].strftime("%a %d"), round(float(r["VWAP"]), 2),
                       is_min=(r["VWAP"] == lo), is_max=(r["VWAP"] == hi))
            for _, r in df.iterrows()]


# ================================ Pelican daily gas usage ===================
def read_pelican_daily() -> list:
    """
    Daily Pelican gas usage for the chart, from GPG_NM's compute_daily_gas_tj export.
    Add this to the end of your GPG_NM Pelican run so the parquet exists:
        daily = compute_daily_gas_tj(hh_df)
        daily.to_parquet(MODELS_DIR / "pelican_daily_latest.parquet", index=False)
    Columns used: GAS_DATE, PP_TJ, RUN_REASON, RRP_AVG, RRP_MAX.
    """
    from contracts import PelicanDay
    try:
        df = pd.read_parquet(config.PELICAN_DAILY_PARQUET)
    except (FileNotFoundError, OSError) as e:
        print(f"[models] pelican daily export unavailable: {e}")
        return []
    df["GAS_DATE"] = pd.to_datetime(df["GAS_DATE"])
    df = df[df["GAS_DATE"] >= pd.Timestamp.today().normalize()].sort_values("GAS_DATE").head(7)
    return [PelicanDay(r["GAS_DATE"].strftime("%a %d"), round(float(r["PP_TJ"]), 1),
                       str(r.get("RUN_REASON", "OFF")),
                       round(float(r.get("RRP_AVG", 0)), 0), round(float(r.get("RRP_MAX", 0)), 0))
            for _, r in df.iterrows()]
