// Serves the rendered videos for the phone while the app runs on mock data: apps/web/public (run
// `npm run fixtures` in apps/web first). iOS's player needs HTTP Range requests, which `python -m http.server` lacks.
// Usage: npm run media            (port 8787; MEDIA_PORT to change)
import { createReadStream, existsSync, statSync } from "node:fs";
import { createServer } from "node:http";
import { dirname, extname, join, normalize, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../../web/public");
const port = Number(process.env.MEDIA_PORT ?? 8787);
const TYPES = { ".mp4": "video/mp4", ".webm": "video/webm", ".jpg": "image/jpeg", ".png": "image/png", ".vtt": "text/vtt" };

if (!existsSync(join(root, "fixtures"))) {
  console.error("No apps/web/public/fixtures. Run: cd apps/web && npm run fixtures");
  process.exit(1);
}

createServer((req, res) => {
  const file = normalize(join(root, decodeURIComponent(new URL(req.url, "http://x").pathname)));
  if (!file.startsWith(root + sep) ||!existsSync(file) || !statSync(file).isFile()) {
    res.writeHead(404).end();
    return;
  }
  const size = statSync(file).size;
  const head = { "Content-Type": TYPES[extname(file)] ?? "application/octet-stream", "Accept-Ranges": "bytes" };
  const range = /^bytes=(\d*)-(\d*)$/.exec(req.headers.range ?? "");
  if (!range) {
    res.writeHead(200, { ...head, "Content-Length": size });
    if (req.method === "HEAD") res.end();
    else createReadStream(file).pipe(res);
    return;
  }
  // "bytes=a-b", "bytes=a-" and the suffix form "bytes=-n"
  let start = range[1] === "" ? Math.max(0, size - Number(range[2])) : Number(range[1]);
  const end = range[1] === "" || range[2] === "" ? size - 1 : Math.min(Number(range[2]), size - 1);
  if (start > end || start >= size) {
    res.writeHead(416, { "Content-Range": `bytes */${size}` }).end();
    return;
  }
  res.writeHead(206, { ...head, "Content-Range": `bytes ${start}-${end}/${size}`, "Content-Length": end - start + 1 });
  if (req.method === "HEAD") res.end();
  else createReadStream(file, { start, end }).pipe(res);
}).listen(port, "0.0.0.0", () => console.log(`serving ${root} on http://0.0.0.0:${port}`));
