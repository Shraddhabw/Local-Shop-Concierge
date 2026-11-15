"""Tenant data layer. Every function REQUIRES shop_id and filters by it.

Functions that cannot take a shop_id live in app/global_lookups.py.
Prices are whole currency units (integers), never cents.
"""
import re
from datetime import datetime, timezone

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

# table -> {field: (kind, a, b)}; kinds: text(max_len, required), int(min, max), time, bool
_SPECS = {
    "services": {
        "name": ("text", 120, True),
        "price": ("int", 0, 10_000_000),
        "duration_min": ("int", 1, 1440),
        "description": ("text", 500, False),
        "keywords": ("text", 300, False),
    },
    "faqs": {
        "question": ("text", 300, True),
        "answer": ("text", 1000, True),
        "keywords": ("text", 300, False),
    },
    "hours": {
        "weekday": ("int", 0, 6, True),
        "open_time": ("time",),
        "close_time": ("time",),
        "closed": ("bool",),
    },
}
_DEFAULTS = {"hours": {"closed": 0}}


def _sid(shop_id):
    if isinstance(shop_id, bool) or not isinstance(shop_id, int) or shop_id <= 0:
        raise ValueError("shop_id is required and must be a positive integer")
    return shop_id


def _id(value, field="id"):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field} must be a positive integer")
    return value


def _clean(table, field, value):
    spec = _SPECS[table][field]
    kind = spec[0]
    if kind == "text":
        if value is None:
            value = ""
        if not isinstance(value, str):
            raise ValueError(f"{field} must be text")
        value = value.strip()
        if spec[2] and not value:
            raise ValueError(f"{field} is required")
        if len(value) > spec[1]:
            raise ValueError(f"{field} is too long")
        return value
    if kind == "int":
        if value is None:
            if len(spec) > 3 and spec[3]:
                raise ValueError(f"{field} is required")
            return None
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{field} must be a whole number")
        if not spec[1] <= value <= spec[2]:
            raise ValueError(f"{field} is out of range")
        return value
    if kind == "time":
        if value is None:
            return None
        if not isinstance(value, str) or not _TIME_RE.match(value):
            raise ValueError(f"{field} must be HH:MM")
        return value
    if kind == "bool":
        return 1 if value else 0
    raise ValueError("bad spec")


def _clean_row(table, values, partial=False):
    out = {}
    for field in _SPECS[table]:
        if field in values:
            out[field] = _clean(table, field, values[field])
        elif not partial:
            out[field] = _clean(table, field, _DEFAULTS.get(table, {}).get(field))
    unknown = set(values) - set(_SPECS[table])
    if unknown:
        raise ValueError(f"unknown field(s): {', '.join(sorted(unknown))}")
    return out


def _check_hours(row):
    if row["closed"]:
        row["open_time"] = row["close_time"] = None
    elif not row["open_time"] or not row["close_time"]:
        raise ValueError("open_time and close_time are required unless closed")
    elif row["open_time"] >= row["close_time"]:
        raise ValueError("open_time must be before close_time")
    return row


def _insert(conn, table, shop_id, values):
    row = _clean_row(table, values)
    if table == "hours":
        row = _check_hours(row)
    cols = ["shop_id"] + list(row)
    cur = conn.execute(
        f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
        [shop_id] + list(row.values()),
    )
    conn.commit()
    return cur.lastrowid


def _list(conn, table, shop_id, order):
    return [dict(r) for r in conn.execute(
        f"SELECT * FROM {table} WHERE shop_id = ? ORDER BY {order}", (shop_id,))]


def _get(conn, table, shop_id, item_id):
    row = conn.execute(
        f"SELECT * FROM {table} WHERE id = ? AND shop_id = ?", (item_id, shop_id)).fetchone()
    return dict(row) if row else None


def _update(conn, table, shop_id, item_id, values):
    current = _get(conn, table, shop_id, item_id)
    if current is None:
        return False
    row = {k: current[k] for k in _SPECS[table]}
    row.update(_clean_row(table, values, partial=True))
    if table == "hours":
        row = _check_hours(row)
    sets = ", ".join(f"{k} = ?" for k in row)
    cur = conn.execute(
        f"UPDATE {table} SET {sets} WHERE id = ? AND shop_id = ?",
        list(row.values()) + [item_id, shop_id])
    conn.commit()
    return cur.rowcount > 0


def _delete(conn, table, shop_id, item_id):
    cur = conn.execute(f"DELETE FROM {table} WHERE id = ? AND shop_id = ?", (item_id, shop_id))
    conn.commit()
    return cur.rowcount > 0


# ---- shop ----
_SHOP_FIELDS = {"name": 120, "address": 300, "phone": 40, "whatsapp": 40, "currency": 3}


def get_shop(conn, shop_id):
    row = conn.execute("SELECT * FROM shops WHERE id = ?", (_sid(shop_id),)).fetchone()
    return dict(row) if row else None


def update_shop(conn, shop_id, **fields):
    _sid(shop_id)
    if not fields or set(fields) - set(_SHOP_FIELDS):
        raise ValueError("unknown or empty shop fields")
    clean = {}
    for k, v in fields.items():
        if not isinstance(v, str) or len(v.strip()) > _SHOP_FIELDS[k]:
            raise ValueError(f"{k} is invalid")
        clean[k] = v.strip()
    if "name" in clean and not clean["name"]:
        raise ValueError("name is required")
    if "currency" in clean and not re.fullmatch(r"[A-Z]{3}", clean["currency"]):
        raise ValueError("currency must be a 3-letter code")
    sets = ", ".join(f"{k} = ?" for k in clean)
    cur = conn.execute(f"UPDATE shops SET {sets} WHERE id = ?", list(clean.values()) + [shop_id])
    conn.commit()
    return cur.rowcount > 0


# ---- services ----
def add_service(conn, shop_id, name, price=None, duration_min=None, description="", keywords=""):
    return _insert(conn, "services", _sid(shop_id), dict(
        name=name, price=price, duration_min=duration_min,
        description=description, keywords=keywords))


def list_services(conn, shop_id):
    return _list(conn, "services", _sid(shop_id), "id")


def get_service(conn, shop_id, service_id):
    return _get(conn, "services", _sid(shop_id), _id(service_id))


def update_service(conn, shop_id, service_id, **fields):
    return _update(conn, "services", _sid(shop_id), _id(service_id), fields)


def delete_service(conn, shop_id, service_id):
    return _delete(conn, "services", _sid(shop_id), _id(service_id))


# ---- faqs ----
def add_faq(conn, shop_id, question, answer, keywords=""):
    return _insert(conn, "faqs", _sid(shop_id), dict(
        question=question, answer=answer, keywords=keywords))


def list_faqs(conn, shop_id):
    return _list(conn, "faqs", _sid(shop_id), "id")


def get_faq(conn, shop_id, faq_id):
    return _get(conn, "faqs", _sid(shop_id), _id(faq_id))


def update_faq(conn, shop_id, faq_id, **fields):
    return _update(conn, "faqs", _sid(shop_id), _id(faq_id), fields)


def delete_faq(conn, shop_id, faq_id):
    return _delete(conn, "faqs", _sid(shop_id), _id(faq_id))


# ---- hours (weekday 0 = Monday; several rows per day allowed for split shifts) ----
def add_hours(conn, shop_id, weekday, open_time=None, close_time=None, closed=False):
    return _insert(conn, "hours", _sid(shop_id), dict(
        weekday=weekday, open_time=open_time, close_time=close_time, closed=closed))


def list_hours(conn, shop_id):
    return _list(conn, "hours", _sid(shop_id), "weekday, open_time, id")


def get_hours(conn, shop_id, hours_id):
    return _get(conn, "hours", _sid(shop_id), _id(hours_id))


def update_hours(conn, shop_id, hours_id, **fields):
    return _update(conn, "hours", _sid(shop_id), _id(hours_id), fields)


def delete_hours(conn, shop_id, hours_id):
    return _delete(conn, "hours", _sid(shop_id), _id(hours_id))


# ---- leads (only saved after the customer confirmed sharing details) ----
def add_lead(conn, shop_id, name, contact, message=""):
    _sid(shop_id)
    name, contact, message = (str(x or "").strip() for x in (name, contact, message))
    if not name or not contact or len(name) > 120 or len(contact) > 200 or len(message) > 1000:
        raise ValueError("name and contact are required and must be short")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    cur = conn.execute(
        "INSERT INTO leads (shop_id, name, contact, message, confirmed_at) VALUES (?,?,?,?,?)",
        (shop_id, name, contact, message, now))
    conn.commit()
    return cur.lastrowid


def list_leads(conn, shop_id):
    return _list(conn, "leads", _sid(shop_id), "id DESC")


def get_lead(conn, shop_id, lead_id):
    return _get(conn, "leads", _sid(shop_id), _id(lead_id))


def delete_lead(conn, shop_id, lead_id):
    return _delete(conn, "leads", _sid(shop_id), _id(lead_id))


# ---- unanswered questions ----
def _norm_question(q):
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", q.lower())).strip()


def log_unanswered(conn, shop_id, question):
    _sid(shop_id)
    question = str(question or "").strip()[:300]
    norm = _norm_question(question)
    if not norm:
        return None
    conn.execute(
        "INSERT INTO unanswered_questions (shop_id, question, norm) VALUES (?,?,?) "
        "ON CONFLICT(shop_id, norm) DO UPDATE SET count = count + 1, last_seen = CURRENT_TIMESTAMP",
        (shop_id, question, norm))
    conn.commit()
    return conn.execute(
        "SELECT id FROM unanswered_questions WHERE shop_id = ? AND norm = ?",
        (shop_id, norm)).fetchone()["id"]


def list_unanswered(conn, shop_id, limit=20):
    return [dict(r) for r in conn.execute(
        "SELECT * FROM unanswered_questions WHERE shop_id = ? AND resolved_faq_id IS NULL "
        "ORDER BY count DESC, last_seen DESC LIMIT ?", (_sid(shop_id), int(limit)))]


def delete_unanswered(conn, shop_id, item_id):
    return _delete(conn, "unanswered_questions", _sid(shop_id), _id(item_id))


def resolve_unanswered(conn, shop_id, item_id, faq_id):
    """Mark a question as resolved by one of THIS shop's FAQs."""
    _sid(shop_id)
    if get_faq(conn, shop_id, faq_id) is None:
        return False
    cur = conn.execute(
        "UPDATE unanswered_questions SET resolved_faq_id = ? WHERE id = ? AND shop_id = ?",
        (faq_id, _id(item_id), shop_id))
    conn.commit()
    return cur.rowcount > 0


# ---- analytics ----
def record_chat_event(conn, shop_id):
    conn.execute("INSERT INTO chat_events (shop_id) VALUES (?)", (_sid(shop_id),))
    conn.commit()


def _since(days):
    from datetime import timedelta
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")


def count_chats_since(conn, shop_id, days=7):
    return conn.execute("SELECT COUNT(*) FROM chat_events WHERE shop_id = ? AND ts >= ?",
                        (_sid(shop_id), _since(days))).fetchone()[0]


def count_leads_since(conn, shop_id, days=7):
    return conn.execute("SELECT COUNT(*) FROM leads WHERE shop_id = ? AND created_at >= ?",
                        (_sid(shop_id), _since(days))).fetchone()[0]


def get_unanswered(conn, shop_id, item_id):
    return _get(conn, "unanswered_questions", _sid(shop_id), _id(item_id))


def replace_week_hours(conn, shop_id, week):
    """week: {weekday: (open, close) or None for closed}. Replaces all hours rows atomically."""
    _sid(shop_id)
    rows = []
    for day in range(7):
        span = week.get(day)
        rows.append(dict(weekday=day, open_time=span[0] if span else None,
                         close_time=span[1] if span else None, closed=span is None))
    cleaned = [_check_hours(_clean_row("hours", r)) for r in rows]      # validate before deleting
    conn.execute("DELETE FROM hours WHERE shop_id = ?", (shop_id,))
    for r in cleaned:
        conn.execute("INSERT INTO hours (shop_id, weekday, open_time, close_time, closed) "
                     "VALUES (?,?,?,?,?)", (shop_id, r["weekday"], r["open_time"], r["close_time"], r["closed"]))
    conn.commit()
