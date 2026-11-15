"""T9 security regression tests: each one guards a finding listed in SECURITY.md."""
import inspect
import logging
import re
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import global_lookups as g, mailer, repo
from app.main import create_app
from tests.test_dashboard import browser, csrf, env, make_owner  # noqa: F401

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import scan_secrets  # noqa: E402


def all_routes():
    """Every route of every router (read from the router modules, not Starlette internals)."""
    from app.routers import auth_routes, chat, contact, internal, owner, public
    return [r for m in (auth_routes, chat, contact, internal, owner, public) for r in m.router.routes]


def post_routes(app):
    out = []
    for r in all_routes():
        methods = getattr(r, "methods", None) or set()
        if methods & {"POST", "PUT", "PATCH", "DELETE"} and not r.path.startswith("/api/"):
            out.append((r.path, sorted(methods - {"HEAD", "OPTIONS"})))
    return out


def fill(path):
    return re.sub(r"\{[^}]+\}", "1", path)


# ---- CSRF: every state-changing browser route rejects a missing/forged token ----
def test_every_post_route_requires_csrf(env):
    make_owner(env, "Glow Salon", "glow-salon", "a@example.com")
    c = browser("tok-glow-salon")                        # logged in, so the auth guard passes
    routes = post_routes(c.app)
    assert len(routes) >= 17
    for path, methods in routes:
        for method in methods:
            r = c.request(method, fill(path), data={})
            assert r.status_code == 400, f"{method} {path} accepted a request without a CSRF token"
            r = c.request(method, fill(path), data={"csrf_token": "0" * 64})
            assert r.status_code == 400, f"{method} {path} accepted a forged CSRF token"


def test_every_dashboard_route_requires_login(env):
    anon = browser()
    seen = 0
    for r in all_routes():
        if r.path.startswith("/dashboard"):
            seen += 1
            for method in sorted((r.methods or set()) - {"HEAD", "OPTIONS"}):
                resp = anon.request(method, fill(r.path), data={})
                assert resp.status_code == 303 and resp.headers["location"] == "/login", (method, r.path)
    assert seen >= 20


def test_cookie_flags(env):
    c = browser()
    cookie = c.get("/login").headers["set-cookie"].lower()
    assert "httponly" in cookie and "secure" in cookie and "samesite=lax" in cookie and "domain=" not in cookie


# ---- tenant scoping ----
def test_every_repo_function_requires_shop_id():
    funcs = [f for n, f in inspect.getmembers(repo, inspect.isfunction)
             if not n.startswith("_") and f.__module__ == repo.__name__]
    assert len(funcs) > 30
    for f in funcs:
        params = list(inspect.signature(f).parameters)
        assert params[:2] == ["conn", "shop_id"], f"{f.__name__} must take (conn, shop_id, ...)"


def test_every_tenant_sql_statement_mentions_shop_id():
    src = (ROOT / "app" / "repo.py").read_text()
    tenant = re.compile(r"services|faqs|hours|leads|unanswered_questions|chat_events|ai_usage|\{table\}|users")
    for chunk in src.split("conn.execute(")[1:]:
        stmt = chunk.split(")\n", 1)[0][:600]
        if re.search(r"\b(FROM|INTO|UPDATE)\b", stmt) and tenant.search(stmt):
            assert "shop_id" in stmt, f"SQL without shop_id: {stmt[:120]}"


def test_functions_without_shop_id_live_only_in_global_lookups():
    # the data layer has none (test above); anything else unscoped must be in global_lookups
    names = {n for n, f in inspect.getmembers(g, inspect.isfunction) if not n.startswith("_") and f.__module__ == g.__name__}
    assert {"get_user_by_email", "get_shop_by_slug", "tls_ask_allowed"} <= names


# ---- CORS / API hardening ----
def test_no_cors_headers_anywhere(env):
    g.create_shop(env, "S", "shop-one")
    c = browser()
    for r in (c.get("/api/chat", headers={"Origin": "https://evil.example"}),
              c.options("/api/chat", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"}),
              c.post("/api/chat", json={"slug": "shop-one", "message": "hi"}, headers={"Origin": "https://evil.example"}),
              c.get("/s/shop-one", headers={"Origin": "https://evil.example"})):
        assert not [h for h in r.headers if h.lower().startswith("access-control-")]
    assert c.options("/api/chat", headers={"Origin": "https://evil.example"}).status_code == 405


def test_api_rejects_non_json_content_types(env):
    g.create_shop(env, "S", "shop-one")
    c = browser()
    body = '{"slug": "shop-one", "name": "A", "contact": "1", "consent": true}'
    for ctype in ("text/plain", "application/x-www-form-urlencoded", "multipart/form-data; boundary=x"):
        assert c.post("/api/lead", content=body, headers={"Content-Type": ctype}).status_code == 422
    assert repo.list_leads(env, 1) == []


def test_security_headers_on_every_kind_of_response(env):
    g.create_shop(env, "S", "shop-one")
    c = browser()
    for r in (c.get("/login"), c.get("/nope"), c.get("/dashboard"), c.get("/static/style.css"),
              c.get("/s/shop-one"), c.post("/api/chat", json={"slug": "x"})):
        h = r.headers
        assert h["x-content-type-options"] == "nosniff" and "max-age" in h["strict-transport-security"]
        assert "content-security-policy" in h and h["referrer-policy"]
    assert c.get("/dashboard").headers["cache-control"] == "no-store"
    assert c.get("/login").headers["x-frame-options"] == "DENY"


# ---- abuse limits ----
def test_one_shop_cannot_be_flooded_with_leads_from_many_ips(env, monkeypatch):
    make_owner(env, "Glow Salon", "glow-salon", "owner@example.com")
    monkeypatch.setenv("RATE_LIMITS_ENABLED", "true")
    monkeypatch.setenv("TRUSTED_PROXIES", "172.28.0.0/24")
    c = TestClient(create_app(), base_url="https://example.com", client=("172.28.0.2", 1), follow_redirects=False)
    mailer.OUTBOX.clear()
    codes = [c.post("/api/lead", json={"slug": "glow-salon", "name": "N", "contact": "1", "consent": True},
                    headers={"X-Forwarded-For": f"203.0.113.{i}"}).status_code for i in range(1, 36)]
    assert codes.count(200) == 30 and codes[-1] == 429
    assert len(repo.list_leads(env, 1)) == 30 and len(mailer.OUTBOX) == 30


def test_expired_sessions_are_purged(env):
    sid = g.create_shop(env, "S", "shop-one")
    uid = g.create_user(env, sid, "o@example.com", "h")
    g.create_session(env, uid, "old")
    env.execute("UPDATE sessions SET expires = '2000-01-01T00:00:00+00:00'")
    g.create_session(env, uid, "new")
    assert env.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 1


# ---- secrets: files, history, logs ----
def test_repo_and_history_contain_no_secrets():
    assert scan_secrets.scan(ROOT) == []


def run_git(repo_dir, *args):
    subprocess.run(["git", "-C", str(repo_dir), "-c", "user.name=t", "-c", "user.email=t@t", *args],
                   check=True, capture_output=True)


def test_scanner_detects_planted_secrets_even_after_removal(tmp_path):
    run_git(tmp_path, "init", "-q")
    fake_key = "sk-ant-" + "A1b2" * 10
    (tmp_path / "config.py").write_text(f'KEY = "{fake_key}"\n')
    (tmp_path / ".env").write_text("X=1\n")
    run_git(tmp_path, "add", "-A")
    run_git(tmp_path, "commit", "-qm", "oops")
    (tmp_path / "config.py").write_text("KEY = None\n")
    run_git(tmp_path, "rm", "-q", "--cached", ".env")
    run_git(tmp_path, "commit", "-qam", "removed")
    found = scan_secrets.scan(tmp_path)
    kinds = {what for _, what in found}
    assert {"anthropic-api-key", "forbidden-file-in-history"} <= kinds
    assert all(fake_key not in where for where, _ in found)          # values are never printed


def test_tokens_never_reach_logs(env, caplog, monkeypatch):
    monkeypatch.setenv("RATE_LIMITS_ENABLED", "false")
    c = TestClient(create_app(), base_url="https://example.com", follow_redirects=False)
    mailer.OUTBOX.clear()
    with caplog.at_level(logging.DEBUG):
        tok = re.search(r'value="([0-9a-f]+)"', c.get("/register").text).group(1)
        c.post("/register", data={"shop_name": "Glow", "email": "o@example.com",
                                  "password": "correct-horse-1", "csrf_token": tok})
        token = re.search(r"token=(\S+)", mailer.OUTBOX[-1]["body"]).group(1)
        c.get(f"/verify?token={token}")
    app_logs = "\n".join(r.getMessage() for r in caplog.records
                         if not r.name.startswith(("httpx", "asyncio")))   # test client's own log excluded
    assert token not in app_logs and "correct-horse-1" not in app_logs


def test_container_does_not_log_request_urls_and_caddy_limits_bodies():
    assert "--no-access-log" in (ROOT / "Dockerfile").read_text()
    cf = (ROOT / "Caddyfile").read_text()
    assert re.search(r"request_body\s*\{\s*max_size 256KB", cf)
