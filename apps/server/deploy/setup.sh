#!/usr/bin/env bash
# One-time setup of a fresh Ubuntu 24.04 droplet. Run as root on the droplet:  bash setup.sh
# Safe to run again: every step checks before it changes anything.
set -euo pipefail

APP_USER=syllabyte
APP_DIR=/opt/syllabyte
DATA_DIR=/var/lib/syllabyte
ENV_FILE=/etc/syllabyte/env

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get upgrade -y
apt-get install -y curl ca-certificates gnupg ufw rsync unattended-upgrades debian-keyring debian-archive-keyring apt-transport-https

# a little swap, so a memory spike on a 1 GB machine does not kill the server
if ! swapon --show | grep -q /swapfile; then
  fallocate -l 1G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

# Node 24 (the server uses node:sqlite)
if ! command -v node >/dev/null || ! node -v | grep -q '^v24'; then
  curl -fsSL https://deb.nodesource.com/setup_24.x | bash -
  apt-get install -y nodejs
fi

# Caddy (HTTPS in front of the server)
if ! command -v caddy >/dev/null; then
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -y
  apt-get install -y caddy
fi

# the account the server runs as: no login, no shell
id "$APP_USER" >/dev/null 2>&1 || useradd --system --home "$DATA_DIR" --shell /usr/sbin/nologin "$APP_USER"
mkdir -p "$APP_DIR" "$DATA_DIR" /etc/syllabyte
chown "$APP_USER:$APP_USER" "$DATA_DIR"
chmod 750 "$DATA_DIR"

# secrets file: created once, never overwritten
if [ ! -f "$ENV_FILE" ]; then
  cat > "$ENV_FILE" <<ENVEOF
SYLLABYTE_SECRET=$(openssl rand -hex 32)
SYLLABYTE_DB=$DATA_DIR/syllabyte.db
PORT=8788
# Test mode: no NODE_ENV and no RESEND_API_KEY, so sign-in codes are printed in the log (journalctl -u syllabyte).
# For real students set NODE_ENV=production, RESEND_API_KEY=... and MAIL_FROM="SyllaByte <signin@your-domain>".
ENVEOF
fi
chown root:"$APP_USER" "$ENV_FILE"
chmod 640 "$ENV_FILE"

# firewall: SSH and web only. The server itself listens on 8788 behind Caddy and is not opened.
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

# automatic security updates
dpkg-reconfigure -f noninteractive unattended-upgrades

echo "setup done"
