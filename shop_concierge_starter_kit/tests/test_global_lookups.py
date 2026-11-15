import pytest

from app import global_lookups as g


def test_create_and_find_shop(conn):
    sid = g.create_shop(conn, "Asha's Tutoring", "asha-tutoring")
    assert g.get_shop_by_slug(conn, "ASHA-tutoring")["id"] == sid
    assert g.get_shop_by_slug(conn, "nope") is None
    assert g.get_shop_by_slug(conn, None) is None


@pytest.mark.parametrize("slug", ["www", "admin", "api", "mail", "app", "static"])
def test_reserved_slugs_blocked(conn, slug):
    with pytest.raises(ValueError):
        g.create_shop(conn, "X", slug)


@pytest.mark.parametrize("slug", ["", "a", "-ab", "ab-", "a b", "A_B", "x" * 50, "a--b", "a.b", None])
def test_invalid_slugs_rejected(conn, slug):
    with pytest.raises(ValueError):
        g.create_shop(conn, "X", slug)


def test_duplicate_slug_rejected(conn):
    g.create_shop(conn, "One", "same-slug")
    with pytest.raises(ValueError):
        g.create_shop(conn, "Two", "same-slug")


def test_users_by_email_case_insensitive_unique(conn):
    sid = g.create_shop(conn, "S", "shop-one")
    g.create_user(conn, sid, "Owner@Example.com", "hash")
    assert g.get_user_by_email(conn, "owner@example.COM")["shop_id"] == sid
    assert g.get_user_by_email(conn, "other@example.com") is None
    with pytest.raises(ValueError):
        g.create_user(conn, sid, "owner@example.com", "hash")
    with pytest.raises(ValueError):
        g.create_user(conn, sid, "not-an-email", "hash")


def test_tls_ask_only_existing_slugs(conn):
    g.create_shop(conn, "S", "real-shop")
    ok = lambda d: g.tls_ask_allowed(conn, d, "example.com")
    assert ok("example.com") and ok("www.example.com") and ok("real-shop.example.com")
    assert not ok("ghost.example.com")
    assert not ok("a.real-shop.example.com")
    assert not ok("real-shop.example.com.evil.com")
    assert not ok("evilexample.com")
    assert not ok("") and not ok(None)
    assert not g.tls_ask_allowed(conn, "real-shop.example.com", "")
