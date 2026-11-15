# DECISIONS (assumptions made where the spec was ambiguous)

- T1: data functions take `(conn, shop_id, ...)`; `answer(shop_id, message, *, conn=None, now=None)` opens its own connection if none is given. DB path from `DATABASE_PATH` (default `data/shop_concierge.db`, git-ignored via `*.db`).
- T1: `answer()` is read-only. Logging unanswered questions and saving leads is done by the caller (chat router), never by the answer engine or the AI.
- T1: `unanswered_questions` has an extra `norm` column (lower-cased question without punctuation) so repeats are counted; unique per (shop_id, norm).
- T1: hours use weekday 0=Monday, "HH:MM" 24h, no overnight ranges (open must be before close); several rows per day allowed for split shifts. Times are shown as 12-hour AM/PM. "today/tomorrow/now" use the server's local clock (assumption: server timezone = shop timezone).
- T1: honesty rule: if the question contains a meaningful word that appears nowhere in the shop's data (e.g. "tattoo", "physics"), the engine answers "I don't know" and offers to take details instead of guessing from partial matches.
- T1: a not-found reply deliberately contains no currency symbols or digits.
- T1: reserved slugs also include ftp, smtp, imap, pop, ns1, ns2, webmail, dashboard, login, register, internal, s, demo (the demo shops use `demo-*` names, which are allowed).
- Env: use .venv (python3 -m venv .venv; .venv/bin/pip install -r requirements-dev.txt); run tests with .venv/bin/python -m pytest.
- T3: CSRF uses a random `csrf` cookie plus a form field = HMAC(SECRET_KEY, cookie); works before and after login. Session ids are stored hashed (sha256) in `sessions`. Verification tokens are stored hashed, single use, 48h expiry.
- T3: registering with an email that already exists returns the same "check your email" page (no account enumeration) and sends nothing. There is no "resend link" yet; an unverified owner re-registers after the token expires is NOT supported, so a resend route should be added in T4/T5 if needed.
- T3: mailer.send_email is an in-memory outbox stub until T5 (no real email is sent).
- T3: requests whose Host is not BASE_DOMAIN, www.BASE_DOMAIN or a single-label subdomain get 404 (except /healthz). Owner paths (/register /login /logout /verify /dashboard) are 404 on shop subdomains.
- T3: SECRET_KEY must be 32+ chars and not start with "change-me", otherwise the app refuses to start.
