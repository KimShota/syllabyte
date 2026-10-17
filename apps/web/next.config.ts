import path from "node:path";
import type { NextConfig } from "next";

// Phase 0 is a static site (plan §9.2). From Phase 2 the app runs as a Node server
// behind Caddy; drop `output: "export"` then.
const nextConfig: NextConfig = {
  output: "export",
  images: { unoptimized: true },
  // The shared logic is TypeScript source in packages/core, linked into node_modules.
  transpilePackages: ["@syllabyte/core"],
  // Turbopack only resolves files under its root, so the root is the repo (apps/web and packages/core). Set it
  // explicitly: a stray package-lock.json above the repo makes Next guess the wrong one.
  turbopack: { root: path.resolve(process.cwd(), "../..") },
};

export default nextConfig;
