// src/content/consent.md is the file the approved IRB text gets dropped into. Apps can't read the filesystem at
// runtime, so mirror it into a TS module before dev/build (apps/web runs this from predev/prebuild).
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const content = join(resolve(dirname(fileURLToPath(import.meta.url)), ".."), "src", "content");
const md = readFileSync(join(content, "consent.md"), "utf8");
writeFileSync(
  join(content, "consent.ts"),
  `// Generated from consent.md by packages/core/scripts/sync-consent.mjs (runs before dev/build). Do not edit.\nexport const CONSENT_TEXT = ${JSON.stringify(md)};\n`,
);
