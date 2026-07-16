"""Run the KnockBlock app locally with a stubbed panel, for UI work.

    python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
    ./venv/bin/python3 dev/dev_server.py

Runtime files (auth.json, state.json, media) live in dev/state/ so the
real sign's files are never touched. Environment switches:

    KNOCKBLOCK_DEV_FRESH=1      wipe dev/state/ before starting
    KNOCKBLOCK_DEV_LOCAL=1      treat the browser as a LAN client
                                (default: it poses as a public client so
                                the login and demo flows are exercisable)
    KNOCKBLOCK_DEV_UNCLAIMED=1  skip setting the dev password (first-run
                                claim flow; combine with DEV_LOCAL)
    KNOCKBLOCK_DEV_FAKE_GIFS=1  offline GIF search/pick fixtures, so the
                                flow is testable without provider keys
"""
import os
import shutil
import sys
from pathlib import Path

DEV_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(DEV_DIR))  # rgbmatrix stub
sys.path.insert(0, str(DEV_DIR.parent))

RUN_DIR = DEV_DIR / "state"
if os.environ.get("KNOCKBLOCK_DEV_FRESH") and RUN_DIR.exists():
    shutil.rmtree(RUN_DIR)
RUN_DIR.mkdir(exist_ok=True)

import auth
auth.AUTH_FILE = RUN_DIR / "auth.json"
import media
media.MEDIA_DIR = RUN_DIR / "media"
media.CURRENT_FILE = media.MEDIA_DIR / "current"
media.FIRE_GIF = media.MEDIA_DIR / "fire.gif"
import history
history.HISTORY_DIR = RUN_DIR
import app as kb
kb.STATE_FILE = RUN_DIR / "state.json"

from matrix import MatrixDisplay

kb.display = MatrixDisplay()
# Never let the Update button reset the development checkout.
kb.UPDATE_SCRIPT = RUN_DIR / "no-self-update-in-dev"

if os.environ.get("KNOCKBLOCK_DEV_FAKE_GIFS"):
    import base64
    import random as _random
    from io import BytesIO
    from PIL import Image

    def _fixture_bytes(seed):
        rng = _random.Random(seed)
        base = tuple(rng.randrange(30, 180) for _ in range(3))
        frames = [
            Image.new("RGB", (64, 32), tuple(min(255, c + i * 20) for c in base))
            for i in range(4)
        ]
        buf = BytesIO()
        frames[0].save(buf, "GIF", save_all=True, append_images=frames[1:],
                       duration=200, loop=0)
        return buf.getvalue()

    _FIXTURES = {f"https://media.tenor.com/fixture/{i}.gif": _fixture_bytes(i)
                 for i in range(6)}

    def _fake_search(query, limit=12):
        return [
            {"url": url,
             "preview": "data:image/gif;base64," + base64.b64encode(raw).decode(),
             "title": f"{(query or 'fixture').strip() or 'fixture'} #{i + 1}"}
            for i, (url, raw) in enumerate(_FIXTURES.items())
        ]

    def _fake_fetch(url):
        if url in _FIXTURES:
            return _FIXTURES[url]
        raise ValueError("that URL isn't from a known GIF provider")

    media.search_gifs = _fake_search
    media.fetch_gif_url = _fake_fetch
    print("Fake GIF providers active")
if not auth.password_set() and not os.environ.get("KNOCKBLOCK_DEV_UNCLAIMED"):
    auth.set_password("devpassword1")
if not os.environ.get("KNOCKBLOCK_DEV_LOCAL"):
    # Localhost normally bypasses auth entirely; mark it untrusted so the
    # login/demo flows behave like they do for a public client.
    auth._load()
    auth._data["untrusted_proxies"] = ["127.0.0.1"]

kb._load_state()
if not kb.state["recents"]:
    kb.state["recents"] = [
        {"text": "🍕 Back at 1:30", "color": "orange"},
        {"text": "🎧 Focus time", "color": "purple"},
    ]
kb._render_current(force=True)
kb.app.config["TEMPLATES_AUTO_RELOAD"] = True
kb.app.jinja_env.auto_reload = True
print("Dev password: devpassword1" if auth.password_set() else "Unclaimed — claim flow active")
kb.app.run(host="127.0.0.1", port=5099)
