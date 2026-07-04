"""Password + API-token auth backed by auth.json next to the app.

The password is set from the shell (`python3 app.py --set-password`), never
through the web — an internet-exposed sign with no password yet shouldn't be
claimable by whoever visits first. The API token authenticates scripted
clients (Stream Deck, curl) without a browser session.
"""
import hmac
import json
import secrets
import threading
from pathlib import Path

from werkzeug.security import check_password_hash, generate_password_hash

AUTH_FILE = Path(__file__).resolve().parent / "auth.json"

_lock = threading.Lock()
_data = None


def _load():
    global _data
    if _data is None:
        try:
            _data = json.loads(AUTH_FILE.read_text())
        except (FileNotFoundError, ValueError):
            _data = {}
    return _data


def _save():
    tmp = AUTH_FILE.with_suffix(".auth.tmp")
    tmp.write_text(json.dumps(_data))
    tmp.chmod(0o600)
    tmp.replace(AUTH_FILE)


def secret_key():
    """Stable Flask session key, so logins survive server restarts."""
    with _lock:
        data = _load()
        if not data.get("secret_key"):
            data["secret_key"] = secrets.token_hex(32)
            _save()
        return data["secret_key"]


def password_set():
    return bool(_load().get("password_hash"))


def check_password(password):
    stored = _load().get("password_hash")
    return bool(stored) and check_password_hash(stored, password)


def set_password(password):
    with _lock:
        data = _load()
        # pbkdf2 rather than werkzeug's scrypt default: scrypt needs
        # OpenSSL 1.1+ in hashlib, which not every Python build has.
        data["password_hash"] = generate_password_hash(password, method="pbkdf2:sha256")
        if not data.get("api_token"):
            data["api_token"] = secrets.token_urlsafe(24)
        _save()


def api_token():
    with _lock:
        data = _load()
        if not data.get("api_token"):
            data["api_token"] = secrets.token_urlsafe(24)
            _save()
        return data["api_token"]


def check_token(token):
    stored = _load().get("api_token")
    return bool(stored) and hmac.compare_digest(stored, token)


def regenerate_token():
    with _lock:
        data = _load()
        data["api_token"] = secrets.token_urlsafe(24)
        _save()
        return data["api_token"]
