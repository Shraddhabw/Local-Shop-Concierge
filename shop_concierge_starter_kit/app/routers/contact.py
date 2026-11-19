"""Platform contact form (visitor -> platform operator). Honeypot, CSRF and a rate limit."""
import os
import re

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from .. import mailer
from ..ratelimit import client_ip
from ..web import csrf_ok, render

router = APIRouter()
THANKS = ("Thanks, your message was sent", "We will reply to you by email.")
SEND_FAILED = "Sorry, your message could not be sent right now. Please try again in a few minutes."


@router.get("/contact", response_class=HTMLResponse)
def contact_form(request: Request):
    return render(request, "contact.html", error=None, values={})


@router.post("/contact", response_class=HTMLResponse)
def contact_send(request: Request, name: str = Form(""), email: str = Form(""),
                 message: str = Form(""), website: str = Form(""), csrf_token: str = Form("")):
    st = request.app.state
    values = {"name": name.strip(), "email": email.strip(), "message": message.strip()}
    if not csrf_ok(request, csrf_token):      # keep what the visitor typed; the form gets a fresh token
        return render(request, "contact.html", 400, values=values,
                      error="Your form expired. Please press Send again.")
    if not st.limits["contact"].allow(client_ip(request, st.settings.trusted_proxies)):
        return render(request, "contact.html", 429, values=values,
                      error="Too many messages from your network. Please wait a few minutes and try again.")
    if website.strip():                      # honeypot: only bots fill this hidden field
        return render(request, "message.html", title=THANKS[0], message=THANKS[1])
    name, email, message = values["name"], values["email"], values["message"]
    error = None
    if not name or len(name) > 100:
        error = "Please enter your name."
    elif not mailer._ADDR_RE.match(email) or len(email) > 254:
        error = "Please enter a valid email address."
    elif not 10 <= len(message) <= 2000:
        error = "Please write a message of 10 to 2000 characters."
    if error:
        return render(request, "contact.html", 400, error=error, values=values)
    recipient = os.environ.get("CONTACT_RECIPIENT", "").strip()
    sent = bool(recipient) and mailer.send_email_now(
        recipient, f"Contact form: {mailer.clean_header(name, 60)}",
        f"From: {mailer.clean_header(name)} <{email}>\n\n{message}\n",
        reply_to=email, echo=st.settings.dev_log_emails)
    if not sent:                              # never claim success for a message nobody received
        return render(request, "contact.html", 503, error=SEND_FAILED, values=values)
    return render(request, "message.html", title=THANKS[0], message=THANKS[1])
