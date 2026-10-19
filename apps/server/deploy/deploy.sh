#!/usr/bin/env bash
# Copy the server and the shared core to the droplet and restart it. Run from your laptop:
#   apps/server/deploy/deploy.sh root@134.209.54.77
# (packages/core/fixtures is gitignored but the server needs it, so this copies from the working folder, not from git.)
set -euo pipefail
HOST="${1:?usage: deploy.sh user@host}"
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"

ssh "$HOST" 'mkdir -p /opt/syllabyte/apps /opt/syllabyte/packages'
rsync -az --delete --exclude node_modules --exclude data --exclude .env --exclude tests \
  "$ROOT/apps/server/" "$HOST:/opt/syllabyte/apps/server/"
rsync -az --delete --exclude node_modules --exclude tests \
  "$ROOT/packages/core/" "$HOST:/opt/syllabyte/packages/core/"

ssh "$HOST" bash -s <<'REMOTE'
set -euo pipefail
cd /opt/syllabyte/apps/server
npm ci --no-audit --no-fund
chown -R root:root /opt/syllabyte
chmod -R a+rX /opt/syllabyte
install -m 644 deploy/syllabyte.service /etc/systemd/system/syllabyte.service
install -m 644 deploy/Caddyfile /etc/caddy/Caddyfile
systemctl daemon-reload
systemctl enable syllabyte >/dev/null 2>&1
systemctl restart syllabyte
systemctl reload caddy || systemctl restart caddy
sleep 2
systemctl is-active syllabyte
curl -fsS http://127.0.0.1:8788/api/health && echo
REMOTE
