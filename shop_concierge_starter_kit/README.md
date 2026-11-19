# Local Shop Concierge

A small multi-tenant web app for local shops (salons, tutors, repair shops, clinics). A shop owner enters services, prices, hours and FAQs once and gets a public page, an embeddable chat widget, lead capture with email alerts, and a report of the questions customers asked that the chat could not answer.

Live demo: `https://shopconcierge.online` (live once the T10 deployment is done). Demo shop: `https://shopconcierge.online/s/demo-salon`.

## The problem

A shop owner is busy with customers and cannot answer "how much is X?", "are you open on Sunday?" or "do you do Y?" on the phone all day. Customers who do not get a quick answer go to another shop. Generic chatbots make it worse by inventing prices and hours.

## Who benefits

- **The shop owner** (not technical): fills in simple forms once, or pastes a price list and approves what the app understood. Sees every question that could not be answered and turns it into an FAQ with one click.
- **The shop's customer** (on a phone): gets a correct answer from the shop's own data in about a second, or an honest "I don't know" and a way to leave contact details.

"Good" means a correct answer from the shop's own data, or an honest "I don't know". Never an invented price, hour or service.

## How it works

```
 Customer phone / website visitor            Shop owner (apex domain only)
        |                                              |
        |  /s/{slug}, slug.shopconcierge.online, widget.js       |  register, verify email, log in
        v                                              v
 +--------------------------- Caddy (HTTPS, on-demand certificates) ----------------------------+
 |  asks the app "/internal/tls-ask" before issuing a certificate for a shop subdomain          |
 +------------------------------------------+---------------------------------------------------+
                                            |
                                  +---------v----------+      +---------------------------+
                                  |  FastAPI app       |----->|  SQLite (app_data volume) |
                                  |  (1 uvicorn worker)|      +-------------+-------------+
                                  +----+----------+----+                    |
                    keyword answers    |          |  only when allowed      |  nightly
                    (always first)     |          v                         v
                                       |   Claude API (optional)     backup container -> backups volume
                                       |   - fallback answers WITH tools
                                       |   - onboarding import
                                       v
                              Microsoft 365 mailbox (SMTP) -> lead alerts, contact form, verification
```

Chat flow: the keyword engine answers from the shop's services, prices, hours and FAQs. If it is not confident and AI is on and the limits allow, Claude answers by calling read-only tools (`get_services`, `get_hours`, `search_faqs`, `propose_lead`) that read the database for that shop. If it still cannot answer, the question is logged for the owner and the customer is offered a lead form. A lead is saved, and the owner emailed, only after the customer ticks the consent box.

## Features

- Owner dashboard: services, hours, FAQs, leads, shop details, analytics card (chats and leads this week, top unanswered questions with "Suggest FAQ" drafts the owner must approve), import from pasted text.
- Public page with services, hours, QR code and WhatsApp button; `slug.shopconcierge.online` serves the same page; embeddable chat via `<script src="https://shopconcierge.online/widget.js?shop=your-slug" defer></script>`.
- Platform contact form with honeypot and rate limit.
- Works fully with `AI_ENABLED=false`.

## Security

Argon2 password hashing; HttpOnly + Secure + SameSite host-only cookies; CSRF tokens on every browser form; rate limits (login, register, chat, leads, contact, AI, import); strict input validation; output escaping and a strict CSP; security headers (HSTS, nosniff, frame protection); every query scoped by `shop_id` (data functions require it, and AI tools get it from the server, never from the model); no secrets in git (scanner included); the AI can only propose, a person confirms. Details and accepted risks: [SECURITY.md](SECURITY.md).

## How Claude and GoDaddy are used

**Claude** (model from `CLAUDE_MODEL`, key from `ANTHROPIC_API_KEY`) is used in exactly two places, and both are optional:
1. **Grounded fallback answers** when the keyword engine is not confident. Claude may only use facts returned by tools that read the shop's data; replies must be strict JSON that cites real records; a question that mentions something not in the shop's data always gets "I don't know". Capped per IP, per shop and per day (`AI_DAILY_CAP`).
2. **Onboarding import**: the owner pastes a price list or website text, Claude proposes services, hours and FAQs as JSON, and nothing is saved until the owner reviews and confirms.

Claude never sends email, edits shop data or writes to the database by itself. If the API fails for any reason (rate limit, billing, timeout), customers silently get keyword answers plus lead capture, and the app pauses AI calls for 5 minutes.

**GoDaddy** provides the domain (and DNS, with a wildcard record so shop subdomains work), the Ubuntu VPS that runs the Docker stack, and the domain registration. Email is a **Microsoft 365 Email Essentials** mailbox (bought through GoDaddy) used for sending: `smtp.office365.com`, port 587 (STARTTLS), user = the full mailbox address, e.g. `info@shopconcierge.online`. Authenticated SMTP must be enabled for that mailbox in the Microsoft 365 admin center, and Microsoft is phasing out password sign-in for SMTP, so if login fails with correct settings see OPERATIONS.md.

### Switching AI off

Set `AI_ENABLED=false` in `.env` and recreate the app container (`docker compose up -d --force-recreate app`). Every Claude call stops immediately: no client is created. Chat, the dashboard and email keep working; the import page shows "enter your details by hand".

## Setup (local development)

Requirements: Python 3.12+ (developed on 3.14).

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
cp .env.example .env            # then edit: set SECRET_KEY to a random 32+ character value
```

Run locally (AI off, emails printed to the console):

```bash
export SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(24))')"
export BASE_DOMAIN=localhost BASE_URL=http://localhost:8000 DATABASE_PATH=data/dev.db DEV_LOG_EMAILS=true
.venv/bin/python scripts/seed.py --owner-email you@example.com --owner-password 'a-long-dev-password'
.venv/bin/uvicorn app.main:create_app --factory --workers 1 --port 8000
```

Open http://localhost:8000 (landing page), http://localhost:8000/s/demo-salon (public page), http://localhost:8000/login (owner log in with the account above). Shop subdomains work locally too: http://demo-salon.localhost:8000 in Chrome or Firefox.

Tests and evals:

```bash
.venv/bin/python -m pytest -q                 # unit and integration tests (no network, no real API)
.venv/bin/python eval/run_evals.py            # saved real questions through the keyword engine
.venv/bin/python eval/run_evals.py --ai       # same cases with the AI fallback (needs AI_ENABLED=true and a key; makes live calls)
.venv/bin/python scripts/scan_secrets.py      # secrets scan of files and git history
```

## Environment variables

Set in `.env` (never committed; `.env.example` lists them all). Compose reads `.env` by default; to use another file (for example a throwaway one for testing) set `ENV_FILE`, e.g. `ENV_FILE=/tmp/test.env docker compose --env-file /tmp/test.env config`.

| Variable | Meaning | Default |
|---|---|---|
| `SECRET_KEY` | Signs CSRF tokens. 32+ random characters; the app refuses to start without it. | none |
| `BASE_DOMAIN` | Apex domain, e.g. `shopconcierge.online`. Owner pages only work here (and `www`). | `example.com` |
| `BASE_URL` | Public URL used in emails and the QR code. | `https://BASE_DOMAIN` |
| `ACME_EMAIL` | Contact address for Caddy / Let's Encrypt (required by Docker Compose). | none |
| `DATABASE_PATH` | SQLite file. Docker sets `/data/shop_concierge.db`. | `data/shop_concierge.db` |
| `TRUSTED_PROXIES` | Networks allowed to set `X-Forwarded-For` and call the TLS ask endpoint. Docker sets the Caddy network. | empty (nothing trusted) |
| `SMTP_HOST` / `SMTP_PORT` | Microsoft 365: `smtp.office365.com`, `587` (STARTTLS). The built-in defaults are `smtpout.secureserver.net` / `465`, so always set both. | `smtpout.secureserver.net` / `465` |
| `SMTP_USER` / `SMTP_PASSWORD` | Full mailbox address and its password. Empty password = emails are not sent. | empty |
| `MAIL_FROM` | Sender address (must be the same as `SMTP_USER` for Microsoft 365). | `SMTP_USER` |
| `CONTACT_RECIPIENT` | Where the platform contact form is sent. | empty |
| `AI_ENABLED` | Kill switch for every Claude call. | `false` |
| `ANTHROPIC_API_KEY` | Claude key (server gets its own key with a low spend limit). | empty |
| `CLAUDE_MODEL` | Model name. | `claude-haiku-5-5` |
| `AI_DAILY_CAP` | Platform-wide AI calls per day. | `200` |
| `AI_SHOP_DAILY_CAP` / `AI_IP_HOURLY` | AI calls per shop per day / per IP per hour. | `30` / `10` |
| `AI_COOLDOWN_SECONDS` | Pause after any AI API error. | `300` |
| `SESSION_DAYS` / `VERIFY_HOURS` | Login session and email-link lifetime. | `7` / `48` |
| `RATE_LIMITS_ENABLED` | Leave `true` (tests turn it off). | `true` |
| `DEV_LOG_EMAILS` | Local only: print outgoing emails to the console. Never in production. | `false` |

## Deploying

The stack is `docker compose up -d --build` (app, Caddy, nightly backup) on an Ubuntu VPS. Prerequisites and the by-hand steps (domain, DNS, mailbox, `.env`) are in the T10 checklist in [TASKS.md](TASKS.md); helper scripts are in `scripts/` (`server_bootstrap.sh`, `deploy.sh`, `check_live.sh`, `send_test_email.py`, `seed.py`, `backup_db.py`). Day-to-day running: [OPERATIONS.md](OPERATIONS.md). Presenting it: [DEMO.md](DEMO.md).

## Requirements and evidence

Each requirement, where it is met in this repo, and how to check it. Items in `[brackets]` are screenshots or outputs the owner adds; nothing in brackets has been captured yet.

| Requirement | Where it is met | How to check / evidence |
|---|---|---|
| Live app in Docker on a GoDaddy VPS | `Dockerfile` (non-root, one worker), `docker-compose.yml` (app, Caddy, nightly backup), `scripts/server_bootstrap.sh`, `scripts/deploy.sh`. Deployed by hand to a GoDaddy Gen4 Linux VPS (Ubuntu) on 2026-11-18. | On the VPS: `cd /opt/shopconcierge && docker compose ps` (app and caddy `healthy`, backup `Up`). `[screenshot: docker compose ps on the VPS]` |
| Own domain with DNS pointing at the app | `shopconcierge.online`, registered at GoDaddy. DNS (GoDaddy): A record for `@` and for `*` (shop subdomains) to the VPS address; `www` is a CNAME to the apex. The Microsoft 365 mail records stay in the same zone. | `dig +short A shopconcierge.online`, `dig +short A demo-salon.shopconcierge.online`. `[screenshot: GoDaddy DNS records]` |
| HTTPS via Caddy and Let's Encrypt | `Caddyfile`: automatic certificates for the domain and `www`; on-demand certificates for shop subdomains, issued only if `/internal/tls-ask` confirms the shop exists; HSTS and other security headers. | `DOMAIN=shopconcierge.online ./scripts/check_live.sh` (HTTPS, redirect, HSTS, a shop subdomain). `[screenshot: padlock on https://shopconcierge.online]` |
| Email on the domain | A **Microsoft 365 Email Essentials** mailbox (bought through GoDaddy, 1-month term; not Titan), e.g. `shraddhawagh@shopconcierge.online`. Sent via `smtp.office365.com:587` (STARTTLS) by `app/mailer.py`. SPF, DKIM and DMARC are set up (see OPERATIONS.md, "Email deliverability"). | `docker compose exec app python scripts/send_test_email.py you@gmail.com`, then Gmail "Show original" (SPF, DKIM, DMARC PASS). Mailbox list: `gddy email list` `[paste output]`. `[screenshot: Gmail "Show original"]` |
| Contact form delivering to the mailbox | `GET/POST /contact` in `app/routers/contact.py`, linked from the landing page and the footer; sends to `CONTACT_RECIPIENT`, with a honeypot, CSRF and a rate limit; shows an error instead of success if sending fails. Tested with SMTP mocked in `tests/test_email.py`. | Send a message at `https://shopconcierge.online/contact`. `[screenshot: the message in the mailbox]` |
| No secrets in code or repo | Configuration only through environment variables (`app/config.py`, `.env.example` lists them, the real `.env` exists only on the server). `.env`, databases, backups and keys are in `.gitignore` and `.dockerignore`; `scripts/scan_secrets.py` scans files and git history; `SECURITY.md` has the review. | `python scripts/scan_secrets.py` (exit code 0 means nothing found); `git check-ignore .env`. |

Tests and evals: `python -m pytest -q` and `python eval/run_evals.py` (with `AI_ENABLED=false`) both run without network access or real email.

## Project layout

```
app/            FastAPI app: main.py, repo.py (shop-scoped data), global_lookups.py (the only unscoped
                functions), answer.py (keyword engine), ai/ (chat fallback, import), routers/, templates/, static/
eval/           cases.json (saved questions) and run_evals.py
scripts/        seed, backup/restore, scan_secrets, send_test_email, deploy helpers
tests/          pytest suite
PLAN.md  DECISIONS.md  SECURITY.md  OPERATIONS.md  DEMO.md
```
