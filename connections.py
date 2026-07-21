"""
Oracle connections — mirrors the env-var scheme from your Godfather db.py.

Aliases -> owners (from your db.py KNOWN_ALIASES):
    me_market   -> TESTER, GSH
    gas_market  -> VENCORP, STTM, WEATHERZONE, SEAGAS
    gas_trading -> tolling, gastrading

Each alias first tries the Godfather-style env prefix (GAS_MARKET/ME_MARKET/
GAS_TRADING), then the report-style prefix (GASMARKET/MEMARKET/GASTRADING).
Each prefix reads {PREFIX}_TNS, {PREFIX}_DSN, or
{PREFIX}_HOST/_PORT/_SERVICE plus _USER/_PASS. Thin mode, no Oracle client
needed when you use host/service.
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

# report alias -> env prefixes, in preference order. Prefer Godfather's names so
# this report uses the same database settings when both naming schemes exist.
_PREFIXES = {
    "gas_market": ("GAS_MARKET", "GASMARKET"),
    "me_market": ("ME_MARKET", "MEMARKET"),
    "gas_trading": ("GAS_TRADING", "GASTRADING"),
}
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


def _has_credentials(prefix: str) -> bool:
    return bool(os.environ.get(f"{prefix}_USER", "").strip()
                and os.environ.get(f"{prefix}_PASS", "").strip())


def _has_address(prefix: str) -> bool:
    return bool(os.environ.get(f"{prefix}_TNS", "").strip()
                or os.environ.get(f"{prefix}_DSN", "").strip()
                or (os.environ.get(f"{prefix}_HOST", "").strip()
                    and os.environ.get(f"{prefix}_SERVICE", "").strip()))


def _resolve_prefix(alias: str) -> str:
    for prefix in _PREFIXES[alias]:
        if _has_credentials(prefix) and _has_address(prefix):
            return prefix
    expected = " or ".join(_PREFIXES[alias])
    raise EnvironmentError(
        f"No complete environment block for {alias}. Set USER/PASS and TNS/DSN "
        f"or HOST/SERVICE for one of: {expected}"
    )


def _conn(alias: str) -> oracledb.Connection:
    if alias not in _conns or not _conns[alias].is_healthy():
        prefix = _resolve_prefix(alias)
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
