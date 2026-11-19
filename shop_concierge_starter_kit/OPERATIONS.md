# Operations runbook (keep the app alive until 11 December 2026)

Run these on the VPS in `/opt/shopconcierge` unless noted. Nothing here needs special skills. Nothing in this file has been run against a real server yet (deployment is done by hand, see T10 in TASKS.md); fix this file if a command behaves differently.

## Key dates

- Project submission: 20 November 2026. Live demo: 11 December 2026.
- The **VPS, domain and Microsoft 365 mailbox must all be paid past 11 December 2026.** Check the end dates in the GoDaddy account now and again each week. If any ends before then, renew it.
- Certificates renew themselves (Caddy). Keep the `caddy_data` volume: never run `docker compose down -v`.

## Weekly checks (10 minutes)

1. `docker compose ps`: `app` and `caddy` show `healthy`, `backup` is `Up`.
2. `DOMAIN=shopconcierge.online ./scripts/check_live.sh` (run it on your laptop): all PASS.
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

## Email deliverability (verified 2026-11-18, facts supplied by the owner)

**What the mailbox is.** `shraddhawagh@shopconcierge.online` is a **GoDaddy Microsoft 365 Email Essentials** mailbox (1-month term), not Titan. Because the term is only one month, check its end date every week: it must run past 11 December 2026. The app sends through it with `SMTP_HOST=smtp.office365.com`, `SMTP_PORT=587` (STARTTLS) and `SMTP_USER` = the full address. `MAIL_FROM` must be that address or an alias of the same mailbox.

**The three DNS items** (GoDaddy, DNS tab of `shopconcierge.online`). Do not delete or "tidy up" any of them: mail then goes to spam.

| Item | Where | Value now |
|---|---|---|
| SPF | one TXT record on `@` (never two) | `v=spf1 include:spf.protection.outlook.com include:secureserver.net -all` |
| DKIM | two CNAME records, `selector1._domainkey` and `selector2._domainkey` | point to Microsoft (`*.dkim.mail.microsoft`); signing is switched on in the Microsoft Defender portal (Email authentication settings, DKIM) |
| DMARC | one TXT record on `_dmarc` | `p=quarantine` (`v=DMARC1; p=quarantine; adkim=r; aspf=r; rua=mailto:...`) |

History: the SPF record was GoDaddy's default (`v=spf1 include:secureserver.net -all`), which did not authorise Microsoft's servers, so with the `p=quarantine` DMARC policy mail could have been treated as spam. It was fixed on 2026-11-18.

**Result of the check.** A test email sent from the server to a Gmail address landed in the inbox with SPF PASS, DKIM PASS (`d=shopconcierge.online`) and DMARC PASS.

**How to re-check (2 minutes, after any DNS or mailbox change).**
1. On the VPS: `cd /opt/shopconcierge && docker compose exec app python scripts/send_test_email.py YOU@gmail.com`
2. In Gmail open the message, then the three dots, then *Show original*. The top box must say `SPF: PASS`, `DKIM: PASS` with `d=shopconcierge.online`, and `DMARC: PASS`. If one says FAIL or NEUTRAL, fix the matching DNS item above.
3. From your laptop (read-only): `dig +short TXT shopconcierge.online`, `dig +short CNAME selector1._domainkey.shopconcierge.online`, `dig +short CNAME selector2._domainkey.shopconcierge.online`, `dig +short TXT _dmarc.shopconcierge.online`.

**Microsoft is switching off password sign-in for SMTP.** Microsoft plans to disable Basic authentication for SMTP AUTH by default for existing tenants at the end of December 2026 (after the 11 December demo; check Microsoft's current notices, the date may change). Administrators can re-enable it. The app signs in to SMTP with the mailbox password, so if sending suddenly stops (the app log shows an email send failure, the contact form says "could not be sent", `send_test_email.py` reports `535 5.7.139 ... SmtpClientAuthentication is disabled for the Tenant`), do this in order:
1. Re-enable it for the whole organisation (admin, PowerShell on your laptop): `Connect-ExchangeOnline`, then `Set-TransportConfig -SmtpClientAuthenticationDisabled $false`. Changes can take up to about 30 minutes.
2. Re-enable *Authenticated SMTP* for the mailbox: Microsoft 365 admin center, Users, Active users, the mailbox, Mail, Manage email apps.
3. If Security defaults are on (Microsoft Entra, Properties, Manage security defaults), they also block password sign-in. Turning them off lowers protection for the whole tenant: decide that deliberately.
4. If Microsoft no longer allows it at all, the options are sending through OAuth (Microsoft Graph, needs a code change and an app registration) or a different sender service (new account, new DNS records). Both need the developer; until then the contact form shows an honest error, and lead alerts are still saved on the *Leads* page.

## Common problems

| Symptom | What to do |
|---|---|
| Site not loading | `docker compose ps`; if `caddy` is down, `docker compose logs caddy`; `docker compose up -d`. Check ports 80 and 443 are open (`sudo ufw status`). |
| Browser certificate warning on a shop subdomain | Wait 10-20 seconds and reload (first visit issues the certificate). Check the wildcard DNS record `*` points to the VPS. Unknown subdomains are refused on purpose. |
| Emails not arriving | `send_test_email.py` (above) prints a checklist. Common causes: wrong `SMTP_USER` (must be the full address), `SMTP_HOST` must be `smtp.office365.com` with `SMTP_PORT=587`, `MAIL_FROM` must equal `SMTP_USER`, Authenticated SMTP must be enabled for the mailbox (Microsoft 365 admin center, Users, Active users, the mailbox, Mail, Manage email apps), an expired subscription. If everything is correct and login is still refused, Microsoft may have switched off password (basic) SMTP sign-in for your tenant; the mailer does not support OAuth, so tell the developer. |
| Chat answers but never uses AI | `AI_ENABLED` is false, the key is empty, a daily cap was reached, or the 5-minute pause is active. `docker compose logs --tail 50 app` shows a line "AI call failed (ErrorName)" for API errors. This is safe: customers still get keyword answers. |
| "Too many attempts" messages | Rate limits working. They reset after the window, or after `docker compose restart app`. |
| Disk filling up | Remove old logs: `docker system prune` (never with `--volumes`). Backups are capped at 14 files. |

## Never do this

- `docker compose down -v`, `docker volume rm`, or `docker system prune --volumes`: they delete the database, backups and certificates.
- Commit `.env`, a database or a backup to git. Print or paste the API key or mailbox password anywhere.
- Set `DEV_LOG_EMAILS=true` on the server.
