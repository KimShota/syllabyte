// Copies the media referenced by fixtures/videos.json from the pipeline run into
// public/fixtures/ (plan Q9). Course slides and videos never go into git.
import { execFileSync } from "node:child_process";
import { copyFileSync, existsSync, mkdirSync, readFileSync, rmSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const web = resolve(here, "..");
const repo = resolve(web, "../..");
const fixtures = join(web, "fixtures");
const target = join(web, "public", "fixtures");

if (!existsSync(join(fixtures, "videos.json"))) {
  console.error("No fixtures/videos.json. Run: uv run python scripts/build_ui_fixtures.py");
  process.exit(1);
}
const videos = JSON.parse(readFileSync(join(fixtures, "videos.json"), "utf8"));
rmSync(target, { recursive: true, force: true });

let n = 0;
const copy = (from, to) => {
  const src = resolve(repo, from);
  if (!existsSync(src)) throw new Error(`missing source file: ${src}`);
  mkdirSync(dirname(to), { recursive: true });
  copyFileSync(src, to);
  n++;
};

const slides = new Set();
for (const v of videos) {
  copy(v.video_src, join(target, v.id, "video.mp4"));
  if (process.env.FIXTURES_WEBM === "1") {
    // Test browsers (Playwright's Chromium) can't decode H.264. Small VP9 copies, used only in test builds.
    execFileSync("ffmpeg", ["-v", "error", "-y", "-i", resolve(repo, v.video_src), "-vf", "scale=180:-2", "-c:v", "libvpx-vp9", "-b:v", "60k", "-g", "30", "-keyint_min", "30", "-deadline", "realtime", "-cpu-used", "8", "-c:a", "libopus", "-b:a", "16k", join(target, v.id, "video.webm")]);
    n++;
  }
  copy(v.poster_src, join(target, v.id, "poster.jpg"));
  copy(v.vtt_src, join(target, v.id, "captions.vtt"));
  v.source_slides.forEach((s) => slides.add(s));
}
// Slide images sit next to the run's corpus; the run dir is the video's grandparent.
const runDir = dirname(dirname(videos[0].video_src));
const slideFile = (s) => `${runDir}/images/slides_slide${String(s).padStart(3, "0")}.png`;
for (const s of slides) copy(slideFile(s), join(target, "slides", `slide-${String(s).padStart(3, "0")}.png`));
console.log(`copied ${n} files into public/fixtures/`);
