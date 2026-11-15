"""Platform contact form (visitor -> platform operator). Honeypot, CSRF and a rate limit."""
import os
import re

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from .. import mailer
from ..ratelimit import client_ip
from ..web import bad_csrf, csrf_ok, render, too_many

router = APIRouter()
THANKS = ("Thank you", "Your message has been sent. We will reply by email.")


@router.get("/contact", response_class=HTMLResponse)
def contact_form(request: Request):
    return render(request, "contact.html", error=None, values={})


@router.post("/contact", response_class=HTMLResponse)
def contact_send(request: Request, name: str = Form(""), email: str = Form(""),
                 message: str = Form(""), website: str = Form(""), csrf_token: str = Form("")):
    st = request.app.state
    if not csrf_ok(request, csrf_token):
        return bad_csrf(request)
    if not st.limits["contact"].allow(client_ip(request, st.settings.trusted_proxies)):
        return too_many(request)
    if website.strip():                      # honeypot: only bots fill this hidden field
        return render(request, "message.html", title=THANKS[0], message=THANKS[1])
    name, email, message = name.strip(), email.strip(), message.strip()
    values, error = {"name": name, "email": email, "message": message}, None
    if not name or len(name) > 100:
        error = "Please enter your name."
    elif not mailer._ADDR_RE.match(email) or len(email) > 254:
        error = "Please enter a valid email address."
    elif not 10 <= len(message) <= 2000:
        error = "Please write a message of 10 to 2000 characters."
    if error:
        return render(request, "contact.html", 400, error=error, values=values)
    recipient = os.environ.get("CONTACT_RECIPIENT", "").strip()
    if recipient:
        mailer.send_email(recipient, f"Contact form: {mailer.clean_header(name, 60)}",
                          f"From: {mailer.clean_header(name)} <{email}>\n\n{message}\n",
                          reply_to=email, echo=st.settings.dev_log_emails)
    return render(request, "message.html", title=THANKS[0], message=THANKS[1])
