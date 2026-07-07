"""Busy/free detection from a secret iCal URL (no OAuth).

Google Calendar → Settings → your calendar → "Secret address in iCal
format". The URL itself is the credential, so it lives in settings and
never in git. Recurring events are expanded with recurring-ical-events,
which handles RRULE/RDATE/EXDATE and overridden instances.
"""
import urllib.request
from datetime import datetime, timedelta, timezone

try:
    import recurring_ical_events
    from icalendar import Calendar
except ImportError:  # optional feature; the sign runs fine without it
    recurring_ical_events = None

FETCH_TIMEOUT = 15
LOOKBEHIND = timedelta(hours=2)   # catch already-running events
LOOKAHEAD = timedelta(hours=26)


def available():
    return recurring_ical_events is not None


def fetch(url):
    """Fetch and expand events near now.

    Returns a sorted list of (start_ts, end_ts, summary), or None on any
    failure so the caller can keep its last good copy.
    """
    if recurring_ical_events is None:
        return None
    try:
        with urllib.request.urlopen(url, timeout=FETCH_TIMEOUT) as resp:
            raw = resp.read()
        cal = Calendar.from_ical(raw)
        now = datetime.now(timezone.utc)
        events = []
        for event in recurring_ical_events.of(cal).between(
            now - LOOKBEHIND, now + LOOKAHEAD
        ):
            start = event.get("DTSTART")
            end = event.get("DTEND")
            if start is None or end is None:
                continue
            start, end = start.dt, end.dt
            # date (not datetime) = all-day event; being "busy" all day
            # would pin the sign on In a Meeting, so skip those.
            if not isinstance(start, datetime) or not isinstance(end, datetime):
                continue
            if str(event.get("TRANSP", "OPAQUE")).upper() == "TRANSPARENT":
                continue  # marked "Free" in the calendar UI
            if str(event.get("STATUS", "CONFIRMED")).upper() == "CANCELLED":
                continue
            events.append(
                (start.timestamp(), end.timestamp(), str(event.get("SUMMARY", "Meeting")))
            )
        return sorted(events)
    except Exception:
        return None


def current(events, now_ts):
    """The (start_ts, end_ts, summary) covering now_ts, or None."""
    for start, end, summary in events or ():
        if start <= now_ts < end:
            return (start, end, summary)
    return None
