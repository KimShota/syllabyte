// Who may sign in. Usage: npm run allowlist -- students.csv      (lines: email[,role]; role defaults to student)
//                        npm run allowlist -- add me@nyu.edu researcher
import { readFileSync } from "node:fs";
import { Auth, looksLikeEmail, normalizeEmail } from "../src/auth";
import { ROLES, openDb, type Role } from "../src/db";
import { consoleMailer } from "../src/mail";

const db = openDb(process.env.SYLLABYTE_DB ?? "data/syllabyte.db");
const auth = new Auth(db, consoleMailer, "unused");
const [first, ...rest] = process.argv.slice(2);

const entries: [string, Role][] = [];
if (first === "add") {
  entries.push([rest[0] ?? "", (rest[1] ?? "student") as Role]);
} else if (first) {
  for (const line of readFileSync(first, "utf8").split(/\r?\n/)) {
    const [email, role] = line.split(",").map((x) => x.trim());
    if (email && email.toLowerCase() !== "email") entries.push([email, (role || "student") as Role]);
  }
} else {
  console.error("usage: npm run allowlist -- <file.csv> | add <email> [student|instructor|researcher]");
  process.exit(1);
}

let added = 0;
for (const [email, role] of entries) {
  if (!looksLikeEmail(normalizeEmail(email)) || !ROLES.includes(role)) {
    console.error(`skipped: ${email} ${role}`);
    continue;
  }
  auth.addToAllowlist(email, role);
  added += 1;
}
console.log(`${added} on the allowlist`);
