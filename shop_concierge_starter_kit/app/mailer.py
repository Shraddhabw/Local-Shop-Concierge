"""Email sending. T3 stub: messages go to an in-memory outbox (nothing is sent).

T5 replaces send_email with the Titan SMTP implementation behind the same function.
"""
OUTBOX = []


def send_email(to, subject, body, echo=False):
    OUTBOX.append({"to": to, "subject": subject, "body": body})
    if echo:        # local development only (DEV_LOG_EMAILS=true): print instead of sending
        print(f"[dev email] to={to} subject={subject}\n{body}", flush=True)
