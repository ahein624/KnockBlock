"""Append-only status history and the weekly-insights aggregation.

One JSONL line per arbitration outcome change:

    {"ts": 1751234567, "source": "manual", "status": "on_a_call"}

Lines land in monthly files (``history-YYYY-MM.jsonl``) next to state.json —
human-inspectable, a bad trailing line after a power cut costs one event,
and retention is just deleting old files. Custom message text is
deliberately never logged; the status name is enough to aggregate.
"""
import json
import time
from datetime import datetime, timedelta
from pathlib import Path

HISTORY_DIR = Path(__file__).resolve().parent
RETENTION_MONTHS = 3


def _month_stamp(ts):
    return datetime.fromtimestamp(ts).strftime("%Y-%m")


def append(source, status, ts=None):
    ts = int(ts if ts is not None else time.time())
    path = HISTORY_DIR / f"history-{_month_stamp(ts)}.jsonl"
    new_month = not path.exists()
    with path.open("a") as handle:
        handle.write(json.dumps({"ts": ts, "source": source, "status": status}) + "\n")
    if new_month:
        prune()


def prune(now=None):
    """Drop files older than RETENTION_MONTHS whole months."""
    now = datetime.fromtimestamp(now if now is not None else time.time())
    year, month = now.year, now.month - RETENTION_MONTHS
    while month <= 0:
        year, month = year - 1, month + 12
    cutoff = f"{year:04d}-{month:02d}"
    for path in HISTORY_DIR.glob("history-*.jsonl"):
        if path.stem[len("history-"):] < cutoff:
            try:
                path.unlink()
            except OSError:
                pass


def _events():
    """All retained events, oldest first. Skips unparseable lines."""
    events = []
    for path in sorted(HISTORY_DIR.glob("history-*.jsonl")):
        try:
            lines = path.read_text().splitlines()
        except OSError:
            continue
        for line in lines:
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if isinstance(event, dict) and isinstance(event.get("ts"), (int, float)):
                events.append(event)
    events.sort(key=lambda e: e["ts"])
    return events


def aggregate(days=7, now=None):
    """Seconds per status per local day over the trailing window.

    Consecutive events pair into intervals (the last one runs to now);
    intervals are clipped to the window and split across midnights.
    Negative durations — the Pi has no RTC, so the clock jumps after NTP
    sync — are dropped rather than corrupting a day.
    """
    now = now if now is not None else time.time()
    start_day = (datetime.fromtimestamp(now) - timedelta(days=days - 1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    window_start = start_day.timestamp()

    buckets = {}  # "YYYY-MM-DD" -> {status: seconds}
    totals = {}

    def credit(status, begin, end):
        begin, end = max(begin, window_start), min(end, now)
        cursor = begin
        while cursor < end:
            day = datetime.fromtimestamp(cursor)
            next_midnight = (day.replace(hour=0, minute=0, second=0, microsecond=0)
                             + timedelta(days=1)).timestamp()
            chunk_end = min(end, next_midnight)
            seconds = int(chunk_end - cursor)
            if seconds > 0:
                key = day.strftime("%Y-%m-%d")
                buckets.setdefault(key, {})
                buckets[key][status] = buckets[key].get(status, 0) + seconds
                totals[status] = totals.get(status, 0) + seconds
            cursor = chunk_end

    events = _events()
    for current, following in zip(events, events[1:] + [None]):
        end = following["ts"] if following else now
        if end <= current["ts"]:
            continue  # clock jumped backwards across this pair
        if end < window_start or current["ts"] > now:
            continue
        credit(current["status"], current["ts"], end)

    day_list = []
    for offset in range(days):
        key = (start_day + timedelta(days=offset)).strftime("%Y-%m-%d")
        day_list.append({"date": key, "seconds": buckets.get(key, {})})
    return {"days": day_list, "totals": totals}
