"""Owner dashboard. Every query uses shop_id from the logged-in session (require_owner)."""
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse

from .. import answer as engine, repo
from ..ai import importer
from ..web import csrf_protect, get_conn, pop_flash, redirect_with_flash, render, require_owner

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
    flash = pop_flash(request)                       # single use: cleared below, so a reload shows nothing
    response = render(request, name, status, shop=shop, error=error, flash=flash, **ctx)
    if request.cookies.get("flash"):
        response.delete_cookie("flash", path="/")
    return response


def _services(request, conn, user, status=200, error=None, add=None, edit=None):
    """add / edit hold what the owner typed so a validation error does not lose it."""
    rows = [dict(r) for r in repo.list_services(conn, user["shop_id"])]
    if edit:
        rows = [{**r, **edit[1]} if r["id"] == edit[0] else r for r in rows]
    return _page(request, conn, user, "dash_services.html", status, error,
                 services=rows, add=add or {}, active="services")



def _faqs(request, conn, user, status=200, error=None, draft=None, add=None, edit=None):
    rows = [dict(r) for r in repo.list_faqs(conn, user["shop_id"])]
    if edit:
        rows = [{**r, **edit[1]} if r["id"] == edit[0] else r for r in rows]
    return _page(request, conn, user, "dash_faqs.html", status, error,
                 faqs=rows, active="faqs", draft=draft, add=add or {})


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
    typed = dict(name=name, price=price, duration_min=duration_min, description=description, keywords=keywords)
    try:
        repo.add_service(conn, user["shop_id"], name, _int(price), _int(duration_min), description, keywords)
    except ValueError as e:
        return _services(request, conn, user, 400, str(e), add=typed)
    return redirect_with_flash(request, "/dashboard/services", f"Service added: {name.strip()[:80]}", public=True)


@router.post("/services/{service_id}", **POST)
def service_update(service_id: int, request: Request, name: str = Form(""), price: str = Form(""),
                   duration_min: str = Form(""), description: str = Form(""), keywords: str = Form(""),
                   user=Depends(require_owner), conn=Depends(get_conn)):
    typed = dict(name=name, price=price, duration_min=duration_min, description=description, keywords=keywords)
    try:
        ok = repo.update_service(conn, user["shop_id"], service_id, name=name, price=_int(price),
                                 duration_min=_int(duration_min), description=description, keywords=keywords)
    except ValueError as e:
        return _services(request, conn, user, 400, str(e), edit=(service_id, typed))
    if not ok:
        raise HTTPException(404)
    return redirect_with_flash(request, "/dashboard/services", f"Service saved: {name.strip()[:80]}", public=True)


@router.post("/services/{service_id}/delete", **POST)
def service_delete(service_id: int, request: Request, user=Depends(require_owner), conn=Depends(get_conn)):
    old = repo.get_service(conn, user["shop_id"], service_id)
    if not repo.delete_service(conn, user["shop_id"], service_id):
        raise HTTPException(404)
    return redirect_with_flash(request, "/dashboard/services", f"Service deleted: {old['name'][:80]}")


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
        typed = {"question": question, "answer": answer, "keywords": keywords}
        if from_unanswered.isdigit():
            return _faqs(request, conn, user, 400, str(e), draft={**typed, "unanswered_id": from_unanswered})
        return _faqs(request, conn, user, 400, str(e), add=typed)
    if from_unanswered.isdigit():                 # the owner approved the draft: mark it resolved
        repo.resolve_unanswered(conn, sid, int(from_unanswered), faq_id)
        return redirect_with_flash(request, "/dashboard/faqs", "FAQ approved and added")
    return redirect_with_flash(request, "/dashboard/faqs", f"FAQ added: {question.strip()[:80]}")


@router.post("/faqs/{faq_id}", **POST)
def faq_update(faq_id: int, request: Request, question: str = Form(""), answer: str = Form(""),
               keywords: str = Form(""), user=Depends(require_owner), conn=Depends(get_conn)):
    try:
        ok = repo.update_faq(conn, user["shop_id"], faq_id, question=question, answer=answer, keywords=keywords)
    except ValueError as e:
        return _faqs(request, conn, user, 400, str(e),
                     edit=(faq_id, {"question": question, "answer": answer, "keywords": keywords}))
    if not ok:
        raise HTTPException(404)
    return redirect_with_flash(request, "/dashboard/faqs", f"FAQ saved: {question.strip()[:80]}")


@router.post("/faqs/{faq_id}/delete", **POST)
def faq_delete(faq_id: int, request: Request, user=Depends(require_owner), conn=Depends(get_conn)):
    if not repo.delete_faq(conn, user["shop_id"], faq_id):
        raise HTTPException(404)
    return redirect_with_flash(request, "/dashboard/faqs", "FAQ deleted")


@router.post("/unanswered/{item_id}/suggest", response_class=HTMLResponse, **POST)
def suggest_faq(item_id: int, request: Request, user=Depends(require_owner), conn=Depends(get_conn)):
    """Shows a DRAFT FAQ. Nothing is saved until the owner edits it and clicks Approve."""
    item = repo.get_unanswered(conn, user["shop_id"], item_id)
    if item is None:
        raise HTTPException(404)
    return _faqs(request, conn, user, draft={"question": item["question"], "answer": "",
                                             "keywords": "", "unanswered_id": str(item["id"])})


@router.post("/unanswered/{item_id}/dismiss", **POST)
def dismiss_unanswered(item_id: int, request: Request, user=Depends(require_owner), conn=Depends(get_conn)):
    if not repo.delete_unanswered(conn, user["shop_id"], item_id):
        raise HTTPException(404)
    return redirect_with_flash(request, "/dashboard", "Question dismissed")


# ---- hours ----
def _hours(request, conn, user, status=200, error=None, typed=None):
    rows = {r["weekday"]: r for r in repo.list_hours(conn, user["shop_id"])}
    if typed:                                        # redisplay what the owner typed after an error
        rows = {d: {"open_time": o, "close_time": c, "closed": cl} for d, (o, c, cl) in typed.items()}
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
        typed = {d: (str(form.get(f"open_{d}", "")), str(form.get(f"close_{d}", "")), bool(form.get(f"closed_{d}")))
                 for d in range(7)}
        return _hours(request, conn, user, 400, str(e), typed=typed)
    return redirect_with_flash(request, "/dashboard/hours", "Hours saved")


# ---- leads and profile ----
@router.get("/leads", response_class=HTMLResponse)
def leads(request: Request, user=Depends(require_owner), conn=Depends(get_conn)):
    return _page(request, conn, user, "dash_leads.html", leads=repo.list_leads(conn, user["shop_id"]),
                 active="leads")


@router.post("/leads/{lead_id}/delete", **POST)
def lead_delete(lead_id: int, request: Request, user=Depends(require_owner), conn=Depends(get_conn)):
    if not repo.delete_lead(conn, user["shop_id"], lead_id):
        raise HTTPException(404)
    return redirect_with_flash(request, "/dashboard/leads", "Lead deleted")


@router.get("/profile", response_class=HTMLResponse)
def profile(request: Request, user=Depends(require_owner), conn=Depends(get_conn)):
    return _page(request, conn, user, "dash_profile.html", active="profile", vals={})


@router.post("/profile", **POST)
def profile_save(request: Request, name: str = Form(""), address: str = Form(""), phone: str = Form(""),
                 whatsapp: str = Form(""), currency: str = Form("INR"),
                 user=Depends(require_owner), conn=Depends(get_conn)):
    try:
        repo.update_shop(conn, user["shop_id"], name=name, address=address, phone=phone,
                         whatsapp=whatsapp, currency=currency.strip().upper())
    except ValueError as e:
        typed = dict(name=name, address=address, phone=phone, whatsapp=whatsapp, currency=currency)
        return _page(request, conn, user, "dash_profile.html", 400, str(e), active="profile", vals=typed)
    return redirect_with_flash(request, "/dashboard/profile", "Settings saved")


# ---- onboarding import: Claude proposes, the owner reviews and confirms ----
HAND_ENTRY = ("We could not read that automatically right now. Please enter your services, "
              "hours and FAQs by hand using the pages above. Nothing was changed.")


def _import_form(request, conn, user, status=200, error=None, pasted=""):
    return _page(request, conn, user, "dash_import.html", status, error, pasted=pasted,
                 active="import", max_chars=importer.MAX_PASTE_CHARS)


def _preview(request, conn, user, data, status=200, error=None):
    days = [(d["weekday"], engine._DAY_NAMES[d["weekday"]], d) for d in data["hours"]]
    return _page(request, conn, user, "dash_import_preview.html", status, error,
                 services=data["services"], faqs=data["faqs"], days=days, active="import")


@router.get("/import", response_class=HTMLResponse)
def import_form(request: Request, user=Depends(require_owner), conn=Depends(get_conn)):
    return _import_form(request, conn, user)


@router.post("/import", response_class=HTMLResponse, **POST)
def import_propose(request: Request, pasted: str = Form(""), user=Depends(require_owner),
                   conn=Depends(get_conn)):
    st = request.app.state
    pasted = pasted.strip()
    if not pasted:
        return _import_form(request, conn, user, 400, "Please paste some text first.")
    if len(pasted) > importer.MAX_PASTE_CHARS:
        return _import_form(request, conn, user, 400,
                            f"Please paste at most {importer.MAX_PASTE_CHARS} characters at a time.", pasted)
    if not st.limits["import"].allow(f"shop:{user['shop_id']}"):
        return _import_form(request, conn, user, 429, "Too many imports. Please try again in an hour.", pasted)
    proposal = importer.propose(st.ai, conn, user["shop_id"], pasted) if st.ai.enabled else None
    if proposal is None:                                   # AI off, API error, bad JSON: never an error page
        return _import_form(request, conn, user, 200, HAND_ENTRY, pasted)
    return _preview(request, conn, user, proposal)


def _parse_preview(form):
    """Read the owner's edited preview. Only rows with 'keep' ticked are used."""
    def count(name):
        n = form.get(name, "0")
        return min(int(n), 40) if n.isdigit() else 0
    services, faqs, hours = [], [], []
    for i in range(count("svc_n")):
        if form.get(f"svc_keep_{i}"):
            services.append({"name": str(form.get(f"svc_name_{i}", "")).strip(),
                             "price": _int(str(form.get(f"svc_price_{i}", ""))),
                             "duration": _int(str(form.get(f"svc_dur_{i}", "")))})
    for i in range(count("faq_n")):
        if form.get(f"faq_keep_{i}"):
            faqs.append({"question": str(form.get(f"faq_q_{i}", "")).strip(),
                         "answer": str(form.get(f"faq_a_{i}", "")).strip(),
                         "keywords": str(form.get(f"faq_k_{i}", "")).strip()})
    for d in range(7):
        if form.get(f"hrs_keep_{d}"):
            closed = bool(form.get(f"hrs_closed_{d}"))
            hours.append({"weekday": d, "closed": closed,
                          "open": None if closed else str(form.get(f"hrs_open_{d}", "")),
                          "close": None if closed else str(form.get(f"hrs_close_{d}", ""))})
    return {"services": services, "faqs": faqs, "hours": hours}


@router.post("/import/confirm", response_class=HTMLResponse, **POST)
async def import_confirm(request: Request, user=Depends(require_owner), conn=Depends(get_conn)):
    """The ONLY place the import writes data, and only after the owner clicked Confirm."""
    form = await request.form()
    try:
        data = _parse_preview(form)
        done = importer.save_confirmed(conn, user["shop_id"], data["services"], data["hours"], data["faqs"])
    except ValueError as e:
        data = _parse_preview_lenient(form)
        return _preview(request, conn, user, data, 400, str(e) or "Please check the values you entered.")
    msg = (f"Added {done['services']} services and {done['faqs']} FAQs, updated hours for {done['hours']} days."
           + (f" Skipped {done['skipped_services']} services and {done['skipped_faqs']} FAQs that already existed."
              if done["skipped_services"] or done["skipped_faqs"] else ""))
    return redirect_with_flash(request, "/dashboard", "Import saved: " + msg[0].lower() + msg[1:], public=True)


def _parse_preview_lenient(form):
    """Re-show the owner's edits after a validation error (bad numbers are shown as typed)."""
    out = {"services": [], "faqs": [], "hours": []}
    for i in range(min(int(form.get("svc_n", "0")) if str(form.get("svc_n", "0")).isdigit() else 0, 40)):
        if form.get(f"svc_keep_{i}"):
            digits = lambda v: int(v) if str(v).strip().isdigit() else None
            out["services"].append({"name": str(form.get(f"svc_name_{i}", "")), "price": digits(form.get(f"svc_price_{i}", "")),
                                    "duration": digits(form.get(f"svc_dur_{i}", ""))})
    for i in range(min(int(form.get("faq_n", "0")) if str(form.get("faq_n", "0")).isdigit() else 0, 40)):
        if form.get(f"faq_keep_{i}"):
            out["faqs"].append({"question": str(form.get(f"faq_q_{i}", "")), "answer": str(form.get(f"faq_a_{i}", "")),
                                "keywords": str(form.get(f"faq_k_{i}", ""))})
    for d in range(7):
        if form.get(f"hrs_keep_{d}"):
            closed = bool(form.get(f"hrs_closed_{d}"))
            out["hours"].append({"weekday": d, "closed": closed, "open": str(form.get(f"hrs_open_{d}", "")),
                                 "close": str(form.get(f"hrs_close_{d}", ""))})
    return out
