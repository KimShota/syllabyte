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

Endpoints (all under `/api`): `POST auth/request-code`, `POST auth/verify`, `GET session`, `POST session/logout`,
`POST rpc/<method>` (`{ "args": [...] }`; any method of the core's `Api`), `POST events`, `GET research/study.csv`
(researchers), `GET health`. Send `Authorization: Bearer <token>`, and `X-Visit: <id of this app launch>` so the
"next session" cap counts per visit.
