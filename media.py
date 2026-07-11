"""GIF/image handling for the panel: uploads and random funny GIFs.

Anything displayed is normalized to a list of (64x32 RGB frame,
duration_seconds) tuples. The original file is kept in media/ so the
current GIF survives a restart.
"""
import json
import math
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
        # Letterbox rather than crop: scale to fit, centered on black —
        # unlit pixels read as bezel on an LED panel, so nothing is lost.
        scaled = ImageOps.contain(
            frame.convert("RGB"), (PANEL_COLS, PANEL_ROWS), Image.LANCZOS
        )
        fitted = Image.new("RGB", (PANEL_COLS, PANEL_ROWS), (0, 0, 0))
        fitted.paste(
            scaled,
            ((PANEL_COLS - scaled.width) // 2, (PANEL_ROWS - scaled.height) // 2),
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


# ---- arcade mode ------------------------------------------------------
# An original retro-platformer loop (no licensed sprites): scrolling brick
# ground, pipes, blinking coins, and a little runner in KnockBlock colors
# who jumps the pipes. World is 128px wide and tiles seamlessly.

ARCADE_FRAME_COUNT = 64
ARCADE_FRAME_SECONDS = 0.08
_WORLD = 128
_arcade_frames_cache = None

_SKY = (8, 24, 72)
_CLOUD = (150, 150, 165)
_BRICK = (110, 52, 12)
_MORTAR = (46, 20, 4)
_PIPE = (0, 110, 20)
_PIPE_DARK = (0, 70, 12)
_PIPE_LIP = (0, 140, 30)
_BUSH = (0, 90, 16)
_COIN = (200, 150, 0)
_COIN_BRIGHT = (255, 215, 40)
_HERO_SUIT = (230, 80, 10)   # hi-vis, of course
_HERO_SKIN = (220, 170, 120)
_HERO_PANTS = (60, 58, 30)
_HERO_SHOE = (30, 20, 8)
_HERO_EYE = (10, 10, 10)

_HERO_ROWS = (  # (color, [x spans]) per row, 6px wide
    (_HERO_SUIT, [(1, 4)]),          # cap
    (_HERO_SUIT, [(1, 5)]),          # cap brim
    (_HERO_SKIN, [(1, 4)]),          # face (eye stamped after)
    (_HERO_SKIN, [(2, 4)]),          # chin
    (_HERO_SUIT, [(1, 4)]),          # shirt
    (_HERO_SUIT, [(0, 5)]),          # arms out
    (_HERO_PANTS, [(1, 4)]),         # pants
)


def _wrapped(draw_fn, sx, width):
    """Call draw_fn(base_x) for every wrap position that touches the screen."""
    for base in (sx, sx - _WORLD, sx + _WORLD):
        if -width < base < PANEL_COLS:
            draw_fn(base)


def _draw_hero(pixels, x, top, airborne, stride):
    for row, (color, spans) in enumerate(_HERO_ROWS):
        for x0, x1 in spans:
            for dx in range(x0, x1 + 1):
                if 0 <= x + dx < PANEL_COLS:
                    pixels[x + dx, top + row] = color
    pixels[x + 4, top + 2] = _HERO_EYE
    feet = top + 7
    if airborne:
        shoes = [(1, 1), (4, 5)]     # tucked mid-jump
    elif stride:
        shoes = [(0, 1), (4, 5)]     # legs apart
    else:
        shoes = [(2, 3)]             # legs together
    for x0, x1 in shoes:
        for dx in range(x0, x1 + 1):
            if 0 <= x + dx < PANEL_COLS:
                pixels[x + dx, feet] = _HERO_SHOE


def _arcade_frame(t):
    from PIL import ImageDraw

    image = Image.new("RGB", (PANEL_COLS, PANEL_ROWS), _SKY)
    draw = ImageDraw.Draw(image)
    pixels = image.load()
    scroll = (t * 2) % _WORLD

    # Clouds drift at half speed (parallax).
    cloud_scroll = (t) % _WORLD
    for wx, y in ((10, 4), (58, 7), (96, 3)):
        sx = (wx - cloud_scroll) % _WORLD
        _wrapped(lambda b, y=y: (
            draw.rectangle([b, y + 1, b + 8, y + 2], fill=_CLOUD),
            draw.rectangle([b + 2, y, b + 6, y + 3], fill=_CLOUD),
        ), sx, 9)

    # Bush on the ground line.
    sx = (62 - scroll) % _WORLD
    _wrapped(lambda b: (
        draw.rectangle([b, 24, b + 9, 25], fill=_BUSH),
        draw.rectangle([b + 2, 22, b + 7, 23], fill=_BUSH),
    ), sx, 10)

    # Blinking coins.
    coin = _COIN_BRIGHT if (t // 4) % 2 else _COIN
    for wx in (24, 82):
        sx = (wx - scroll) % _WORLD
        _wrapped(lambda b: (
            draw.rectangle([b, 11, b + 2, 14], fill=coin),
            draw.rectangle([b + 1, 12, b + 1, 13], fill=_COIN_BRIGHT),
        ), sx, 3)

    # Pipes.
    for wx in (40, 100):
        sx = (wx - scroll) % _WORLD
        def pipe(b):
            draw.rectangle([b + 1, 20, b + 8, 25], fill=_PIPE)
            draw.rectangle([b + 2, 20, b + 3, 25], fill=_PIPE_DARK)
            draw.rectangle([b, 18, b + 9, 19], fill=_PIPE_LIP)
        _wrapped(pipe, sx, 10)

    # Brick ground: two 3px courses, mortar seams offset per course.
    draw.rectangle([0, 26, PANEL_COLS - 1, PANEL_ROWS - 1], fill=_BRICK)
    for x in range(PANEL_COLS):
        world_x = (x + scroll) % _WORLD
        if world_x % 8 == 0:
            pixels[x, 27] = _MORTAR
            pixels[x, 28] = _MORTAR
        if world_x % 8 == 4:
            pixels[x, 30] = _MORTAR
            pixels[x, 31] = _MORTAR
    for x in range(PANEL_COLS):
        pixels[x, 26] = _MORTAR if (x + scroll) % 2 else _BRICK
        pixels[x, 29] = _MORTAR

    # The runner: jumps timed so each pipe passes underneath mid-flight.
    height = 0
    for start in (11, 41):  # scroll/2 when each pipe reaches the hero
        if start <= t <= start + 10:
            progress = (t - start) / 10
            height = round(12 * math.sin(math.pi * progress))
    _draw_hero(pixels, 10, 18 - height, airborne=height > 0, stride=(t // 2) % 2)

    return image


def arcade_frames():
    """Looping frames for arcade mode. Deterministic; generated once."""
    global _arcade_frames_cache
    if _arcade_frames_cache is None:
        _arcade_frames_cache = [
            (_arcade_frame(t), ARCADE_FRAME_SECONDS)
            for t in range(ARCADE_FRAME_COUNT)
        ]
    return _arcade_frames_cache


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


