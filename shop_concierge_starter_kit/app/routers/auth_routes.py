"""Register, verify email, login, logout, and a minimal dashboard stub (T4 builds it out)."""
import re

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .. import db, global_lookups as g, mailer, repo, security
from ..ratelimit import client_ip

router = APIRouter()
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def get_conn():
    conn = db.connect()
    try:
        yield conn
    finally:
        conn.close()


def _render(request, name, status=200, **ctx):
    """Render a template with a CSRF token; sets the csrf cookie if the visitor has none."""
    st = request.app.state.settings
    cookie = request.cookies.get("csrf") or security.new_token()
    ctx["csrf_token"] = security.csrf_field_for(st.secret_key, cookie)
    response = request.app.state.templates.TemplateResponse(request, name, ctx, status_code=status)
    if request.cookies.get("csrf") != cookie:
        response.set_cookie("csrf", cookie, max_age=86400, **security.COOKIE_OPTS)
    return response


def _csrf_ok(request, token):
    return security.csrf_ok(request.app.state.settings.secret_key, request.cookies.get("csrf"), token)


def _too_many(request):
    return _render(request, "message.html", 429, title="Slow down",
                   message="Too many attempts. Please wait a few minutes and try again.")


def _bad_csrf(request):
    return _render(request, "message.html", 400, title="Please try again",
                   message="Your form expired. Please go back, reload the page and try again.")


def current_user(request: Request, conn=Depends(get_conn)):
    return g.get_session_user(conn, request.cookies.get("session"))


@router.get("/register", response_class=HTMLResponse)
def register_form(request: Request):
    return _render(request, "register.html", error=None, values={})


@router.post("/register", response_class=HTMLResponse)
def register(request: Request, shop_name: str = Form(""), email: str = Form(""),
             password: str = Form(""), csrf_token: str = Form(""), conn=Depends(get_conn)):
    st = request.app.state
    if not _csrf_ok(request, csrf_token):
        return _bad_csrf(request)
    if not st.limits["register"].allow(client_ip(request, st.settings.trusted_proxies)):
        return _too_many(request)
    shop_name, email = shop_name.strip(), email.strip().lower()
    values = {"shop_name": shop_name, "email": email}
    error = None
    if not shop_name or len(shop_name) > 120:
        error = "Please enter your shop name (up to 120 characters)."
    elif not EMAIL_RE.match(email) or len(email) > 254:
        error = "Please enter a valid email address."
    elif not security.MIN_PASSWORD <= len(password) <= security.MAX_PASSWORD:
        error = f"Password must be {security.MIN_PASSWORD} to {security.MAX_PASSWORD} characters."
    if error:
        return _render(request, "register.html", 400, error=error, values=values)

    if g.get_user_by_email(conn, email) is None:
        try:
            shop_id = g.create_shop(conn, shop_name, g.slug_for_name(conn, shop_name))
            user_id = g.create_user(conn, shop_id, email, security.hash_password(password))
            token = security.new_token()
            g.set_verify_token(conn, user_id, token, st.settings.verify_hours)
            link = f"https://{st.settings.base_domain}/verify?token={token}"
            mailer.send_email(email, "Confirm your email",
                              f"Welcome! Open this link to confirm your email:\n{link}\n")
        except ValueError:
            return _render(request, "register.html", 400,
                           error="We could not create that account. Please try different details.",
                           values=values)
    # same reply whether or not the email already existed (no account enumeration)
    return _render(request, "message.html", title="Check your email",
                   message="If that address can be registered, we have sent a confirmation link. "
                           "Open it to activate your account.")


@router.get("/verify", response_class=HTMLResponse)
def verify(request: Request, token: str = "", conn=Depends(get_conn)):
    st = request.app.state
    if not st.limits["verify"].allow(client_ip(request, st.settings.trusted_proxies)):
        return _too_many(request)
    if g.consume_verify_token(conn, token):
        return _render(request, "message.html", title="Email confirmed",
                       message="Your email is confirmed. You can log in now.", link=("/login", "Log in"))
    return _render(request, "message.html", 400, title="Link not valid",
                   message="This confirmation link is invalid or has expired. Please register again.")


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return _render(request, "login.html", error=None)


@router.post("/login", response_class=HTMLResponse)
def login(request: Request, email: str = Form(""), password: str = Form(""),
          csrf_token: str = Form(""), conn=Depends(get_conn)):
    st = request.app.state
    if not _csrf_ok(request, csrf_token):
        return _bad_csrf(request)
    email = email.strip().lower()[:254]
    ip = client_ip(request, st.settings.trusted_proxies)
    if not (st.limits["login_ip"].allow(ip) and st.limits["login_email"].allow(email)):
        return _too_many(request)
    user = g.get_user_by_email(conn, email)
    ok = security.verify_password(password[: security.MAX_PASSWORD], user["pw_hash"] if user else None)
    if not (ok and user and user["verified"]):
        return _render(request, "login.html", 400,
                       error="Wrong email or password, or the email is not confirmed yet.")
    token = security.new_token()
    g.create_session(conn, user["id"], token, st.settings.session_days)
    response = RedirectResponse("/dashboard", status_code=303)
    response.set_cookie("session", token, max_age=st.settings.session_days * 86400,
                        **security.COOKIE_OPTS)
    return response


@router.post("/logout")
def logout(request: Request, csrf_token: str = Form(""), conn=Depends(get_conn)):
    if not _csrf_ok(request, csrf_token):
        return _bad_csrf(request)
    g.delete_session(conn, request.cookies.get("session"))
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie("session", path="/")
    return response


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, user=Depends(current_user), conn=Depends(get_conn)):
    if user is None:
        return RedirectResponse("/login", status_code=303)
    shop = repo.get_shop(conn, user["shop_id"])      # shop_id comes from the session, never the URL
    return _render(request, "dashboard.html", shop=shop)
