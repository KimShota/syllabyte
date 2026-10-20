#!/usr/bin/env bash
# Switch the server from test mode (codes printed in the log) to real emails.
# Run as root on the droplet:  bash /opt/syllabyte/apps/server/deploy/set-resend-key.sh
# The key is typed or pasted at a hidden prompt, so it never appears on screen, in the shell history or in any chat.
set -euo pipefail
ENV_FILE=/etc/syllabyte/env
FROM="${1:-SyllaByte <signin@syllabyte.app>}"

read -rsp "Paste the Resend API key (nothing will show), then press Enter: " KEY
echo
if [[ "$KEY" != re_* ]]; then
  echo "That does not look like a Resend key (they start with re_). Nothing was changed."
  exit 1
fi

sed -i '/^RESEND_API_KEY=/d;/^MAIL_FROM=/d;/^NODE_ENV=/d' "$ENV_FILE"
{
  echo "NODE_ENV=production"
  echo "RESEND_API_KEY=$KEY"
  echo "MAIL_FROM=\"$FROM\""
} >> "$ENV_FILE"
unset KEY

systemctl restart syllabyte
sleep 2
systemctl is-active syllabyte
echo "Real emails are on. Sign-in codes are no longer printed in the log."
