# SECURITY review (T9)

Scope: the whole repository, its git history, and the deployment files. Method: scripted scans (`scripts/scan_secrets.py`, `pip-audit`), a read-through of every route, query, template and log line, and regression tests (`tests/test_security.py` and others). Re-run any time: `python scripts/scan_secrets.py`, `.venv/bin/pip-audit -r requirements.txt`, `pytest`, `python eval/run_evals.py`.

## Findings that were fixed

| # | Severity | Finding | Fix | Guarded by |
|---|----------|---------|-----|-----------|
| F1 | Medium | `/api/lead` was limited per IP only, so many IPs could flood one shop owner's inbox with alert emails. | Added a per-shop limit (30 leads/hour); the per-IP limit (5/hour) stays. | `test_one_shop_cannot_be_flooded_with_leads_from_many_ips` |
| F2 | Low | `/verify?token=...` puts a one-time token in the URL, and uvicorn's access log would write it to container logs. | Container runs with `--no-access-log`; Caddy does not log requests unless configured. | `test_container_does_not_log_request_urls...`, `test_tokens_never_reach_logs` |
| F3 | Low | No request body limit: a huge POST could use memory. | Caddy `request_body max_size 256KB` (largest legitimate form is the 8000-character import). | `test_container_does_not_log_request_urls_and_caddy_limits_bodies` |
| F4 | Low | Expired sessions were never deleted from the database. | Expired rows are purged whenever a session is created. | `test_expired_sessions_are_purged` |
| F5 | Info | Nothing stopped a future route from forgetting CSRF, login or shop_id scoping. | Tests walk every router: every browser POST rejects a missing/forged CSRF token, every `/dashboard` route redirects anonymous users, every data function takes `(conn, shop_id)`, every tenant SQL statement mentions `shop_id`. | `test_every_post_route_requires_csrf`, `test_every_dashboard_route_requires_login`, `test_every_repo_function_requires_shop_id`, `test_every_tenant_sql_statement_mentions_shop_id` |
| F6 | Medium (found during T7) | The email-script test loaded the real `.env` into the test process, so a later test made one real Claude call. | Autouse fixture strips `ANTHROPIC_API_KEY` and forces `AI_ENABLED=false` in every test; the script test no longer reads `.env`. | `test_tests_are_isolated_from_real_ai_env` |

## Checked, no problem found

- **Secrets in files and history:** `scan_secrets.py` finds nothing across all commits (API-key, private-key, cloud-token patterns, secret-looking assignments, tracked `.env`/`*.db`/`*.pem`). `.env`, databases, backups and keys are git-ignored and also excluded from the Docker image (`.dockerignore`). The only `sk-ant-` string in history is the obvious fake `sk-ant-TEST-SECRET-KEY` in a test.
- **SQL injection:** every value is a bound parameter. Two statements build SQL with f-strings; both interpolate only fixed table names or column names taken from a whitelist (never request data).
- **XSS:** Jinja autoescape is on; the single `| safe` is the QR code, an SVG that segno builds from a URL (it encodes data as paths, not text). The widget and chat use `textContent`, never `innerHTML`. CSP forbids inline scripts and styles. Tests cover a hostile shop name and hostile import output.
- **CSRF:** see F5. Public JSON endpoints use no cookies; they reject non-JSON content types (cross-site form posts cannot reach them). Session and CSRF cookies are HttpOnly, Secure, SameSite=Lax and host-only.
- **Multi-tenant scoping:** cross-shop read/edit/delete is tested at the data layer and over HTTP; the shop for the AI tools and for the dashboard comes from the server (session or slug), never from form or model output.
- **CORS:** no CORS headers are sent anywhere; the widget is an iframe of our own page, so none are needed. Only `/embed/{slug}` may be framed.
- **Secrets in logs:** the mailer and AI code log only error class names and codes; no keys, passwords, addresses, message bodies or tokens (tests check this, including a password inside an exception message).
- **Dependencies:** `pip-audit` reported no known vulnerabilities on 2026-11-15.
- **Other:** unknown `Host` headers get 404; links in emails use `BASE_URL`, not the request's Host; redirects go only to fixed paths; `/internal/tls-ask` is restricted to the Caddy network, fails closed and is blocked at the proxy.

## Accepted risks and limits (decisions for the owner)

| # | Risk | Why accepted / what to do |
|---|------|---------------------------|
| R1 | Login lock-out: 5 failed attempts per email per 15 minutes means someone can keep a victim's login blocked. | Protects against password guessing; limit is short. Tell owners to wait 15 minutes. |
| R2 | Registration can send one confirmation email to any address (5 per IP per hour); registering an existing email is not distinguishable by response, only by timing. | Low impact; limits in place. |
| R3 | Rate limits, AI cooldown and counters are in memory: they reset on restart and need the single uvicorn worker. | Documented rule; AI daily caps are stored in the database so they survive restarts. |
| R4 | The confirmation link is a GET with a token in the URL (single use, 48 h, `Referrer-Policy` set). | Normal for email verification. |
| R5 | Backups live on the same VPS volume. | Copy them off the server regularly (OPERATIONS.md, T11). |
| R6 | `/api/chat` and `/api/lead` are public by design. | Per-IP, per-shop and AI caps; consent required for leads. |
| R7 | The model could still phrase something misleadingly using the shop's own data. | Mitigations: read-only tools, citation and number checks, unknown-word guard, no AI writes. Owner reviews unanswered questions. |
| R8 | `docker compose config`/build and Caddy's `header_down ?` defaults were not run on this machine (no Docker). | Run `docker compose config`, `docker compose build`, then `scripts/check_live.sh` after deploy. |
| R9 | `DEV_LOG_EMAILS=true` prints verification links to the console. | Local development only; the compose file never sets it. |
| R10 | The developer's local `.env` holds a real API key. | Keep it out of chat and git; the server uses a separate key with its own spend limit; rotate the local key if the laptop is shared. |
| R11 | No password reset, 2FA or account deletion yet. | Out of scope for this project; add before real customers. |
