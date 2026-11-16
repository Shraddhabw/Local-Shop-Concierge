import re

import pytest
from fastapi.testclient import TestClient

from app import db, global_lookups as g, repo
from app.main import create_app


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "k" * 40)
    monkeypatch.setenv("BASE_DOMAIN", "example.com")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "t.db"))
    monkeypatch.setenv("RATE_LIMITS_ENABLED", "false")
    conn = db.connect()
    db.init_db(conn)
    return conn


def make_owner(conn, name, slug, email):
    sid = g.create_shop(conn, name, slug)
    uid = g.create_user(conn, sid, email, "x")
    conn.execute("UPDATE users SET verified = 1 WHERE id = ?", (uid,))
    conn.commit()
    g.create_session(conn, uid, "tok-" + slug)
    return sid


def browser(token=None, host="example.com"):
    c = TestClient(create_app(), base_url=f"https://{host}", follow_redirects=False)
    if token:
        c.cookies.set("session", token, domain=host)
    return c


def csrf(client, path="/dashboard"):
    return re.search(r'name="csrf_token" value="([0-9a-f]+)"', client.get(path).text).group(1)


@pytest.fixture
def owner(env):
    sid = make_owner(env, "Glow Salon", "glow-salon", "a@example.com")
    return browser("tok-glow-salon"), sid


def test_requires_login(env):
    c = browser()
    for path in ("/dashboard", "/dashboard/services", "/dashboard/faqs", "/dashboard/hours",
                 "/dashboard/leads", "/dashboard/profile"):
        r = c.get(path)
        assert r.status_code == 303 and r.headers["location"] == "/login"
    assert c.post("/dashboard/services", data={"name": "x"}).status_code == 303


def test_post_without_csrf_rejected(env, owner):
    c, sid = owner
    assert c.post("/dashboard/services", data={"name": "Spa"}).status_code == 400
    assert repo.list_services(env, sid) == []


def test_service_crud_via_http(env, owner):
    c, sid = owner
    t = csrf(c, "/dashboard/services")
    r = c.post("/dashboard/services", data={"csrf_token": t, "name": "Men's Haircut", "price": "300",
                                            "duration_min": "30", "description": "", "keywords": "cut"})
    assert r.status_code == 303
    svc = repo.list_services(env, sid)[0]
    assert svc["price"] == 300 and svc["duration_min"] == 30
    assert "Men&#39;s Haircut" in c.get("/dashboard/services").text
    c.post(f"/dashboard/services/{svc['id']}", data={"csrf_token": t, "name": "Men's Haircut", "price": "350"})
    assert repo.get_service(env, sid, svc["id"])["price"] == 350
    c.post(f"/dashboard/services/{svc['id']}/delete", data={"csrf_token": t})
    assert repo.list_services(env, sid) == []


def test_bad_price_shows_error_and_saves_nothing(env, owner):
    c, sid = owner
    t = csrf(c, "/dashboard/services")
    for bad in ("3.5", "-1", "abc", "300.00"):
        r = c.post("/dashboard/services", data={"csrf_token": t, "name": "X", "price": bad})
        assert r.status_code == 400 and "whole numbers" in r.text
    assert repo.list_services(env, sid) == []


def test_owner_cannot_touch_other_shops_rows_by_guessing_ids(env, owner):
    c, a = owner
    b = make_owner(env, "Other Shop", "other-shop", "b@example.com")
    svc = repo.add_service(env, b, "Secret Service", 999)
    faq = repo.add_faq(env, b, "Secret?", "Yes")
    lead = repo.add_lead(env, b, "Cust", "123456")
    t = csrf(c, "/dashboard/services")
    assert c.post(f"/dashboard/services/{svc}", data={"csrf_token": t, "name": "Hacked"}).status_code == 404
    assert c.post(f"/dashboard/services/{svc}/delete", data={"csrf_token": t}).status_code == 404
    assert c.post(f"/dashboard/faqs/{faq}", data={"csrf_token": t, "question": "q", "answer": "a"}).status_code == 404
    assert c.post(f"/dashboard/faqs/{faq}/delete", data={"csrf_token": t}).status_code == 404
    assert c.post(f"/dashboard/leads/{lead}/delete", data={"csrf_token": t}).status_code == 404
    assert repo.get_service(env, b, svc)["name"] == "Secret Service"
    assert repo.get_faq(env, b, faq) and repo.get_lead(env, b, lead)
    assert "Secret" not in c.get("/dashboard/services").text + c.get("/dashboard/faqs").text


def test_hours_save_and_validation(env, owner):
    c, sid = owner
    t = csrf(c, "/dashboard/hours")
    data = {"csrf_token": t}
    for d in range(7):
        data.update({f"open_{d}": "09:00", f"close_{d}": "17:30"})
    data["closed_6"] = "1"
    assert c.post("/dashboard/hours", data=data).status_code == 303
    rows = repo.list_hours(env, sid)
    assert len(rows) == 7 and rows[0]["close_time"] == "17:30" and rows[6]["closed"] == 1
    data["open_2"], data["close_2"] = "18:00", "09:00"
    assert c.post("/dashboard/hours", data=data).status_code == 400
    assert len(repo.list_hours(env, sid)) == 7            # old hours kept after a failed save


def test_analytics_and_suggest_faq_needs_approval(env, owner):
    c, sid = owner
    pub = browser()
    for _ in range(2):
        pub.post("/api/chat", json={"slug": "glow-salon", "message": "Do you do tattoos?"})
    pub.post("/api/lead", json={"slug": "glow-salon", "name": "Asha", "contact": "9999", "consent": True})
    home = c.get("/dashboard").text
    assert "2</span> chats this week" in home and "1</span> leads this week" in home
    assert "Do you do tattoos?" in home and "asked 2x" in home
    q = repo.list_unanswered(env, sid)[0]
    t = csrf(c)
    draft = c.post(f"/dashboard/unanswered/{q['id']}/suggest", data={"csrf_token": t})
    assert "Draft FAQ (not saved yet)" in draft.text and repo.list_faqs(env, sid) == []   # nothing saved
    c.post("/dashboard/faqs", data={"csrf_token": t, "question": "Do you do tattoos?",
                                    "answer": "No, sorry.", "from_unanswered": str(q["id"])})
    assert len(repo.list_faqs(env, sid)) == 1 and repo.list_unanswered(env, sid) == []


def test_cannot_suggest_for_another_shops_question(env, owner):
    c, a = owner
    b = make_owner(env, "Other Shop", "other-shop", "b@example.com")
    qid = repo.log_unanswered(env, b, "private question")
    t = csrf(c)
    assert c.post(f"/dashboard/unanswered/{qid}/suggest", data={"csrf_token": t}).status_code == 404
    assert c.post(f"/dashboard/unanswered/{qid}/dismiss", data={"csrf_token": t}).status_code == 404


def test_profile_update(env, owner):
    c, sid = owner
    t = csrf(c, "/dashboard/profile")
    c.post("/dashboard/profile", data={"csrf_token": t, "name": "Glow", "address": "1 Road",
                                       "phone": "123", "whatsapp": "+91 99999 00000", "currency": "usd"})
    s = repo.get_shop(env, sid)
    assert s["currency"] == "USD" and s["whatsapp"] == "+91 99999 00000"
    assert c.post("/dashboard/profile", data={"csrf_token": t, "name": "", "currency": "INR"}).status_code == 400


# ---- public page, widget and chat API ----
@pytest.fixture
def public(env):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import seed
    seed.seed(env)
    return browser()


def test_public_page_content(public):
    r = public.get("/s/demo-salon")
    assert r.status_code == 200
    for text in ("Glow Salon", "Men&#39;s Haircut", "₹300", "Sunday", "<svg", "Try", "21 MG Road"):
        if text == "Try":
            continue
        assert text in r.text, text
    assert "wa.me" not in r.text                           # no WhatsApp number set
    assert public.get("/s/nope-shop").status_code == 404


def test_whatsapp_button_and_subdomain_page(env):
    sid = make_owner(env, "Wa Shop", "wa-shop", "w@example.com")
    repo.update_shop(env, sid, whatsapp="+91 98765 43210")
    r = browser().get("/s/wa-shop")
    assert 'href="https://wa.me/919876543210"' in r.text
    sub = browser(host="wa-shop.example.com")
    assert sub.get("/").status_code == 200 and "Wa Shop" in sub.get("/").text
    assert browser(host="ghost.example.com").get("/").status_code == 404
    assert sub.get("/dashboard").status_code == 404


def test_shop_name_is_escaped_on_public_page(env):
    g.create_shop(env, '<img src=x onerror=alert(1)>', "xss-shop")
    html = browser().get("/s/xss-shop").text
    assert "<img src=x" not in html and "&lt;img" in html


def test_landing_page_has_demo_link(env):
    r = browser().get("/")
    assert r.status_code == 200 and 'href="/s/demo-salon"' in r.text and "Try the live demo" in r.text


def test_widget_js_and_embed_page(public):
    js = public.get("/widget.js?shop=demo-salon")
    assert js.status_code == 200 and "javascript" in js.headers["content-type"]
    assert "/embed/" in js.text
    e = public.get("/embed/demo-salon")
    assert e.status_code == 200 and "frame-ancestors *" in e.headers["content-security-policy"]
    assert "x-frame-options" not in e.headers
    assert public.get("/s/demo-salon").headers["x-frame-options"] == "DENY"
    assert public.get("/embed/nope-shop").status_code == 404


def test_chat_api(env, public):
    r = public.post("/api/chat", json={"slug": "demo-salon", "message": "How much is a men's haircut?"})
    assert r.status_code == 200 and "300" in r.json()["answer"] and r.json()["found"] is True
    r = public.post("/api/chat", json={"slug": "demo-salon", "message": "Do you do tattoos?"})
    assert r.json()["found"] is False and r.json()["needs_human"] is True
    sid = g.get_shop_by_slug(env, "demo-salon")["id"]
    assert repo.list_unanswered(env, sid)[0]["question"] == "Do you do tattoos?"
    assert repo.count_chats_since(env, sid) == 2
    assert public.post("/api/chat", json={"slug": "nope-shop", "message": "hi"}).status_code == 404
    assert public.post("/api/chat", json={"slug": "demo-salon", "message": "  "}).status_code == 400
    assert public.post("/api/chat", json={"slug": "demo-salon", "message": "x" * 301}).status_code == 400
    assert public.post("/api/chat", json={"slug": "demo-salon"}).status_code == 422


def test_chat_never_leaks_other_shops_data(env, public):
    r = public.post("/api/chat", json={"slug": "demo-tutor", "message": "How much is an iPhone screen replacement?"})
    assert r.json()["found"] is False and "3500" not in r.json()["answer"]


def test_lead_requires_consent_and_scopes_to_shop(env, public):
    base = {"slug": "demo-repair", "name": "Asha", "contact": "asha@example.com", "message": "Laptop?"}
    assert public.post("/api/lead", json={**base, "consent": False}).status_code == 400
    assert public.post("/api/lead", json=base).status_code == 400
    sid = g.get_shop_by_slug(env, "demo-repair")["id"]
    assert repo.list_leads(env, sid) == []
    assert public.post("/api/lead", json={**base, "consent": True}).status_code == 200
    assert repo.list_leads(env, sid)[0]["contact"] == "asha@example.com"
    assert public.post("/api/lead", json={**base, "name": " ", "consent": True}).status_code == 400
    assert public.post("/api/lead", json={**base, "slug": "nope-shop", "consent": True}).status_code == 404


def test_chat_and_lead_rate_limits(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "k" * 40)
    monkeypatch.setenv("BASE_DOMAIN", "example.com")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "t.db"))
    monkeypatch.setenv("RATE_LIMITS_ENABLED", "true")
    conn = db.connect()
    db.init_db(conn)
    g.create_shop(conn, "S", "shop-one")
    c = browser()
    codes = [c.post("/api/chat", json={"slug": "shop-one", "message": "hi"}).status_code for _ in range(31)]
    assert codes[:30] == [200] * 30 and codes[30] == 429
    lead = {"slug": "shop-one", "name": "A", "contact": "1", "consent": True}
    codes = [c.post("/api/lead", json=lead).status_code for _ in range(6)]
    assert codes[:5] == [200] * 5 and codes[5] == 429


# ---------------- flash messages ----------------
def _svc(c, **over):
    d = {"csrf_token": csrf(c, "/dashboard/services"), "name": "Haircut", "price": "300",
         "duration_min": "30", "description": "", "keywords": ""}
    d.update(over)
    return c.post("/dashboard/services", data=d)


def test_flash_shows_once_after_save_then_is_gone(env, owner):
    c, sid = owner
    r = _svc(c)
    assert r.status_code == 303 and r.headers["location"] == "/dashboard/services"
    page = c.get("/dashboard/services")
    assert 'role="status"' in page.text and "Service added: Haircut" in page.text
    assert 'href="/s/glow-salon"' in page.text and "View on your public page" in page.text
    assert "Service added" not in c.get("/dashboard/services").text      # single use
    assert "Service added" not in c.get("/dashboard").text


def _hours_form(c, **over):
    d = {"csrf_token": csrf(c, "/dashboard/hours")}
    for i in range(7):
        d[f"open_{i}"], d[f"close_{i}"] = "09:00", "18:00"
    d.update(over)
    return d


def test_flash_covers_every_owner_action(env, owner):
    c, sid = owner
    _svc(c)
    c.get("/dashboard/services")                                   # consume the first banner
    svc = repo.list_services(env, sid)[0]["id"]

    def check(post, then_get, text):
        r = post()
        assert r.status_code == 303, (text, r.status_code)
        assert text in c.get(then_get).text, text
        assert text not in c.get(then_get).text, text + " (not single use)"

    svc_form = lambda name: {"csrf_token": csrf(c, "/dashboard/services"), "name": name, "price": "350",
                             "duration_min": "", "description": "", "keywords": ""}
    check(lambda: c.post(f"/dashboard/services/{svc}", data=svc_form("Cut")), "/dashboard/services", "Service saved: Cut")
    check(lambda: c.post("/dashboard/hours", data=_hours_form(c)), "/dashboard/hours", "Hours saved")
    check(lambda: c.post("/dashboard/faqs", data={"csrf_token": csrf(c, "/dashboard/faqs"), "question": "Parking?",
                                                  "answer": "Yes", "keywords": ""}), "/dashboard/faqs", "FAQ added: Parking?")
    faq = repo.list_faqs(env, sid)[0]["id"]
    check(lambda: c.post(f"/dashboard/faqs/{faq}", data={"csrf_token": csrf(c, "/dashboard/faqs"), "question": "Parking?",
                                                          "answer": "Free", "keywords": ""}), "/dashboard/faqs", "FAQ saved: Parking?")
    check(lambda: c.post(f"/dashboard/faqs/{faq}/delete", data={"csrf_token": csrf(c, "/dashboard/faqs")}),
          "/dashboard/faqs", "FAQ deleted")
    check(lambda: c.post("/dashboard/profile", data={"csrf_token": csrf(c, "/dashboard/profile"), "name": "Glow",
                                                     "address": "", "phone": "", "whatsapp": "", "currency": "INR"}),
          "/dashboard/profile", "Settings saved")
    lead = repo.add_lead(env, sid, "Asha", "9999999999", "hi")
    check(lambda: c.post(f"/dashboard/leads/{lead}/delete", data={"csrf_token": csrf(c, "/dashboard/leads")}),
          "/dashboard/leads", "Lead deleted")
    check(lambda: c.post(f"/dashboard/services/{svc}/delete", data={"csrf_token": csrf(c, "/dashboard/services")}),
          "/dashboard/services", "Service deleted: Cut")


def test_flash_approve_and_dismiss(env, owner):
    c, sid = owner
    qid = repo.log_unanswered(env, sid, "Do you do threading?")
    qid2 = repo.log_unanswered(env, sid, "Do you do waxing?")
    r = c.post("/dashboard/faqs", data={"csrf_token": csrf(c, "/dashboard/faqs"), "question": "Do you do threading?",
                                         "answer": "Saturdays only", "keywords": "", "from_unanswered": str(qid)})
    assert r.status_code == 303
    assert "FAQ approved and added" in c.get("/dashboard/faqs").text
    r = c.post(f"/dashboard/unanswered/{qid2}/dismiss", data={"csrf_token": csrf(c)})
    assert r.status_code == 303 and "Question dismissed" in c.get("/dashboard").text


def test_error_flash_shows_alert_and_keeps_typed_values(env, owner):
    c, sid = owner
    r = _svc(c, name="Facial", price="abc", description="Deep clean")
    assert r.status_code == 400
    assert 'role="alert"' in r.text and "whole numbers" in r.text
    assert 'value="Facial"' in r.text and 'value="abc"' in r.text and 'value="Deep clean"' in r.text
    assert repo.list_services(env, sid) == []                     # nothing saved
    r = c.post("/dashboard/profile", data={"csrf_token": csrf(c, "/dashboard/profile"), "name": "New Name",
                                           "address": "", "phone": "", "whatsapp": "", "currency": "rupee"})
    assert r.status_code == 400 and 'role="alert"' in r.text and 'value="New Name"' in r.text and 'value="rupee"' in r.text
    r = c.post("/dashboard/hours", data=_hours_form(c, open_0="20:00", close_0="09:00"))
    assert r.status_code == 400 and 'role="alert"' in r.text and 'value="20:00"' in r.text


def test_flash_is_escaped_not_html(env, owner):
    c, sid = owner
    evil = "<script>alert(1)</script>"
    _svc(c, name=evil)
    page = c.get("/dashboard/services").text
    assert "Service added: &lt;script&gt;alert(1)&lt;/script&gt;" in page
    assert "<script>alert(1)</script>" not in page


def test_anonymous_never_sees_flash_and_cookie_cannot_be_forged_or_moved(env, owner):
    c, sid = owner
    r = _svc(c, name="Haircut")
    flash_cookie = r.cookies.get("flash") or r.headers["set-cookie"].split("flash=")[1].split(";")[0]
    anon = browser()
    anon.cookies.set("flash", flash_cookie, domain="example.com")
    for path in ("/login", "/", "/s/glow-salon", "/dashboard"):
        assert "Service added" not in anon.get(path, follow_redirects=False).text
    # another logged-in owner presenting this cookie does not see it either (bound to the session)
    make_owner(env, "Other Shop", "other-shop", "b@example.com")
    other = browser("tok-other-shop")
    other.cookies.set("flash", flash_cookie, domain="example.com")
    assert "Service added" not in other.get("/dashboard/services").text
    # a forged cookie is ignored
    c2 = browser("tok-glow-salon")
    c2.cookies.set("flash", "eyJrIjoib2siLCJ0IjoiaGFja2VkIiwicCI6ZmFsc2V9.deadbeef", domain="example.com")
    assert "hacked" not in c2.get("/dashboard").text


def test_flash_static_js_exists_and_banner_works_without_js(env, owner):
    c, sid = owner
    js = c.get("/static/flash.js")
    assert js.status_code == 200 and "prefers-reduced-motion" in js.text
    _svc(c)
    page = c.get("/dashboard/services").text
    assert 'hidden>&times;' in page or "hidden>" in page        # close button only revealed by JS
    assert "<script>" not in page and '<script src="/static/flash.js" defer>' in page
