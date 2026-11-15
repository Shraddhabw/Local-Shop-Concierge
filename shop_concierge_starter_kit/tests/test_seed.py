import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import seed  # noqa: E402

from app import global_lookups as g, repo  # noqa: E402


def test_seed_shape_and_not_offered(conn):
    seed.seed(conn)
    seed.seed(conn)  # idempotent
    for slug in ("demo-salon", "demo-tutor", "demo-repair"):
        sid = g.get_shop_by_slug(conn, slug)["id"]
        assert 8 <= len(repo.list_services(conn, sid)) <= 10
        assert len(repo.list_faqs(conn, sid)) == 10
        assert len(repo.list_hours(conn, sid)) == 7
    n = conn.execute("SELECT COUNT(*) FROM shops").fetchone()[0]
    assert n == 3
    text = " ".join(str(dict(r)) for t in ("services", "faqs") for r in conn.execute(f"SELECT * FROM {t}")).lower()
    for banned in ("physics", "laptop", "tattoo", "rebonding", "discount"):
        assert banned not in text
