"""Send one test email through the configured SMTP account.

Usage:  python scripts/send_test_email.py you@example.com
Reads SMTP_* and MAIL_FROM from the environment (or from a .env file in the project root).
Prints what happened, never the password.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CHECKLIST = """
Troubleshooting checklist
  1. SMTP_HOST must be smtpout.secureserver.net (NOT smtp.titan.email) for GoDaddy Titan.
  2. SMTP_PORT: 465 (SSL) or 587 (STARTTLS). Try the other one if one is blocked.
  3. SMTP_USER must be the FULL mailbox address (hello@yourdomain.com), not just "hello".
  4. SMTP_PASSWORD is the mailbox password. If it has special characters keep it in .env without quotes issues.
  5. MAIL_FROM should be the same address as SMTP_USER (Titan rejects other senders).
  6. Log in to the Titan webmail with the same password to prove the mailbox works.
  7. The mailbox and domain must be active (not expired) in your GoDaddy account.
  8. Your server/VPS must allow outbound traffic on port 465 / 587 (some hosts block it).
  9. Check the domain's MX/SPF/DKIM records were NOT changed after buying Titan.
 10. Timeouts mean the port is blocked; "authentication failed" means user or password is wrong.
"""


def load_dotenv(path):
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 2
    load_dotenv(ROOT / ".env")
    from app import mailer
    cfg = mailer.MailConfig()
    if not cfg.configured:
        print("SMTP is not configured: set SMTP_USER, SMTP_PASSWORD (and MAIL_FROM).")
        print(CHECKLIST)
        return 2
    print(f"Sending via {cfg.host}:{cfg.port} as {cfg.user} (password not shown)...")
    try:
        msg = mailer.build_message(cfg, argv[1], "Local Shop Concierge test email",
                                   "If you can read this, email sending works.")
    except ValueError:
        print("That recipient address is not valid.")
        return 2
    mailer.RETRY_DELAY_SECONDS = 1
    if mailer.deliver(cfg, msg):
        print("OK: the server accepted the message. Check the inbox (and spam folder).")
        return 0
    print("FAILED: see the log line above for the error type, then work through the checklist.")
    print(CHECKLIST)
    return 1


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    sys.exit(main(sys.argv))
