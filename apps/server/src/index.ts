import { serve } from "@hono/node-server";
import { randomBytes } from "node:crypto";
import { createApp } from "./app";
import { Auth } from "./auth";
import { openDb } from "./db";
import { consoleMailer, resendMailer } from "./mail";
import { StateRunner } from "./runner";

const production = process.env.NODE_ENV === "production";
const secret = process.env.SYLLABYTE_SECRET ?? (production ? "" : randomBytes(16).toString("hex"));
if (!secret) {
  console.error("SYLLABYTE_SECRET is required in production (any long random string; it signs the sign-in codes).");
  process.exit(1);
}
const resendKey = process.env.RESEND_API_KEY;
if (production && !resendKey) {
  console.error("RESEND_API_KEY is required in production: sign-in codes are emailed.");
  process.exit(1);
}

const db = openDb(process.env.SYLLABYTE_DB ?? "data/syllabyte.db");
const mailer = resendKey ? resendMailer(resendKey, process.env.MAIL_FROM ?? "SyllaByte <signin@example.com>") : consoleMailer;
const semesterStart = process.env.SYLLABYTE_SEMESTER_START ? new Date(process.env.SYLLABYTE_SEMESTER_START).getTime() : undefined;
const auth = new Auth(db, mailer, secret);
const app = createApp({ db, auth, runner: new StateRunner(db, { semesterStart }), corsOrigin: process.env.SYLLABYTE_CORS_ORIGIN });

const port = Number(process.env.PORT ?? 8788);
serve({ fetch: app.fetch, port, hostname: "0.0.0.0" }, () => console.log(`SyllaByte server on http://0.0.0.0:${port}`));
