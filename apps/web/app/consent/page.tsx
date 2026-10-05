import { readFileSync } from "node:fs";
import { join } from "node:path";
import { ConsentView } from "./ConsentView";

export default function Consent() {
  // Read at build time; the text lives in content/consent.md so the approved wording can be dropped in.
  const text = readFileSync(join(process.cwd(), "content", "consent.md"), "utf8");
  return <ConsentView markdown={text} />;
}
