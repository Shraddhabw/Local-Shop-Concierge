import re
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import global_lookups as g, mailer
from app.main import create_app
from app.ratelimit import client_ip


@pytest.fixture
def make_client(tmp_path, monkeypatch):
    def make(rate_limits="false", host="example.com"):
        monkeypatch.setenv("SECRET_KEY", "k" * 40)
        monkeypatch.setenv("BASE_DOMAIN", "example.com")
        monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "t.db"))
        monkeypatch.setenv("RATE_LIMITS_ENABLED", rate_limits)
        from app import db
        c = db.connect()
        db.init_db(c)
        c.close()
        mailer.OUTBOX.clear()
        return TestClient(create_app(), base_url=f"https://{host}", follow_redirects=False)
    return make


@pytest.fixture
def client(make_client):
    return make_client()


def token_from(client, path="/register"):
    html = client.get(path).text
    return re.search(r'name="csrf_token" value="([0-9a-f]+)"', html).group(1)


def register(client, email="owner@example.com", password="correct-horse-1", name="Glow Salon"):
    return client.post("/register", data={"shop_name": name, "email": email, "password": password,
                                          "csrf_token": token_from(client)})


def login(client, email="owner@example.com", password="correct-horse-1"):
    return client.post("/login", data={"email": email, "password": password,
                                       "csrf_token": token_from(client, "/login")})


def verify_link():
    body = mailer.OUTBOX[-1]["body"]
    return re.search(r"https://example\.com(/verify\?token=\S+)", body).group(1)


def test_register_verify_login_flow(client, tmp_path):
    r = register(client)
    assert r.status_code == 200 and "Check your email" in r.text
    assert len(mailer.OUTBOX) == 1 and mailer.OUTBOX[0]["to"] == "owner@example.com"
    assert login(client).status_code == 400                       # not verified yet
    assert client.get(verify_link()).status_code == 200
    r = login(client)
    assert r.status_code == 303 and r.headers["location"] == "/dashboard"
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "secure" in cookie and "samesite=lax" in cookie
    assert "domain=" not in cookie                                # host-only cookie
    page = client.get("/dashboard")
    assert page.status_code == 200 and "Glow Salon" in page.text and "/s/glow-salon" in page.text


def test_password_stored_as_argon2(client):
    register(client)
    from app import db
    c = db.connect()
    assert g.get_user_by_email(c, "owner@example.com")["pw_hash"].startswith("$argon2")


def test_dashboard_requires_login_and_logout_ends_session(client):
    assert client.get("/dashboard").status_code == 303
    register(client)
    client.get(verify_link())
    login(client)
    assert client.get("/dashboard").status_code == 200
    r = client.post("/logout", data={"csrf_token": token_from(client, "/login")})
    assert r.status_code == 303
    assert client.get("/dashboard").status_code == 303


def test_csrf_required_on_all_post_forms(client):
    for path, data in [("/register", {"shop_name": "A Shop", "email": "a@b.co", "password": "x" * 12}),
                       ("/login", {"email": "a@b.co", "password": "x"}), ("/logout", {})]:
        assert client.post(path, data=data).status_code == 400
        assert client.post(path, data={**data, "csrf_token": "f" * 64}).status_code == 400


def test_validation_errors(client):
    assert register(client, password="short").status_code == 400
    assert register(client, email="not-an-email").status_code == 400
    assert register(client, name="   ").status_code == 400
    assert mailer.OUTBOX == []


def test_duplicate_email_looks_identical_and_creates_nothing(client):
    first = register(client)
    again = register(client, name="Other Shop")
    assert again.status_code == first.status_code == 200 and "Check your email" in again.text
    assert len(mailer.OUTBOX) == 1
    from app import db
    assert db.connect().execute("SELECT COUNT(*) FROM shops").fetchone()[0] == 1


@pytest.mark.parametrize("name", ["www", "admin", "API", "Mail", "app", "static"])
def test_reserved_names_never_become_slugs(client, name):
    register(client, name=name)
    from app import db
    slug = db.connect().execute("SELECT slug FROM shops").fetchone()["slug"]
    assert slug not in g.RESERVED_SLUGS and g.valid_slug(slug)


def test_slugs_are_unique(client):
    register(client, email="a@example.com", name="Glow Salon")
    register(client, email="b@example.com", name="Glow Salon")
    from app import db
    slugs = [r[0] for r in db.connect().execute("SELECT slug FROM shops")]
    assert sorted(slugs) == ["glow-salon", "glow-salon-2"]


def test_verify_token_single_use_invalid_and_expired(client):
    register(client)
    link = verify_link()
    assert client.get(link).status_code == 200
    assert client.get(link).status_code == 400                    # already used
    assert client.get("/verify?token=bogus").status_code == 400
    assert client.get("/verify").status_code == 400
    register(client, email="late@example.com", name="Late Shop")
    from app import db
    c = db.connect()
    c.execute("UPDATE users SET verify_expires = '2000-01-01T00:00:00+00:00' WHERE email = 'late@example.com'")
    c.commit()
    assert client.get(verify_link()).status_code == 400


def test_login_rate_limit_per_email(make_client):
    client = make_client("true")
    codes = [login(client, password="wrong-password-1").status_code for _ in range(6)]
    assert codes[:5] == [400] * 5 and codes[5] == 429


def test_register_rate_limit_per_ip(make_client):
    client = make_client("true")
    codes = [register(client, email=f"u{i}@example.com", name=f"Shop {i}").status_code for i in range(6)]
    assert codes[:5] == [200] * 5 and codes[5] == 429


def test_owner_pages_only_on_apex_domain(make_client):
    shop_client = make_client(host="glow.example.com")
    for path in ("/login", "/register", "/dashboard", "/verify"):
        assert shop_client.get(path).status_code == 404
    assert shop_client.get("/healthz").status_code == 200
    assert make_client(host="evil.com").get("/login").status_code == 404
    assert make_client(host="a.b.example.com").get("/login").status_code == 404
    assert make_client(host="www.example.com").get("/login").status_code == 200


def test_security_headers_present(client):
    h = client.get("/login").headers
    assert h["x-content-type-options"] == "nosniff" and h["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in h["content-security-policy"]
    assert "max-age" in h["strict-transport-security"]


def test_output_is_escaped(client):
    r = client.post("/register", data={"shop_name": '"><script>alert(1)</script>', "email": "bad",
                                       "password": "x" * 12, "csrf_token": token_from(client)})
    assert "<script>alert(1)</script>" not in r.text and "&lt;script&gt;" in r.text


def _req(peer, xff=None):
    headers = {"x-forwarded-for": xff} if xff else {}
    return SimpleNamespace(client=SimpleNamespace(host=peer), headers=headers)


def test_client_ip_trusts_forwarded_for_only_from_proxy():
    trusted = ["172.18.0.0/16"]
    assert client_ip(_req("172.18.0.5", "203.0.113.9"), trusted) == "203.0.113.9"
    assert client_ip(_req("172.18.0.5", "1.2.3.4, 203.0.113.9"), trusted) == "203.0.113.9"
    assert client_ip(_req("198.51.100.7", "1.2.3.4"), trusted) == "198.51.100.7"   # spoof attempt
    assert client_ip(_req("172.18.0.5", "1.2.3.4"), []) == "172.18.0.5"
    assert client_ip(_req("172.18.0.5"), trusted) == "172.18.0.5"


def test_secret_key_is_required(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "change-me-long-random")
    with pytest.raises(RuntimeError):
        create_app()
    monkeypatch.setenv("SECRET_KEY", "short")
    with pytest.raises(RuntimeError):
        create_app()


def test_sessions_expiry_and_unverified(conn):
    sid = g.create_shop(conn, "S", "shop-one")
    uid = g.create_user(conn, sid, "o@example.com", "h")
    g.create_session(conn, uid, "tok")
    assert g.get_session_user(conn, "tok") is None                # unverified user
    conn.execute("UPDATE users SET verified = 1")
    assert g.get_session_user(conn, "tok")["id"] == uid
    assert g.get_session_user(conn, "other") is None and g.get_session_user(conn, None) is None
    conn.execute("UPDATE sessions SET expires = '2000-01-01T00:00:00+00:00'")
    assert g.get_session_user(conn, "tok") is None
    g.delete_session(conn, "tok")
