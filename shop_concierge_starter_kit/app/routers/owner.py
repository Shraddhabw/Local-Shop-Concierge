"""Owner dashboard. Every query uses shop_id from the logged-in session (require_owner)."""
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .. import answer as engine, repo
from ..web import csrf_protect, get_conn, render, require_owner

router = APIRouter(prefix="/dashboard", dependencies=[Depends(require_owner)])
POST = dict(dependencies=[Depends(csrf_protect)])


def _int(value):
    value = (value or "").strip()
    if value == "":
        return None
    if not value.isdigit():
        raise ValueError("Please use whole numbers only, for example 300.")
    return int(value)


def _page(request, conn, user, name, status=200, error=None, **ctx):
    shop = repo.get_shop(conn, user["shop_id"])
    return render(request, name, status, shop=shop, error=error, **ctx)


def _services(request, conn, user, status=200, error=None):
    return _page(request, conn, user, "dash_services.html", status, error,
                 services=repo.list_services(conn, user["shop_id"]), active="services")


def _faqs(request, conn, user, status=200, error=None, draft=None):
    return _page(request, conn, user, "dash_faqs.html", status, error,
                 faqs=repo.list_faqs(conn, user["shop_id"]), active="faqs", draft=draft)


@router.get("", response_class=HTMLResponse)
def overview(request: Request, user=Depends(require_owner), conn=Depends(get_conn)):
    sid = user["shop_id"]
    return _page(request, conn, user, "dashboard.html", active="home",
                 chats=repo.count_chats_since(conn, sid), leads=repo.count_leads_since(conn, sid),
                 unanswered=repo.list_unanswered(conn, sid, 5))


# ---- services ----
@router.get("/services", response_class=HTMLResponse)
def services(request: Request, user=Depends(require_owner), conn=Depends(get_conn)):
    return _services(request, conn, user)


@router.post("/services", **POST)
def service_add(request: Request, name: str = Form(""), price: str = Form(""),
                duration_min: str = Form(""), description: str = Form(""), keywords: str = Form(""),
                user=Depends(require_owner), conn=Depends(get_conn)):
    try:
        repo.add_service(conn, user["shop_id"], name, _int(price), _int(duration_min), description, keywords)
    except ValueError as e:
        return _services(request, conn, user, 400, str(e))
    return RedirectResponse("/dashboard/services", status_code=303)


@router.post("/services/{service_id}", **POST)
def service_update(service_id: int, request: Request, name: str = Form(""), price: str = Form(""),
                   duration_min: str = Form(""), description: str = Form(""), keywords: str = Form(""),
                   user=Depends(require_owner), conn=Depends(get_conn)):
    try:
        ok = repo.update_service(conn, user["shop_id"], service_id, name=name, price=_int(price),
                                 duration_min=_int(duration_min), description=description, keywords=keywords)
    except ValueError as e:
        return _services(request, conn, user, 400, str(e))
    if not ok:
        raise HTTPException(404)
    return RedirectResponse("/dashboard/services", status_code=303)


@router.post("/services/{service_id}/delete", **POST)
def service_delete(service_id: int, user=Depends(require_owner), conn=Depends(get_conn)):
    if not repo.delete_service(conn, user["shop_id"], service_id):
        raise HTTPException(404)
    return RedirectResponse("/dashboard/services", status_code=303)


# ---- faqs ----
@router.get("/faqs", response_class=HTMLResponse)
def faqs(request: Request, user=Depends(require_owner), conn=Depends(get_conn)):
    return _faqs(request, conn, user)


@router.post("/faqs", **POST)
def faq_add(request: Request, question: str = Form(""), answer: str = Form(""), keywords: str = Form(""),
            from_unanswered: str = Form(""), user=Depends(require_owner), conn=Depends(get_conn)):
    sid = user["shop_id"]
    try:
        faq_id = repo.add_faq(conn, sid, question, answer, keywords)
    except ValueError as e:
        return _faqs(request, conn, user, 400, str(e), draft={"question": question, "answer": answer,
                                                              "keywords": keywords, "unanswered_id": from_unanswered})
    if from_unanswered.isdigit():                 # the owner approved the draft: mark it resolved
        repo.resolve_unanswered(conn, sid, int(from_unanswered), faq_id)
    return RedirectResponse("/dashboard/faqs", status_code=303)


@router.post("/faqs/{faq_id}", **POST)
def faq_update(faq_id: int, request: Request, question: str = Form(""), answer: str = Form(""),
               keywords: str = Form(""), user=Depends(require_owner), conn=Depends(get_conn)):
    try:
        ok = repo.update_faq(conn, user["shop_id"], faq_id, question=question, answer=answer, keywords=keywords)
    except ValueError as e:
        return _faqs(request, conn, user, 400, str(e))
    if not ok:
        raise HTTPException(404)
    return RedirectResponse("/dashboard/faqs", status_code=303)


@router.post("/faqs/{faq_id}/delete", **POST)
def faq_delete(faq_id: int, user=Depends(require_owner), conn=Depends(get_conn)):
    if not repo.delete_faq(conn, user["shop_id"], faq_id):
        raise HTTPException(404)
    return RedirectResponse("/dashboard/faqs", status_code=303)


@router.post("/unanswered/{item_id}/suggest", response_class=HTMLResponse, **POST)
def suggest_faq(item_id: int, request: Request, user=Depends(require_owner), conn=Depends(get_conn)):
    """Shows a DRAFT FAQ. Nothing is saved until the owner edits it and clicks Approve."""
    item = repo.get_unanswered(conn, user["shop_id"], item_id)
    if item is None:
        raise HTTPException(404)
    return _faqs(request, conn, user, draft={"question": item["question"], "answer": "",
                                             "keywords": "", "unanswered_id": str(item["id"])})


@router.post("/unanswered/{item_id}/dismiss", **POST)
def dismiss_unanswered(item_id: int, user=Depends(require_owner), conn=Depends(get_conn)):
    if not repo.delete_unanswered(conn, user["shop_id"], item_id):
        raise HTTPException(404)
    return RedirectResponse("/dashboard", status_code=303)


# ---- hours ----
def _hours(request, conn, user, status=200, error=None):
    rows = {r["weekday"]: r for r in repo.list_hours(conn, user["shop_id"])}
    days = [(i, name, rows.get(i)) for i, name in enumerate(engine._DAY_NAMES)]
    return _page(request, conn, user, "dash_hours.html", status, error, days=days, active="hours")


@router.get("/hours", response_class=HTMLResponse)
def hours(request: Request, user=Depends(require_owner), conn=Depends(get_conn)):
    return _hours(request, conn, user)


@router.post("/hours", **POST)
async def hours_save(request: Request, user=Depends(require_owner), conn=Depends(get_conn)):
    form = await request.form()
    week = {}
    for d in range(7):
        if form.get(f"closed_{d}"):
            week[d] = None
        else:
            week[d] = (str(form.get(f"open_{d}", "")), str(form.get(f"close_{d}", "")))
    try:
        repo.replace_week_hours(conn, user["shop_id"], week)
    except ValueError as e:
        return _hours(request, conn, user, 400, str(e))
    return RedirectResponse("/dashboard/hours", status_code=303)


# ---- leads and profile ----
@router.get("/leads", response_class=HTMLResponse)
def leads(request: Request, user=Depends(require_owner), conn=Depends(get_conn)):
    return _page(request, conn, user, "dash_leads.html", leads=repo.list_leads(conn, user["shop_id"]),
                 active="leads")


@router.post("/leads/{lead_id}/delete", **POST)
def lead_delete(lead_id: int, user=Depends(require_owner), conn=Depends(get_conn)):
    if not repo.delete_lead(conn, user["shop_id"], lead_id):
        raise HTTPException(404)
    return RedirectResponse("/dashboard/leads", status_code=303)


@router.get("/profile", response_class=HTMLResponse)
def profile(request: Request, user=Depends(require_owner), conn=Depends(get_conn)):
    return _page(request, conn, user, "dash_profile.html", active="profile")


@router.post("/profile", **POST)
def profile_save(request: Request, name: str = Form(""), address: str = Form(""), phone: str = Form(""),
                 whatsapp: str = Form(""), currency: str = Form("INR"),
                 user=Depends(require_owner), conn=Depends(get_conn)):
    try:
        repo.update_shop(conn, user["shop_id"], name=name, address=address, phone=phone,
                         whatsapp=whatsapp, currency=currency.strip().upper())
    except ValueError as e:
        return _page(request, conn, user, "dash_profile.html", 400, str(e), active="profile")
    return RedirectResponse("/dashboard/profile", status_code=303)
