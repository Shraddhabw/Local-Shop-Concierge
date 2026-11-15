"""Email via a GoDaddy Titan mailbox (SMTP). Configured only from environment variables.

SMTP_HOST (smtpout.secureserver.net), SMTP_PORT (465 = SSL, 587 = STARTTLS), SMTP_USER (full
address), SMTP_PASSWORD, MAIL_FROM. If SMTP_PASSWORD is empty the mailer is in "memory mode":
messages are kept in OUTBOX (development and tests) and nothing is sent.

Safety: header values may not contain line breaks (header injection), connections time out,
one retry for temporary failures, and logs never contain the password, body or addresses.
"""
import logging
import os
import re
import smtplib
import ssl
import time
from concurrent.futures import ThreadPoolExecutor
from email.message import EmailMessage

log = logging.getLogger("mailer")
OUTBOX = []                      # memory mode only (bounded)
TIMEOUT_SECONDS = 10
RETRY_DELAY_SECONDS = 2
_ADDR_RE = re.compile(r"^[^@\s<>\",;]+@[^@\s<>\",;]+\.[^@\s<>\",;]+$")
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="mailer")


class MailConfig:
    def __init__(self, env=None):
        env = os.environ if env is None else env
        self.host = env.get("SMTP_HOST", "smtpout.secureserver.net")
        self.port = int(env.get("SMTP_PORT", "465") or 465)
        self.user = env.get("SMTP_USER", "")
        self.password = env.get("SMTP_PASSWORD", "")
        self.mail_from = env.get("MAIL_FROM", "") or self.user

    @property
    def configured(self):
        return bool(self.password and self.user and self.mail_from)


def clean_address(value):
    """Return a bare, single email address or raise ValueError (blocks header injection)."""
    value = (value or "").strip()
    if len(value) > 254 or not _ADDR_RE.match(value):
        raise ValueError("invalid email address")
    return value


def clean_header(value, limit=200):
    """Header text: line breaks and control characters removed, length capped."""
    return re.sub(r"[\r\n\x00-\x1f\x7f]+", " ", str(value or "")).strip()[:limit]


def build_message(cfg, to, subject, body, reply_to=None):
    msg = EmailMessage()
    msg["From"] = clean_address(cfg.mail_from)
    msg["To"] = clean_address(to)
    msg["Subject"] = clean_header(subject)
    if reply_to:
        msg["Reply-To"] = clean_address(reply_to)
    msg.set_content(str(body or ""))
    return msg


def _transient(exc):
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return False
    if isinstance(exc, smtplib.SMTPResponseException):
        return 400 <= exc.smtp_code < 500
    return isinstance(exc, (OSError, smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError))


def _send_once(cfg, msg):
    context = ssl.create_default_context()
    if cfg.port == 465:
        with smtplib.SMTP_SSL(cfg.host, cfg.port, timeout=TIMEOUT_SECONDS, context=context) as s:
            s.login(cfg.user, cfg.password)
            s.send_message(msg)
    else:
        with smtplib.SMTP(cfg.host, cfg.port, timeout=TIMEOUT_SECONDS) as s:
            s.starttls(context=context)
            s.login(cfg.user, cfg.password)
            s.send_message(msg)


def deliver(cfg, msg):
    """Send now with one retry for temporary errors. Returns True/False; never raises."""
    for attempt in (1, 2):
        try:
            _send_once(cfg, msg)
            return True
        except Exception as exc:                 # noqa: BLE001 - log the type only, never details
            code = getattr(exc, "smtp_code", None)
            log.warning("email send failed (attempt %d): %s%s", attempt, type(exc).__name__,
                        f" code={code}" if code else "")
            if attempt == 2 or not _transient(exc):
                return False
            time.sleep(RETRY_DELAY_SECONDS)
    return False


def run_in_background(fn, *args):
    _executor.submit(fn, *args)


def send_email(to, subject, body, reply_to=None, echo=False):
    """Queue an email. Returns False (and sends nothing) if an address or header is invalid."""
    cfg = MailConfig()
    try:
        msg = build_message(cfg if cfg.mail_from else _Anon(), to, subject, body, reply_to)
    except ValueError:
        log.warning("email rejected: invalid address or header")
        return False
    if not cfg.configured:
        OUTBOX.append({"to": msg["To"], "subject": msg["Subject"], "body": body,
                       "reply_to": msg["Reply-To"]})
        del OUTBOX[:-100]
        if echo:                      # local development only (DEV_LOG_EMAILS=true)
            print(f"[dev email] to={msg['To']} subject={msg['Subject']}\n{body}", flush=True)
        return True
    run_in_background(deliver, cfg, msg)
    return True


class _Anon:
    mail_from = "noreply@invalid.example"
