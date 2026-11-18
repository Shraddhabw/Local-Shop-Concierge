# PLAN: Local Shop Concierge

Stack: FastAPI + SQLite (WAL) + Jinja + plain CSS/JS, Caddy, Docker Compose. Config via env only. Works fully with AI_ENABLED=false.

## File structure
```
app/
  main.py          app factory, routers, middleware (security headers, host routing)
  config.py        env settings (no defaults for secrets)
  db.py            sqlite connection, schema init, migrations
  repo.py          data layer: every function REQUIRES shop_id
  global_lookups.py  the ONLY functions without shop_id: login by email, slug->shop, tls-ask check (own tests)
  answer.py        keyword engine: answer(shop_id, message) -> {answer, found, source_ids}
  auth.py          argon2, sessions, CSRF, email verify, rate limits
  ratelimit.py     in-memory + db-backed limiter
  mailer.py        SMTP (Microsoft 365), background send, retry
  ai/              chat_ai.py (tools, JSON schema, cooldown, caps), importer.py
  routers/         public.py, owner.py, chat.py, auth_routes.py, contact.py, health.py
  templates/ static/   Jinja, widget.js, css
eval/cases.json run_evals.py     scripts/ (seed, backup, send_test_email, deploy)
tests/            Dockerfile  docker-compose.yml  Caddyfile  .env.example
```

## SQLite schema (every tenant table has shop_id, indexed)
- shops(id, slug UNIQUE, name, address, phone, whatsapp, currency DEFAULT 'INR', created_at)
- users(id, shop_id, email UNIQUE, pw_hash, verified, verify_token_hash, created_at)
- services(id, shop_id, name, price INTEGER NULL  -- whole currency units, e.g. 300 (never cents), duration_min NULL, description, keywords)
- hours(id, shop_id, weekday 0-6, open_time, close_time, closed)
- faqs(id, shop_id, question, answer, keywords)
- leads(id, shop_id, name, contact, message, confirmed_at, created_at)  (only customer-confirmed leads are saved)
- unanswered_questions(id, shop_id, question, count, last_seen, resolved_faq_id NULL)
- ai_usage(id, shop_id, day, input_tokens, output_tokens, calls, errors)
- Also: chat_events(shop_id, ts) for analytics; sessions(id, user_id, expires).

## Request flows
- Customer chat: POST /api/chat {shop slug, message<=300 chars} -> shop_id resolved from slug -> answer() keywords -> if confident return; else if AI enabled + caps + no cooldown -> Claude with tools (shop_id bound in code) -> schema-validated JSON (1 retry, then fallback) -> if not found, log unanswered question + offer lead form -> customer confirms -> lead saved -> email alert queued.
- Owner: register -> verify email -> login (argon2, cookie, CSRF) -> dashboard CRUD, always filtered by session user's shop_id. "Suggest FAQ" shows a draft; owner approves to save.
- Import (T7): paste text -> Claude JSON -> validated -> editable preview -> owner confirms -> save.

## Subdomain routing
Caddy on-demand TLS asks `/internal/tls-ask?domain=` (approves only BASE_DOMAIN, www, existing slugs). App middleware: Host `slug.BASE_DOMAIN` -> shop slug; otherwise `/s/{slug}` path. Reserved slugs blocked: www, admin, api, mail, app, static (plus ftp, smtp, etc.). Unknown slug -> 404.

## Top-8 threat model
1. Cross-tenant access via guessed IDs -> shop_id required in all data functions; tests for read/edit/delete.
2. Prompt injection (chat or imported text) -> tools only read; shop_id from context; AI proposes only; JSON schema; text treated as data.
3. AI cost abuse -> per-IP limit, per-shop and global daily caps, 300-char input, max_tokens 300, kill switch, error cooldown.
4. Credential attacks -> argon2, login rate limit, generic errors, verified email required.
5. XSS -> Jinja autoescape, textContent in widget, CSP.
6. CSRF / session theft -> CSRF tokens, HttpOnly+Secure+SameSite cookies.
7. Email abuse / header injection -> strip CR/LF, honeypot, rate limit, alerts only after customer confirmation.
8. Secrets and subdomain/TLS abuse -> env only, git-ignored, no secrets in logs; ask endpoint stops cert issuance for random hosts; SQL injection via parameterised queries only.

## Adjustments (owner-approved)
1. **Prices:** stored as whole integer currency units; `shops.currency` holds the code. Answers show "300", not "30000".
2. **Client IP:** per-IP limits use the real client IP. X-Forwarded-For is trusted only when the direct peer is the Caddy container (configured trusted proxy); otherwise the socket IP is used.
3. **Single worker:** run one uvicorn worker so in-memory limiters and the AI cooldown are consistent.
4. **Cookies/hosts:** session cookies are host-only (no Domain attribute). Owner dashboard, login and register are served on the apex domain only; shop subdomains serve public page and chat only (dashboard paths return 404 there).
5. **tls-ask:** `/internal/tls-ask` is reachable only from the Caddy container (peer check plus Caddy never proxies it publicly; Caddyfile blocks `/internal/*` from the outside).
6. **No-shop_id functions:** isolated in `app/global_lookups.py` with dedicated tests; all other data code requires shop_id.
