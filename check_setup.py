"""Pre-flight setup checker for Tom's Monday Report.

Run before the report to verify required .env keys, model paths, output files, and
optional Oracle connectivity without printing passwords:
    python check_setup.py
    python check_setup.py --connect
"""
from __future__ import annotations

import argparse
import os
import shlex
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # dependency check should still explain the issue cleanly
    load_dotenv = None

ROOT = Path(__file__).parent
ENV_PATH = ROOT / ".env"
DB_PREFIXES = ("GASMARKET", "MEMARKET", "GASTRADING")
ENTRY_CANDIDATES = ("main.py", "run.py", "forecast.py", "dwgm_forecast.py", "run_forecast.py", "godfather.py")


def _clean(value: str | None) -> str:
    return (value or "").split("#", 1)[0].strip().strip('"').strip("'")


def _status(ok: bool, label: str, detail: str = "") -> bool:
    mark = "OK" if ok else "MISSING"
    suffix = f" — {detail}" if detail else ""
    print(f"[{mark}] {label}{suffix}")
    return ok


def _has_db_address(prefix: str) -> tuple[bool, str]:
    tns = _clean(os.environ.get(f"{prefix}_TNS"))
    dsn = _clean(os.environ.get(f"{prefix}_DSN"))
    host = _clean(os.environ.get(f"{prefix}_HOST"))
    service = _clean(os.environ.get(f"{prefix}_SERVICE"))
    if tns:
        return True, f"{prefix}_TNS={tns}"
    if dsn:
        return True, f"{prefix}_DSN={dsn}"
    if host and service:
        port = _clean(os.environ.get(f"{prefix}_PORT")) or "1521"
        return True, f"{prefix}_HOST/{prefix}_SERVICE={host}:{port}/{service}"
    return False, f"set {prefix}_TNS, {prefix}_DSN, or {prefix}_HOST + {prefix}_SERVICE"


def _check_db_env() -> bool:
    ok = True
    print("\nDatabase environment")
    for prefix in DB_PREFIXES:
        user_ok = bool(_clean(os.environ.get(f"{prefix}_USER")))
        pass_ok = bool(_clean(os.environ.get(f"{prefix}_PASS")))
        addr_ok, addr_detail = _has_db_address(prefix)
        ok &= _status(user_ok, f"{prefix}_USER")
        ok &= _status(pass_ok, f"{prefix}_PASS", "set, hidden" if pass_ok else "")
        ok &= _status(addr_ok, f"{prefix} connection address", addr_detail)
    return ok


def _model_repo_from_env(repo_key: str, models_key: str) -> Path | None:
    repo = _clean(os.environ.get(repo_key))
    if repo:
        return Path(repo)
    models_dir = _clean(os.environ.get(models_key))
    return Path(models_dir).parent if models_dir else None


def _resolve_command(repo: Path, command: str) -> tuple[bool, str]:
    parts = shlex.split(command or "python main.py", posix=False)
    if not parts:
        return False, "command is blank"
    executable = Path(parts[0].strip('"')).stem.lower()
    if len(parts) >= 2 and executable.startswith("python"):
        script = repo / parts[1]
        if script.exists():
            return True, " ".join(parts)
        if parts[1].lower() == "main.py":
            for candidate in ENTRY_CANDIDATES[1:]:
                if (repo / candidate).exists():
                    return True, f"auto-detectable as: {parts[0]} {candidate}"
            py_files = sorted(p.name for p in repo.glob("*.py")) if repo.exists() else []
            return False, "main.py missing; set command explicitly. Python files: " + (", ".join(py_files) or "none")
        return False, f"script not found: {script}"
    return True, " ".join(parts)


def _check_model(label: str, repo_key: str, models_key: str, command_key: str, outputs: tuple[str | tuple[str, ...], ...]) -> bool:
    ok = True
    print(f"\n{label}")
    repo = _model_repo_from_env(repo_key, models_key)
    ok &= _status(repo is not None, repo_key, str(repo) if repo else f"set {repo_key} or {models_key}")
    if repo is not None:
        ok &= _status(repo.exists(), f"{repo_key} exists", str(repo))
        cmd_ok, cmd_detail = _resolve_command(repo, _clean(os.environ.get(command_key)) or "python main.py")
        ok &= _status(cmd_ok, command_key, cmd_detail)

    models_dir_raw = _clean(os.environ.get(models_key))
    models_dir = Path(models_dir_raw) if models_dir_raw else None
    ok &= _status(models_dir is not None, models_key, str(models_dir) if models_dir else "required for freshness/output reads")
    if models_dir is not None:
        ok &= _status(models_dir.exists(), f"{models_key} exists", str(models_dir))
        for output in outputs:
            choices = output if isinstance(output, tuple) else (output,)
            paths = [models_dir / name for name in choices]
            found = next((path for path in paths if path.exists()), None)
            label = " or ".join(choices)
            detail = str(found) if found else "checked " + "; ".join(str(p) for p in paths)
            # Forecast outputs may be created by the next model run, so mark absent
            # as fix-required for a clean report but do not print file contents.
            ok &= _status(found is not None, label, detail)
    return ok


def _check_gsh_env() -> bool:
    print("\nGSH fallback curve mapping")
    ok = True
    keys = ("GSH_TRADES_TABLE", "GSH_TRADE_DATE_COL", "GSH_TRADE_PRICE_COL", "GSH_TRADE_QTY_COL")
    for key in keys:
        value = _clean(os.environ.get(key))
        defaulted = {
            "GSH_TRADES_TABLE": "GSH.GAS_TRADE",
            "GSH_TRADE_DATE_COL": "DELIVERYDATE",
            "GSH_TRADE_PRICE_COL": "PRICE",
            "GSH_TRADE_QTY_COL": "QUANTITY",
        }[key]
        ok &= _status(bool(value or defaulted), key, value or f"default {defaulted} (confirm table/column names)")
    return ok


def _check_godfather_pickle_override() -> bool:
    path = _clean(os.environ.get("GODFATHER_FORECAST_PATH"))
    if not path:
        return True
    print("\nGodfather pickle override")
    p = Path(path)
    return _status(p.exists(), "GODFATHER_FORECAST_PATH", str(p))


def _check_connectivity() -> bool:
    print("\nOracle connectivity")
    import connections

    ok = True
    for alias in ("gas_market", "me_market", "gas_trading"):
        try:
            df = connections.q(alias, "SELECT 1 AS OK FROM DUAL")
            ok &= _status(not df.empty, alias, "SELECT 1 succeeded")
        except Exception as exc:
            ok &= _status(False, alias, str(exc))
    connections.close_all()
    return ok


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--connect", action="store_true", help="also test Oracle logins with SELECT 1 FROM DUAL")
    args = parser.parse_args()

    ok = True
    ok &= _status(ENV_PATH.exists(), ".env file", str(ENV_PATH))
    if load_dotenv is None:
        ok &= _status(False, "python-dotenv", "pip install -r requirements.txt")
    elif ENV_PATH.exists():
        load_dotenv(ENV_PATH, override=False)

    ok &= _check_db_env()
    ok &= _check_model("GPG_NM / Pelican forecast", "GPG_NM_REPO_DIR", "GPG_NM_MODELS_DIR", "GPG_NM_COMMAND", ("gpg_forecast_latest.parquet", "gpg_forecast_meta.json", "pelican_daily_latest.parquet"))
    ok &= _check_model("Godfather / DWGM forecast", "GODFATHER_REPO_DIR", "GODFATHER_MODELS_DIR", "GODFATHER_COMMAND", (("dwgm_forecast_latest.parquet", "dwgm_forecast.pkl"),))
    ok &= _check_godfather_pickle_override()
    ok &= _check_gsh_env()
    if args.connect:
        ok &= _check_connectivity()

    print("\nResult:", "ready" if ok else "fix the MISSING items above, then re-run this checker")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
