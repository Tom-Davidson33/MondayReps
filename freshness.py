"""
Generic freshness gate.

For each upstream (GPG NM, Godfather) we:
  1. read the last-updated timestamp of its output,
  2. if newer than max_age -> already fresh, done,
  3. else kick off the run and poll the timestamp until it advances or we time out.

Fail-closed: if it can't be made fresh, we say so and let the orchestrator decide
(per config.STALE_POLICY) — we never silently proceed on stale numbers.
"""
from __future__ import annotations
import time
from datetime import datetime, timedelta
from typing import Callable, Optional


def is_fresh(last_updated: Optional[datetime], max_age: timedelta) -> bool:
    if last_updated is None:
        return False
    return (datetime.now() - last_updated) <= max_age


def ensure_fresh(
    name: str,
    get_last_updated: Callable[[], Optional[datetime]],
    trigger_run: Callable[[], None],
    max_age: timedelta,
    poll: timedelta,
    timeout: timedelta,
    log: Callable[[str], None] = print,
) -> tuple[bool, Optional[datetime]]:
    """Returns (fresh_ok, last_updated_after)."""
    last = get_last_updated()
    if is_fresh(last, max_age):
        log(f"[{name}] fresh (updated {last:%Y-%m-%d %H:%M}) — no run needed")
        return True, last

    log(f"[{name}] stale (last {last}) — triggering run…")
    baseline = last
    trigger_run()

    deadline = datetime.now() + timeout
    while datetime.now() < deadline:
        time.sleep(poll.total_seconds())
        now_updated = get_last_updated()
        advanced = now_updated is not None and (baseline is None or now_updated > baseline)
        if advanced and is_fresh(now_updated, max_age):
            log(f"[{name}] run complete (updated {now_updated:%Y-%m-%d %H:%M})")
            return True, now_updated

    log(f"[{name}] FAILED to refresh within {timeout} — report will not ship stale numbers")
    return False, get_last_updated()
