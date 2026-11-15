"""Password hashing, CSRF tokens and cookie helpers."""
import hashlib
import hmac
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
