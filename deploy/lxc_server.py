"""Run the full KnockBlock app without Raspberry Pi GPIO hardware."""
import os
import sys
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
RUN_DIR = Path(os.environ.get("KNOCKBLOCK_STATE_DIR", "/var/lib/knockblock"))
RUN_DIR.mkdir(parents=True, exist_ok=True)

# The development rgbmatrix shim preserves MatrixDisplay's exact frame
# bookkeeping without attempting to access Raspberry Pi GPIO.
sys.path.insert(0, str(REPO_DIR / "dev"))
sys.path.insert(0, str(REPO_DIR))

import auth
import history
import media

auth.AUTH_FILE = RUN_DIR / "auth.json"
media.MEDIA_DIR = RUN_DIR / "media"
media.CURRENT_FILE = media.MEDIA_DIR / "current"
media.FIRE_GIF = media.MEDIA_DIR / "fire.gif"
history.HISTORY_DIR = RUN_DIR

import app as knockblock

knockblock.STATE_FILE = RUN_DIR / "state.json"
knockblock.UPDATE_SCRIPT = RUN_DIR / "self-update-disabled"

if __name__ == "__main__":
    knockblock.main()
