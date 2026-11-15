"""Landing page, public shop page, QR code, embeddable widget."""
import re

import segno
from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse

from .. import answer as engine, global_lookups as g, repo
from ..web import get_conn, render

router = APIRouter()
STATIC = __import__("pathlib").Path(__file__).resolve().parent.parent / "static"


def _shop_page(request, conn, slug):
    shop = g.get_shop_by_slug(conn, slug)
    if shop is None:
        return PlainTextResponse("Shop not found", status_code=404)
    url = f"{request.app.state.settings.base_url}/s/{shop['slug']}"
    qr = segno.make(url, error="m").svg_inline(scale=4, border=2, dark="#000000")
    digits = re.sub(r"\D", "", shop["whatsapp"])
    return render(request, "public_shop.html", shop=shop, url=url, qr=qr,
                  services=repo.list_services(conn, shop["id"]),
                  hours=engine.hours_rows(repo.list_hours(conn, shop["id"])),
                  whatsapp=f"https://wa.me/{digits}" if 6 <= len(digits) <= 15 else None)


@router.get("/", response_class=HTMLResponse)
def home(request: Request, conn=Depends(get_conn)):
    if request.state.kind == "shop":              # slug.BASE_DOMAIN serves that shop's page
        return _shop_page(request, conn, request.state.shop_slug)
    return render(request, "landing.html")


@router.get("/s/{slug}", response_class=HTMLResponse)
def shop_page(slug: str, request: Request, conn=Depends(get_conn)):
    return _shop_page(request, conn, slug)


@router.get("/embed/{slug}", response_class=HTMLResponse)
def embed(slug: str, request: Request, conn=Depends(get_conn)):
    shop = g.get_shop_by_slug(conn, slug)
    if shop is None:
        return PlainTextResponse("Shop not found", status_code=404)
    response = render(request, "embed.html", shop=shop)
    # the only page that may be framed, by any site (that is what an embeddable widget is)
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; style-src 'self'; script-src 'self'; frame-ancestors *; base-uri 'none'")
    return response


@router.get("/widget.js", include_in_schema=False)
def widget_js():
    return FileResponse(STATIC / "widget.js", media_type="application/javascript",
                        headers={"Cache-Control": "public, max-age=300"})
