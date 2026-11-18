#!/usr/bin/env bash
# Run on your laptop. Usage: SERVER=user@1.2.3.4 ./scripts/deploy.sh
# Copies the project (never .env, .git or databases) and rebuilds the containers.
set -euo pipefail
: "${SERVER:?Set SERVER=user@your-server-ip}"
rsync -az --delete --exclude '.env' --exclude '.git' --exclude '*.db' --exclude '__pycache__' --exclude '.venv' --exclude '.pytest_cache' --exclude '/data' --exclude '/backups' ./ "$SERVER:/opt/shopconcierge/"
ssh "$SERVER" 'cd /opt/shopconcierge && test -f .env || { echo "ERROR: create /opt/shopconcierge/.env on the server first"; exit 1; } && docker compose up -d --build && docker compose ps'
