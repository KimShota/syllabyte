// Learn more https://docs.expo.dev/guides/customizing-metro
const path = require("path");
const { getDefaultConfig } = require("expo/metro-config");

const config = getDefaultConfig(__dirname);

// The shared logic (packages/core) is linked into node_modules from outside this folder; Metro only bundles files
// in folders it watches. The repo has no npm workspaces, so Expo's automatic monorepo setup doesn't see it.
config.watchFolders = [...(config.watchFolders ?? []), path.resolve(__dirname, "../../packages/core")];

module.exports = config;
