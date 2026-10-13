// Fails fast with an actionable message instead of a blank prototype.
import { existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const web = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const need = ["course.json", "items.json", "bank.json", "videos.json", "slides.json"].map((f) => join(web, "fixtures", f));
const missing = need.filter((f) => !existsSync(f));
if (missing.length) {
  console.error("\nFixtures are missing. From the repo root run:\n  uv run python scripts/build_ui_fixtures.py\n  uv run python scripts/build_item_bank.py   # spends LLM credits unless runs/<id>/ui_cache has the bank\n  cd apps/web && npm run fixtures\n");
  process.exit(1);
}
if (!existsSync(join(web, "public", "fixtures"))) {
  console.error("\nMedia is missing. Run: npm run fixtures\n");
  process.exit(1);
}
