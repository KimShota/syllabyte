#!/usr/bin/env bash
# Adds the settings the current server needs and the droplet's settings file may lack. deploy.sh runs it on the
# droplet before every restart; it only adds what is missing and never prints a secret.
#  - SYLLABYTE_PUBLIC_URL: the server refuses to start in production without its HTTPS address.
#  - SYLLABYTE_FILES: uploaded syllabi, slides and the worker's videos. The default (data/files inside the app folder)
#    is read-only under the service's ProtectSystem=strict, so the server could not start; this puts them with the
#    database, under /var/lib/syllabyte, which the service may write.
#  - SYLLABYTE_WORKER_TOKEN: without it the worker routes are off and nothing processes uploads. The worker gets the
#    same token from deploy/worker/connect.sh.
set -euo pipefail
ENV_FILE=/etc/syllabyte/env
DATA_DIR=/var/lib/syllabyte

has() { grep -Eq "^$1=.+" "$ENV_FILE"; }
add() { sed -i "/^$1=/d" "$ENV_FILE"; printf '%s=%s\n' "$1" "$2" >> "$ENV_FILE"; echo "added $1"; }

has SYLLABYTE_PUBLIC_URL || add SYLLABYTE_PUBLIC_URL https://api.syllabyte.app
has SYLLABYTE_FILES || add SYLLABYTE_FILES "$DATA_DIR/files"
has SYLLABYTE_WORKER_TOKEN || add SYLLABYTE_WORKER_TOKEN "$(openssl rand -hex 32)"

FILES="$(sed -n 's/^SYLLABYTE_FILES=//p' "$ENV_FILE" | tail -1)"
mkdir -p "$FILES"
chown syllabyte:syllabyte "$FILES"
chmod 750 "$FILES"
