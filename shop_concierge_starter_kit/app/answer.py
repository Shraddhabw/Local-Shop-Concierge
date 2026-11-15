"""Keyword answer engine (no AI). Read-only: answers only from the shop's own data.

answer(shop_id, message) -> {answer, found, source_ids, sources, confidence, intent, needs_human}
It never invents facts. If it is not confident it says so and asks for contact details.
"""
import math
import re
from datetime import datetime, timedelta

from . import db, repo

MAX_MESSAGE_CHARS = 300
CURRENCY_SYMBOLS = {"INR": "₹", "USD": "$", "GBP": "£", "EUR": "€"}
NOT_FOUND_TEXT = (
    "Sorry, I don't have that information and I don't want to guess. "
    "Leave your name and a phone or email and the shop will get back to you."
)

_SYN = {}
for _canon, _words in {
    "price": "price prices pricing cost costs fee fees rate rates charge charges amount kitna kitne kitni",
    "pay": "pay payment payments paying",
    "month": "monthly month months",
    "week": "weekly",
    "repair": "repair repairs repairing fix fixes fixing fixed mend",
    "warranty": "warranty warranties guarantee guarantees",
    "demo": "demo demos trial",
    "phone": "phone phones mobile mobiles smartphone handset",
    "open": "open opens opening timing timings hours schedule close closes closing closed kab",
    "where": "where address addresses location located locate direction directions kahan map",
    "service": "service services menu list",
    "long": "long duration",
}.items():
    for _w in _words.split():
        _SYN[_w] = _canon

_DAYS = {"monday": 0, "mon": 0, "tuesday": 1, "tue": 1, "tues": 1, "wednesday": 2, "wed": 2,
         "thursday": 3, "thu": 3, "thur": 3, "thurs": 3, "friday": 4, "fri": 4,
         "saturday": 5, "sat": 5, "sunday": 6, "sun": 6}
_DAY_GROUPS = {"weekday": [0, 1, 2, 3, 4], "weekend": [5, 6]}
_DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

_STOP = set("""a an the is are am was were be been do does did you your yours u ur i me my we us our it
its this that these those of for to in on at by with and or but if so as from about into there here can
could would should will shall may might have has had hai hain ka ki ke ko se kya aap what which who whom
whose how why please pls any some get got give tell know want need like also just only very too really
many offer provide available teach sell make cater take takes took see let kindly okay ok yes no
""".split())
_FILLER = set("""fell fall fallen dropped drop broke broken stopped issue problem wont not working work
today tomorrow tonight now morning afternoon evening night anyone someone everyone thing things stuff kind
type types lot bit new old good best cheap cheapest nearby near around shop store place business salon
clinic parlour parlor pay month week
""".split())
_GREETING = set("hi hello hey namaste thanks thank bye hii helo good morning evening".split())

_STEM_KEEP = ("ss", "us", "is")


def _stem(tok):
    if len(tok) > 5 and tok.endswith("ing"):
        return tok[:-3]
    if len(tok) > 4 and tok.endswith("ies"):
        return tok[:-3] + "y"
    if len(tok) > 3 and tok.endswith("s") and not tok.endswith(_STEM_KEEP):
        return tok[:-1]
    return tok


def _tokens(text):
    t = (text or "").lower().replace("’", "'")
    t = re.sub(r"walk[\s-]*ins?\b", "walkin", t)
    t = re.sub(r"hair\s+cut", "haircut", t)
    t = re.sub(r"how\s+(much\s+time|many\s+(minutes|hours))", "how long", t)
    t = re.sub(r"(\w)'s\b", r"\1s", t).replace("'", "")
    return [_SYN.get(w) or _stem(w) for w in re.findall(r"[a-z0-9ऀ-ॿ]+", t)]


_STOP = {_SYN.get(w) or _stem(w) for w in _STOP}
_FILLER = {_SYN.get(w) or _stem(w) for w in _FILLER}
_GREETING = {_SYN.get(w) or _stem(w) for w in _GREETING}


def _result(answer, found, intent, sources=(), confidence=0.0):
    sources = [{"type": t, "id": i} for t, i in sources]
    return {"answer": answer, "found": found, "source_ids": [s["id"] for s in sources],
            "sources": sources, "confidence": round(confidence, 2) if found else 0.0,
            "intent": intent, "needs_human": not found}


def _not_found(intent="unknown"):
    return _result(NOT_FOUND_TEXT, False, intent)


def _money(shop, price):
    cur = shop["currency"]
    return f"{CURRENCY_SYMBOLS.get(cur, cur + ' ')}{price}"


def _clock(hhmm):
    h, m = int(hhmm[:2]), int(hhmm[3:])
    return f"{h % 12 or 12}:{m:02d} {'AM' if h < 12 else 'PM'}"


def _day_text(rows):
    if not rows:
        return None
    if all(r["closed"] for r in rows):
        return "Closed"
    return " and ".join(f"{_clock(r['open_time'])} to {_clock(r['close_time'])}"
                        for r in rows if not r["closed"])


def _hours_answer(hours, days, label_day=None):
    by_day = {d: [r for r in hours if r["weekday"] == d] for d in range(7)}
    texts = {d: _day_text(by_day[d]) for d in days}
    known = [d for d in days if texts[d]]
    if not known:
        return None
    if len(days) == 1 or label_day is not None:
        d = known[0]
        name = _DAY_NAMES[d]
        who = f"{label_day} ({name})" if label_day else f"on {name}"
        return (f"We're closed {who}." if texts[d] == "Closed"
                else f"We're open {who} from {texts[d]}.")
    groups, start = [], known[0]
    for i, d in enumerate(known):
        last = i == len(known) - 1
        if last or texts[known[i + 1]] != texts[d] or known[i + 1] != d + 1:
            groups.append((start, d, texts[d]))
            if not last:
                start = known[i + 1]
    parts = []
    for a, b, t in groups:
        span = _SHORT[a] if a == b else f"{_SHORT[a]}-{_SHORT[b]}"
        parts.append(f"{span}: {t}")
    return "Our hours: " + "; ".join(parts) + "."


def _build_docs(services, faqs):
    docs = []
    for kind, rows, fields in (("service", services, ("name", "keywords", "description")),
                               ("faq", faqs, ("question", "keywords", "answer"))):
        for row in rows:
            weights = {}
            for field, w in zip(fields, (3, 2, 1)):
                for tok in _tokens(row[field]):
                    weights[tok] = max(weights.get(tok, 0), w)
            docs.append({"kind": kind, "row": row, "w": weights})
    return docs


def _rank(docs, content, kinds, idf, kind_bonus=None):
    rare = {t for t, v in idf.items() if v >= 1 + math.log(max(2, len(docs)) / 2)}
    ranked = []
    for d in docs:
        if d["kind"] not in kinds:
            continue
        matched = [t for t in content if t in d["w"]]
        if not matched:
            continue
        strong = (any(d["w"][t] >= 2 or t in rare for t in matched) or len(matched) >= 2)
        cov = len(matched) / len(content)
        if strong and cov >= 0.5:
            score = sum(d["w"][t] * idf[t] for t in matched) * (kind_bonus or {}).get(d["kind"], 1)
            ranked.append((score, 1 if d["kind"] == "faq" else 0, cov, d))
    ranked.sort(key=lambda r: (r[0], r[1]), reverse=True)
    return ranked


def _top_group(ranked, limit=3):
    best = ranked[0][0]
    group = [r for r in ranked if r[0] >= 0.8 * best and r[3]["kind"] == ranked[0][3]["kind"]]
    return group[:limit if ranked[0][3]["kind"] == "service" else 1]


def _service_line(shop, svc, mode):
    name = svc["name"]
    if mode == "duration":
        return f"{name} takes about {svc['duration_min']} minutes."
    if svc["price"] is None:
        price = "please contact the shop for the price"
    else:
        price = _money(shop, svc["price"])
    extra = f" ({svc['duration_min']} min)" if svc["duration_min"] else ""
    return f"{name}: {price}{extra}"


def _service_answer(shop, group, intent):
    svcs = [r[3]["row"] for r in group]
    sources = [("service", s["id"]) for s in svcs]
    cov = group[0][2]
    if intent == "price" and len(svcs) == 1 and svcs[0]["price"] is not None:
        text = f"{svcs[0]['name']} costs {_money(shop, svcs[0]['price'])}."
        if svcs[0]["duration_min"]:
            text += f" It takes about {svcs[0]['duration_min']} minutes."
    elif intent == "duration":
        text = " ".join(_service_line(shop, s, "duration") for s in svcs)
    else:
        text = "; ".join(_service_line(shop, s, "price") for s in svcs) + "."
        if len(svcs) == 1 and svcs[0]["description"]:
            text += f" {svcs[0]['description']}"
    return _result(text, True, intent, sources, cov)


def answer(shop_id, message, *, conn=None, now=None):
    repo._sid(shop_id)
    own = conn is None
    if own:
        conn = db.connect()
    try:
        return _answer(conn, shop_id, message, now or datetime.now())
    finally:
        if own:
            conn.close()


def _answer(conn, shop_id, message, now):
    shop = repo.get_shop(conn, shop_id)
    message = str(message or "").strip()[:MAX_MESSAGE_CHARS]
    if shop is None or not message:
        return _not_found()
    tokens = _tokens(message)
    if tokens and all(t in _GREETING for t in tokens):
        return _result(f"Hi! I can help with {shop['name']}'s services, prices, hours and "
                       "location. What would you like to know?", True, "greeting", (), 1.0)

    # intents and day filters
    tset = set(tokens)
    if "long" in tset:
        intent = "duration"
    elif tset & {"price", "much"}:
        intent = "price"
    elif "open" in tset or "time" in tset:
        intent = "hours"
    elif "where" in tset:
        intent = "location"
    elif tset & {"call", "contact", "number", "whatsapp"}:
        intent = "contact"
    else:
        intent = "general"
    days, label_day = [], None
    for t in tokens:
        if t in _DAYS:
            days.append(_DAYS[t])
        elif t in _DAY_GROUPS:
            days.extend(_DAY_GROUPS[t])
        elif t in ("today", "now"):
            days, label_day = [now.weekday()], "today"
        elif t == "tomorrow":
            days, label_day = [(now + timedelta(days=1)).weekday()], "tomorrow"
    days = sorted(set(days))

    services, faqs = repo.list_services(conn, shop_id), repo.list_faqs(conn, shop_id)
    hours = repo.list_hours(conn, shop_id)
    docs = _build_docs(services, faqs)
    vocab = {t for d in docs for t in d["w"]}
    ignore = _STOP | _FILLER | {t for t in _tokens(shop["name"])}
    control = {"price", "much", "open", "time", "where", "long", "service", "call", "contact",
               "number", "whatsapp"} | set(_DAYS) | set(_DAY_GROUPS)
    content = [t for t in dict.fromkeys(tokens)
               if t not in ignore and t not in control]
    if any(t not in vocab for t in content):
        return _not_found(intent)      # a word we know nothing about: never guess

    n = max(len(docs), 1)
    df = {}
    for d in docs:
        for t in d["w"]:
            df[t] = df.get(t, 0) + 1
    idf = {t: 1 + math.log(n / df[t]) for t in df}

    def ranked(kinds, bonus=None):
        return _rank(docs, content, kinds, idf, bonus) if content else []

    def faq_answer(r):
        row = r[0][3]["row"]
        return _result(row["answer"], True, intent, [("faq", row["id"])], r[0][2])

    if intent in ("price", "duration"):
        r = ranked({"service"})
        if intent == "duration":
            r = [x for x in r if x[3]["row"]["duration_min"]]
        if r:
            return _service_answer(shop, _top_group(r), intent)
        r = ranked({"faq"})
        if r:
            return faq_answer(r)
        if not content and intent == "price" and services:
            lines = [_service_line(shop, s, "price") for s in services[:10]]
            return _result("Here are our services: " + "; ".join(lines) + ".", True,
                           "service_list", [("service", s["id"]) for s in services[:10]], 1.0)
        return _not_found(intent)

    if intent in ("hours", "location", "contact"):
        if content:
            r = ranked({"faq"})
            return faq_answer(r) if r else _not_found(intent)
        if intent == "hours":
            text = _hours_answer(hours, days or list(range(7)), label_day if days else None)
            return _result(text, True, intent, (), 1.0) if text else _not_found(intent)
        if intent == "location" and shop["address"]:
            return _result(f"You can find us at {shop['address']}.", True, intent, (), 1.0)
        if intent == "contact" and (shop["phone"] or shop["whatsapp"]):
            number = shop["phone"] or shop["whatsapp"]
            return _result(f"You can reach us on {number}.", True, intent, (), 1.0)
        return _not_found(intent)

    if "service" in tset and not content and services:
        lines = [_service_line(shop, s, "price") for s in services[:10]]
        return _result("Here are our services: " + "; ".join(lines) + ".", True,
                       "service_list", [("service", s["id"]) for s in services[:10]], 1.0)
    r = ranked({"service", "faq"})
    if not r:
        return _not_found(intent)
    if r[0][3]["kind"] == "faq":
        return faq_answer(r)
    return _service_answer(shop, _top_group(r), "general")
