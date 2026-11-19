#!/usr/bin/env bash
# Give the worker the Anthropic key it spends on questions and videos. Run from the laptop:
#   deploy/worker/set-anthropic-key.sh root@<worker-ip>
# The key is pasted at a hidden prompt on this laptop and sent over SSH on standard input, so it never appears on
# screen, in the shell history, in a process list, or in any chat. Consider a key used only for the study, with a
# spending limit set in the Anthropic console.
set -euo pipefail
WORKER="${1:?usage: deploy/worker/set-anthropic-key.sh root@<worker-ip>}"

read -rsp "Paste the Anthropic API key (nothing will show), then press Enter: " KEY
echo
if [[ "$KEY" != sk-ant-* ]]; then
  echo "That does not look like an Anthropic key (they start with sk-ant-). Nothing was changed."
  exit 1
fi

printf 'ANTHROPIC_API_KEY=%s\n' "$KEY" | ssh "$WORKER" bash -c "'
  set -euo pipefail
  ENV_FILE=/etc/syllabyte-worker/env
  IFS= read -r LINE
  sed -i \"/^ANTHROPIC_API_KEY=/d;/^ANTHROPIC_KEY_NAME=/d\" \"\$ENV_FILE\"
  printf \"%s\nANTHROPIC_KEY_NAME=ANTHROPIC_API_KEY\n\" \"\$LINE\" >> \"\$ENV_FILE\"
  if systemctl is-active --quiet syllabyte-worker; then systemctl restart syllabyte-worker; fi
'"
unset KEY
echo "The worker has the key. Next, if not done yet: deploy/worker/deploy.sh $WORKER (it checks the key works)"
