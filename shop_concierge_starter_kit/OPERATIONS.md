# Operations runbook (keep the app alive until 11 December 2026)

Run these on the VPS in `/opt/shopconcierge` unless noted. Nothing here needs special skills. Nothing in this file has been run against a real server yet (deployment is done by hand, see T10 in TASKS.md); fix this file if a command behaves differently.

## Key dates

- Project submission: 20 November 2026. Live demo: 11 December 2026.
- The **VPS, domain and Titan mailbox must all be paid past 11 December 2026.** Check the end dates in the GoDaddy account now and again each week. If any ends before then, renew it.
- Certificates renew themselves (Caddy). Keep the `caddy_data` volume: never run `docker compose down -v`.

## Weekly checks (10 minutes)

1. `docker compose ps`: `app` and `caddy` show `healthy`, `backup` is `Up`.
2. `DOMAIN=yourdomain.com ./scripts/check_live.sh` (run it on your laptop): all PASS.
3. `df -h /` and `docker system df`: disk not above 80% full.
4. `docker compose logs --tail 100 app`: no repeating errors. (Request URLs are intentionally not logged.)
5. Backups: `docker compose run --rm --no-deps backup ls -lh /backups`: there is one file per night, newest from last night. Copy one off the server to your laptop: `docker compose cp backup:/backups ./backups-copy` (a backup on the same server does not protect you if the server is lost).
6. Console usage (Anthropic Console, your server key's workspace): open the *Usage* and *Cost* pages and look at the last 7 days. Compare with `AI_DAILY_CAP` (calls per day) and your spend limit on the *Limits* page. Spend rising without more customers means something is wrong: switch AI off (below).
7. Send a test email: `docker compose exec app python scripts/send_test_email.py you@elsewhere.com`.
8. Open the demo shop and ask one price question.

## Kill switch: turn AI off immediately

1. Edit `.env`: `AI_ENABLED=false`.
2. `docker compose up -d --force-recreate app` (a plain `restart` does not re-read `.env`).
3. Check: the import page now says to enter details by hand, and chat still answers from the shop's data.

Turn it on again by setting `AI_ENABLED=true` and recreating the app. The app also stops AI by itself for 5 minutes after any Claude API error (rate limit, empty credit balance, timeout); customers never see an error.

## Start, stop, restart

```bash
docker compose ps                        # status
docker compose logs --tail 100 app       # recent app logs (also: caddy, backup)
docker compose restart app               # restart only the app (clears in-memory limits and the AI pause)
docker compose up -d --build             # rebuild and start everything after a code change
docker compose stop                      # stop everything (data stays)
docker compose up -d                     # start everything again
```

After a reboot of the VPS the containers start again by themselves (`restart: unless-stopped`). If they do not: `cd /opt/shopconcierge && docker compose up -d`.

## Backups and restoring the SQLite database

A `backup` container writes a compressed, integrity-checked copy of the database every night at 21:00 UTC (02:30 India time) into the `backups` volume and keeps the newest 14.

Make a backup right now:

```bash
docker compose exec backup python scripts/backup_db.py
```

Restore (this replaces the live database; shops' changes since that backup are lost):

```bash
docker compose run --rm --no-deps backup ls /backups            # pick a file name
docker compose stop app backup
docker compose run --rm --no-deps backup python scripts/backup_db.py --restore /backups/shop_concierge-YYYYMMDD-HHMMSS.db.gz
docker compose up -d
```

The old database is kept next to the new one as `shop_concierge.db.before-restore` in the `app_data` volume. If the restore message says the integrity check failed, nothing was changed; try the next older backup. To restore from a copy on your laptop, copy it into the volume first: `docker compose cp ./file.db.gz backup:/backups/` (the container must be running), then use the commands above.

## Common problems

| Symptom | What to do |
|---|---|
| Site not loading | `docker compose ps`; if `caddy` is down, `docker compose logs caddy`; `docker compose up -d`. Check ports 80 and 443 are open (`sudo ufw status`). |
| Browser certificate warning on a shop subdomain | Wait 10-20 seconds and reload (first visit issues the certificate). Check the wildcard DNS record `*` points to the VPS. Unknown subdomains are refused on purpose. |
| Emails not arriving | `send_test_email.py` (above) prints a checklist. Common causes: wrong `SMTP_USER` (must be the full address), `SMTP_HOST` must be `smtpout.secureserver.net`, expired mailbox. |
| Chat answers but never uses AI | `AI_ENABLED` is false, the key is empty, a daily cap was reached, or the 5-minute pause is active. `docker compose logs --tail 50 app` shows a line "AI call failed (ErrorName)" for API errors. This is safe: customers still get keyword answers. |
| "Too many attempts" messages | Rate limits working. They reset after the window, or after `docker compose restart app`. |
| Disk filling up | Remove old logs: `docker system prune` (never with `--volumes`). Backups are capped at 14 files. |

## Never do this

- `docker compose down -v`, `docker volume rm`, or `docker system prune --volumes`: they delete the database, backups and certificates.
- Commit `.env`, a database or a backup to git. Print or paste the API key or mailbox password anywhere.
- Set `DEV_LOG_EMAILS=true` on the server.
