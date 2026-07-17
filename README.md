# Tom's Monday Report — rules-only v1 (DB-wired)

Freshness-gated weekly gas/power report. Data + triggers are deterministic; the
report is the LAST stage after the two model runs.

## Run

**Preview the layout, no database:**
    pip install jinja2 pandas pyarrow
    python preview.py

**Real pipeline (needs DB + model outputs):**
    pip install jinja2 pandas pyarrow oracledb python-dotenv pywin32
    python run_report.py --no-send      # render only
    python run_report.py                # render + Outlook draft

## Wiring status

Verified against your Godfather / GPG_NM repos and wired with REAL queries:

| Adapter | Source (verified) |
|---|---|
| sources/weather.py | WEATHERZONE.WEATHER_DAILY_FORECASTS + TESTER.STPASA_REGIONSOLUTION |
| sources/gas.py | GSH.GAS_MEDIUM_TERM_CAP_OUTLOOK + GSH.GAS_FACILITY_SUMMARY |
| sources/nem.py | TESTER.STPASA_DUIDAVAILABILITY (+DUDETAIL/SUMMARY/GENUNITS); DISPATCHCONSTRAINT |
| sources/models.py (Pelican) | GPG_NM/models/gpg_forecast_latest.parquet (REGION='SA1') |
| sources/models.py (curve) | GODFATHER_MODELS_DIR/dwgm_forecast_latest.parquet (see note) |

## Two things you still set

1. **.env** — DB creds/TNS + the two model dirs. Your export path uses `GPG_NM`;
   your repo folder is `3. GPG_NM`. Point GPG_NM_MODELS_DIR at wherever the parquet
   actually lands, and check the Godfather dir.

2. **Godfather curve export** — Godfather doesn't persist a daily curve file today.
   Add these 4 lines after your forecast run so the report can read it:
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
- **7-day gas curve graph** from GSH settled trades (VWAP per delivery day), rendered
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
