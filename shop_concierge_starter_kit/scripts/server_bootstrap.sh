#!/usr/bin/env bash
# Run ON the VPS (Ubuntu) after your first SSH login. Installs Docker, firewall, fail2ban.
# It does NOT disable SSH password login; do that by hand after confirming key login works.
set -euo pipefail
sudo apt-get update
sudo apt-get install -y ca-certificates curl git ufw fail2ban rsync
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo usermod -aG docker "$USER"
sudo ufw allow 22/tcp && sudo ufw allow 80/tcp && sudo ufw allow 443/tcp
sudo ufw --force enable
sudo mkdir -p /opt/shopconcierge && sudo chown "$USER":"$USER" /opt/shopconcierge
echo "Done. Log out and back in so docker works without sudo."
echo "Next: create /opt/shopconcierge/.env by hand (never commit it)."
