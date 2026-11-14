# Local Shop Concierge: project rules (read first, every session)

## Product
Multi-tenant platform. Local shops (salons, tutors, repair shops, clinics) register, enter services, prices, hours and FAQs, and get a public page, an embeddable chat widget, lead capture, email alerts and a report of questions customers asked that could not be answered.
Primary user: a busy shop owner with no technical skills. Secondary user: that shop's customer asking quick questions on a phone.
"Good" means: a customer gets a correct answer from the shop's own data in under 2 seconds, or an honest "I don't know" plus an offer to leave contact details. Never an invented price, hour or service.

## Stack and hard rules
- One Docker Compose stack: FastAPI + SQLite + Caddy, on a GoDaddy Ubuntu VPS. Frontend: Jinja + plain CSS/JS, no build step.
- No secrets in code or repo. Config only via environment variables. Keep .env.example current. .env, *.db, backups and keys stay git-ignored.
- Multi-tenant: every query is scoped by shop_id; data functions REQUIRE shop_id. The shop_id for any AI tool call comes from the request context, never from model output.
- The app works fully with AI_ENABLED=false. With AI_ENABLED=true, Claude (model from CLAUDE_MODEL, key from ANTHROPIC_API_KEY) is used in two places only: grounded fallback answers (with tools) and onboarding import.
- Security: argon2, HttpOnly+Secure+SameSite cookies, CSRF, rate limits, validation, output escaping, security headers.
- Email: GoDaddy Titan mailbox. SMTP_HOST=smtpout.secureserver.net (not smtp.titan.email), SMTP_USER = full address.

## Six habits (how you must work)
1. Start simple: finish and test the non-AI path first. Add AI only after evals pass without it.
2. Be specific: every task in TASKS.md states goal, user and done-when. If something is ambiguous, pick the simplest option and note the assumption in DECISIONS.md.
3. Use tools, don't guess: Claude answers customer questions by calling tools (get_services, get_hours, search_faqs, propose_lead) that read the database. It must not rely on remembered or invented facts.
4. Structured output: model replies the code consumes must be strict JSON validated against a schema. Invalid JSON means one retry, then a safe fallback.
5. Test on real cases: eval/cases.json holds saved cases. Run `python eval/run_evals.py` after EVERY change that touches chat, prompts or data, and `pytest` after every task. Report pass counts. Never edit a case just to make it pass.
6. Human in control: the AI never sends email, spends money, edits shop data or writes to the database on its own. It proposes; a person confirms (owner for data changes, customer for sharing contact details). AI calls are capped by AI_DAILY_CAP and AI_ENABLED is a kill switch.

## How to work through TASKS.md
- Do tasks in order. For each: implement, run pytest and evals, fix failures, tick the box, `git commit` with a clear message.
- Open only the files you need. Do not re-read the whole repo each turn. Keep summaries to 3 lines.
- When a task is marked [STOP], finish your part, print the exact steps I must do by hand, and wait for me to say "continue".
- You may not buy anything, change DNS, send real emails, SSH into a server, or print secrets. Give me the command or the instruction instead.
