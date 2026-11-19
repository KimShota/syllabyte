import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

// Pure-logic tests only (src/data); screens get React Native Testing Library / Maestro later.
export default defineConfig({
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
      "expo-constants": fileURLToPath(new URL("./test/expo-constants.ts", import.meta.url)),
    },
  },
  // React Native's global: tests run as a development session (an installed build is tested through backendBase's `dev`)
  define: { __DEV__: "true" },
  test: { include: ["src/**/*.test.ts"] },
});
