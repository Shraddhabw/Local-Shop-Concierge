"""Shared web helpers: DB dependency, template rendering with CSRF, owner guard."""
from fastapi import Depends, HTTPException, Request

from . import answer as engine, db, global_lookups as g, security


def get_conn():
    conn = db.connect()
    try:
        yield conn
    finally:
        conn.close()


def render(request, name, status=200, **ctx):
    """Render a template with a CSRF token; sets the csrf cookie if the visitor has none."""
    st = request.app.state.settings
    cookie = request.cookies.get("csrf") or security.new_token()
    ctx["csrf_token"] = security.csrf_field_for(st.secret_key, cookie)
    response = request.app.state.templates.TemplateResponse(request, name, ctx, status_code=status)
    if request.cookies.get("csrf") != cookie:
        response.set_cookie("csrf", cookie, max_age=86400, **security.COOKIE_OPTS)
    return response


def csrf_ok(request, token):
    return security.csrf_ok(request.app.state.settings.secret_key, request.cookies.get("csrf"), token)


def too_many(request):
    return render(request, "message.html", 429, title="Slow down",
                  message="Too many attempts. Please wait a few minutes and try again.")


def bad_csrf(request):
    return render(request, "message.html", 400, title="Please try again",
                  message="Your form expired. Please go back, reload the page and try again.")


def current_user(request: Request, conn=Depends(get_conn)):
    return g.get_session_user(conn, request.cookies.get("session"))


def require_owner(user=Depends(current_user)):
    """The owner's shop_id comes from the session row, never from the URL or the form."""
    if user is None:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return user


async def csrf_protect(request: Request):
    form = await request.form()
    if not csrf_ok(request, form.get("csrf_token", "")):
        raise HTTPException(status_code=400, detail="Your form expired. Reload the page and try again.")


def money(shop, price):
    return engine._money(shop, price)


def redirect_with_flash(request, url, text, kind="ok", public=False, focus=False):
    """303 redirect that carries one message, shown once on the next owner page."""
    from fastapi.responses import RedirectResponse
    response = RedirectResponse(url, status_code=303)
    st = request.app.state.settings
    response.set_cookie("flash", security.flash_pack(st.secret_key, request.cookies.get("session", ""),
                                                     kind, text, public, focus),
                        max_age=120, **security.COOKIE_OPTS)
    return response


def pop_flash(request):
    """The pending message for this owner session, or None. The caller must clear the cookie."""
    st = request.app.state.settings
    return security.flash_unpack(st.secret_key, request.cookies.get("session", ""), request.cookies.get("flash"))
