"""The ONLY functions that cannot take a shop_id.

login-by-email, slug -> shop lookup, shop/user creation and the TLS "ask" check
all start from something other than a known shop. Everything else lives in repo.py
and requires shop_id. Keep this module small and review it carefully.
"""
import re
import sqlite3

RESERVED_SLUGS = frozenset({
    "www", "admin", "api", "mail", "app", "static", "ftp", "smtp", "imap", "pop",
    "ns1", "ns2", "webmail", "dashboard", "login", "register", "internal", "s", "demo",
})
_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,38}[a-z0-9])$")


def valid_slug(slug):
    return isinstance(slug, str) and bool(_SLUG_RE.match(slug)) and "--" not in slug


def create_shop(conn, name, slug, currency="INR"):
    name = (name or "").strip() if isinstance(name, str) else ""
    if not name or len(name) > 120:
        raise ValueError("shop name is required (max 120 characters)")
    if not valid_slug(slug):
        raise ValueError("invalid slug")
    if slug in RESERVED_SLUGS:
        raise ValueError("slug is reserved")
    if not re.fullmatch(r"[A-Z]{3}", currency or ""):
        raise ValueError("currency must be a 3-letter code")
    try:
        cur = conn.execute(
            "INSERT INTO shops (slug, name, currency) VALUES (?,?,?)", (slug, name, currency))
    except sqlite3.IntegrityError:
        raise ValueError("slug is already taken") from None
    conn.commit()
    return cur.lastrowid


def get_shop_by_slug(conn, slug):
    if not isinstance(slug, str):
        return None
    row = conn.execute("SELECT * FROM shops WHERE slug = ?", (slug.lower(),)).fetchone()
    return dict(row) if row else None


def slug_exists(conn, slug):
    return get_shop_by_slug(conn, slug) is not None


def create_user(conn, shop_id, email, pw_hash):
    email = (email or "").strip().lower() if isinstance(email, str) else ""
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) or len(email) > 254:
        raise ValueError("invalid email")
    try:
        cur = conn.execute(
            "INSERT INTO users (shop_id, email, pw_hash) VALUES (?,?,?)", (shop_id, email, pw_hash))
    except sqlite3.IntegrityError:
        raise ValueError("email already registered") from None
    conn.commit()
    return cur.lastrowid


def get_user_by_email(conn, email):
    if not isinstance(email, str):
        return None
    row = conn.execute("SELECT * FROM users WHERE email = ?", (email.strip().lower(),)).fetchone()
    return dict(row) if row else None


def tls_ask_allowed(conn, domain, base_domain):
    """True only for the apex, www, or a direct subdomain that is an existing shop slug."""
    if not isinstance(domain, str) or not isinstance(base_domain, str) or not base_domain:
        return False
    domain, base = domain.strip().lower().rstrip("."), base_domain.strip().lower()
    if domain in (base, "www." + base):
        return True
    if not domain.endswith("." + base):
        return False
    label = domain[: -(len(base) + 1)]
    return "." not in label and slug_exists(conn, label)
