"""Flask server that lets a phone control the KnockBlock LED status sign."""
import argparse
import getpass
import ipaddress
import json
import random
import re
import secrets
import shutil
import subprocess
import threading
import time
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template, request, send_file, session
from PIL import Image

import auth
import calendar_source
import history
import media
import panel_themes
import weather
from matrix import (
    PANEL_COLS,
    PANEL_ROWS,
    MatrixDisplay,
    build_message_preset,
    compose_preset,
)
from presets import (
    DEFAULT_MESSAGE_COLOR,
    DEFAULT_PRESET,
    FOCUS_STATUS,
    MESSAGE_COLORS,
    PRESETS,
)

STATE_FILE = Path(__file__).resolve().parent / "state.json"
MAX_MESSAGE_LENGTH = 80
MAX_SIGN_NAME = 40
MAX_SCHEDULES = 20
MAX_RECENTS = 6
MAX_REVERT_MINUTES = 12 * 60
PREVIEW_SCALE = 6
WEATHER_REFRESH_SECONDS = 15 * 60
CALENDAR_REFRESH_SECONDS = 5 * 60
# 1s tick: the focus countdown repaints every second; everything else is a
# no-op signature comparison, so the fast tick costs almost nothing.
SCHEDULER_INTERVAL = 1
# The on-call sensor heartbeats every ~5s; if beats stop (agent crashed,
# laptop asleep) the status clears itself this many seconds later.
ONCALL_TTL = 15
TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

DEFAULT_SETTINGS = {
    "sign_name": "Knockblock",
    "panel_theme": "classic",  # how preset statuses render on the panel
    "weather_idle": True,
    "work_start": "08:00",
    "work_end": "18:00",
    "work_days": [0, 1, 2, 3, 4],  # Mon-Fri
    "units": "f",
    "lat": None,  # None = auto-detect from public IP
    "lon": None,
    "sleep_enabled": False,
    "sleep_start": "22:00",
    "sleep_end": "07:00",
    "ical_url": None,  # Google Calendar secret iCal address
    "manual_ttl_minutes": 120,  # 0 = manual presses hold forever
}

# All black; what the panel shows during scheduled sleep.
SLEEP_PRESET = {"lines": [], "bg_color": (0, 0, 0)}

# What demo visitors get instead of side effects.
DEMO_QUIPS = [
    "Demo mode: admired, not altered.",
    "Nice tap. The hardware respectfully declines.",
    "The sign remains under Andrew's exclusive jurisdiction.",
    "Look with your eyes, not with your HTTP requests.",
]

LOGIN_FREE_ATTEMPTS = 3
LOGIN_LOCK_SECONDS = 30
LOGIN_LOCK_MAX = 600

app = Flask(__name__)
app.secret_key = auth.secret_key()
app.config["MAX_CONTENT_LENGTH"] = media.MAX_UPLOAD_BYTES
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=180)
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
display = None  # MatrixDisplay, created in main() — needs GPIO/root
lock = threading.Lock()
login_attempts = {}  # ip -> (failure count, last failure timestamp)
weather_data = None
calendar_events = []  # last good fetch: [(start_ts, end_ts, summary), ...]
calendar_fetched = 0
render_signature = None
media_frames = None  # [(64x32 RGB frame, seconds), ...] for status "media"
media_generation = 0  # bumps when new media is set, so playback restarts

# The sign shows whichever *source* wins arbitration (see _arbitrate):
#   manual  — a tapped button or custom message, held until `until` passes
#             (None = forever); `explicit` means the user picked the timer,
#             so the UI shows a countdown for it
#   oncall  — laptop sensor heartbeats; active while now < oncall_until
#   focus   — focus timer; panel counts down MM:SS until `until`
#   calendar— an event from the iCal feed is happening now
#   idle    — the default preset (plus the clock/sleep behavior)
state = {
    "manual": None,  # {"status", "message", "until", "explicit"}
    "focus": None,  # {"until": epoch, "minutes": original duration}
    "oncall_until": None,
    "brightness": 70,
    "recents": [],
    "schedules": [],  # recurring rules; see _valid_schedule for the shape
    "settings": dict(DEFAULT_SETTINGS),
}


def _valid_color(color):
    return color if color in MESSAGE_COLORS else DEFAULT_MESSAGE_COLOR


def _valid_message(message):
    if isinstance(message, dict) and message.get("text"):
        return {
            "text": str(message["text"])[:MAX_MESSAGE_LENGTH],
            "color": _valid_color(message.get("color")),
        }
    return None


def _valid_schedule(rule):
    """Normalize one recurring-schedule rule, or None if it's unusable.

    Shape: {"id", "enabled", "label", "status", "message", "start", "end",
    "days"} — status is a preset key, "clock", or "custom" (which requires
    a message). start > end means the window spans midnight and belongs to
    the day it starts on. start == end is rejected rather than meaning
    "all day" — an always-on rule is just a status.
    """
    if not isinstance(rule, dict):
        return None
    status = rule.get("status")
    message = _valid_message(rule.get("message")) if status == "custom" else None
    if status == "custom":
        if message is None:
            return None
    elif status not in list(PRESETS) + ["clock"]:
        return None
    start, end = rule.get("start"), rule.get("end")
    if not (isinstance(start, str) and TIME_RE.match(start)
            and isinstance(end, str) and TIME_RE.match(end) and start != end):
        return None
    if not isinstance(rule.get("days"), list):
        return None
    days = sorted({d for d in rule["days"] if isinstance(d, int) and 0 <= d <= 6})
    if not days:
        return None
    rule_id = rule.get("id")
    if not (isinstance(rule_id, str) and re.fullmatch(r"[0-9a-f]{8}", rule_id)):
        rule_id = secrets.token_hex(4)
    return {
        "id": rule_id,
        "enabled": bool(rule.get("enabled", True)),
        "label": str(rule.get("label") or "").strip()[:MAX_SIGN_NAME],
        "status": status,
        "message": message,
        "start": start,
        "end": end,
        "days": days,
    }


def _load_state():
    try:
        saved = json.loads(STATE_FILE.read_text())
    except (FileNotFoundError, ValueError):
        return

    global media_frames
    manual = saved.get("manual")
    if isinstance(manual, dict):
        status = manual.get("status")
        message = _valid_message(manual.get("message"))
        until = manual.get("until")
        ok = (status in list(PRESETS) + ["clock", "dumpster_fire", "arcade"]
              or (status == "custom" and message))
        if status == "media":
            media_frames = media.load_current()
            ok = media_frames is not None
        if ok:
            info = manual.get("media")
            state["manual"] = {
                "status": status,
                "message": message if status == "custom" else None,
                "media": info if status == "media" and isinstance(info, dict) else None,
                "until": until if isinstance(until, (int, float)) else None,
                "explicit": bool(manual.get("explicit")),
            }
    elif "status" in saved:  # legacy schema: top-level status/message/revert_at
        status = saved.get("status")
        if status == "off":
            status = "clock"
        message = _valid_message(saved.get("message"))
        revert_at = saved.get("revert_at")
        until = revert_at if isinstance(revert_at, (int, float)) else None
        if status in list(PRESETS) + ["clock"] and status != DEFAULT_PRESET:
            state["manual"] = {
                "status": status, "message": None, "until": until, "explicit": until is not None,
            }
        elif status == "custom" and message:
            state["manual"] = {
                "status": "custom", "message": message, "until": until, "explicit": until is not None,
            }

    focus = saved.get("focus")
    if isinstance(focus, dict) and isinstance(focus.get("until"), (int, float)):
        minutes = focus.get("minutes")
        state["focus"] = {
            "until": focus["until"],
            "minutes": minutes if isinstance(minutes, int) else 0,
        }
    if isinstance(saved.get("oncall_until"), (int, float)):
        state["oncall_until"] = saved["oncall_until"]

    if isinstance(saved.get("brightness"), int) and 5 <= saved["brightness"] <= 100:
        state["brightness"] = saved["brightness"]
    recents = saved.get("recents")
    if isinstance(recents, list):
        state["recents"] = [
            {
                "text": str(entry["text"])[:MAX_MESSAGE_LENGTH],
                "color": _valid_color(entry.get("color")),
            }
            for entry in recents
            if isinstance(entry, dict) and entry.get("text")
        ][:MAX_RECENTS]
    schedules = saved.get("schedules")
    if isinstance(schedules, list):
        rules = [_valid_schedule(rule) for rule in schedules]
        state["schedules"] = [rule for rule in rules if rule][:MAX_SCHEDULES]

    settings = saved.get("settings")
    if isinstance(settings, dict):
        merged = dict(DEFAULT_SETTINGS)
        for key in ("weather_idle", "sleep_enabled"):
            if isinstance(settings.get(key), bool):
                merged[key] = settings[key]
        for key in ("work_start", "work_end", "sleep_start", "sleep_end"):
            if isinstance(settings.get(key), str) and TIME_RE.match(settings[key]):
                merged[key] = settings[key]
        if isinstance(settings.get("work_days"), list):
            days = sorted({d for d in settings["work_days"] if isinstance(d, int) and 0 <= d <= 6})
            if days:
                merged["work_days"] = days
        if settings.get("units") in ("f", "c"):
            merged["units"] = settings["units"]
        for key in ("lat", "lon"):
            if isinstance(settings.get(key), (int, float)):
                merged[key] = settings[key]
        url = settings.get("ical_url")
        if isinstance(url, str) and url.startswith(("http://", "https://")):
            merged["ical_url"] = url
        ttl = settings.get("manual_ttl_minutes")
        if isinstance(ttl, int) and 0 <= ttl <= MAX_REVERT_MINUTES:
            merged["manual_ttl_minutes"] = ttl
        name = settings.get("sign_name")
        if isinstance(name, str) and name.strip():
            merged["sign_name"] = name.strip()[:MAX_SIGN_NAME]
        if settings.get("panel_theme") in panel_themes.PANEL_THEMES:
            merged["panel_theme"] = settings["panel_theme"]
        state["settings"] = merged


def _save_state():
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state))
    tmp.replace(STATE_FILE)


def _in_window(start, end, now):
    current = now.strftime("%H:%M")
    if start <= end:
        return start <= current < end
    return current >= start or current < end  # overnight span


def _in_work_hours(now=None):
    settings = state["settings"]
    now = now or datetime.now()
    if now.weekday() not in settings["work_days"]:
        return False
    return _in_window(settings["work_start"], settings["work_end"], now)


def _active_schedule(now=None):
    """First enabled rule whose window covers now — list order is priority.

    An overnight window (start > end) belongs to the day it starts on: a
    Mon 22:00–02:00 rule matches Monday evening and Tuesday morning."""
    now = now or datetime.now()
    current = now.strftime("%H:%M")
    weekday = now.weekday()
    yesterday = (weekday - 1) % 7
    for rule in state["schedules"]:
        if not rule["enabled"]:
            continue
        if rule["start"] <= rule["end"]:
            if weekday in rule["days"] and rule["start"] <= current < rule["end"]:
                return rule
        else:
            if weekday in rule["days"] and current >= rule["start"]:
                return rule
            if yesterday in rule["days"] and current < rule["end"]:
                return rule
    return None


def _schedule_end_ts(rule, now_ts):
    """Epoch when the currently-active rule's window closes."""
    now = datetime.fromtimestamp(now_ts)
    hour, minute = map(int, rule["end"].split(":"))
    end = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if end <= now:  # overnight window still running: it closes tomorrow
        end += timedelta(days=1)
    return end.timestamp()


def _arbitrate(now):
    """Decide what the sign shows. Highest-priority active source wins:
    manual hold → on-call → focus timer → calendar → schedule → idle.

    Returns (source, status, message, countdown_until). Expired holds and
    timers are cleared as a side effect, so callers must hold the lock.
    """
    manual = state["manual"]
    if manual and manual["until"] is not None and now >= manual["until"]:
        state["manual"] = manual = None
    if manual:
        until = manual["until"] if manual["explicit"] else None
        return "manual", manual["status"], manual["message"], until
    if state["oncall_until"] is not None and now >= state["oncall_until"]:
        state["oncall_until"] = None  # watchdog: heartbeats stopped
    if state["oncall_until"]:
        return "oncall", "on_a_call", None, None
    focus = state["focus"]
    if focus and now >= focus["until"]:
        state["focus"] = focus = None
    if focus:
        return "focus", "focus", None, focus["until"]
    if calendar_source.current(calendar_events, now):
        return "calendar", "in_a_meeting", None, None
    rule = _active_schedule(datetime.fromtimestamp(now))
    if rule:
        return "schedule", rule["status"], rule["message"], _schedule_end_ts(rule, now)
    return "idle", DEFAULT_PRESET, None, None


def _set_manual(status, message, revert_minutes, media_info=None):
    """Install a manual hold. An explicit timer wins; otherwise the default
    TTL applies so a tapped button doesn't suppress autodetect all day."""
    if revert_minutes is not None:
        until, explicit = time.time() + revert_minutes * 60, True
    else:
        ttl = state["settings"]["manual_ttl_minutes"]
        until, explicit = (time.time() + ttl * 60 if ttl else None), False
    state["manual"] = {
        "status": status, "message": message, "media": media_info,
        "until": until, "explicit": explicit,
    }


def _set_media(frames, media_info, revert_minutes):
    global media_frames, media_generation
    media_frames = frames
    media_generation += 1
    _set_manual("media", None, revert_minutes, media_info)


def _idle_clock_active(source, now=None):
    """After hours with nobody claiming the sign → show the clock screen."""
    return (
        state["settings"]["weather_idle"]
        and source == "idle"
        and not _in_work_hours(now)
    )


def _sleeping(source, status, now=None):
    """Scheduled panel rest. Only idle screens (idle default, clock) go
    dark — calls, focus, meetings, and held statuses still show."""
    settings = state["settings"]
    return (
        settings["sleep_enabled"]
        and (source == "idle" or status == "clock")
        and _in_window(settings["sleep_start"], settings["sleep_end"], now or datetime.now())
    )


def _focus_countdown(now):
    left = max(0, int(round(state["focus"]["until"] - now))) if state["focus"] else 0
    return f"{left // 60}:{left % 60:02d}"


_last_logged = None


def _record_transition(source, status):
    """One history line per arbitration outcome change (caller holds lock)."""
    global _last_logged
    if (source, status) != _last_logged:
        _last_logged = (source, status)
        try:
            history.append(source, status)
        except OSError:
            pass  # a full SD card shouldn't take down rendering


def _render_current(force=False):
    """Render whatever should be on the panel now; skips no-op repaints."""
    global render_signature
    now_dt = datetime.now()
    source, status, message, _ = _arbitrate(time.time())
    _record_transition(source, status)
    if _sleeping(source, status, now_dt):
        signature = ("sleep",)
    elif status == "media":
        signature = ("media", media_generation)
    elif status == "dumpster_fire":
        signature = ("fire", media.fire_gif_mtime())
    elif status == "arcade":
        signature = ("arcade",)
    elif status == "custom":
        signature = ("custom", message["text"], message["color"])
    elif status == "focus":
        signature = ("focus", _focus_countdown(time.time()))
    elif status == "clock" or _idle_clock_active(source, now_dt):
        signature = (
            "clock",
            now_dt.strftime("%H:%M"),
            weather_data["temp"] if weather_data else None,
            weather_data["code"] if weather_data else None,
        )
    else:
        signature = ("preset", status, state["settings"]["panel_theme"])

    if not force and signature == render_signature:
        return
    render_signature = signature

    if signature[0] == "sleep":
        display.render_preset(SLEEP_PRESET)
    elif signature[0] == "media":
        display.play_frames(media_frames or [])
    elif signature[0] == "fire":
        display.play_frames(media.fire_frames())
    elif signature[0] == "arcade":
        display.play_frames(media.arcade_frames())
    elif signature[0] == "custom":
        display.render_preset(build_message_preset(message["text"], message["color"]))
    elif signature[0] == "focus":
        display.render_preset({**FOCUS_STATUS, "lines": ["FOCUS", signature[1]]})
    elif signature[0] == "clock":
        display.render_preset(weather.clock_preset(weather_data, now_dt))
    elif signature[2] == "classic":
        display.render_preset(PRESETS[status])
    else:
        # A themed preset is a composed scene; a one-frame "animation"
        # shows it and stops whatever was looping before.
        display.play_frames([(panel_themes.compose(PRESETS[status], signature[2]), 1.0)])


def _remember_message(text, color):
    recents = state["recents"]
    recents[:] = [entry for entry in recents if entry["text"] != text]
    recents.insert(0, {"text": text, "color": color})
    del recents[MAX_RECENTS:]


def _refresh_calendar():
    global calendar_events, calendar_fetched
    url = state["settings"]["ical_url"]
    calendar_fetched = time.time()
    if not url:
        calendar_events = []
        return
    fresh = calendar_source.fetch(url)
    if fresh is not None:  # on failure keep the last good copy
        calendar_events = fresh


def _scheduler_loop():
    """Keeps weather and calendar fresh; repaints when the signature moves
    (countdowns, expiring holds, work-hour/sleep boundaries)."""
    global weather_data
    while True:
        try:
            settings = state["settings"]
            if settings["weather_idle"]:
                if settings["lat"] is None or settings["lon"] is None:
                    location = weather.detect_location()
                    if location:
                        with lock:
                            settings["lat"], settings["lon"] = location
                            _save_state()
                if settings["lat"] is not None:
                    stale = (
                        weather_data is None
                        or time.time() - weather_data["fetched"] > WEATHER_REFRESH_SECONDS
                    )
                    if stale:
                        fresh = weather.fetch(
                            settings["lat"], settings["lon"], settings["units"]
                        )
                        if fresh:
                            weather_data = fresh
            if settings["ical_url"] and (
                time.time() - calendar_fetched > CALENDAR_REFRESH_SECONDS
            ):
                _refresh_calendar()
            with lock:
                _render_current()
        except Exception:
            pass
        time.sleep(SCHEDULER_INTERVAL)


def _api_payload(demo=False):
    """Assumes the caller holds the lock (arbitration mutates expired holds)."""
    now = time.time()
    source, status, message, until = _arbitrate(now)
    manual = state["manual"]
    event = calendar_source.current(calendar_events, now)
    return {
        "status": status,
        "message": message,
        "source": source,
        "revert_at": until,
        "held": manual is not None,
        "hold_until": manual["until"] if manual else None,
        "media": manual.get("media") if manual else None,
        "focus": state["focus"],
        "oncall": source == "oncall" or bool(state["oncall_until"]),
        "calendar": {
            "configured": bool(state["settings"]["ical_url"]),
            "supported": calendar_source.available(),
            "busy": event is not None,
            "event": event[2] if event else None,
            "until": event[1] if event else None,
        },
        "recents": state["recents"],
        "brightness": state["brightness"],
        # Spectators don't get the schedule list (labels are personal).
        "schedules": [] if demo else state["schedules"],
        "schedule_label": (
            (_active_schedule() or {}).get("label") if source == "schedule" else None
        ),
        # Spectators don't get the secret calendar URL or the location.
        "settings": (
            {**state["settings"], "ical_url": None, "lat": None, "lon": None}
            if demo
            else state["settings"]
        ),
        "showing_weather": _idle_clock_active(source),
        "sleeping": _sleeping(source, status),
        "weather": weather_data,
    }


def _request_token():
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        return header[7:].strip()
    return request.headers.get("X-Api-Token") or request.args.get("token")


# Headers a reverse proxy (nginx, Cloudflare) adds when relaying traffic.
# A request straight from a LAN client never carries these.
PROXY_HEADERS = (
    "X-Forwarded-For",
    "X-Real-IP",
    "X-Forwarded-Proto",
    "CF-Connecting-IP",
    "CF-Ray",
)


def _is_local_request():
    """True only for LAN clients talking directly to the sign.

    Public traffic reaches the Pi through a reverse proxy that itself
    sits on the LAN, so a private source address alone proves nothing.
    Every layer must agree: private source, no proxy headers, source not
    a known proxy, and not addressed to the public hostname.
    """
    try:
        addr = ipaddress.ip_address(request.remote_addr or "")
    except ValueError:
        return False
    if not (addr.is_private or addr.is_loopback):
        return False
    if any(request.headers.get(h) for h in PROXY_HEADERS):
        return False
    if request.remote_addr in auth.untrusted_proxies():
        return False
    host = (request.host or "").split(":")[0].lower()
    if auth.public_host() and host == auth.public_host():
        return False
    return True


@app.before_request
def _require_auth():
    if request.path in ("/login", "/demo") or request.path.startswith("/static/"):
        return None
    if _is_local_request():
        return None
    if session.get("authed"):
        return None
    token = _request_token()
    if token and auth.check_token(token):
        return None
    if session.get("demo"):
        # Spectators: live reads only. Everything mutating — including the
        # GET-able /api/set/* — earns a quip.
        if request.method == "GET" and (
            request.path in ("/", "/api/state", "/preview.png")
            or request.path.startswith("/thumb/")
        ):
            return None
        if request.path.startswith("/api/"):
            return jsonify(error=random.choice(DEMO_QUIPS)), 403
        return redirect("/")
    if request.path.startswith("/api/") or request.path == "/preview.png":
        return jsonify(error="unauthorized"), 401
    return redirect("/login")


def _demo_active():
    """True when this request is a spectator: has the demo cookie and no
    real credentials (locals, sessions, and tokens outrank demo)."""
    if not session.get("demo") or session.get("authed"):
        return False
    if _is_local_request():
        return False
    token = _request_token()
    return not (token and auth.check_token(token))


@app.route("/demo")
def demo():
    session["demo"] = True
    return redirect("/")


def _login_wait(ip):
    """Seconds until this IP may try again, or 0. Backoff grows per failure."""
    failures, last = login_attempts.get(ip, (0, 0))
    if failures < LOGIN_FREE_ATTEMPTS:
        return 0
    wait = min(LOGIN_LOCK_SECONDS * (failures - LOGIN_FREE_ATTEMPTS + 1), LOGIN_LOCK_MAX)
    return max(0, int(last + wait - time.time()))


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("authed") or _is_local_request():
        return redirect("/")
    if not auth.password_set():
        return render_template("login.html", setup_needed=True, error=None)
    error = None
    if request.method == "POST":
        ip = request.remote_addr or "?"
        wait = _login_wait(ip)
        if wait:
            error = f"Too many attempts — try again in {wait}s"
        elif auth.check_password(request.form.get("password", "")):
            login_attempts.pop(ip, None)
            session.permanent = True
            session.pop("demo", None)
            session["authed"] = True
            return redirect("/")
        else:
            failures, _ = login_attempts.get(ip, (0, 0))
            login_attempts[ip] = (failures + 1, time.time())
            error = "Wrong password"
    return render_template("login.html", setup_needed=False, error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


@app.route("/setup", methods=["GET", "POST"])
def setup():
    """First-run claim flow: set the password from a phone on the sign's own
    network. LAN-only while unclaimed — an internet visitor to a fresh sign
    still can't seize it (same property as the --set-password CLI, which
    remains the fallback and the only way to *reset* a password)."""
    if auth.password_set() or not _is_local_request():
        return redirect("/")
    error = None
    if request.method == "POST":
        form = request.form
        password = form.get("password", "")
        sign_name = (form.get("sign_name") or "").strip()[:MAX_SIGN_NAME]
        units = form.get("units", "f")
        work_start = form.get("work_start", "08:00")
        work_end = form.get("work_end", "18:00")
        days = sorted({
            int(d) for d in form.getlist("work_days")
            if d.isdigit() and 0 <= int(d) <= 6
        })
        if len(password) < 8:
            error = "Password needs at least 8 characters"
        elif password != form.get("confirm", ""):
            error = "Passwords don't match"
        elif units not in ("f", "c"):
            error = "Pick °F or °C"
        elif not (TIME_RE.match(work_start) and TIME_RE.match(work_end)):
            error = "Work hours must be HH:MM"
        else:
            with lock:
                if auth.password_set():  # claim race: the first tap won
                    return redirect("/")
                auth.set_password(password)
                settings = state["settings"]
                if sign_name:
                    settings["sign_name"] = sign_name
                settings["units"] = units
                settings["work_start"] = work_start
                settings["work_end"] = work_end
                if days:
                    settings["work_days"] = days
                _save_state()
                _render_current()
            session.permanent = True
            session["authed"] = True
            return render_template(
                "setup.html", done=True, error=None,
                api_token=auth.api_token(), settings=state["settings"],
            )
    return render_template(
        "setup.html", done=False, error=error,
        api_token=None, settings=state["settings"],
    )


@app.route("/api/token", methods=["GET", "POST"])
def api_token():
    # Session or local only: a leaked token shouldn't be able to mint
    # replacements, and token-authed clients have no business reading it back.
    if not (session.get("authed") or _is_local_request()):
        return jsonify(error="unauthorized"), 401
    if request.method == "POST":
        return jsonify(token=auth.regenerate_token())
    return jsonify(token=auth.api_token())


UPDATE_STATUS_FILE = Path(__file__).resolve().parent / "update_status.json"
UPDATE_SCRIPT = Path(__file__).resolve().parent / "scripts" / "update.sh"


def _app_version():
    try:
        return subprocess.check_output(
            ["git", "describe", "--tags", "--always"],
            cwd=Path(__file__).resolve().parent, text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


APP_VERSION = _app_version()  # code can't change without a restart


@app.route("/api/update", methods=["POST"])
def start_update():
    # Session or local only, like /api/token: a leaked API token must not
    # be able to trigger code swaps on the sign.
    if not (session.get("authed") or _is_local_request()):
        return jsonify(error="unauthorized"), 401
    repo = Path(__file__).resolve().parent
    if not (repo / ".git").exists():
        return jsonify(error="this install isn't a git clone — reinstall with install.sh"), 400
    # systemd-run detaches the updater from this process, so it survives
    # the service restart it performs. Outside systemd (dev), plain Popen.
    if shutil.which("systemd-run"):
        command = ["systemd-run", "--unit", "knockblock-update", "--collect", str(UPDATE_SCRIPT)]
    else:
        command = [str(UPDATE_SCRIPT)]
    try:
        subprocess.Popen(command, cwd=repo, start_new_session=True)
    except OSError as exc:
        return jsonify(error=f"couldn't start the updater: {exc}"), 500
    return jsonify(started=True), 202


@app.route("/api/update/status")
def update_status():
    if not (session.get("authed") or _is_local_request()):
        return jsonify(error="unauthorized"), 401
    try:
        status = json.loads(UPDATE_STATUS_FILE.read_text())
    except (FileNotFoundError, ValueError):
        status = None
    return jsonify(version=APP_VERSION, update=status)


THEMES = ("workshop", "glass", "clear")


@app.route("/")
def index():
    if not auth.password_set() and _is_local_request():
        return redirect("/setup")
    demo = _demo_active()
    # Theme is a per-browser choice, not sign state — a cookie, read here
    # so the first paint is already in the right theme (no flash).
    theme = request.cookies.get("kb_theme")
    if theme not in THEMES:
        theme = "workshop"
    with lock:
        payload = _api_payload(demo=demo)
    return render_template(
        "index.html",
        theme=theme,
        sign_name=payload["settings"]["sign_name"],
        presets=PRESETS,
        message_colors=MESSAGE_COLORS,
        demo=demo,
        api_token="" if demo else auth.api_token(),
        state=payload,
        labels_json=json.dumps({key: preset["label"] for key, preset in PRESETS.items()}),
        msg_colors_json=json.dumps({name: c["ui"] for name, c in MESSAGE_COLORS.items()}),
    )


@app.route("/preview.png")
def preview():
    with lock:
        image = display.snapshot()
    if image is None:
        image = Image.new("RGB", (PANEL_COLS, PANEL_ROWS), (4, 4, 6))
    image = image.resize(
        (image.width * PREVIEW_SCALE, image.height * PREVIEW_SCALE), Image.NEAREST
    )
    buffer = BytesIO()
    image.save(buffer, "PNG")
    buffer.seek(0)
    response = send_file(buffer, mimetype="image/png")
    response.headers["Cache-Control"] = "no-store"
    return response


THUMB_SCALE = 3


@app.route("/thumb/<key>.png")
def status_thumb(key):
    """A small render of what a status would show — the buttons wear these.

    Presets and clock are composed live (so the clock thumb tells the real
    time); fire and arcade use their first animation frame.
    """
    if key in PRESETS:
        image = panel_themes.compose(PRESETS[key], state["settings"]["panel_theme"])
    elif key == "clock":
        image = compose_preset(weather.clock_preset(weather_data, datetime.now()))
    elif key == "dumpster_fire":
        image = media.fire_frames()[0][0]
    elif key == "arcade":
        image = media.arcade_frames()[0][0]
    else:
        return jsonify(error="unknown status"), 404
    image = image.resize(
        (image.width * THUMB_SCALE, image.height * THUMB_SCALE), Image.NEAREST
    )
    buffer = BytesIO()
    image.save(buffer, "PNG")
    buffer.seek(0)
    response = send_file(buffer, mimetype="image/png")
    response.headers["Cache-Control"] = "max-age=300"
    return response


@app.route("/api/state")
def get_state():
    with lock:
        return jsonify(_api_payload(demo=_demo_active()))


@app.route("/api/insights")
def insights():
    # Not on the demo allowlist in _require_auth — spectators see the live
    # sign, not a week of the owner's working patterns.
    try:
        days = min(31, max(1, int(request.args.get("days", 7))))
    except (TypeError, ValueError):
        days = 7
    return jsonify(history.aggregate(days))


@app.route("/api/state", methods=["POST"])
def set_state():
    global weather_data
    data = request.get_json(silent=True) or {}
    with lock:
        if "brightness" in data:
            try:
                brightness = int(data["brightness"])
            except (TypeError, ValueError):
                return jsonify(error="brightness must be a number"), 400
            if not 5 <= brightness <= 100:
                return jsonify(error="brightness must be between 5 and 100"), 400
            state["brightness"] = brightness
            display.set_brightness(brightness)

        if "settings" in data:
            incoming = data["settings"] or {}
            settings = state["settings"]
            for key in ("weather_idle", "sleep_enabled"):
                if key in incoming:
                    settings[key] = bool(incoming[key])
            for key in ("work_start", "work_end", "sleep_start", "sleep_end"):
                if key in incoming:
                    value = str(incoming[key])
                    if not TIME_RE.match(value):
                        return jsonify(error=f"{key} must be HH:MM"), 400
                    settings[key] = value
            if "units" in incoming:
                if incoming["units"] not in ("f", "c"):
                    return jsonify(error="units must be 'f' or 'c'"), 400
                if incoming["units"] != settings["units"]:
                    settings["units"] = incoming["units"]
                    weather_data = None  # refetch in the new units
            for key in ("lat", "lon"):
                if key in incoming:
                    if incoming[key] is None:
                        settings[key] = None
                    else:
                        try:
                            settings[key] = float(incoming[key])
                        except (TypeError, ValueError):
                            return jsonify(error=f"{key} must be a number"), 400
            if "ical_url" in incoming:
                url = (str(incoming["ical_url"] or "")).strip()
                if url and not url.startswith(("http://", "https://")):
                    return jsonify(error="ical_url must be an http(s) URL"), 400
                if (url or None) != settings["ical_url"]:
                    settings["ical_url"] = url or None
                    global calendar_fetched, calendar_events
                    calendar_events = []
                    calendar_fetched = 0  # scheduler refetches on next tick
            if "manual_ttl_minutes" in incoming:
                try:
                    ttl = int(incoming["manual_ttl_minutes"])
                except (TypeError, ValueError):
                    return jsonify(error="manual_ttl_minutes must be a number"), 400
                if not 0 <= ttl <= MAX_REVERT_MINUTES:
                    return jsonify(error="manual_ttl_minutes out of range"), 400
                settings["manual_ttl_minutes"] = ttl
            if "sign_name" in incoming:
                name = str(incoming["sign_name"] or "").strip()
                if not name:
                    return jsonify(error="sign_name can't be empty"), 400
                settings["sign_name"] = name[:MAX_SIGN_NAME]
            if "panel_theme" in incoming:
                if incoming["panel_theme"] not in panel_themes.PANEL_THEMES:
                    return jsonify(error="unknown panel_theme"), 400
                settings["panel_theme"] = incoming["panel_theme"]
            _render_current()

        if "schedules" in data:
            incoming = data["schedules"]
            if not isinstance(incoming, list) or len(incoming) > MAX_SCHEDULES:
                return jsonify(error=f"schedules must be a list of at most {MAX_SCHEDULES} rules"), 400
            validated = []
            for index, rule in enumerate(incoming):
                valid = _valid_schedule(rule)
                if valid is None:
                    return jsonify(error=f"schedule rule {index + 1} is invalid"), 400
                validated.append(valid)
            state["schedules"] = validated  # full-list replace, like settings
            _render_current()

        minutes = data.get("revert_minutes")
        if minutes is not None:
            try:
                minutes = int(minutes)
            except (TypeError, ValueError):
                return jsonify(error="revert_minutes must be a number"), 400
            if not 1 <= minutes <= MAX_REVERT_MINUTES:
                return jsonify(error="revert_minutes out of range"), 400

        if "message" in data:
            message = data["message"] or {}
            text = str(message.get("text", "")).strip()[:MAX_MESSAGE_LENGTH]
            if not text:
                return jsonify(error="message text is required"), 400
            color = _valid_color(message.get("color"))
            _set_manual("custom", {"text": text, "color": color}, minutes)
            _remember_message(text, color)
            _render_current()
        elif "status" in data:
            status = data["status"]
            if status == "off":  # accept the old name from stale clients
                status = "clock"
            if status == "auto":
                state["manual"] = None  # release the hold; autodetect takes over
            elif status in ("clock", "dumpster_fire", "arcade") or status in PRESETS:
                _set_manual(status, None, minutes)
            else:
                return jsonify(error="unknown status"), 400
            _render_current()

        if "focus_minutes" in data:
            try:
                focus_minutes = int(data["focus_minutes"] or 0)
            except (TypeError, ValueError):
                return jsonify(error="focus_minutes must be a number"), 400
            if not 0 <= focus_minutes <= MAX_REVERT_MINUTES:
                return jsonify(error="focus_minutes out of range"), 400
            state["focus"] = (
                {"until": time.time() + focus_minutes * 60, "minutes": focus_minutes}
                if focus_minutes
                else None
            )
            _render_current()

        _save_state()
        return jsonify(_api_payload())


@app.route("/api/set/<status>", methods=["GET", "POST"])
def quick_set(status):
    """One-URL change for Stream Deck / Shortcuts buttons.

    /api/set/on_a_call?minutes=30 — hold a status (default hold TTL if no
    minutes), /api/set/focus?minutes=25 — start a focus timer,
    /api/set/auto — release the manual hold.
    """
    if status == "off":
        status = "clock"
    minutes = request.args.get("minutes")
    if minutes is not None:
        try:
            minutes = int(minutes)
        except ValueError:
            return jsonify(error="minutes must be a number"), 400
        if not 1 <= minutes <= MAX_REVERT_MINUTES:
            return jsonify(error="minutes out of range"), 400
    with lock:
        if status == "auto":
            state["manual"] = None
        elif status == "focus":
            minutes = minutes or 25
            state["focus"] = {"until": time.time() + minutes * 60, "minutes": minutes}
        elif status in ("clock", "dumpster_fire", "arcade") or status in PRESETS:
            _set_manual(status, None, minutes)
        else:
            return jsonify(error="unknown status"), 400
        _render_current()
        _save_state()
        return jsonify(_api_payload())


def _parse_revert_minutes(value):
    """→ (minutes or None, error or None)."""
    if value is None:
        return None, None
    try:
        value = int(value)
    except (TypeError, ValueError):
        return None, "revert_minutes must be a number"
    if not 1 <= value <= MAX_REVERT_MINUTES:
        return None, "revert_minutes out of range"
    return value, None


@app.route("/api/gif", methods=["POST"])
def random_gif():
    """Fetch a random GIF (optionally for a search) and put it on the panel."""
    data = request.get_json(silent=True) or {}
    minutes, err = _parse_revert_minutes(data.get("revert_minutes"))
    if err:
        return jsonify(error=err), 400
    query = str(data.get("query") or "")[:60]
    try:
        raw, used_query = media.fetch_random_gif(query)
        frames = media.frames_from_bytes(raw)
    except (RuntimeError, ValueError) as exc:
        return jsonify(error=str(exc)), 502
    media.save_current(raw, "gif")
    with lock:
        _set_media(frames, {"kind": "gif", "label": f"GIF · {used_query}"}, minutes)
        _render_current()
        _save_state()
        return jsonify(_api_payload())


@app.route("/api/upload", methods=["POST"])
def upload_media():
    """Show an uploaded image or GIF on the panel."""
    file = request.files.get("file")
    if file is None or not file.filename:
        return jsonify(error="attach a file field named 'file'"), 400
    minutes, err = _parse_revert_minutes(request.form.get("revert_minutes"))
    if err:
        return jsonify(error=err), 400
    raw = file.read()
    try:
        frames = media.frames_from_bytes(raw)
    except ValueError:
        return jsonify(error="that doesn't look like an image or GIF"), 400
    kind = "gif" if len(frames) > 1 else "image"
    media.save_current(raw, kind)
    label = file.filename[:40]
    with lock:
        _set_media(frames, {"kind": kind, "label": label}, minutes)
        _render_current()
        _save_state()
        return jsonify(_api_payload())


@app.route("/api/oncall", methods=["POST"])
def oncall():
    """Heartbeat from a laptop camera/mic sensor agent.

    The agent POSTs {"active": true} every ~5s during a call and
    {"active": false} once when it ends. If the beats just stop (agent
    crashed, laptop lid closed) the watchdog clears the status ONCALL_TTL
    seconds after the last one.
    """
    data = request.get_json(silent=True) or {}
    if not isinstance(data.get("active"), bool):
        return jsonify(error="active must be true or false"), 400
    with lock:
        state["oncall_until"] = time.time() + ONCALL_TTL if data["active"] else None
        _render_current()
        _save_state()
        return jsonify(_api_payload())


def _set_password_interactive():
    password = getpass.getpass("New KnockBlock password: ")
    if len(password) < 8:
        raise SystemExit("Password must be at least 8 characters.")
    if getpass.getpass("Repeat password: ") != password:
        raise SystemExit("Passwords didn't match.")
    auth.set_password(password)
    print("Password set.")
    print(f"API token (for Stream Deck / scripts): {auth.api_token()}")


def main():
    global display
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--set-password", action="store_true", help="set the web login password and exit"
    )
    parser.add_argument(
        "--show-token", action="store_true", help="print the API token and exit"
    )
    args = parser.parse_args()
    if args.set_password:
        _set_password_interactive()
        return
    if args.show_token:
        print(auth.api_token())
        return

    if not auth.password_set():
        print("No password set — the web UI will refuse access until you run:")
        print("  sudo ./venv/bin/python3 app.py --set-password")

    display = MatrixDisplay()
    _load_state()
    display.set_brightness(state["brightness"])
    with lock:
        # Expired holds/timers clear themselves inside _arbitrate.
        _render_current(force=True)
        _save_state()
    threading.Thread(target=_scheduler_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=5000)


if __name__ == "__main__":
    main()
