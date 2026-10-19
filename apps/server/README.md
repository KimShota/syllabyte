# SyllaByte server

Sign-in, one saved state per student, and the shared app rules (`packages/core`) running on the server.
Plan and status: `plan/backend-plan.md`.

```bash
npm install
npm test                 # 20 tests, no network
npm run allowlist -- add you@nyu.edu researcher     # or: npm run allowlist -- students.csv
npm run dev              # http://localhost:8788; sign-in codes are printed in this terminal
```

Environment (all optional in development):

| Variable | Meaning |
|---|---|
| `PORT` | default 8788 |
| `SYLLABYTE_DB` | database file, default `data/syllabyte.db` |
| `SYLLABYTE_SECRET` | signs sign-in codes; required when `NODE_ENV=production` |
| `RESEND_API_KEY`, `MAIL_FROM` | send codes by email (Resend); without a key they are logged |
| `SYLLABYTE_SEMESTER_START` | ISO date; week 1 for new students |
| `SYLLABYTE_CORS_ORIGIN` | let a browser at this origin call the API (the phone app doesn't need it); development only |

Endpoints (all under `/api`): `POST auth/request-code`, `POST auth/verify`, `GET session`, `POST session/logout`,
`POST rpc/<method>` (`{ "args": [...] }`; any method of the core's `Api`), `POST events`, `GET research/study.csv`
(researchers), `GET health`. Send `Authorization: Bearer <token>`, and `X-Visit: <id of this app launch>` so the
"next session" cap counts per visit.

## Running the phone against it

```bash
# terminal 1
npm run allowlist -- add you@nyu.edu student && npm run dev
# terminal 2 (apps/mobile): the simulator reaches the server at localhost; a phone on Wi-Fi uses EXPO_PUBLIC_USE_SERVER=1
EXPO_PUBLIC_API_BASE=http://localhost:8788 npx expo start --ios
```
The sign-in code appears in terminal 1. See `apps/mobile/src/data/backend.ts` for the switch.

## Deploying (DigitalOcean droplet)

Files are in `deploy/`.

1. **Once, on a fresh Ubuntu 24.04 droplet:** `scp deploy/setup.sh root@<ip>:/root/ && ssh root@<ip> bash /root/setup.sh`.
   It installs Node 24 and Caddy, adds 1 GB of swap, creates the `syllabyte` user, a firewall (SSH, 80, 443),
   automatic security updates, and `/etc/syllabyte/env` with a random `SYLLABYTE_SECRET`.
2. **Each release, from your laptop:** `apps/server/deploy/deploy.sh root@<ip>`. It copies `apps/server` and
   `packages/core` (including the gitignored `fixtures/`, which the server needs), runs `npm ci`, restarts the service
   and checks `/api/health`.
3. **Allowlist a student:** `ssh root@<ip>`, then `cd /opt/syllabyte/apps/server && set -a && . /etc/syllabyte/env && set +a &&
   sudo -u syllabyte -E env HOME=/var/lib/syllabyte npm run allowlist -- add student@nyu.edu`.
4. **Logs:** `journalctl -u syllabyte -f`. In test mode (no `RESEND_API_KEY`) the sign-in codes appear there.
5. **Database:** `/var/lib/syllabyte/syllabyte.db` (plus `-wal` and `-shm` files while running).

The server is at **https://api.syllabyte.app** (Cloudflare DNS `A` record `api` -> the droplet, "DNS only"; Caddy gets
the certificate by itself). It is still in test mode: with no `RESEND_API_KEY` the sign-in codes are printed in the log.
For real students set `NODE_ENV=production`, `RESEND_API_KEY` and `MAIL_FROM` in `/etc/syllabyte/env`.
