import { execFileSync } from "node:child_process";
import { readFileSync, rmSync } from "node:fs";
import { readdir } from "node:fs/promises";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { beforeAll, describe, expect, it } from "vitest";

/**
 * The static build must not contain the admin half.
 *
 * Not hidden behind a route, not guarded by a runtime flag: absent. The site
 * is public and has no backend, so anything shipped with it is shipped to
 * everyone. `__LOCAL__` is substituted with a literal at build time and Rollup
 * drops the dead branch -- but that is an optimisation, and optimisations
 * quietly stop applying when someone refactors the condition into a variable.
 * This test builds both modes for real and reads what came out.
 */

const FRONTEND = fileURLToPath(new URL("..", import.meta.url));

/** Strings that must never reach a competitor's browser. */
const ADMIN_FINGERPRINTS = [
  "gymrats-admin-upload", // UPLOAD_MARKER, in modes/local/AdminApp.tsx
  "Escolher prints",
  "image/*", // the file picker's accept attribute
  "createObjectURL",
];

function build(mode: "static" | "local", outDir: string): void {
  rmSync(join(FRONTEND, outDir), { recursive: true, force: true });
  execFileSync("npx", ["vite", "build", "--outDir", outDir], {
    cwd: FRONTEND,
    env: { ...process.env, VITE_APP_MODE: mode },
    stdio: "pipe",
  });
}

async function filesUnder(dir: string): Promise<string[]> {
  const entries = await readdir(join(FRONTEND, dir), {
    recursive: true,
    withFileTypes: true,
  });
  return entries
    .filter((entry) => entry.isFile())
    .map((entry) => join(entry.parentPath ?? entry.path, entry.name));
}

/** Concatenate the whole build, so nothing hides in a lazily loaded chunk. */
async function bundleText(dir: string): Promise<string> {
  const paths = await filesUnder(dir);
  return paths
    .filter((path) => /\.(js|css|html)$/.test(path))
    .map((path) => readFileSync(path, "utf8"))
    .join("\n");
}

describe("the static build", () => {
  let staticBundle: string;
  let localBundle: string;
  let staticFiles: string[];

  beforeAll(async () => {
    build("static", "dist-test-static");
    build("local", "dist-test-local");
    staticBundle = await bundleText("dist-test-static");
    localBundle = await bundleText("dist-test-local");
    staticFiles = (await filesUnder("dist-test-static")).map((path) =>
      relative(FRONTEND, path),
    );
  });

  it.each(ADMIN_FINGERPRINTS)("does not ship %s", (fingerprint) => {
    expect(staticBundle).not.toContain(fingerprint);
  });

  it("does not ship a chunk built from modes/local", () => {
    expect(staticFiles.some((path) => /admin|local/i.test(path))).toBe(false);
  });

  it("makes no calls to the API", () => {
    expect(staticBundle).not.toContain("/api/");
    expect(staticBundle).not.toContain("multipart/form-data");
  });

  it("still reads the published JSON", () => {
    // The path is built from BASE_URL, so only the tail survives as a literal.
    expect(staticBundle).toContain("index.json");
    expect(staticBundle).toContain("months/");
    expect(staticBundle).toContain("season/");
  });

  it("ships the data the site reads", () => {
    expect(staticFiles).toContain(join("dist-test-static", "data", "index.json"));
    expect(staticFiles.some((path) => path.endsWith(join("months", "2026-06.json")))).toBe(
      true,
    );
  });

  /*
   * Without this the suite would pass green on the day someone renames the
   * marker, or deletes the admin screen entirely: absent from a build that
   * never had it is not the same as compiled out.
   */
  it.each(ADMIN_FINGERPRINTS)("is what removed %s, not the source", (fingerprint) => {
    expect(localBundle).toContain(fingerprint);
  });
});
