"""Flask server that lets a phone control the KnockBlock LED status sign."""
import json
import re
import threading
import time
from datetime import datetime
from io import BytesIO
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file
from PIL import Image

import weather
from matrix import PANEL_COLS, PANEL_ROWS, MatrixDisplay, build_message_preset
from presets import DEFAULT_MESSAGE_COLOR, DEFAULT_PRESET, MESSAGE_COLORS, PRESETS

STATE_FILE = Path(__file__).resolve().parent / "state.json"
MAX_MESSAGE_LENGTH = 80
MAX_RECENTS = 6
MAX_REVERT_MINUTES = 12 * 60
PREVIEW_SCALE = 6
WEATHER_REFRESH_SECONDS = 15 * 60
SCHEDULER_INTERVAL = 30
TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

DEFAULT_SETTINGS = {
    "weather_idle": True,
    "work_start": "08:00",
    "work_end": "18:00",
    "work_days": [0, 1, 2, 3, 4],  # Mon-Fri
    "units": "f",
    "lat": None,  # None = auto-detect from public IP
    "lon": None,
}

app = Flask(__name__)
display = MatrixDisplay()
lock = threading.Lock()
revert_timer = None
weather_data = None
render_signature = None

# status is a preset key, "custom" (showing `message`), or "clock".
# revert_at is an epoch timestamp when the sign flips back to the default
# status, or None. recents are previously shown custom messages, newest first.
state = {
    "status": DEFAULT_PRESET,
    "brightness": 70,
    "message": None,
    "recents": [],
    "revert_at": None,
    "settings": dict(DEFAULT_SETTINGS),
}


def _valid_color(color):
    return color if color in MESSAGE_COLORS else DEFAULT_MESSAGE_COLOR


def _load_state():
    try:
        saved = json.loads(STATE_FILE.read_text())
    except (FileNotFoundError, ValueError):
        return
    if saved.get("status") == "off":  # pre-clock versions had a blank-panel mode
        state["status"] = "clock"
    elif saved.get("status") in list(PRESETS) + ["custom", "clock"]:
        state["status"] = saved["status"]
    if isinstance(saved.get("brightness"), int) and 5 <= saved["brightness"] <= 100:
        state["brightness"] = saved["brightness"]
    message = saved.get("message")
    if isinstance(message, dict) and message.get("text"):
        state["message"] = {
            "text": str(message["text"])[:MAX_MESSAGE_LENGTH],
            "color": _valid_color(message.get("color")),
        }
    if state["status"] == "custom" and not state["message"]:
        state["status"] = DEFAULT_PRESET
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
    if isinstance(saved.get("revert_at"), (int, float)):
        state["revert_at"] = saved["revert_at"]
    settings = saved.get("settings")
    if isinstance(settings, dict):
        merged = dict(DEFAULT_SETTINGS)
        if isinstance(settings.get("weather_idle"), bool):
            merged["weather_idle"] = settings["weather_idle"]
        for key in ("work_start", "work_end"):
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
        state["settings"] = merged


def _save_state():
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state))
    tmp.replace(STATE_FILE)


def _in_work_hours(now=None):
    settings = state["settings"]
    now = now or datetime.now()
    if now.weekday() not in settings["work_days"]:
        return False
    current = now.strftime("%H:%M")
    start, end = settings["work_start"], settings["work_end"]
    if start <= end:
        return start <= current < end
    return current >= start or current < end  # overnight span


def _idle_clock_active():
    """After hours with nobody claiming the sign → show the clock screen."""
    return (
        state["settings"]["weather_idle"]
        and state["status"] == DEFAULT_PRESET
        and not _in_work_hours()
    )


def _render_current(force=False):
    """Render whatever should be on the panel now; skips no-op repaints."""
    global render_signature
    now = datetime.now()
    if state["status"] == "custom":
        message = state["message"]
        signature = ("custom", message["text"], message["color"])
    elif state["status"] == "clock" or _idle_clock_active():
        signature = (
            "clock",
            now.strftime("%H:%M"),
            weather_data["temp"] if weather_data else None,
            weather_data["code"] if weather_data else None,
        )
    else:
        signature = ("preset", state["status"])

    if not force and signature == render_signature:
        return
    render_signature = signature

    if signature[0] == "custom":
        message = state["message"]
        display.render_preset(build_message_preset(message["text"], message["color"]))
    elif signature[0] == "clock":
        display.render_preset(weather.clock_preset(weather_data, now))
    else:
        display.render_preset(PRESETS[state["status"]])


def _cancel_revert():
    global revert_timer
    if revert_timer is not None:
        revert_timer.cancel()
        revert_timer = None
    state["revert_at"] = None


def _revert_now():
    global revert_timer
    with lock:
        revert_timer = None
        state["revert_at"] = None
        state["status"] = DEFAULT_PRESET
        _render_current()
        _save_state()


def _arm_revert(seconds):
    global revert_timer
    if revert_timer is not None:
        revert_timer.cancel()
    state["revert_at"] = int(time.time() + seconds)
    revert_timer = threading.Timer(seconds, _revert_now)
    revert_timer.daemon = True
    revert_timer.start()


def _remember_message(text, color):
    recents = state["recents"]
    recents[:] = [entry for entry in recents if entry["text"] != text]
    recents.insert(0, {"text": text, "color": color})
    del recents[MAX_RECENTS:]


def _scheduler_loop():
    """Keeps weather fresh and flips the idle screen at work-hour boundaries."""
    global weather_data
    while True:
        try:
            settings = state["settings"]
            if settings["weather_idle"] or state["status"] == "clock":
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
            with lock:
                _render_current()
        except Exception:
            pass
        time.sleep(SCHEDULER_INTERVAL)


def _api_payload():
    return {**state, "showing_weather": _idle_clock_active(), "weather": weather_data}


@app.route("/")
def index():
    return render_template(
        "index.html",
        presets=PRESETS,
        message_colors=MESSAGE_COLORS,
        state=_api_payload(),
        labels_json=json.dumps({key: preset["label"] for key, preset in PRESETS.items()}),
        preset_colors_json=json.dumps(
            {key: preset["ui_color"] for key, preset in PRESETS.items()}
        ),
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


@app.route("/api/state")
def get_state():
    return jsonify(_api_payload())


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
            if "weather_idle" in incoming:
                settings["weather_idle"] = bool(incoming["weather_idle"])
            for key in ("work_start", "work_end"):
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
            _render_current()

        screen_changed = False
        if "message" in data:
            message = data["message"] or {}
            text = str(message.get("text", "")).strip()[:MAX_MESSAGE_LENGTH]
            if not text:
                return jsonify(error="message text is required"), 400
            color = _valid_color(message.get("color"))
            state["message"] = {"text": text, "color": color}
            state["status"] = "custom"
            _remember_message(text, color)
            _render_current()
            screen_changed = True
        elif "status" in data:
            status = data["status"]
            if status == "off":  # accept the old name from stale clients
                status = "clock"
            if status != "clock" and status not in PRESETS:
                return jsonify(error="unknown status"), 400
            state["status"] = status
            _render_current()
            screen_changed = True

        if screen_changed:
            minutes = data.get("revert_minutes")
            if minutes is not None:
                try:
                    minutes = int(minutes)
                except (TypeError, ValueError):
                    return jsonify(error="revert_minutes must be a number"), 400
                if not 1 <= minutes <= MAX_REVERT_MINUTES:
                    return jsonify(error="revert_minutes out of range"), 400
                _arm_revert(minutes * 60)
            else:
                _cancel_revert()

        _save_state()
    return jsonify(_api_payload())


if __name__ == "__main__":
    _load_state()
    display.set_brightness(state["brightness"])
    with lock:
        if state["revert_at"] is not None:
            remaining = state["revert_at"] - time.time()
            if remaining <= 0:
                state["status"] = DEFAULT_PRESET
                state["revert_at"] = None
            else:
                _arm_revert(remaining)
        _render_current(force=True)
        _save_state()
    threading.Thread(target=_scheduler_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=5000)
