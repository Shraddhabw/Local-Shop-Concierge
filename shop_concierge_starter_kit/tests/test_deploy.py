import gzip
import ipaddress
import re
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from app import db, global_lookups as g
from app.main import create_app
from tests.test_dashboard import env  # noqa: F401

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import backup_db  # noqa: E402

CADDY_IP = "172.28.0.2"


def ask_client(monkeypatch, proxies="172.28.0.0/24", peer=CADDY_IP):
    monkeypatch.setenv("TRUSTED_PROXIES", proxies)
    return TestClient(create_app(), base_url="http://app:8000", client=(peer, 50000), follow_redirects=False)


# ---------------- /internal/tls-ask ----------------
def test_tls_ask_approves_only_apex_www_and_existing_slugs(env, monkeypatch):
    g.create_shop(env, "Glow Salon", "glow-salon")
    c = ask_client(monkeypatch)
    ok = lambda d: c.get("/internal/tls-ask", params={"domain": d}).status_code
    assert ok("example.com") == ok("www.example.com") == ok("glow-salon.example.com") == 200
    assert ok("GLOW-SALON.example.com") == 200
    for bad in ("ghost.example.com", "a.glow-salon.example.com", "glow-salon.example.com.evil.com",
                "evil.com", "example.com.evil.com", "admin.example.com", "", "..", "glow-salon.example.org"):
        assert ok(bad) == 404, bad
    assert c.get("/internal/tls-ask").status_code == 404           # no domain given


def test_tls_ask_only_from_the_caddy_network(env, monkeypatch):
    g.create_shop(env, "Glow Salon", "glow-salon")
    for peer in ("203.0.113.9", "172.28.1.5", "127.0.0.1", "not-an-ip"):
        c = ask_client(monkeypatch, peer=peer)
        assert c.get("/internal/tls-ask", params={"domain": "example.com"}).status_code == 404, peer
    c = ask_client(monkeypatch, proxies="")                          # nothing trusted: fails closed
    assert c.get("/internal/tls-ask", params={"domain": "example.com"}).status_code == 404


def test_tls_ask_spoofed_forwarded_header_does_not_help(env, monkeypatch):
    c = ask_client(monkeypatch, peer="203.0.113.9")
    r = c.get("/internal/tls-ask", params={"domain": "example.com"},
              headers={"X-Forwarded-For": CADDY_IP, "Host": "example.com"})
    assert r.status_code == 404


def test_unknown_hosts_still_404_but_healthz_works(env, monkeypatch):
    c = ask_client(monkeypatch)
    assert c.get("/login").status_code == 404                        # Host "app:8000" is not ours
    assert c.get("/healthz").text == "ok"


# ---------------- deployment files ----------------
def compose():
    return yaml.safe_load((ROOT / "docker-compose.yml").read_text())


def test_compose_structure():
    c = compose()
    assert set(c["services"]) == {"app", "caddy", "backup"}
    assert "ports" not in c["services"]["app"] and "8000" in c["services"]["app"]["expose"]
    assert set(c["services"]["caddy"]["ports"]) == {"80:80", "443:443", "443:443/udp"}
    assert set(c["volumes"]) == {"app_data", "backups", "caddy_data", "caddy_config"}
    for name in ("app", "caddy"):
        assert c["services"][name]["healthcheck"]["test"]
        assert c["services"][name]["restart"] == "unless-stopped"
    assert c["services"]["caddy"]["depends_on"]["app"]["condition"] == "service_healthy"
    assert "app_data:/data" in c["services"]["app"]["volumes"] and "backups:/backups" in c["services"]["backup"]["volumes"]
    assert "caddy_data:/data" in c["services"]["caddy"]["volumes"]       # certificates survive restarts
    for name in ("app", "backup"):
        svc = c["services"][name]
        assert svc["read_only"] is True and svc["cap_drop"] == ["ALL"] and "no-new-privileges:true" in svc["security_opt"]


def test_trusted_proxy_range_is_the_private_caddy_network():
    c = compose()
    subnet = ipaddress.ip_network(c["networks"]["web"]["ipam"]["config"][0]["subnet"])
    trusted = ipaddress.ip_network(c["services"]["app"]["environment"]["TRUSTED_PROXIES"])
    assert trusted.subnet_of(subnet) and trusted.num_addresses <= 256
    assert ipaddress.ip_address(CADDY_IP) in trusted
    assert c["services"]["app"]["networks"] == ["web"] and c["services"]["caddy"]["networks"] == ["web"]


def test_dockerfile_non_root_slim_single_worker():
    d = (ROOT / "Dockerfile").read_text()
    assert re.search(r"^FROM python:[\d.]+-slim", d, re.M)
    users = re.findall(r"^USER (\S+)", d, re.M)
    assert users and users[-1] not in ("root", "0")
    assert d.index("USER app") < d.index("CMD")
    assert '"--workers", "1"' in d and "--no-proxy-headers" in d and "HEALTHCHECK" in d
    assert "COPY . " not in d and ".env" not in d


def test_dockerignore_keeps_secrets_and_data_out():
    ignored = (ROOT / ".dockerignore").read_text().split()
    for item in (".env", ".git", "*.db", "backups/", "*.pem", ".venv"):
        assert item in ignored


def test_caddyfile_security_and_routing():
    cf = (ROOT / "Caddyfile").read_text()
    assert "ask http://app:8000/internal/tls-ask" in cf and "on_demand" in cf
    assert "{$BASE_DOMAIN}, www.{$BASE_DOMAIN}" in cf
    assert cf.index("respond @internal 404") < cf.index("reverse_proxy")        # internal blocked first
    assert "path /internal /internal/*" in cf
    assert "header_up X-Forwarded-For {remote_host}" in cf
    for h in ("Strict-Transport-Security", "X-Content-Type-Options", "X-Frame-Options", "frame-ancestors 'none'"):
        assert h in cf


def test_no_secrets_in_deployment_files():
    for name in ("Dockerfile", "docker-compose.yml", "Caddyfile", ".env.example", ".dockerignore"):
        text = (ROOT / name).read_text()
        assert not re.search(r"sk-ant-[A-Za-z0-9_-]{8,}", text), name
        assert not re.search(r"(?im)^[ \t]*(SECRET_KEY|SMTP_PASSWORD|ANTHROPIC_API_KEY)[ \t]*[:=][ \t]*\S+", text.replace(
            "SECRET_KEY=change-me-long-random", "")), name
    assert "SMTP_HOST=smtpout.secureserver.net" in (ROOT / ".env.example").read_text()


# ---------------- backups ----------------
def make_db(path):
    conn = db.connect(path)
    db.init_db(conn)
    g.create_shop(conn, "Glow Salon", "glow-salon")
    return conn


def test_backup_is_consistent_compressed_and_restorable(tmp_path):
    live = make_db(tmp_path / "live.db")                      # connection stays open (app running, WAL on)
    out = backup_db.backup(tmp_path / "live.db", tmp_path / "bk")
    assert out.name.startswith("shop_concierge-") and out.name.endswith(".db.gz")
    assert oct(out.stat().st_mode & 0o777) == "0o600"
    restored = tmp_path / "restored.db"
    restored.write_bytes(gzip.decompress(out.read_bytes()))
    r = sqlite3.connect(restored)
    assert r.execute("SELECT slug FROM shops").fetchone()[0] == "glow-salon"
    assert r.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    live.close()
    assert not list((tmp_path / "bk").glob("*.partial"))


def test_backup_retention_keeps_newest(tmp_path):
    make_db(tmp_path / "live.db").close()
    base = datetime(2026, 11, 1, 21, 0, tzinfo=timezone.utc)
    for day in range(5):
        backup_db.backup(tmp_path / "live.db", tmp_path / "bk", keep=3, now=base + timedelta(days=day))
    names = sorted(p.name for p in (tmp_path / "bk").glob("*.db.gz"))
    assert [n[15:23] for n in names] == ["20261103", "20261104", "20261105"]


def test_backup_missing_db_fails_cleanly(tmp_path):
    with pytest.raises(FileNotFoundError):
        backup_db.backup(tmp_path / "nope.db", tmp_path / "bk")
    assert backup_db.main(["--db", str(tmp_path / "nope.db"), "--out", str(tmp_path / "bk")]) == 1


def test_backup_cli_and_schedule(tmp_path, capsys):
    make_db(tmp_path / "live.db").close()
    assert backup_db.main(["--db", str(tmp_path / "live.db"), "--out", str(tmp_path / "bk")]) == 0
    assert "backup written" in capsys.readouterr().out
    now = datetime(2026, 11, 15, 10, 0, tzinfo=timezone.utc)
    assert backup_db.seconds_until(21, now) == 11 * 3600
    assert backup_db.seconds_until(9, now) == 23 * 3600
