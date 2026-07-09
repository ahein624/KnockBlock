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
import app as kb
kb.STATE_FILE = RUN_DIR / "state.json"

from matrix import MatrixDisplay

kb.display = MatrixDisplay()
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
