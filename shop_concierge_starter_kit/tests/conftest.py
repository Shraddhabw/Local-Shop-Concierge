import pytest

from app import db, global_lookups as g, repo


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "test.db")
    db.init_db(c)
    yield c
    c.close()


def _salon(conn):
    sid = g.create_shop(conn, "Demo Salon", "demo-salon")
    repo.update_shop(conn, sid, address="12 MG Road, Pune")
    for name, price, dur, desc in [("Men's Haircut", 300, 30, ""), ("Women's Haircut", 600, 60, ""),
                                   ("Facial", 1200, 45, ""), ("Bridal Makeup", 8000, 120, "Includes trial")]:
        repo.add_service(conn, sid, name, price, dur, desc)
    repo.add_faq(conn, sid, "Do you accept walk-ins?", "Yes, walk-ins are welcome.")
    repo.add_faq(conn, sid, "Which payment methods do you accept?", "We accept UPI, cards and cash.")
    for d in range(6):
        repo.add_hours(conn, sid, d, "10:00", "20:00")
    repo.add_hours(conn, sid, 6, "10:00", "17:00")
    return sid


def _repair(conn):
    sid = g.create_shop(conn, "Fix It Repairs", "demo-repair")
    repo.add_service(conn, sid, "iPhone Screen Replacement", 3500, 60)
    repo.add_service(conn, sid, "Battery Replacement", 1800, 30)
    repo.add_faq(conn, sid, "Do you give a warranty?", "3 month warranty on all repairs.")
    repo.add_hours(conn, sid, 0, "10:00", "19:00")
    return sid


@pytest.fixture
def salon(conn):
    return _salon(conn)


@pytest.fixture
def two_shops(conn):
    return _salon(conn), _repair(conn)
