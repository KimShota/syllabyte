// Learn more https://docs.expo.dev/guides/customizing-metro
const path = require("path");
const { getDefaultConfig } = require("expo/metro-config");

const config = getDefaultConfig(__dirname);

// The shared logic (packages/core) is linked into node_modules from outside this folder; Metro only bundles files
// in folders it watches. The repo has no npm workspaces, so Expo's automatic monorepo setup doesn't see it.
config.watchFolders = [...(config.watchFolders ?? []), path.resolve(__dirname, "../../packages/core")];

// Testing on a real phone over a network that lets the app reach Metro but not the server's own port (seen on campus
// Wi-Fi): with SYLLABYTE_API_PROXY=http://127.0.0.1:8798 Metro forwards /api/* to the server, keeping the Host header so
// the server's sign-in links and media URLs point back through Metro too. Start Expo with
// EXPO_PUBLIC_API_BASE=http://<this Mac's address>:8081. Unset, nothing changes.
const proxyTarget = process.env.SYLLABYTE_API_PROXY;
if (proxyTarget) {
  const http = require("http");
  const target = new URL(proxyTarget);
  const previous = config.server?.enhanceMiddleware;
  config.server = {
    ...config.server,
    enhanceMiddleware: (middleware, server) => {
      const base = previous ? previous(middleware, server) : middleware;
      return (req, res, next) => {
        if (!req.url || !req.url.startsWith("/api/")) return base(req, res, next);
        const upstream = http.request(
          { hostname: target.hostname, port: target.port, path: req.url, method: req.method, headers: req.headers },
          (r) => {
            res.writeHead(r.statusCode ?? 502, r.headers);
            r.pipe(res);
          },
        );
        upstream.on("error", () => {
          res.statusCode = 502;
          res.end();
        });
        req.pipe(upstream);
      };
    },
  };
}

module.exports = config;
