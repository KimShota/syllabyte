// content/consent.md is the file the approved IRB text gets dropped into. Client components
// can't read the filesystem, so mirror it into a TS module before dev/build.
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const web = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const md = readFileSync(join(web, "content", "consent.md"), "utf8");
writeFileSync(
  join(web, "content", "consent.ts"),
  `// Generated from consent.md by scripts/sync-consent.mjs (runs before dev/build). Do not edit.\nexport const CONSENT_TEXT = ${JSON.stringify(md)};\n`,
);
