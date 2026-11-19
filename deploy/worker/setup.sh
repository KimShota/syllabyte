#!/usr/bin/env bash
# One-time setup of a fresh Ubuntu 24.04 droplet as the SyllaByte worker: the machine that writes the questions and
# makes the videos for the production server (api.syllabyte.app). See deploy/README.md.
# Run from your laptop, not on the droplet:   deploy/worker/setup.sh root@<worker-ip>
# Safe to run again: every step checks before it changes anything.
set -euo pipefail
HOST="${1:?usage: deploy/worker/setup.sh root@<worker-ip>}"

ssh "$HOST" bash -s <<'REMOTE'
set -euo pipefail
APP_USER=syllabyte-worker
APP_DIR=/opt/syllabyte-worker
DATA_DIR=/var/lib/syllabyte-worker
ENV_FILE=/etc/syllabyte-worker/env

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get upgrade -y
# - rendering: Manim needs Cairo and Pango (built from source by pip), ffmpeg, and LaTeX with dvisvgm for formulas
# - voices: Kokoro's phonemizer is espeak-ng; soundfile needs libsndfile; manim-voiceover wants sox
apt-get install -y --no-install-recommends \
  curl ca-certificates rsync ufw unattended-upgrades git \
  build-essential pkg-config python3-dev libcairo2-dev libpango1.0-dev \
  ffmpeg sox libsox-fmt-all espeak-ng libsndfile1 fonts-dejavu-core \
  texlive-latex-base texlive-latex-recommended texlive-latex-extra texlive-fonts-recommended texlive-fonts-extra \
  texlive-science texlive-pictures texlive-lang-english cm-super tipa dvisvgm

# swap, so a burst of three renders at once slows down instead of being killed
if ! swapon --show | grep -q /swapfile; then
  fallocate -l 4G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

# uv, which installs Python 3.12 and the locked packages (uv.lock), as on the laptop
if ! command -v uv >/dev/null; then
  curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh
fi

# the account the worker runs as: no login, no shell. Its home holds the model caches (voices, language model).
id "$APP_USER" >/dev/null 2>&1 || useradd --system --home "$DATA_DIR" --shell /usr/sbin/nologin "$APP_USER"
mkdir -p "$APP_DIR" "$DATA_DIR/work" /etc/syllabyte-worker
chown -R "$APP_USER:$APP_USER" "$APP_DIR" "$DATA_DIR"
chmod 750 "$DATA_DIR"

# settings: created once, never overwritten. The two secrets are filled in by connect.sh and set-anthropic-key.sh.
if [ ! -f "$ENV_FILE" ]; then
  cat > "$ENV_FILE" <<'ENVEOF'
# The production API the worker takes jobs from.
SYLLABYTE_SERVER=https://api.syllabyte.app
# Must equal SYLLABYTE_WORKER_TOKEN on the API server: deploy/worker/connect.sh copies it across.
SYLLABYTE_WORKER_TOKEN=
# The Anthropic key the worker spends: deploy/worker/set-anthropic-key.sh asks for it.
ANTHROPIC_API_KEY=
ANTHROPIC_KEY_NAME=ANTHROPIC_API_KEY
# Extra worker options, e.g. --concurrency 2 (default 3 jobs at once).
WORKER_ARGS=
ENVEOF
fi
chown root:"$APP_USER" "$ENV_FILE"
chmod 640 "$ENV_FILE"

# firewall: SSH only. The worker calls out to the API; nothing calls in.
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw --force enable

dpkg-reconfigure -f noninteractive unattended-upgrades
echo "worker setup done"
REMOTE
