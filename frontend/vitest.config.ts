import { defineConfig } from "vitest/config";

// Kept apart from vite.config.ts on purpose: the suite drives real `vite build`
// runs as a subprocess and inspects what they emit, so it must not inherit the
// config of the build it is inspecting.
export default defineConfig({
  test: {
    environment: "node",
    include: ["tests/**/*.test.ts"],
    // Two production builds run inside one test.
    testTimeout: 180_000,
    hookTimeout: 180_000,
  },
});
