import type { NextConfig } from "next";

// Phase 0 is a static site (plan §9.2). From Phase 2 the app runs as a Node server
// behind Caddy; drop `output: "export"` then.
const nextConfig: NextConfig = {
  output: "export",
  images: { unoptimized: true },
  // A stray package-lock.json above the repo makes Next guess the wrong workspace root.
  turbopack: { root: process.cwd() },
};

export default nextConfig;
