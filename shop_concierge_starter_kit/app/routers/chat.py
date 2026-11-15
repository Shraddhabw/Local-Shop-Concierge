"""Public JSON API used by the chat widget: /api/chat and /api/lead.

No cookies are used, so there is nothing for CSRF to protect; abuse is handled by rate limits.
The shop is resolved from the slug; shop_id is never taken from the client.
"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .. import answer as engine, global_lookups as g, mailer, repo
from ..ratelimit import client_ip
from ..web import get_conn

router = APIRouter(prefix="/api")


class ChatIn(BaseModel):
    slug: str
    message: str


class LeadIn(BaseModel):
    slug: str
    name: str
    contact: str
    message: str = ""
    consent: bool = False


def _err(status, text):
    return JSONResponse({"error": text}, status_code=status)


@router.post("/chat")
def chat(body: ChatIn, request: Request, conn=Depends(get_conn)):
    st = request.app.state
    if not st.limits["chat"].allow(client_ip(request, st.settings.trusted_proxies)):
        return _err(429, "You're sending messages very fast. Please wait a moment.")
    shop = g.get_shop_by_slug(conn, body.slug)
    if shop is None:
        return _err(404, "Shop not found.")
    message = body.message.strip()
    if not message:
        return _err(400, "Please type a question.")
    if len(message) > engine.MAX_MESSAGE_CHARS:
        return _err(400, f"Please keep your question under {engine.MAX_MESSAGE_CHARS} characters.")
    ip = client_ip(request, st.settings.trusted_proxies)
    result = engine.answer(shop["id"], message, conn=conn)
    proposed = None
    if not result["found"]:                  # keyword engine not confident: try the AI fallback
        ai = st.ai.try_answer(conn, shop, message, st.limits["ai_ip"], ip)
        if ai is not None:
            result, proposed = ai, ai["proposed_lead"]
    repo.record_chat_event(conn, shop["id"])
    if not result["found"]:
        repo.log_unanswered(conn, shop["id"], message)
    return {"answer": result["answer"], "found": result["found"],
            "needs_human": result["needs_human"], "proposed_lead": proposed}


@router.post("/lead")
def lead(body: LeadIn, request: Request, conn=Depends(get_conn)):
    st = request.app.state
    if not st.limits["lead"].allow(client_ip(request, st.settings.trusted_proxies)):
        return _err(429, "Too many requests. Please try again later.")
    if body.consent is not True:
        return _err(400, "Please confirm that you agree to share your details with the shop.")
    shop = g.get_shop_by_slug(conn, body.slug)
    if shop is None:
        return _err(404, "Shop not found.")
    if not st.limits["lead_shop"].allow(shop["id"]):       # many IPs cannot flood one owner's inbox
        return _err(429, "This shop is receiving many requests. Please try again later.")
    try:
        repo.add_lead(conn, shop["id"], body.name, body.contact, body.message)
    except ValueError:
        return _err(400, "Please enter your name and a phone number or email.")
    # the customer confirmed (consent checked), so the owner may now be alerted
    alert = (f"New lead for {shop['name']}\n\nName: {body.name.strip()}\n"
             f"Contact: {body.contact.strip()}\nQuestion: {body.message.strip()}\n\n"
             "The customer agreed to share these details with you.")
    for email in repo.owner_emails(conn, shop["id"]):
        mailer.send_email(email, f"New lead: {mailer.clean_header(body.name, 60)}", alert,
                          echo=st.settings.dev_log_emails)
    return {"ok": True, "message": "Thank you! The shop will contact you soon."}
