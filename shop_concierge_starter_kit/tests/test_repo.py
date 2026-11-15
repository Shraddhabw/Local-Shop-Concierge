import pytest

from app import repo


def test_shop_id_is_required(conn):
    with pytest.raises(TypeError):
        repo.list_services(conn)
    for bad in (None, 0, -1, "1", True, 1.5):
        with pytest.raises(ValueError):
            repo.list_services(conn, bad)
        with pytest.raises(ValueError):
            repo.add_faq(conn, bad, "q", "a")


def test_service_crud_roundtrip(conn, salon):
    sid = repo.add_service(conn, salon, "Spa", 999, 20, "desc", "relax")
    assert repo.get_service(conn, salon, sid)["price"] == 999
    assert repo.update_service(conn, salon, sid, price=500) is True
    assert repo.get_service(conn, salon, sid)["price"] == 500
    assert repo.delete_service(conn, salon, sid) is True
    assert repo.get_service(conn, salon, sid) is None


def test_price_is_whole_units_and_validated(conn, salon):
    sid = repo.add_service(conn, salon, "Thing", 300)
    assert repo.get_service(conn, salon, sid)["price"] == 300
    for bad in (-1, 3.5, "300", True):
        with pytest.raises(ValueError):
            repo.add_service(conn, salon, "Bad", bad)
    with pytest.raises(ValueError):
        repo.add_service(conn, salon, "   ")
    with pytest.raises(ValueError):
        repo.update_service(conn, salon, sid, nope=1)


def test_hours_validation(conn, salon):
    with pytest.raises(ValueError):
        repo.add_hours(conn, salon, 7, "10:00", "11:00")
    with pytest.raises(ValueError):
        repo.add_hours(conn, salon, 1, "25:00", "26:00")
    with pytest.raises(ValueError):
        repo.add_hours(conn, salon, 1, "12:00", "11:00")
    hid = repo.add_hours(conn, salon, 1, closed=True)
    assert repo.get_hours(conn, salon, hid)["open_time"] is None


def test_lead_requires_name_and_contact(conn, salon):
    with pytest.raises(ValueError):
        repo.add_lead(conn, salon, "", "x")
    lid = repo.add_lead(conn, salon, "Asha", "asha@example.com", "call me")
    assert repo.get_lead(conn, salon, lid)["confirmed_at"]


def test_unanswered_counts_repeats(conn, salon):
    a = repo.log_unanswered(conn, salon, "Do you do tattoos?")
    b = repo.log_unanswered(conn, salon, "do you do TATTOOS")
    assert a == b
    assert repo.list_unanswered(conn, salon)[0]["count"] == 2


# ---- tenant isolation: shop A can never touch shop B by guessing ids ----
def test_cross_tenant_services(conn, two_shops):
    a, b = two_shops
    b_svc = repo.list_services(conn, b)[0]["id"]
    assert repo.get_service(conn, a, b_svc) is None
    assert repo.update_service(conn, a, b_svc, price=1) is False
    assert repo.delete_service(conn, a, b_svc) is False
    row = repo.get_service(conn, b, b_svc)
    assert row is not None and row["price"] == 3500
    assert all(s["id"] != b_svc for s in repo.list_services(conn, a))


def test_cross_tenant_faqs_hours_leads_unanswered(conn, two_shops):
    a, b = two_shops
    faq = repo.list_faqs(conn, b)[0]["id"]
    hrs = repo.list_hours(conn, b)[0]["id"]
    lead = repo.add_lead(conn, b, "Ravi", "9999999999")
    una = repo.log_unanswered(conn, b, "secret question")
    assert repo.get_faq(conn, a, faq) is None
    assert repo.update_faq(conn, a, faq, answer="hacked") is False
    assert repo.delete_faq(conn, a, faq) is False
    assert repo.get_hours(conn, a, hrs) is None
    assert repo.update_hours(conn, a, hrs, closed=True) is False
    assert repo.delete_hours(conn, a, hrs) is False
    assert repo.get_lead(conn, a, lead) is None
    assert repo.delete_lead(conn, a, lead) is False
    assert repo.delete_unanswered(conn, a, una) is False
    assert repo.list_leads(conn, a) == [] and repo.list_unanswered(conn, a) == []
    assert repo.get_faq(conn, b, faq)["answer"].startswith("3 month")
    assert repo.get_lead(conn, b, lead) is not None


def test_cannot_resolve_with_another_shops_faq(conn, two_shops):
    a, b = two_shops
    una = repo.log_unanswered(conn, a, "something")
    foreign_faq = repo.list_faqs(conn, b)[0]["id"]
    assert repo.resolve_unanswered(conn, a, una, foreign_faq) is False
    own_faq = repo.list_faqs(conn, a)[0]["id"]
    assert repo.resolve_unanswered(conn, a, una, own_faq) is True
    assert repo.list_unanswered(conn, a) == []


def test_update_shop_scoped_and_validated(conn, two_shops):
    a, b = two_shops
    assert repo.update_shop(conn, a, phone="123") is True
    assert repo.get_shop(conn, b)["phone"] == ""
    with pytest.raises(ValueError):
        repo.update_shop(conn, a, slug="hijack")
    with pytest.raises(ValueError):
        repo.update_shop(conn, a, currency="rupees")
