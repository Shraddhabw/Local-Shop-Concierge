"""App factory, host routing and security headers."""
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import db
from .config import Settings
from .ratelimit import RateLimiter

BASE = Path(__file__).parent
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Content-Security-Policy": ("default-src 'self'; img-src 'self' data:; "
                                "style-src 'self'; script-src 'self'; frame-ancestors 'none'; "
                                "form-action 'self'; base-uri 'none'"),
}
OWNER_PREFIXES = ("/register", "/login", "/logout", "/verify", "/dashboard", "/contact")
APEX_ONLY_NOTE = "owner pages are 404 on shop subdomains"


def create_app(settings=None):
    settings = settings or Settings()
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    conn = db.connect()
    db.init_db(conn)                      # idempotent: creates tables on a fresh server volume
    conn.close()
    from .ai.chat_ai import AIService
    app.state.ai = AIService(settings)
    app.state.templates = Jinja2Templates(directory=str(BASE / "templates"))
    from .web import money
    app.state.templates.env.globals["money"] = money
    on = settings.rate_limits_enabled
    app.state.limits = {
        "register": RateLimiter(5, 3600, on), "login_ip": RateLimiter(10, 900, on),
        "login_email": RateLimiter(5, 900, on), "verify": RateLimiter(20, 3600, on),
        "chat": RateLimiter(30, 60, on), "lead": RateLimiter(5, 3600, on), "lead_shop": RateLimiter(30, 3600, on), "contact": RateLimiter(3, 3600, on),
        "ai_ip": RateLimiter(settings.ai_ip_hourly, 3600, on),
        "import": RateLimiter(5, 3600, on),
    }
    app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")

    @app.middleware("http")
    async def host_routing_and_headers(request: Request, call_next):
        host = request.headers.get("host", "").split(":")[0].lower()
        base = settings.base_domain
        path = request.url.path
        if host in (base, "www." + base):
            request.state.kind, request.state.shop_slug = "apex", None
        elif host.endswith("." + base) and "." not in host[: -len(base) - 1]:
            request.state.kind, request.state.shop_slug = "shop", host[: -len(base) - 1]
        else:
            request.state.kind, request.state.shop_slug = "unknown", None
        if path not in ("/healthz", "/internal/tls-ask") and (
                request.state.kind == "unknown"
                or (request.state.kind == "shop" and path.startswith(OWNER_PREFIXES))):
            response = PlainTextResponse("Not found", status_code=404)
        else:
            response = await call_next(request)
        for k, v in SECURITY_HEADERS.items():
            if k == "X-Frame-Options" and path.startswith("/embed/"):
                continue                      # the chat iframe page is meant to be embedded
            response.headers.setdefault(k, v)
        response.headers.setdefault("Cache-Control", "no-store")
        return response

    from .routers import auth_routes, chat, contact, internal, owner, public
    for module in (auth_routes, chat, contact, internal, owner, public):
        app.include_router(module.router)

    @app.get("/healthz", include_in_schema=False)
    def healthz():
        return PlainTextResponse("ok")

    return app
