// The study timeline, from the server's command line. Moves one student's clock forward (never back) so the later
// lecture checks and questionnaires can be tried without waiting weeks. Find a student's code with `npm run facilitator -- list`.
//   npm run facilitator -- list
//   npm run facilitator -- show S-ABCDE
//   npm run facilitator -- advance S-ABCDE 7          (days)
//   npm run facilitator -- module S-ABCDE 1           (just past module 1's last lecture week: its questionnaire is due)
//   npm run facilitator -- reset S-ABCDE              (test accounts only: recorded times would go backwards)
import { advanceClock, advanceToModuleEnd, getClock, resetClock } from "../src/clock";
import { openDb } from "../src/db";

const db = openDb(process.env.SYLLABYTE_DB ?? "data/syllabyte.db");
const [cmd, code, arg] = process.argv.slice(2);

function usage(): never {
  console.error("usage: npm run facilitator -- list | show <code> | advance <code> <days> | module <code> <n> | reset <code>");
  process.exit(1);
}

if (cmd === "list") {
  const rows = db.prepare("SELECT participant_code, created_at FROM users ORDER BY created_at").all() as { participant_code: string; created_at: number }[];
  for (const r of rows) console.log(`${r.participant_code}  clock +${getClock(db, r.participant_code)?.offset_days ?? 0} days  first signed in ${new Date(r.created_at).toISOString().slice(0, 10)}`);
  console.log(`${rows.length} participants`);
  process.exit(0);
}
if (!cmd || !code) usage();

let out;
try {
  out =
    cmd === "show" ? getClock(db, code)
    : cmd === "advance" ? advanceClock(db, code, Number(arg))
    : cmd === "module" ? advanceToModuleEnd(db, code, Number(arg))
    : cmd === "reset" ? resetClock(db, code)
    : usage();
} catch (e) {
  console.error((e as Error).message);
  process.exit(1);
}
if (!out) {
  console.error(`no participant ${code}`);
  process.exit(1);
}
console.log(`${out.participant_code}: clock is ${out.offset_days} days ahead of real time`);
