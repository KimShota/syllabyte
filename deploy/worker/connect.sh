#!/usr/bin/env bash
# Give the worker the API server's worker token, so the API hands it jobs. Run from the laptop:
#   deploy/worker/connect.sh root@<api-ip> root@<worker-ip>
# The token goes from one server to the other through this script's memory: it is never printed, typed or put on a
# command line. The API server makes its token when it is deployed (apps/server/deploy/prepare-env.sh).
set -euo pipefail
API="${1:?usage: deploy/worker/connect.sh root@<api-ip> root@<worker-ip>}"
WORKER="${2:?usage: deploy/worker/connect.sh root@<api-ip> root@<worker-ip>}"

TOKEN="$(ssh "$API" "sed -n 's/^SYLLABYTE_WORKER_TOKEN=//p' /etc/syllabyte/env | tail -1")"
if [ -z "$TOKEN" ]; then
  echo "The API server has no SYLLABYTE_WORKER_TOKEN yet. Deploy it first: apps/server/deploy/deploy.sh $API"
  exit 1
fi

printf 'SYLLABYTE_WORKER_TOKEN=%s\n' "$TOKEN" | ssh "$WORKER" bash -c "'
  set -euo pipefail
  ENV_FILE=/etc/syllabyte-worker/env
  IFS= read -r LINE
  sed -i \"/^SYLLABYTE_WORKER_TOKEN=/d\" \"\$ENV_FILE\"
  printf \"%s\n\" \"\$LINE\" >> \"\$ENV_FILE\"
  if systemctl is-active --quiet syllabyte-worker; then systemctl restart syllabyte-worker; fi
'"
unset TOKEN
echo "The worker has the API's token. Next, if not done yet: deploy/worker/set-anthropic-key.sh $WORKER, then deploy/worker/deploy.sh $WORKER"
