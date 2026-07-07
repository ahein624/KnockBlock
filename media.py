"""GIF/image handling for the panel: uploads and random funny GIFs.

Anything displayed is normalized to a list of (64x32 RGB frame,
duration_seconds) tuples. The original file is kept in media/ so the
current GIF survives a restart.
"""
import json
import random
import urllib.parse
import urllib.request
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps, ImageSequence

import auth
from matrix import PANEL_COLS, PANEL_ROWS, _emoji_image, _font

MEDIA_DIR = Path(__file__).resolve().parent / "media"
CURRENT_FILE = MEDIA_DIR / "current"  # extension added on save
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_FRAMES = 200
MIN_FRAME_SECONDS = 0.03
DEFAULT_FRAME_SECONDS = 0.1
FETCH_TIMEOUT = 15

# Queries used when the user just mashes the dice button.
FUNNY_QUERIES = [
    "funny fail", "dancing cat", "office humor", "deal with it", "excited dog",
    "facepalm", "mind blown", "typing furiously", "coffee please", "nope",
    "happy dance", "thumbs up", "this is fine", "raccoon",
]

# Keyless-ish public API keys: Tenor v1's demo key and Giphy's public beta
# key. Either may eventually die; both are tried in order.
TENOR_KEY = "LIVDSRZULELA"
GIPHY_KEY = "dc6zaTOxFJmzC"


def frames_from_bytes(raw):
    """Decode an image/GIF into panel-sized frames.

    Raises ValueError for anything Pillow can't read.
    """
    try:
        image = Image.open(BytesIO(raw))
        image.load()
    except Exception as err:
        raise ValueError("not a readable image") from err
    frames = []
    for frame in ImageSequence.Iterator(image):
        duration = frame.info.get("duration", DEFAULT_FRAME_SECONDS * 1000) / 1000
        fitted = ImageOps.fit(
            frame.convert("RGB"), (PANEL_COLS, PANEL_ROWS), Image.LANCZOS
        )
        frames.append((fitted, max(duration, MIN_FRAME_SECONDS)))
        if len(frames) >= MAX_FRAMES:
            break
    if not frames:
        raise ValueError("no frames in image")
    return frames


def save_current(raw, kind):
    """Persist the raw file as media/current.<ext>; returns the Path."""
    MEDIA_DIR.mkdir(exist_ok=True)
    for old in MEDIA_DIR.glob("current.*"):
        old.unlink()
    path = CURRENT_FILE.with_suffix(".gif" if kind == "gif" else ".png")
    if kind == "gif":
        path.write_bytes(raw)
    else:
        # Normalize stills (JPEG/WebP/PNG…) to PNG.
        image = Image.open(BytesIO(raw))
        image.convert("RGB").save(path, "PNG")
    return path


def load_current():
    """Frames for the persisted file, or None if there isn't one."""
    for path in MEDIA_DIR.glob("current.*"):
        try:
            return frames_from_bytes(path.read_bytes())
        except (OSError, ValueError):
            return None
    return None


# ---- dumpster fire mode ----------------------------------------------

FIRE_FRAME_COUNT = 28
FIRE_FRAME_SECONDS = 0.09
FIRE_GIF = MEDIA_DIR / "fire.gif"  # drop a GIF here to replace the procedural flames
# Heat 0..1 → color ramp: black → deep red → orange → yellow → near-white.
_FIRE_RAMP = [
    (0.00, (0, 0, 0)),
    (0.25, (90, 4, 0)),
    (0.50, (200, 48, 0)),
    (0.75, (255, 140, 10)),
    (0.90, (255, 210, 60)),
    (1.00, (255, 250, 200)),
]
_fire_frames_cache = None


def _heat_color(t):
    for (t0, c0), (t1, c1) in zip(_FIRE_RAMP, _FIRE_RAMP[1:]):
        if t <= t1:
            f = (t - t0) / (t1 - t0)
            return tuple(int(a + (b - a) * f) for a, b in zip(c0, c1))
    return _FIRE_RAMP[-1][1]


def _fire_text_layer():
    """THIS IS FINE (plus the dog, when an emoji font exists) on
    transparent RGBA, composited over every flame frame."""
    from PIL import ImageDraw

    layer = Image.new("RGBA", (PANEL_COLS, PANEL_ROWS), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    font = _font(10)
    for text, y in (("THIS IS", 3), ("FINE.", 15)):
        bbox = draw.textbbox((0, 0), text, font=font)
        x = (PANEL_COLS - (bbox[2] - bbox[0])) // 2 - bbox[0]
        draw.text(
            (x, y), text, font=font, fill=(255, 255, 255, 255),
            stroke_width=1, stroke_fill=(0, 0, 0, 255),
        )
    dog = _emoji_image("\U0001F436", 11)  # 🐶 — sits calmly in the flames
    if dog is not None:
        layer.paste(dog, (2, 2), dog)
    return layer


def dumpster_fire_frames():
    """Looping procedural-flame frames for dumpster fire mode.

    Classic heat-diffusion fire: hidden hot rows below the panel feed
    randomized heat that rises and cools. Deterministic seed, generated
    once and cached.
    """
    global _fire_frames_cache
    if _fire_frames_cache is not None:
        return _fire_frames_cache

    rng = random.Random(20260707)
    width, height = PANEL_COLS, PANEL_ROWS
    rows = height + 3  # 3 hidden feeder rows below the visible panel
    heat = [[0.0] * width for _ in range(rows)]
    text = _fire_text_layer()
    frames = []
    warmup = 40
    for step in range(warmup + FIRE_FRAME_COUNT):
        for x in range(width):  # stoke the feeder rows
            heat[rows - 1][x] = rng.uniform(0.55, 1.0)
            heat[rows - 2][x] = rng.uniform(0.45, 0.95)
        for y in range(rows - 2):
            below = heat[y + 1]
            for x in range(width):
                total = (
                    below[max(x - 1, 0)]
                    + below[x]
                    + below[min(x + 1, width - 1)]
                    + heat[min(y + 2, rows - 1)][x]
                )
                heat[y][x] = max(0.0, total / 4 - rng.uniform(0.02, 0.11))
        if step < warmup:
            continue
        image = Image.new("RGB", (width, height))
        pixels = image.load()
        for y in range(height):
            for x in range(width):
                pixels[x, y] = _heat_color(min(heat[y][x], 1.0))
        image.paste(text, (0, 0), text)
        frames.append((image, FIRE_FRAME_SECONDS))

    _fire_frames_cache = frames
    return frames


_fire_gif_cache = (None, None)  # (mtime, frames)


def fire_gif_mtime():
    """Mtime of the custom fire GIF, or 0 if using procedural flames."""
    try:
        return FIRE_GIF.stat().st_mtime
    except OSError:
        return 0


def fire_frames():
    """What dumpster fire mode plays: media/fire.gif if present (the user's
    chosen meme), else the generated procedural flames."""
    global _fire_gif_cache
    mtime = fire_gif_mtime()
    if not mtime:
        return dumpster_fire_frames()
    cached_mtime, cached_frames = _fire_gif_cache
    if cached_mtime != mtime:
        try:
            frames = frames_from_bytes(FIRE_GIF.read_bytes())
        except (OSError, ValueError):
            return dumpster_fire_frames()
        _fire_gif_cache = (mtime, frames)
    return _fire_gif_cache[1]


def _get_json(url):
    request = urllib.request.Request(url, headers={"User-Agent": "KnockBlock/1.0"})
    with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT) as resp:
        return json.loads(resp.read())


def _download(url):
    request = urllib.request.Request(url, headers={"User-Agent": "KnockBlock/1.0"})
    with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT) as resp:
        return resp.read(MAX_UPLOAD_BYTES)


def _tenor_random(query):
    url = "https://g.tenor.com/v1/random?" + urllib.parse.urlencode(
        {"q": query, "key": TENOR_KEY, "limit": 1, "media_filter": "minimal"}
    )
    results = _get_json(url).get("results") or []
    # nanogif is ~90px tall — plenty for a 64x32 panel and a tiny download.
    media = results[0]["media"][0]
    gif = media.get("nanogif") or media.get("tinygif") or media.get("gif")
    return _download(gif["url"])


def _giphy_random(query, key=None):
    url = "https://api.giphy.com/v1/gifs/random?" + urllib.parse.urlencode(
        {"api_key": key or GIPHY_KEY, "tag": query, "rating": "pg"}
    )
    images = _get_json(url)["data"]["images"]
    pick = (
        images.get("fixed_height_small")
        or images.get("downsized")
        or images.get("original")
    )
    return _download(pick["url"])


def fetch_random_gif(query=None):
    """Random GIF bytes for a query (or a random funny one).

    Returns (raw_bytes, query_used). A personal Giphy key (auth.json
    "giphy_key") is tried first; the public demo keys are fallbacks.
    Raises RuntimeError if every provider fails.
    """
    query = (query or "").strip() or random.choice(FUNNY_QUERIES)
    providers = []
    personal = auth.giphy_key()
    if personal:
        providers.append(lambda q: _giphy_random(q, personal))
    providers += [_tenor_random, _giphy_random]
    for provider in providers:
        try:
            return provider(query), query
        except Exception:
            continue
    raise RuntimeError("couldn't fetch a GIF (providers unreachable)")


