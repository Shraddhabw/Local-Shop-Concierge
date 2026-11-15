# DECISIONS (assumptions made where the spec was ambiguous)

- T1: data functions take `(conn, shop_id, ...)`; `answer(shop_id, message, *, conn=None, now=None)` opens its own connection if none is given. DB path from `DATABASE_PATH` (default `data/shop_concierge.db`, git-ignored via `*.db`).
- T1: `answer()` is read-only. Logging unanswered questions and saving leads is done by the caller (chat router), never by the answer engine or the AI.
- T1: `unanswered_questions` has an extra `norm` column (lower-cased question without punctuation) so repeats are counted; unique per (shop_id, norm).
- T1: hours use weekday 0=Monday, "HH:MM" 24h, no overnight ranges (open must be before close); several rows per day allowed for split shifts. Times are shown as 12-hour AM/PM. "today/tomorrow/now" use the server's local clock (assumption: server timezone = shop timezone).
- T1: honesty rule: if the question contains a meaningful word that appears nowhere in the shop's data (e.g. "tattoo", "physics"), the engine answers "I don't know" and offers to take details instead of guessing from partial matches.
- T1: a not-found reply deliberately contains no currency symbols or digits.
- T1: reserved slugs also include ftp, smtp, imap, pop, ns1, ns2, webmail, dashboard, login, register, internal, s, demo (the demo shops use `demo-*` names, which are allowed).
- Env: python3 here has no pip/venv; pytest could not be installed without sudo (see handoff note).
