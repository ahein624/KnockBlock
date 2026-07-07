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
from matrix import PANEL_COLS, PANEL_ROWS

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


