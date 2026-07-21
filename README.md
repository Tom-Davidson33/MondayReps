# Tom's Monday Report — rules-only v1 (DB-wired)

Freshness-gated weekly gas/power report. Data + triggers are deterministic; the
report is the LAST stage after the two model runs.

## Run

**Preview the layout, no database:**
    pip install jinja2 pandas pyarrow
    python preview.py

**Real pipeline (needs DB + model outputs):**
    pip install -r requirements.txt
    python check_setup.py           # verifies .env keys, paths and output files
    python check_setup.py --connect # optional: also SELECT 1 from each Oracle DB
    python run_report.py --no-send --skip-refresh  # render only, use existing model files
    python run_report.py --no-send      # render only, refresh stale model files first
    python run_report.py                # render + Outlook draft

**Batch runners (Windows):**
    run_all.bat                # 1) GPG_NM model  2) DWGM forecast  3) report + draft
    run_all.bat --no-send      # same, but render only (no Outlook)
    render_report.bat          # report render only — uses existing model files, no model refresh

`run_all.bat` creates `.venv` and installs `requirements.txt` on first run. The two
model repo paths/commands can be set in `.env` (`GPG_NM_REPO_DIR`,
`GODFATHER_REPO_DIR`, `GPG_NM_COMMAND`, `GODFATHER_COMMAND`); otherwise the batch
uses the OneDrive defaults in the file. If a repo does not have `main.py`, set its
command explicitly in `.env` (for example `GODFATHER_COMMAND=python run.py`). Each
model runs with its own repo `.venv` if it has one, otherwise the report venv is
placed on PATH. Because the models run first, the report's freshness gate finds
them fresh and goes straight to the render.

## Wiring status

Verified against your Godfather / GPG_NM repos and wired with REAL queries:

| Adapter | Source (verified) |
|---|---|
| sources/weather.py | WEATHERZONE.WEATHER_DAILY_FORECASTS + TESTER.STPASA_REGIONSOLUTION |
| sources/gas.py | GSH.GAS_MEDIUM_TERM_CAP_OUTLOOK + GSH.GAS_FACILITY_SUMMARY on me_market |
| sources/nem.py | TESTER.STPASA_DUIDAVAILABILITY (+DUDETAIL/SUMMARY/GENUNITS); DISPATCHCONSTRAINT |
| sources/models.py (Pelican) | GPG_NM/models/gpg_forecast_latest.parquet (REGION='SA1') |
| sources/models.py (curve) | GODFATHER_MODELS_DIR/dwgm_forecast_latest.parquet or GODFATHER_MODELS_DIR/dwgm_forecast.pkl, falling back to GSH settled-trade VWAP if both DWGM exports are missing |

## Two things you still set

1. **.env** — copy `.env.example` to `.env`, then fill in DB creds/TNS/DSN or
   host/service + the two model dirs. Never commit the populated `.env`. DB aliases
   prefer the Godfather-style prefixes (`GAS_MARKET`, `ME_MARKET`, `GAS_TRADING`)
   and fall back to report-style prefixes (`GASMARKET`, `MEMARKET`, `GASTRADING`).
   If model dirs are omitted,
   the report defaults to your OneDrive folders:
   `3. GPG_NM\models` and `4. Godfather\models`.

2. **Godfather curve export** — the report now reads the existing
   `GODFATHER_MODELS_DIR/dwgm_forecast.pkl` path, or an explicit
   `GODFATHER_FORECAST_PATH`. If you later add a parquet export, this also works:
       df = result.to_dataframe()
       df = df[df.SCHEDULE == "DAILY AVG"][["GAS_DATE", "FORECAST"]]
       df = df.rename(columns={"FORECAST": "PRICE"})
       df.to_parquet(GODFATHER_MODELS_DIR / "dwgm_forecast_latest.parquet", index=False)

## Known gap (flagged, not faked)

BESS spread ($50 threshold) and Synergen ($1,000 trigger) are electricity PRICE
forecasts. Neither repo forecasts forward NEM RRP beyond predispatch (~D+1) —
Godfather forecasts GAS price. These two stay as explicit inputs in orchestrate.py
until a power-price source is wired (PREDISPATCHPRICE for D+1, or a STPASA
reserve-gap heuristic per your "if STPASA gap is high" framing). Say the word and
I'll wire whichever you prefer.

## Schedule (Task Scheduler)
Weekly, Mon 06:00 → `pythonw.exe run_report.py`, Start in = project folder,
run only when logged on (Outlook COM needs an interactive session).

## Update (charts + GSH curve + Pelican)

Added since last version:
- **7-day gas curve graph** from DWGM export or GSH settled trades on me_market
  (VWAP per delivery day), rendered
  as an email-safe PNG (matplotlib). Replaces the old table.
- **Pelican Point — Daily Gas Usage Forecast chart**: TJ/day bars coloured by run
  reason (economic/NSCAS/SSM/off), implied SA1 price line overlaid.
- **Synergen now uses the real forecast SA1 price** (RRP_MAX from the Pelican daily
  model) instead of a placeholder. Only BESS spread still needs a VIC power-price source.

New dependency: `pip install matplotlib`.

### Two things only you can supply

1. **GSH trades table name.** The repos only reference physical GSH tables, so I don't
   have the settled-trades table. Run this, then set GSH_TRADES_TABLE + the 4 column
   names in .env:
       SELECT owner, table_name FROM all_tables
       WHERE owner='GSH' AND (table_name LIKE '%TRADE%' OR table_name LIKE '%PRICE%'
             OR table_name LIKE '%SETTLE%' OR table_name LIKE '%EXCH%')
       ORDER BY table_name;
   Then for the chosen table:
       SELECT column_name, data_type FROM all_tab_columns
       WHERE owner='GSH' AND table_name='<TABLE>' ORDER BY column_id;
   Map: delivery-date col, price ($/GJ) col, quantity col, trade-datetime col.

2. **Pelican daily export from GPG_NM.** Add to the end of your Pelican run so the
   report can read the daily chart data:
       daily = compute_daily_gas_tj(hh_df)
       daily.to_parquet(MODELS_DIR / "pelican_daily_latest.parquet", index=False)
   (Columns already produced: GAS_DATE, PP_TJ, RUN_REASON, RRP_AVG, RRP_MAX.)
