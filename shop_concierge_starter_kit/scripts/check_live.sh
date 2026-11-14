#!/usr/bin/env bash
# Usage: DOMAIN=mydomain.com SHOP=demo-salon ./scripts/check_live.sh
set -uo pipefail
: "${DOMAIN:?Set DOMAIN=mydomain.com}"; SHOP="${SHOP:-demo-salon}"
ok(){ echo "PASS  $1"; }; bad(){ echo "FAIL  $1"; }
curl -fsS -o /dev/null "https://$DOMAIN/healthz" && ok "https://$DOMAIN/healthz" || bad "https://$DOMAIN/healthz"
curl -sSI "http://$DOMAIN" | grep -qi 'location: https' && ok "HTTP redirects to HTTPS" || bad "HTTP redirect"
curl -sSI "https://$DOMAIN" | grep -qi 'strict-transport-security' && ok "HSTS header" || bad "HSTS header"
curl -fsS -o /dev/null "https://$SHOP.$DOMAIN/" && ok "https://$SHOP.$DOMAIN/ (shop subdomain)" || bad "shop subdomain (check wildcard DNS)"
echo "Manual checks left: send a test email to hello@$DOMAIN from another account; submit the contact form; confirm it arrives."
