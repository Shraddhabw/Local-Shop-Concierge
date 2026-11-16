"""Password hashing, CSRF tokens and cookie helpers."""
import base64
import hashlib
import hmac
import json
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_hasher = PasswordHasher()
_DUMMY_HASH = _hasher.hash("not-a-real-password")
MIN_PASSWORD, MAX_PASSWORD = 10, 128


def hash_password(password):
    return _hasher.hash(password)


def verify_password(password, pw_hash):
    """Constant-ish time: verifies against a dummy hash when the user does not exist."""
    try:
        return _hasher.verify(pw_hash or _DUMMY_HASH, password) and pw_hash is not None
    except (VerificationError, InvalidHashError):
        return False


def new_token():
    return secrets.token_urlsafe(32)


def csrf_field_for(secret_key, cookie_value):
    return hmac.new(secret_key.encode(), f"csrf:{cookie_value}".encode(), hashlib.sha256).hexdigest()


def csrf_ok(secret_key, cookie_value, form_value):
    if not cookie_value or not form_value:
        return False
    return hmac.compare_digest(csrf_field_for(secret_key, cookie_value), form_value)


COOKIE_OPTS = dict(httponly=True, secure=True, samesite="lax", path="/")  # no domain: host-only


# ---- flash messages: a signed, single-use cookie bound to the owner's session cookie ----
FLASH_MAX_TEXT = 300


def _flash_sig(secret_key, session_value, payload):
    return hmac.new(secret_key.encode(), f"flash:{session_value}:{payload}".encode(), hashlib.sha256).hexdigest()


def flash_pack(secret_key, session_value, kind, text, public=False):
    body = json.dumps({"k": "err" if kind == "err" else "ok", "t": str(text)[:FLASH_MAX_TEXT], "p": bool(public)})
    payload = base64.urlsafe_b64encode(body.encode()).decode().rstrip("=")
    return f"{payload}.{_flash_sig(secret_key, session_value, payload)}"


def flash_unpack(secret_key, session_value, cookie_value):
    """Returns {"kind","text","public"} or None for a missing, forged, or other-session cookie."""
    try:
        payload, sig = (cookie_value or "").split(".", 1)
        if not session_value or not hmac.compare_digest(_flash_sig(secret_key, session_value, payload), sig):
            return None
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        return {"kind": "err" if data["k"] == "err" else "ok", "text": str(data["t"])[:FLASH_MAX_TEXT],
                "public": bool(data["p"])}
    except (ValueError, KeyError, TypeError):
        return None
