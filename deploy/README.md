# Two setups: your laptop now, the study's servers later

The same code runs in two setups. Nothing about one changes the other.

| | **Development** (now) | **Production** (the study) |
|---|---|---|
| App | Expo Go on the simulator or your phone, from Metro on the laptop | An installed build from TestFlight (`eas.json`, profile `production`) |
| API | `apps/server` on the laptop (`npm run dev`) | `https://api.syllabyte.app` (the DigitalOcean droplet, `apps/server/deploy`) |
| Worker (questions, videos) | `python -m ingestion_agent.worker` on the laptop | The worker droplet, always on (`deploy/worker`) |
| Who uses it | You | Participants |

**How the app knows which one it is in** (`apps/mobile/src/data/backend.ts`):
- In a development session it uses whatever the environment says: `apps/mobile/.env.local`
  (`EXPO_PUBLIC_API_BASE=http://<laptop-ip>:<port>`), or `EXPO_PUBLIC_USE_SERVER=1`, or neither (demo mode, no server).
  `.env.local` is git-ignored, so it is never part of a build.
- An installed build only ever talks to an HTTPS server: the production one, unless `eas.json` names another HTTPS
  address. It cannot fall back to demo mode or reach a laptop, so a participant's answers always reach the study.
- Profile (the settings screen) shows it at the bottom: "Development server · 10.x.x.x:8790", "Study server ·
  api.syllabyte.app" or "Demo mode".

The production API turns off Expo Go sign-in (`NODE_ENV=production`), so only installed builds sign in there.

## Development (unchanged)

```bash
cd apps/server && npm run dev                                   # API on :8788, sign-in links printed here
SYLLABYTE_WORKER_TOKEN=... uv run python -m ingestion_agent.worker --server http://localhost:8788
cd apps/mobile && npx expo start                                # then open in Expo Go
```

## Production: one-time setup

Do these in order. Steps marked **you** need an account or a decision only you can make; the rest are scripts run
from the repository root on the laptop.

1. **Before any real course material goes on a server:** the professor's OK to host it (`plan/backend-plan.md` §15.1).
2. **Deploy the current API** to the droplet: `apps/server/deploy/deploy.sh root@134.209.54.77`.
   It now runs `apps/server/deploy/prepare-env.sh` first, which adds what the current code needs and the droplet
   lacks: `SYLLABYTE_PUBLIC_URL` (the server refuses to start in production without it), `SYLLABYTE_FILES` under
   `/var/lib/syllabyte/files` (the old default was read-only for the service, so uploads, and now startup, failed),
   and a `SYLLABYTE_WORKER_TOKEN`. It never prints a secret. Check: `curl https://api.syllabyte.app/api/health`.
3. **You: create the worker droplet** in DigitalOcean: Ubuntu 24.04, Basic, Regular, 4 vCPU / 8 GB ($48/month,
   billed per second), same region as the API droplet, your laptop's SSH key (`~/.ssh/id_ed25519.pub`).
4. **Set it up:** `deploy/worker/setup.sh root@<worker-ip>` (system packages, LaTeX, ffmpeg, voices, uv, a
   `syllabyte-worker` account, a firewall that allows only SSH).
5. **Give it the API's token:** `deploy/worker/connect.sh root@134.209.54.77 root@<worker-ip>`.
6. **Give it an Anthropic key:** `deploy/worker/set-anthropic-key.sh root@<worker-ip>` (hidden prompt). A key used only
   for the study, with a spending limit in the Anthropic console, keeps the study's cost separate and capped.
7. **Deploy the worker:** `deploy/worker/deploy.sh root@<worker-ip>`. It copies the code and the cast's pictures
   (`media/characters`, not in git), installs the locked packages (CPU-only PyTorch on Linux), runs
   `deploy/worker/smoke.py` (API reachable, token accepted, Anthropic key works, both voices speak, Manim renders a
   formula), and starts the service only if every check passes.
8. **You: the app build.** An Apple Developer account, then from `apps/mobile`: `npx eas-cli@latest build -p ios
   --profile production` and `npx eas-cli@latest submit -p ios --profile production`. Invite yourself in TestFlight
   first; external testers need Apple's one-time beta review.
9. **Check it end to end with your laptop closed:** sign in from the TestFlight build, upload a syllabus and slides,
   answer a check, and watch a video arrive. Profile should say "Study server · api.syllabyte.app".

Still to do before participants (not covered by these scripts): nightly database backups off the droplet, the
participant allowlist (`npm run allowlist` on the API droplet), and the researcher account.

## Production: day to day

| Task | Command |
|---|---|
| Ship API changes | `apps/server/deploy/deploy.sh root@134.209.54.77` |
| Ship worker changes | `deploy/worker/deploy.sh root@<worker-ip>` |
| Is the worker running? | `ssh root@<worker-ip> systemctl status syllabyte-worker` |
| Worker log | `ssh root@<worker-ip> journalctl -u syllabyte-worker -f` |
| Re-run the worker's checks | `ssh root@<worker-ip> 'cd /opt/syllabyte-worker && systemd-run --wait --pipe --collect -p User=syllabyte-worker -p EnvironmentFile=/etc/syllabyte-worker/env -p WorkingDirectory=/opt/syllabyte-worker -E HOME=/var/lib/syllabyte-worker .venv/bin/python deploy/worker/smoke.py'` |
| Which code is on the worker | `ssh root@<worker-ip> cat /opt/syllabyte-worker/VERSION` |
| Pause the worker | `ssh root@<worker-ip> systemctl stop syllabyte-worker` (jobs wait in the queue) |
| Retry a failed job | `POST /api/research/jobs/:id/retry` as a researcher |
| Students' error reports | `GET /api/research/reports?format=csv` as a researcher |

Deploy the worker when the study is quiet: a job it was in the middle of goes back to the queue after 30 minutes.

**Never run the laptop worker against the production API.** Two workers would split the study's jobs, and the
laptop's copy of the code may differ from the worker droplet's. The laptop worker needs the production token to do
it, which only the two servers hold.

**Between testing and the study** the worker droplet can be deleted (billing is per second) and made again with steps
3-7, or kept as a snapshot. The API droplet and its data are not affected.
