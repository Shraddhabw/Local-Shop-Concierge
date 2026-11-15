"""Endpoints for the Caddy container only."""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import PlainTextResponse

from .. import global_lookups as g
from ..ratelimit import _in_networks
from ..web import get_conn

router = APIRouter()


@router.get("/internal/tls-ask", include_in_schema=False)
def tls_ask(request: Request, domain: str = "", conn=Depends(get_conn)):
    """Caddy asks before issuing a certificate. 200 only for the apex, www or an existing shop slug.

    Fails closed: callable only from a trusted proxy address (the Caddy container), and with no
    TRUSTED_PROXIES configured it always answers 404. The Caddyfile also never proxies /internal/*.
    """
    st = request.app.state.settings
    peer = request.client.host if request.client else ""
    if not st.trusted_proxies or not _in_networks(peer, st.trusted_proxies):
        return PlainTextResponse("Not found", status_code=404)
    if g.tls_ask_allowed(conn, domain, st.base_domain):
        return PlainTextResponse("ok")
    return PlainTextResponse("Not found", status_code=404)
