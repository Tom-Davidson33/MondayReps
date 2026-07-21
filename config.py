"""
Central config. Everything tunable lives here so logic files never hard-code a
number. Change a threshold, a connection string, or a recipient list here only.
"""
from datetime import timedelta
from pathlib import Path

# ---------------------------------------------------------------- paths
ROOT = Path(__file__).parent
TEMPLATE_DIR = ROOT / "templates"
OUTPUT_DIR = ROOT / "out"          # rendered HTML lands here
OUTPUT_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------- connections
# Oracle creds load from .env (thin mode) — see db.py. Nothing to set here.

# ---------------------------------------------------------------- rule thresholds
BESS_SPREAD_THRESHOLD = 50.0              # $/MWh min spread to justify a cycle;
                                          #   BOTH am & pm must clear it for 2 cycles
SYNERGEN_PRICE_TRIGGER = 1000.0           # $/MWh expected peak -> arm peakers
PELICAN_HARD_RUN_TJ = 25.0                # TJ/day above which Pelican counts as "running hard"
# manual BESS spread inputs until a VIC power-price forecast source is wired
BESS_AM_SPREAD = 214.0                    # $/MWh
BESS_PM_SPREAD = 268.0                    # $/MWh
WIND_BAR_SCALE_MW = 3000.0                # full-width wind bar in the weather table
GAS_CURVE_BAR_SCALE = 14.0                # $/GJ full-width gas curve bar

# ---------------------------------------------------------------- freshness gate
# Each upstream must have produced numbers newer than max_age, else it's kicked
# off and we wait. If it can't be made fresh, the report refuses to send.
FRESHNESS = {
    "gpg_nm":    {"max_age": timedelta(hours=6),  "poll": timedelta(seconds=30), "timeout": timedelta(minutes=20)},
    "godfather": {"max_age": timedelta(hours=3),  "poll": timedelta(seconds=30), "timeout": timedelta(minutes=25)},
}

# What to do if an input can't be made fresh:
#   "ABORT"        -> don't render, alert Tom only            (safest, default)
#   "DRAFT_FLAGGED"-> render with a loud STALE banner, save to Drafts, don't auto-send
STALE_POLICY = "DRAFT_FLAGGED"

# ---------------------------------------------------------------- delivery
SUBJECT_FMT = "Tom's Monday Report — week of {week_start}"
RECIPIENTS_TO = ["spot.trading.desk@engie.com"]   # TODO real list
RECIPIENTS_CC = []
OWNER_EMAIL = "tom@engie.com"                      # alerts / stale drafts go here
# True  -> save to Outlook Drafts for Tom to review & send (matches "draft a copy")
# False -> send immediately
DRAFT_ONLY = True

# ---------------------------------------------------------------- data layer (from repos)
import os as _os
from pathlib import Path as _Path
try:
    from dotenv import load_dotenv as _load
    _load(_Path(__file__).parent / ".env")
except ImportError:
    pass

MELBOURNE_STATION = int(_os.environ.get("MELBOURNE_STATION", "86338"))
WEATHER_REGIONS   = ("VIC1", "SA1")          # portfolio wind/solar footprint
PELICAN_REGION    = "SA1"                     # Pelican Point sits in SA1
GPG_HEAT_RATE     = 8.5                       # GJ/MWh, matches GPG_NM implied default

DEFAULT_OPERATION_ARB_DIR = _Path(r"C:\Users\MS6653\OneDrive - ENGIE\Desktop\Operation Arb")
DEFAULT_GPG_NM_REPO_DIR = DEFAULT_OPERATION_ARB_DIR / "3. GPG_NM"
DEFAULT_GODFATHER_REPO_DIR = DEFAULT_OPERATION_ARB_DIR / "4. Godfather"
DEFAULT_GPG_NM_MODELS_DIR = DEFAULT_GPG_NM_REPO_DIR / "models"
DEFAULT_GODFATHER_MODELS_DIR = DEFAULT_GODFATHER_REPO_DIR / "models"

GPG_NM_MODELS_DIR    = _Path(_os.environ.get("GPG_NM_MODELS_DIR", str(DEFAULT_GPG_NM_MODELS_DIR)))
GODFATHER_MODELS_DIR = _Path(_os.environ.get("GODFATHER_MODELS_DIR", str(DEFAULT_GODFATHER_MODELS_DIR)))
GPG_PARQUET   = GPG_NM_MODELS_DIR / "gpg_forecast_latest.parquet"
GPG_META      = GPG_NM_MODELS_DIR / "gpg_forecast_meta.json"
CURVE_PARQUET = GODFATHER_MODELS_DIR / "dwgm_forecast_latest.parquet"   # see models.py note
_gf_models_raw = _os.environ.get("GODFATHER_MODELS_DIR", "").strip()
_curve_pickle_raw = _os.environ.get(
    "GODFATHER_FORECAST_PATH",
    str(_Path(_gf_models_raw) / "dwgm_forecast.pkl") if _gf_models_raw else "",
).strip()
CURVE_PICKLE = _Path(_curve_pickle_raw) if _curve_pickle_raw else None

# Upstream model runners. These are used by both the Python freshness gate and the
# Windows batch orchestrator. Keep tool names here only; report output remains
# desk-safe via orchestrate.py/templates.
def _repo_dir_from_env(repo_key: str, models_key: str, default: _Path) -> _Path:
    """Repo dir from {repo_key}, else the parent of {models_key}, else default."""
    repo = _os.environ.get(repo_key, "").strip()
    if repo:
        return _Path(repo)
    models_dir = _os.environ.get(models_key, "").strip()
    return _Path(models_dir).parent if models_dir else default


GPG_NM_REPO_DIR = _repo_dir_from_env("GPG_NM_REPO_DIR", "GPG_NM_MODELS_DIR", DEFAULT_GPG_NM_REPO_DIR)
GODFATHER_REPO_DIR = _repo_dir_from_env("GODFATHER_REPO_DIR", "GODFATHER_MODELS_DIR", DEFAULT_GODFATHER_REPO_DIR)
GPG_NM_COMMAND = _os.environ.get("GPG_NM_COMMAND", "python main.py").strip()
GODFATHER_COMMAND = _os.environ.get("GODFATHER_COMMAND", "python main.py").strip()

# local snapshot used to compute NEM outage "Δ vs last week"
SNAPSHOT_DIR = _Path(__file__).parent / "out"

# ---------------------------------------------------------------- charts + pelican + GSH curve
PELICAN_DAILY_PARQUET = GPG_NM_MODELS_DIR / "pelican_daily_latest.parquet"

# GSH settled-trades forward curve (confirm table via discovery query)
GSH_TRADES_TABLE   = _os.environ.get("GSH_TRADES_TABLE", "GSH.GAS_TRADE").split("#")[0].strip()
GSH_TRADE_DATE_COL = _os.environ.get("GSH_TRADE_DATE_COL", "DELIVERYDATE").split("#")[0].strip()
GSH_TRADE_PRICE_COL= _os.environ.get("GSH_TRADE_PRICE_COL", "PRICE").split("#")[0].strip()
GSH_TRADE_QTY_COL  = _os.environ.get("GSH_TRADE_QTY_COL", "QUANTITY").split("#")[0].strip()
GSH_TRADE_REPORT_COL=_os.environ.get("GSH_TRADE_REPORT_COL", "TRADEDATETIME").split("#")[0].strip()

# run-reason -> colour for the Pelican daily chart
RUN_REASON_COLOURS = {
    "ECONOMIC": "#2e7d32", "PROFIT": "#2e7d32", "PROFITABLE": "#2e7d32",
    "NSCAS": "#1565c0", "SSM": "#e08a00", "MINLOAD": "#7e8a99",
    "OFF": "#c2c9d2",
}
RUN_REASON_DEFAULT = "#4a5568"
