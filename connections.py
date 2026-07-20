"""
Oracle connections — mirrors the env-var scheme from your Godfather db.py.

Aliases -> owners (from your db.py KNOWN_ALIASES):
    me_market   -> TESTER
    gas_market  -> VENCORP, STTM, GSH, WEATHERZONE
    gas_trading -> GASTRADING, SEAGAS

Each alias reads {PREFIX}_TNS, {PREFIX}_DSN, or {PREFIX}_HOST/_PORT/_SERVICE plus
_USER/_PASS. Thin mode, no Oracle client needed when you use host/service.
"""
from __future__ import annotations
import os
import oracledb
import pandas as pd

try:
    from dotenv import load_dotenv
    from pathlib import Path
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

# report alias -> env prefix
_PREFIX = {"me_market": "MEMARKET", "gas_market": "GASMARKET", "gas_trading": "GASTRADING"}
_conns: dict[str, oracledb.Connection] = {}


def _dsn(prefix: str) -> str:
    tns = os.environ.get(f"{prefix}_TNS", "").strip()
    if tns:
        return tns
    dsn = os.environ.get(f"{prefix}_DSN", "").strip()
    if dsn:
        return dsn
    host = os.environ.get(f"{prefix}_HOST", "").strip()
    port = os.environ.get(f"{prefix}_PORT", "1521").strip()
    svc = os.environ.get(f"{prefix}_SERVICE", "").strip()
    if host and svc:
        return f"{host}:{port}/{svc}"
    raise EnvironmentError(
        f"No DSN for {prefix}: set {prefix}_TNS, {prefix}_DSN, or "
        f"{prefix}_HOST/_PORT/_SERVICE"
    )


def _conn(alias: str) -> oracledb.Connection:
    if alias not in _conns or not _conns[alias].is_healthy():
        prefix = _PREFIX[alias]
        dsn = _dsn(prefix)
        try:
            _conns[alias] = oracledb.connect(
                user=os.environ[f"{prefix}_USER"],
                password=os.environ[f"{prefix}_PASS"],
                dsn=dsn,
            )
        except oracledb.Error as exc:
            raise RuntimeError(
                f"Could not connect to {alias} ({prefix}) using DSN '{dsn}'. "
                f"If this is a TNS alias such as ELEC_MARKET.WORLD, either make "
                f"sure it exists in tnsnames.ora or set {prefix}_HOST and "
                f"{prefix}_SERVICE in .env for thin-mode EZCONNECT."
            ) from exc
    return _conns[alias]


def q(alias: str, sql: str, params: dict | None = None) -> pd.DataFrame:
    """Run a query on an alias, return a DataFrame. params are :named binds."""
    import warnings
    with warnings.catch_warnings():
        # pandas warns that non-SQLAlchemy connections are untested; oracledb works fine
        warnings.filterwarnings("ignore", message=".*supports SQLAlchemy.*")
        return pd.read_sql(sql, _conn(alias), params=params or {})


def close_all() -> None:
    for c in _conns.values():
        try:
            c.close()
        except Exception:
            pass
    _conns.clear()
