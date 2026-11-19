# Local Shop Concierge

**An AI-assisted front desk for local shops, live in minutes.** A small multi-tenant web app for salons, tutors, repair shops and clinics. A shop owner enters services, prices, hours and FAQs once (or pastes an existing price list) and gets a public page, an embeddable chat widget, lead capture with email alerts, and a report of the questions customers asked that the chat could not answer.

- **Live site:** https://shopconcierge.online
- **Demo shops:** [demo-salon](https://demo-salon.shopconcierge.online), [demo-tutor](https://demo-tutor.shopconcierge.online) and [demo-repair](https://demo-repair.shopconcierge.online) (the same pages are also at `https://shopconcierge.online/s/demo-salon`, `/s/demo-tutor` and `/s/demo-repair`)
- **Contact form:** https://shopconcierge.online/contact


The Claude features (import and fallback chat answers) are switched on for the live site during evaluation, with the limits described under "How Claude and GoDaddy are used". If they are ever off, the app still works with keyword answers and the import page asks for details by hand.

1. Open the demo salon and ask the chat: *"How much is a men's haircut?"* The answer comes from the shop's own data.
2. Ask something the shop does not offer: *"Do you do hair rebonding?"* The chat says it does not know and offers to take your details. It never invents a price.
3. Ask *"Do you do eyebrow threading?"*, fill in a made-up name and phone number, and tick the consent box. The owner gets an email alert and the lead appears in the dashboard.
4. Click **Create your shop**, register a shop, verify the email, and open **Import**. Paste a price list and review what Claude proposes. Nothing is saved until you confirm.
5. Open the **Home** tab of the dashboard to see the questions the chat could not answer, and turn one into an FAQ with **Suggest FAQ**.

A full timed walkthrough is in [DEMO.md](DEMO.md).

## The problem

A shop owner is busy with customers and cannot answer "how much is X?", "are you open on Sunday?" or "do you do Y?" on the phone all day. Customers who do not get a quick answer go to another shop. Generic chatbots make it worse by inventing prices and hours.

## Who benefits

- **The shop owner** (not technical): fills in simple forms once, or pastes a price list and approves what the app understood. Sees every question that could not be answered and turns it into an FAQ with one click. Gets an email only when a customer has agreed to share their details.
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

- **Owner dashboard:** services, hours, FAQs, leads, shop details, and an analytics card (chats and leads this week, top unanswered questions with "Suggest FAQ" drafts the owner must approve). Every save shows a confirmation banner, and forms clear after a successful add.
- **Import from pasted text:** the owner pastes a price list, bio or website text, Claude proposes services, hours and FAQs, and the owner edits and confirms before anything is saved.
- **Public page** with services, hours, QR code and WhatsApp button. `slug.shopconcierge.online` serves the same page.
- **Embeddable chat** for the owner's own website. The dashboard shows the complete snippet with a Copy button: `<script src="https://shopconcierge.online/widget.js?shop=your-slug" defer></script>`.
- **Platform contact form** with honeypot and rate limit.
- **Works fully with `AI_ENABLED=false`.** Claude adds value but is never a single point of failure.

## Security

Argon2 password hashing; HttpOnly + Secure + SameSite host-only cookies; CSRF tokens on every browser form; rate limits (login, register, chat, leads, contact, AI, import); strict input validation; output escaping and a strict CSP; security headers (HSTS, nosniff, frame protection); every query scoped by `shop_id` (data functions require it, and AI tools get it from the server, never from the model); no secrets in git (scanner included); the AI can only propose, a person confirms. Details and accepted risks: [SECURITY.md](SECURITY.md).

## How Claude and GoDaddy are used

### Claude

**Built with Claude Code.** The whole app was built from a written spec (`CLAUDE.md`, `TASKS.md`) with Claude Code working through the tasks in order. After every task it ran the test suite and the eval suite, and it stopped at defined checkpoints for a human decision (the plan, the first live API call, and deployment). Design decisions and assumptions are recorded in [DECISIONS.md](DECISIONS.md).

**Claude at runtime** (model from `CLAUDE_MODEL`, key from `ANTHROPIC_API_KEY`) is used in exactly two places, and both are optional:

1. **Grounded fallback answers** when the keyword engine is not confident.
   - Claude may only use facts returned by tools that read the shop's data.
   - Replies must be strict JSON (`answer`, `found`, `source_ids`, `needs_human`), validated against a schema, with one retry and a safe fallback.
   - Answers must cite records the tools actually returned, and numbers in an answer must appear in the tool output.
   - A question that mentions something not in the shop's data always gets "I don't know", whatever the model said.
   - Capped per IP, per shop and per day (`AI_DAILY_CAP`).
2. **Onboarding import:** the owner pastes a price list or website text, Claude proposes services, hours and FAQs as JSON, and nothing is saved until the owner reviews and confirms. Pasted text is treated as data, never as instructions, and tests include prompt-injection attempts.

Claude never sends email, edits shop data or writes to the database by itself. If the API fails for any reason (rate limit, billing, timeout), customers silently get keyword answers plus lead capture, and the app pauses AI calls for 5 minutes.

**Evaluation:** `eval/cases.json` holds 22 saved questions across three demo shops, including unanswerable questions, a mixed-language question and a prompt-injection attempt. They pass 22/22 with AI off and 22/22 against the live API. Two cases failed on the first live run: one real bug (the model generalised "phone repair" to "laptop repair", fixed with a prompt rule and a deterministic unknown-word guard) and one test that was too strict (changed and documented in DECISIONS.md).

**Tested live with AI enabled.** On the deployed site, with `AI_ENABLED=true` and a separate server API key, the onboarding import and the fallback chat answers both work as designed: the import proposes services, hours and FAQs for review, the chat answers from the shop's data, and unanswerable questions get an honest "I don't know" plus lead capture. The live eval (`eval/run_evals.py --ai`) passes 22/22.

**Cost and abuse limits on the live server.** Claude is limited at several layers so a visitor, a bug or an outage cannot run up a bill:

| Limit | Setting | What it does |
|---|---|---|
| Kill switch | `AI_ENABLED` | `false` stops every Claude call immediately after a restart |
| Platform daily cap | `AI_DAILY_CAP` (live value: `[fill in]`) | Total AI calls per day across all shops; stored in the database, so it survives restarts |
| Per-shop daily cap | `AI_SHOP_DAILY_CAP` (live value: `[fill in]`) | One shop cannot use up the whole budget |
| Per-visitor hourly cap | `AI_IP_HOURLY` (live value: `[fill in]`) | Limits calls per IP address, counted only when a call would really happen |
| Input and output size | 300 characters in, `max_tokens` 300 out | Keeps each call small |
| Error cooldown | `AI_COOLDOWN_SECONDS` (`300`) | After any API error, AI pauses for 5 minutes and customers get keyword answers |
| Spend limit | Set in the Anthropic Console on the server's own API key | A hard stop outside the app; the key is separate from the developer key |
| Small model | `claude-haiku-5-5` | Each fallback answer or import costs a fraction of a cent |

### GoDaddy

- **VPS:** a GoDaddy Linux VPS (Ubuntu) runs the Docker Compose stack (app, Caddy, nightly backup).
- **Domain and DNS:** `shopconcierge.online`, with a wildcard DNS record so every shop gets its own subdomain, and automatic HTTPS from Let's Encrypt through Caddy. Certificates for shop subdomains are issued on demand, and only for shops that exist.
- **Email on the domain:** a **Microsoft 365 Email Essentials** mailbox bought through GoDaddy, e.g. `shraddhawagh@shopconcierge.online`. It receives the contact form and sends verification emails and lead alerts: `smtp.office365.com`, port 587 (STARTTLS), user = the full mailbox address. SPF, DKIM and DMARC are configured so mail lands in the inbox (see OPERATIONS.md, "Email deliverability"). Authenticated SMTP must be enabled for that mailbox in the Microsoft 365 admin center, and Microsoft is phasing out password sign-in for SMTP, so if login fails with correct settings see OPERATIONS.md.
- **`gddy` CLI:** used to search domain names and compare prices, and to inspect DNS. The mailbox itself was created in the GoDaddy dashboard (the organizers confirmed this is acceptable).

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
| `ANTHROPIC_API_KEY` | Claude key (the server gets its own key with a low spend limit). | empty |
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

Each requirement, where it is met in this repo, and how to check it. Items in `[brackets]` are screenshots or outputs the owner adds.

| Requirement | Where it is met | How to check / evidence |
|---|---|---|
| Live app in Docker on a GoDaddy VPS | `Dockerfile` (non-root, one worker), `docker-compose.yml` (app, Caddy, nightly backup), `scripts/server_bootstrap.sh`, `scripts/deploy.sh`. Deployed to a GoDaddy Linux VPS (Ubuntu) on 2026-11-18 and updated since with `deploy.sh`. | On the VPS: `cd /opt/shopconcierge && docker compose ps` (app and caddy `healthy`, backup `Up`). `[screenshot: docker compose ps on the VPS]` |
| Own domain with DNS pointing at the app | `shopconcierge.online`, registered at GoDaddy. DNS (GoDaddy): A record for `@` and for `*` (shop subdomains) to the VPS address; `www` is a CNAME to the apex. The Microsoft 365 mail records stay in the same zone. | `dig +short A shopconcierge.online`, `dig +short A demo-salon.shopconcierge.online`. `[screenshot: GoDaddy DNS records]` |
| HTTPS via Caddy and Let's Encrypt | `Caddyfile`: automatic certificates for the domain and `www`; on-demand certificates for shop subdomains, issued only if `/internal/tls-ask` confirms the shop exists; HSTS and other security headers. | `DOMAIN=shopconcierge.online ./scripts/check_live.sh` (HTTPS, redirect, HSTS, a shop subdomain). `[screenshot: padlock on https://shopconcierge.online]` |
| Email on the domain | A **Microsoft 365 Email Essentials** mailbox (bought through GoDaddy on a 1-month term; not Titan), `shraddhawagh@shopconcierge.online`, created in the GoDaddy dashboard (the organizers confirmed this is acceptable; `gddy email list` returns no results for it). Receives mail from other accounts. Sent via `smtp.office365.com:587` (STARTTLS) by `app/mailer.py`. | Test email sent from the server to Gmail on 2026-11-19: delivered in 6 seconds with SPF, DKIM (`d=shopconcierge.online`) and DMARC all PASS. Re-run: `docker compose exec app python scripts/send_test_email.py you@gmail.com`, then Gmail "Show original". `[screenshot: Gmail "Show original"]` `[screenshot: a message from another account arriving in the mailbox]` |
| Contact form delivering to the mailbox | `GET/POST /contact` in `app/routers/contact.py`, linked from the landing page and the footer; sends to `CONTACT_RECIPIENT`, with a honeypot, CSRF and a rate limit; shows an error instead of success if sending fails. Tested with SMTP mocked in `tests/test_email.py`, and tested live. | Send a message at `https://shopconcierge.online/contact`. `[screenshot: the message in the mailbox]` |
| No secrets in code or repo | Configuration only through environment variables (`app/config.py`, `.env.example` lists them, the real `.env` exists only on the server). `.env`, databases, backups and keys are in `.gitignore` and `.dockerignore`; `scripts/scan_secrets.py` scans files and git history; `SECURITY.md` has the review. | `python scripts/scan_secrets.py` (exit code 0 means nothing found); `git check-ignore .env`. |

Tests and evals: `python -m pytest -q` and `python eval/run_evals.py` (with `AI_ENABLED=false`) both run without network access or real email.

## Known limits and next steps

These are decisions, not oversights. The full list of accepted risks is in [SECURITY.md](SECURITY.md).

- **Single server, single worker.** Rate limits and the AI cooldown are held in memory, so they reset on restart and need one uvicorn worker. AI daily caps are stored in the database and survive restarts. Scaling out would need a shared store (for example Redis).
- **No password reset, two-factor sign-in or account deletion yet.** Out of scope for this build; they come first before real customers.
- **Email sign-in method.** The mailer uses a password for SMTP. Microsoft plans to disable password sign-in for SMTP by default for existing tenants at the end of December 2026 (admins can re-enable it). The longer-term fix is OAuth or a transactional email service.
- **Backups live on the same VPS.** Nightly backups are written to a volume; copy them off the server regularly (see OPERATIONS.md).
- **Next features:** password reset, more languages, WhatsApp message handoff, appointment requests, and a paid plan with higher AI limits.

## Project layout

```
app/            FastAPI app: main.py, repo.py (shop-scoped data), global_lookups.py (the only unscoped
                functions), answer.py (keyword engine), ai/ (chat fallback, import), routers/, templates/, static/
eval/           cases.json (saved questions) and run_evals.py
scripts/        seed, backup/restore, scan_secrets, send_test_email, deploy helpers
tests/          pytest suite
PLAN.md  DECISIONS.md  SECURITY.md  OPERATIONS.md  DEMO.md
```
