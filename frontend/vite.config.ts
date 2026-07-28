import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

/**
 * One codebase, two builds.
 *
 * `static` is the site the competitors read: JSON shipped alongside the build,
 * no API, no upload. `local` is the admin tool that runs on my machine once a
 * month and talks to FastAPI.
 *
 * The mode is a compile-time boolean, not a runtime check. `__LOCAL__` is
 * substituted literally, so `if (__LOCAL__)` becomes `if (false)` in the
 * static build and Rollup drops the branch -- along with the dynamically
 * imported chunk behind it. The upload screen is not hidden in the static
 * bundle; it is not in it. `tests/bundle.test.ts` fails if that stops
 * being true.
 */
const APP_MODE = process.env.VITE_APP_MODE === "local" ? "local" : "static";

export default defineConfig({
  // GitHub Pages serves a project site under /<repo>/; pages.yml passes it in.
  base: process.env.VITE_BASE ?? "/",
  plugins: [react()],
  define: {
    __LOCAL__: JSON.stringify(APP_MODE === "local"),
    __APP_MODE__: JSON.stringify(APP_MODE),
  },
  server: {
    // Reachable from the phone over the LAN, which is how the admin uploads.
    host: true,
    port: Number(process.env.PORT) || 5173,
  },
});
