"""Fetches weather from Open-Meteo (no API key) for the idle screen."""
import json
import time
import urllib.request
from datetime import datetime

FETCH_TIMEOUT = 10

# WMO weather interpretation codes → emoji.
_WMO_EMOJI = (
    ({0}, "☀️"),
    ({1}, "🌤️"),
    ({2}, "⛅"),
    ({3}, "☁️"),
    ({45, 48}, "🌫️"),
    ({51, 53, 55, 56, 57}, "🌦️"),
    ({61, 63, 65, 66, 67, 80, 81, 82}, "🌧️"),
    ({71, 73, 75, 77, 85, 86}, "🌨️"),
    ({95, 96, 99}, "⛈️"),
)


def _emoji_for(code):
    for codes, emoji in _WMO_EMOJI:
        if code in codes:
            return emoji
    return "🌡️"


def detect_location():
    """Rough lat/lon from the public IP, or None if offline."""
    try:
        with urllib.request.urlopen("https://ipinfo.io/json", timeout=FETCH_TIMEOUT) as resp:
            data = json.load(resp)
        lat, lon = data["loc"].split(",")
        return float(lat), float(lon)
    except Exception:
        return None


def fetch(lat, lon, units="f"):
    """Current conditions + today's high/low, or None on any failure."""
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        "&current=temperature_2m,weather_code"
        "&daily=temperature_2m_max,temperature_2m_min"
        "&forecast_days=1&timezone=auto"
    )
    if units == "f":
        url += "&temperature_unit=fahrenheit"
    try:
        with urllib.request.urlopen(url, timeout=FETCH_TIMEOUT) as resp:
            data = json.load(resp)
        return {
            "temp": round(data["current"]["temperature_2m"]),
            "code": int(data["current"]["weather_code"]),
            "hi": round(data["daily"]["temperature_2m_max"][0]),
            "lo": round(data["daily"]["temperature_2m_min"][0]),
            "fetched": time.time(),
        }
    except Exception:
        return None


def weather_preset(data):
    """Panel preset dict for the idle weather screen."""
    return {
        "emoji": _emoji_for(data["code"]),
        "lines": [f"{data['temp']}°", f"{data['hi']}/{data['lo']}"],
        "bg_color": (0, 12, 36),
        "text_color": (255, 255, 255),
    }


def clock_preset(data, now=None):
    """Panel preset showing the local time, plus weather when available.

    The Pi's system timezone drives the time shown (set via timedatectl).
    """
    now = now or datetime.now()
    time_str = now.strftime("%-I:%M")
    if data:
        return {
            "emoji": _emoji_for(data["code"]),
            "lines": [time_str, f"{data['temp']}°"],
            "bg_color": (0, 10, 30),
            "text_color": (255, 255, 255),
        }
    return {
        "lines": [time_str],
        "bg_color": (0, 10, 30),
        "text_color": (255, 255, 255),
    }
