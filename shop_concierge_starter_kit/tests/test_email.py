import logging
import smtplib
import sys
from pathlib import Path

import pytest

from app import mailer, repo
from tests.test_dashboard import browser, csrf, env, make_owner  # noqa: F401  (fixtures/helpers)

PASSWORD = "S3cret-mailbox-pw"


class FakeSMTP:
    """Stands in for smtplib.SMTP / SMTP_SSL. Class-level log so tests can inspect it."""
    log = []
    fail_with = []          # exceptions to raise on successive connections

    def __init__(self, host, port, timeout=None, context=None):
        FakeSMTP.log.append(("connect", type(self).__name__, host, port, timeout))
        if FakeSMTP.fail_with:
            raise FakeSMTP.fail_with.pop(0)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self, context=None):
        FakeSMTP.log.append(("starttls",))

    def login(self, user, password):
        FakeSMTP.log.append(("login", user))

    def send_message(self, msg):
        FakeSMTP.log.append(("send", msg))


class FakeSSL(FakeSMTP):
    pass


@pytest.fixture
def smtp(monkeypatch):
    FakeSMTP.log, FakeSMTP.fail_with = [], []
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSSL)
    monkeypatch.setattr(mailer, "RETRY_DELAY_SECONDS", 0)
    monkeypatch.setattr(mailer, "run_in_background", lambda fn, *a: fn(*a))   # run inline
    monkeypatch.setenv("SMTP_HOST", "smtpout.secureserver.net")
    monkeypatch.setenv("SMTP_PORT", "465")
    monkeypatch.setenv("SMTP_USER", "hello@shop.example")
    monkeypatch.setenv("SMTP_PASSWORD", PASSWORD)
    monkeypatch.setenv("MAIL_FROM", "hello@shop.example")
    mailer.OUTBOX.clear()
    return FakeSMTP


def sent(smtp):
    return [e[1] for e in smtp.log if e[0] == "send"]


def test_port_465_uses_ssl_with_timeout_and_login(smtp):
    assert mailer.send_email("owner@example.com", "Hi", "Body") is True
    kinds = [e[0] for e in smtp.log]
    assert smtp.log[0] == ("connect", "FakeSSL", "smtpout.secureserver.net", 465, mailer.TIMEOUT_SECONDS)
    assert kinds == ["connect", "login", "send"] and ("login", "hello@shop.example") in smtp.log
    assert sent(smtp)[0]["To"] == "owner@example.com" and sent(smtp)[0]["From"] == "hello@shop.example"
    assert mailer.OUTBOX == []                              # real mode: nothing kept in memory


def test_port_587_uses_starttls(smtp, monkeypatch):
    monkeypatch.setenv("SMTP_PORT", "587")
    mailer.send_email("owner@example.com", "Hi", "Body")
    assert [e[0] for e in smtp.log] == ["connect", "starttls", "login", "send"]
    assert smtp.log[0][1] == "FakeSMTP"


def test_memory_mode_when_not_configured(monkeypatch):
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    mailer.OUTBOX.clear()
    assert mailer.send_email("owner@example.com", "Hi", "Body") is True
    assert mailer.OUTBOX[0]["to"] == "owner@example.com"


@pytest.mark.parametrize("to", ["a@b.co\nBcc: evil@x.com", "a@b.co\r\nBcc: x@y.zz", "a@b.co,evil@x.com",
                                "<a@b.co>", "no-at-sign", "", None])
def test_recipient_header_injection_rejected(smtp, to):
    assert mailer.send_email(to, "Hi", "Body") is False
    assert smtp.log == []


def test_reply_to_injection_rejected_and_subject_newlines_removed(smtp):
    assert mailer.send_email("a@b.co", "Hi", "Body", reply_to="x@y.zz\nBcc: evil@x.com") is False
    assert mailer.send_email("a@b.co", "Hello\r\nBcc: evil@x.com", "Body") is True
    msg = sent(smtp)[0]
    assert "\n" not in msg["Subject"] and msg["Bcc"] is None


def test_one_retry_for_temporary_failure(smtp):
    smtp.fail_with = [TimeoutError("slow")]
    assert mailer.send_email("a@b.co", "Hi", "Body") is True
    assert [e[0] for e in smtp.log].count("connect") == 2 and len(sent(smtp)) == 1


def test_gives_up_after_one_retry(smtp):
    smtp.fail_with = [TimeoutError(), ConnectionRefusedError()]
    msg = mailer.build_message(mailer.MailConfig(), "a@b.co", "Hi", "Body")
    assert mailer.deliver(mailer.MailConfig(), msg) is False
    assert [e[0] for e in smtp.log].count("connect") == 2 and sent(smtp) == []


def test_no_retry_for_wrong_password(smtp):
    smtp.fail_with = [smtplib.SMTPAuthenticationError(535, b"bad credentials")]
    msg = mailer.build_message(mailer.MailConfig(), "a@b.co", "Hi", "Body")
    assert mailer.deliver(mailer.MailConfig(), msg) is False
    assert [e[0] for e in smtp.log].count("connect") == 1


def test_logs_never_contain_secrets_or_content(smtp, caplog):
    smtp.fail_with = [smtplib.SMTPAuthenticationError(535, PASSWORD.encode())]
    with caplog.at_level(logging.DEBUG):
        mailer.send_email("private-customer@example.com", "Secret subject", "Secret body text")
    text = caplog.text
    assert "SMTPAuthenticationError" in text and "535" in text
    for secret in (PASSWORD, "private-customer", "Secret subject", "Secret body text"):
        assert secret not in text


# ---- lead alerts: only after the customer confirmed ----
def test_lead_alert_only_after_consent(env, smtp):          # noqa: F811
    sid = make_owner(env, "Glow Salon", "glow-salon", "owner@example.com")
    c = browser()
    base = {"slug": "glow-salon", "name": "Asha", "contact": "9999", "message": "Price of bridal?"}
    assert c.post("/api/lead", json={**base, "consent": False}).status_code == 400
    assert sent(smtp) == [] and repo.list_leads(env, sid) == []
    assert c.post("/api/lead", json={**base, "consent": True}).status_code == 200
    assert len(sent(smtp)) == 1
    m = sent(smtp)[0]
    assert m["To"] == "owner@example.com" and "Asha" in m["Subject"]
    assert "9999" in m.get_content() and "agreed to share" in m.get_content()


def test_lead_alert_goes_only_to_that_shops_owner(env, smtp):    # noqa: F811
    make_owner(env, "Glow Salon", "glow-salon", "owner-a@example.com")
    make_owner(env, "Other Shop", "other-shop", "owner-b@example.com")
    browser().post("/api/lead", json={"slug": "other-shop", "name": "N", "contact": "1", "consent": True})
    assert [m["To"] for m in sent(smtp)] == ["owner-b@example.com"]


def test_lead_with_newline_name_cannot_inject_headers(env, smtp):  # noqa: F811
    make_owner(env, "Glow Salon", "glow-salon", "owner@example.com")
    browser().post("/api/lead", json={"slug": "glow-salon", "name": "Eve\nBcc: evil@x.com",
                                      "contact": "1", "consent": True})
    m = sent(smtp)[0]
    assert m["Bcc"] is None and "\n" not in m["Subject"]


# ---- contact form ----
def form(c, **over):
    data = {"name": "Visitor", "email": "visitor@example.com", "message": "I would like a demo please.",
            "website": "", "csrf_token": csrf(c, "/contact")}
    data.update(over)
    return c.post("/contact", data=data)


def test_contact_form_sends_to_operator_with_reply_to(env, smtp, monkeypatch):   # noqa: F811
    monkeypatch.setenv("CONTACT_RECIPIENT", "ops@shop.example")
    r = form(browser())
    assert r.status_code == 200 and "Thanks, your message was sent" in r.text
    m = sent(smtp)[0]
    assert m["To"] == "ops@shop.example" and m["Reply-To"] == "visitor@example.com"
    assert "demo" in m.get_content()


def test_contact_honeypot_sends_nothing(env, smtp, monkeypatch):   # noqa: F811
    monkeypatch.setenv("CONTACT_RECIPIENT", "ops@shop.example")
    r = form(browser(), website="http://spam.example")
    assert r.status_code == 200 and "Thanks, your message was sent" in r.text and sent(smtp) == []


def test_contact_validation_csrf_and_injection(env, smtp, monkeypatch):   # noqa: F811
    monkeypatch.setenv("CONTACT_RECIPIENT", "ops@shop.example")
    c = browser()
    assert form(c, email="bad").status_code == 400
    assert form(c, email="v@example.com\nBcc: evil@x.com").status_code == 400
    assert form(c, message="short").status_code == 400
    assert form(c, name="").status_code == 400
    assert c.post("/contact", data={"name": "A", "email": "a@b.co", "message": "x" * 20}).status_code == 400
    assert sent(smtp) == []
    assert form(c, name="Bob\nBcc: evil@x.com").status_code == 200
    m = sent(smtp)[0]
    assert m["Bcc"] is None and "\n" not in m["Subject"]


def test_contact_rate_limit_and_apex_only(tmp_path, monkeypatch, smtp):   # noqa: F811
    from app import db
    monkeypatch.setenv("SECRET_KEY", "k" * 40)
    monkeypatch.setenv("BASE_DOMAIN", "example.com")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "t.db"))
    monkeypatch.setenv("RATE_LIMITS_ENABLED", "true")
    monkeypatch.setenv("CONTACT_RECIPIENT", "ops@shop.example")
    db.init_db(db.connect())
    c = browser()
    codes = [form(c).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]
    assert browser(host="shop.example.com").get("/contact").status_code == 404


# ---- send_test_email script ----
def test_send_test_email_script(smtp, monkeypatch, capsys):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import send_test_email as script
    monkeypatch.setattr(script, "load_dotenv", lambda path: None)     # never read the real .env in tests
    assert script.main(["x", "me@example.com"]) == 0
    out = capsys.readouterr().out
    assert PASSWORD not in out and "OK" in out and len(sent(smtp)) == 1
    smtp.fail_with = [smtplib.SMTPAuthenticationError(535, b"nope")]
    assert script.main(["x", "me@example.com"]) == 1
    out = capsys.readouterr().out
    assert "Troubleshooting checklist" in out and "smtp.office365.com" in out and PASSWORD not in out
    assert script.main(["x", "bad\naddress"]) == 2
    monkeypatch.delenv("SMTP_PASSWORD")
    assert script.main(["x", "me@example.com"]) == 2


# ---- contact form: links, messages, failures keep the typed text ----
def test_contact_is_linked_from_landing_and_every_footer(env, smtp):   # noqa: F811
    c = browser()
    landing = c.get("/").text
    assert 'href="/contact"' in landing and 'href="https://example.com/contact"' in landing   # body link and footer
    assert 'href="https://example.com/contact"' in c.get("/login").text
    # a shop subdomain page links to the apex form (the form itself is 404 on shop subdomains)
    sid = make_owner(env, "Glow Salon", "glow-salon", "a@example.com")
    shop_page = browser(host="glow-salon.example.com").get("/")
    assert shop_page.status_code == 200 and 'href="https://example.com/contact"' in shop_page.text


def test_contact_success_message_and_destination(env, smtp, monkeypatch):   # noqa: F811
    monkeypatch.setenv("CONTACT_RECIPIENT", "ops@shop.example")
    r = form(browser(), message="Please call me about pricing.")
    assert r.status_code == 200 and "Thanks, your message was sent" in r.text
    assert [m["To"] for m in sent(smtp)] == ["ops@shop.example"]


def test_contact_validation_error_keeps_typed_text(env, smtp, monkeypatch):   # noqa: F811
    monkeypatch.setenv("CONTACT_RECIPIENT", "ops@shop.example")
    r = form(browser(), name="Asha <b>", email="not-an-email", message="A long enough message here.")
    assert r.status_code == 400 and 'role="alert"' in r.text and "valid email" in r.text
    assert 'value="Asha &lt;b&gt;"' in r.text and "A long enough message here." in r.text
    assert sent(smtp) == []


def test_contact_send_failure_shows_error_and_keeps_text(env, smtp, monkeypatch):   # noqa: F811
    monkeypatch.setenv("CONTACT_RECIPIENT", "ops@shop.example")
    smtp.fail_with = [OSError("down"), OSError("down")]                  # first try and the one retry both fail
    r = form(browser(), message="Please do call me back about the demo.")
    assert r.status_code == 503 and "could not be sent" in r.text and 'role="alert"' in r.text
    assert "Thanks, your message was sent" not in r.text
    assert "Please do call me back about the demo." in r.text and 'value="visitor@example.com"' in r.text
    assert PASSWORD not in r.text


def test_contact_without_recipient_never_claims_success(env, smtp, monkeypatch):   # noqa: F811
    monkeypatch.delenv("CONTACT_RECIPIENT", raising=False)
    r = form(browser())
    assert r.status_code == 503 and "Thanks, your message was sent" not in r.text and sent(smtp) == []


def test_contact_bad_csrf_and_rate_limit_keep_text(tmp_path, monkeypatch, smtp):   # noqa: F811
    from app import db
    monkeypatch.setenv("SECRET_KEY", "k" * 40)
    monkeypatch.setenv("BASE_DOMAIN", "example.com")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "t.db"))
    monkeypatch.setenv("RATE_LIMITS_ENABLED", "true")
    monkeypatch.setenv("CONTACT_RECIPIENT", "ops@shop.example")
    db.init_db(db.connect())
    c = browser()
    r = c.post("/contact", data={"name": "Asha", "email": "a@example.com", "message": "Keep this text please.",
                                 "website": "", "csrf_token": "forged"})
    assert r.status_code == 400 and "Keep this text please." in r.text and "expired" in r.text
    assert sent(smtp) == []
    for _ in range(3):
        assert form(c).status_code == 200
    r = form(c, message="Rate limited but kept text.")
    assert r.status_code == 429 and "Rate limited but kept text." in r.text and "Too many" in r.text
    assert len(sent(smtp)) == 3                                                      # nothing extra was sent


def test_contact_success_and_error_pages_keep_the_back_to_home_button(env, smtp, monkeypatch):   # noqa: F811
    monkeypatch.setenv("CONTACT_RECIPIENT", "ops@shop.example")
    c = browser()
    ok = form(c, message="Please call me about pricing.")
    assert ok.status_code == 200 and "Thanks, your message was sent" in ok.text
    for r in (ok, form(c, email="bad"), form(c, website="spam")):          # success, validation error, honeypot
        assert '<p class="home-link"><a href="/">' in r.text and "Back to home" in r.text
        assert r.text.index("home-link") < r.text.index("<h1>")
    smtp.fail_with = [OSError("down"), OSError("down")]
    assert "Back to home" in form(c, message="Another long enough message.").text      # send failure page
