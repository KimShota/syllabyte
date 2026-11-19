#!/usr/bin/env bash
# Copy the worker's code to the worker droplet, install its packages, check it, and (re)start it. Run from the laptop,
# at the repository root:   deploy/worker/deploy.sh root@<worker-ip>
# First time: deploy/worker/setup.sh, then this, then connect.sh and set-anthropic-key.sh (deploy/README.md).
#
# It copies the working folder, as apps/server/deploy/deploy.sh does, because media/characters is not in git; it
# says which commit that was and whether there were uncommitted changes. A video the worker was making when it
# restarts goes back to the queue after 30 minutes, so deploy when the study is quiet.
set -euo pipefail
HOST="${1:?usage: deploy/worker/deploy.sh root@<worker-ip>}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
APP=/opt/syllabyte-worker
cd "$ROOT"

VERSION="$(git rev-parse --short HEAD)$(git diff --quiet HEAD -- packages scripts pyproject.toml uv.lock || echo "+uncommitted")"
[ -f media/characters/cast.json ] || { echo "media/characters/cast.json is missing: the videos' characters are not on this laptop"; exit 1; }
echo "deploying worker $VERSION to $HOST"

SYNC=(rsync -az --delete --exclude __pycache__ --exclude '*.pyc' --exclude tests --exclude node_modules)
rsync -az pyproject.toml uv.lock .python-version "$HOST:$APP/"
for p in common ingestion_agent curriculum_alignment_agent script_generation_agent animation_agent assessment_agent; do
  ssh "$HOST" "mkdir -p $APP/packages/$p"
  "${SYNC[@]}" "packages/$p/" "$HOST:$APP/packages/$p/"
done
ssh "$HOST" "mkdir -p $APP/scripts $APP/media/characters $APP/deploy/worker"
"${SYNC[@]}" scripts/ "$HOST:$APP/scripts/"
"${SYNC[@]}" media/characters/ "$HOST:$APP/media/characters/"
"${SYNC[@]}" deploy/worker/ "$HOST:$APP/deploy/worker/"

ssh "$HOST" VERSION="$VERSION" bash -s <<'REMOTE'
set -euo pipefail
APP=/opt/syllabyte-worker
USER_NAME=syllabyte-worker
ENV_FILE=/etc/syllabyte-worker/env
echo "$VERSION" > "$APP/VERSION"
chown -R "$USER_NAME:$USER_NAME" "$APP"
as_worker() { runuser -u "$USER_NAME" -- env HOME=/var/lib/syllabyte-worker "$@"; }

# the locked packages; --inexact keeps the English language model the voice engine installed itself
cd "$APP"
as_worker uv sync --frozen --no-dev --inexact --python 3.12

install -m 644 deploy/worker/syllabyte-worker.service /etc/systemd/system/syllabyte-worker.service
systemctl daemon-reload
systemctl enable syllabyte-worker >/dev/null 2>&1

# The checks run exactly as the service will: its user, its settings file, its folder (and no secret on a command line).
smoke() {
  systemd-run --quiet --wait --pipe --collect -p User="$USER_NAME" -p EnvironmentFile="$ENV_FILE" -p WorkingDirectory="$APP" \
    -E HOME=/var/lib/syllabyte-worker "$APP/.venv/bin/python" deploy/worker/smoke.py "$@"
}
has() { grep -Eq "^$1=.+" "$ENV_FILE"; }
if ! has SYLLABYTE_WORKER_TOKEN || ! has ANTHROPIC_API_KEY; then
  smoke --offline
  systemctl stop syllabyte-worker 2>/dev/null || true
  echo
  echo "Installed, but not started: it still needs its secrets."
  has SYLLABYTE_WORKER_TOKEN || echo "  deploy/worker/connect.sh root@<api-ip> root@<this-worker>"
  has ANTHROPIC_API_KEY || echo "  deploy/worker/set-anthropic-key.sh root@<this-worker>"
  exit 0
fi
smoke
systemctl restart syllabyte-worker
sleep 3
systemctl is-active syllabyte-worker
echo "worker $VERSION is running. Logs: ssh <this-worker> journalctl -u syllabyte-worker -f"
REMOTE
