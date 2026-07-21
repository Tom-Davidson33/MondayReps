"""
Entrypoint. Windows Task Scheduler runs this at 06:00 Monday.

Flow: build context (freshness-gated) -> render -> deliver, applying STALE_POLICY.

Test now, no DB / no Outlook needed (runs on the sample-data stubs):
    python run_report.py --no-send
then open out/tom_monday_report.html   (Windows:  start out\\tom_monday_report.html)
"""
from __future__ import annotations
import argparse
import sys
from datetime import date, timedelta

import config
import orchestrate
import render
import send


def _week_labels() -> tuple[str, str]:
    """Monday-Sunday of the current week, computed from today."""
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    if monday.month == sunday.month:
        label = f"{monday:%a %d} \u2013 {sunday:%a %d %b %Y}"
    else:
        label = f"{monday:%a %d %b} \u2013 {sunday:%a %d %b %Y}"
    return label, f"{monday:%d %b %Y}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-send", action="store_true",
                    help="render only; skip Outlook (use this to test the look)")
    ap.add_argument("--skip-refresh", action="store_true",
                    help="do not run upstream models; use existing model output files only")
    args = ap.parse_args()

    week_label, week_start = _week_labels()

    ctx = orchestrate.build_context(week_label, week_start, refresh_models=not args.skip_refresh)
    subject = config.SUBJECT_FMT.format(week_start=week_start)
    html_path = render.render_to_file(ctx)
    print(f"[run] rendered -> {html_path}")

    if args.no_send:
        print("[run] --no-send: skipping Outlook. Open the file above to preview.")
        return 0

    html = open(html_path, encoding="utf-8").read()

    if ctx.is_stale:
        msg = f"Report HELD \u2014 inputs not fresh.\n{ctx.freshness.detail}"
        if config.STALE_POLICY == "ABORT":
            send.alert_owner("\u26a0 Monday Report NOT sent \u2014 stale inputs", msg)
            print("[run] ABORT:", msg)
            return 2
        send.deliver(html, "[STALE \u2014 REVIEW] " + subject, [config.OWNER_EMAIL],
                     draft_only=True)
        print("[run] DRAFT_FLAGGED:", msg)
        return 1

    send.deliver(html, subject, config.RECIPIENTS_TO, config.RECIPIENTS_CC,
                 draft_only=config.DRAFT_ONLY)
    return 0


if __name__ == "__main__":
    sys.exit(main())
