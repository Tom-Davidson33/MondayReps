"""
Model outputs feeding the report.

Pelican run : GPG_NM/models/gpg_forecast_latest.parquet (REGION='SA1').
              Columns written by GPG_NM main.py: GAS_DATE, REGION, FORECAST_TJ
              (and, on the combined path, GPG_TJ_PRED / GPG_MW_PRED).
Curve       : Godfather DWGM daily forecast. Reads either
              GODFATHER_MODELS_DIR/dwgm_forecast_latest.parquet or the existing
              Godfather pickle at GODFATHER_FORECAST_PATH / dwgm_forecast.pkl.

Freshness readers/triggers below feed orchestrate.py's gate.
"""
from __future__ import annotations
import json
import shlex
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

import config
from contracts import PelicanRec, CurvePoint


_DEFAULT_COMMAND = "python main.py"
_ENTRY_CANDIDATES = (
    "main.py",
    "run.py",
    "forecast.py",
    "dwgm_forecast.py",
    "run_forecast.py",
    "godfather.py",
)


def _command_parts(command: str) -> list[str]:
    return shlex.split(command, posix=False)


def _resolve_python_command(repo_dir: Path, command: str, env_key: str) -> list[str]:
    """
    Resolve a configured model command.

    The old default was always ``python main.py``. That worked for GPG_NM, but
    failed for your Godfather repo because that folder has no main.py. If the
    command is still the default and main.py is absent, auto-detect a common
    Python entrypoint before giving up with a useful error.
    """
    parts = _command_parts(command)
    if not parts:
        raise RuntimeError("Model command is blank")

    uses_default = command.strip().lower() == _DEFAULT_COMMAND
    if uses_default and not (repo_dir / "main.py").exists():
        for candidate in _ENTRY_CANDIDATES[1:]:
            if (repo_dir / candidate).exists():
                return [parts[0], candidate]
        py_files = sorted(p.name for p in repo_dir.glob("*.py"))
        raise RuntimeError(
            f"No main.py found in {repo_dir}. Set {env_key} in .env to the "
            f"actual model command. Python files in that folder: "
            f"{', '.join(py_files) if py_files else 'none'}"
        )
    return parts


def empty_pelican(note: str) -> PelicanRec:
    return PelicanRec(tj_day=0.0, mw=0.0, peak_days="—", note=note)


def _latest_existing(paths: list[Path | None]) -> Optional[datetime]:
    existing = [p for p in paths if p is not None and p.exists()]
    if not existing:
        return None
    return datetime.fromtimestamp(max(p.stat().st_mtime for p in existing))


def _normalise_curve_df(df: pd.DataFrame) -> pd.DataFrame:
    """Return a daily GAS_DATE/PRICE dataframe from known Godfather export shapes."""
    df = df.copy()
    upper = {str(c).upper(): c for c in df.columns}

    # If the pickle/parquet contains multiple schedules, keep the daily-average curve.
    if "SCHEDULE" in upper:
        sched_col = upper["SCHEDULE"]
        df = df[df[sched_col].astype(str).str.upper().eq("DAILY AVG")]

    date_col = next((upper[c] for c in ("GAS_DATE", "DELIV_DATE", "DELIVERY_DATE", "DATE") if c in upper), None)
    price_col = next((upper[c] for c in ("PRICE", "FORECAST", "DWGM_PRICE", "VALUE", "VWAP") if c in upper), None)
    if date_col is None or price_col is None:
        raise ValueError(
            "Godfather curve export must contain a date column "
            "(GAS_DATE/DELIV_DATE/DELIVERY_DATE/DATE) and a price column "
            "(PRICE/FORECAST/DWGM_PRICE/VALUE/VWAP). "
            f"Found columns: {', '.join(map(str, df.columns))}"
        )

    out = df[[date_col, price_col]].rename(columns={date_col: "GAS_DATE", price_col: "PRICE"})
    out["GAS_DATE"] = pd.to_datetime(out["GAS_DATE"])
    out["PRICE"] = pd.to_numeric(out["PRICE"], errors="coerce")
    out = out.dropna(subset=["GAS_DATE", "PRICE"])
    return out


def _read_pickle_curve(path: Path) -> pd.DataFrame:
    obj = pd.read_pickle(path)
    if isinstance(obj, pd.DataFrame):
        return _normalise_curve_df(obj)
    if hasattr(obj, "to_dataframe"):
        return _normalise_curve_df(obj.to_dataframe())
    if isinstance(obj, dict):
        for key in ("curve", "forecast", "daily", "dwgm", "result"):
            val = obj.get(key)
            if isinstance(val, pd.DataFrame):
                return _normalise_curve_df(val)
            if hasattr(val, "to_dataframe"):
                return _normalise_curve_df(val.to_dataframe())
        return _normalise_curve_df(pd.DataFrame(obj))
    raise TypeError(f"Unsupported Godfather pickle type: {type(obj).__name__}")


def _curve_points_from_df(df: pd.DataFrame) -> list[CurvePoint]:
    df = _normalise_curve_df(df)
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
    if config.GPG_NM_REPO_DIR is None:
        raise RuntimeError("GPG_NM_REPO_DIR is not set")
    repo_dir = Path(config.GPG_NM_REPO_DIR)
    subprocess.run(
        _resolve_python_command(repo_dir, config.GPG_NM_COMMAND, "GPG_NM_COMMAND"),
        cwd=str(repo_dir),
        check=True,
    )


def read_pelican() -> PelicanRec:
    try:
        df = pd.read_parquet(config.GPG_PARQUET)
    except (FileNotFoundError, OSError) as e:
        # missing model output must not kill the render — the freshness gate has
        # already flagged staleness; DRAFT_FLAGGED still wants a report out
        print(f"[models] pelican forecast unavailable: {e}")
        return empty_pelican("Forecast output missing — review before relying on this panel.")
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
    return _latest_existing([config.CURVE_PARQUET, config.CURVE_PICKLE])


def godfather_trigger_run() -> None:
    """Run the upstream DWGM forecast command configured in .env."""
    if config.GODFATHER_REPO_DIR is None:
        raise RuntimeError("GODFATHER_REPO_DIR is not set")
    repo_dir = Path(config.GODFATHER_REPO_DIR)
    subprocess.run(
        _resolve_python_command(repo_dir, config.GODFATHER_COMMAND, "GODFATHER_COMMAND"),
        cwd=str(repo_dir),
        check=True,
    )


def read_curve() -> list[CurvePoint]:
    """
    Read the DWGM implied gas price curve produced by the upstream forecast.

    Primary path is GODFATHER_MODELS_DIR/dwgm_forecast_latest.parquet. If that
    file is missing, read the existing Godfather pickle at GODFATHER_FORECAST_PATH
    / GODFATHER_MODELS_DIR/dwgm_forecast.pkl. If neither file is available, fall
    back to live GSH settled-trades VWAP so render-only previews still have a
    desk-safe curve panel.
    """
    if config.CURVE_PARQUET.exists():
        return _curve_points_from_df(pd.read_parquet(config.CURVE_PARQUET))
    if config.CURVE_PICKLE is not None and config.CURVE_PICKLE.exists():
        return _curve_points_from_df(_read_pickle_curve(config.CURVE_PICKLE))

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
