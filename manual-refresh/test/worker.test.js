import { afterEach, test } from "node:test";
import assert from "node:assert/strict";
import worker from "../src/index.js";

const origin = "https://diogobas.github.io";
const originalFetch = globalThis.fetch;
afterEach(() => { globalThis.fetch = originalFetch; });
function environment() {
  return {
    SITE_ORIGIN: origin, ADMIN_USERNAME: "admin", ADMIN_PASSWORD: "test-password",
    SESSION_SECRET: "test-only-signing-key-with-32-characters", GITHUB_TOKEN: "test-only-github-token",
    LOGIN_LIMIT: { limit: async () => ({ success: true }) },
    DISPATCH_LIMIT: { limit: async () => ({ success: true }) },
  };
}
function call(env, path, { token, body, method, from = origin } = {}) {
  return worker.fetch(new Request(`https://worker.example${path}`, {
    method: method ?? (body === undefined ? "GET" : "POST"),
    headers: { Origin: from, ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(body === undefined ? {} : { "Content-Type": "application/json" }) },
    body: body === undefined ? undefined : JSON.stringify(body),
  }), env);
}
async function login(env) {
  const response = await call(env, "/login", { body: { username: "admin", password: "test-password" } });
  assert.equal(response.status, 200);
  return (await response.json()).token;
}

test("rejects unauthenticated requests and foreign origins without contacting GitHub", async () => {
  globalThis.fetch = () => { throw new Error("must not fetch"); };
  const env = environment();
  assert.equal((await call(env, "/refresh", { body: {} })).status, 401);
  const response = await call(env, "/login", { from: "https://other.example", body: {} });
  assert.equal(response.status, 403);
  assert.equal(response.headers.get("Access-Control-Allow-Origin"), null);
  const preflight = await call(env, "/refresh", { method: "OPTIONS" });
  assert.equal(preflight.status, 204);
  assert.equal(preflight.headers.get("Access-Control-Allow-Origin"), origin);
});

test("login rejects invalid credentials, oversized and malformed input", async () => {
  const env = environment();
  for (const body of [{ username: "admin", password: "wrong" }, { username: "wrong", password: "test-password" }]) {
    assert.equal((await call(env, "/login", { body })).status, 401);
  }
  assert.equal((await call(env, "/login", { body: null })).status, 400);
  assert.equal((await call(env, "/login", { body: { password: "x".repeat(5000) } })).status, 413);
  const bad = new Request("https://worker.example/login", { method: "POST", headers: { Origin: origin, "Content-Type": "application/json" }, body: "{" });
  assert.equal((await worker.fetch(bad, env)).status, 400);
});

test("missing configuration and rate limits fail closed", async () => {
  const env = environment();
  env.ADMIN_PASSWORD = "";
  assert.equal((await call(env, "/login", { body: {} })).status, 503);
  env.ADMIN_PASSWORD = "test-password";
  env.LOGIN_LIMIT.limit = async () => ({ success: false });
  assert.equal((await call(env, "/login", { body: {} })).status, 429);
});

test("session rejects tampering, expiration, and signing key rotation", async () => {
  const env = environment();
  const token = await login(env);
  const parts = token.split(".");
  parts[1] = "tampered";
  assert.equal((await call(env, "/runs", { token: parts.join(".") })).status, 401);
  const originalNow = Date.now;
  try {
    Date.now = () => originalNow() + 901000;
    assert.equal((await call(env, "/runs", { token })).status, 401);
  } finally { Date.now = originalNow; }
  env.SESSION_SECRET = "rotated-test-signing-key";
  assert.equal((await call(env, "/runs", { token })).status, 401);
});

test("dispatches only the fixed workflow and branch, returning the exact run", async () => {
  const env = environment();
  const token = await login(env);
  const calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push({ url, init });
    return Response.json(url.endsWith("/dispatches") ? { workflow_run_id: 123 } : { workflow_runs: [] });
  };
  const response = await call(env, "/refresh", { token, body: { ref: "evil", workflow: "other.yml" } });
  assert.equal(response.status, 202);
  const data = await response.json();
  assert.equal(data.run.id, 123);
  assert.equal(data.existing, false);
  assert.equal(calls[1].url, "https://api.github.com/repos/diogobas/gymrats/actions/workflows/refresh-data.yml/dispatches");
  assert.deepEqual(JSON.parse(calls[1].init.body), { ref: "master", return_run_details: true });
  assert.equal(response.headers.get("Cache-Control"), "no-store");
  assert.equal(JSON.stringify(data).includes(env.GITHUB_TOKEN), false);
});

test("reuses active runs and limits repeated dispatches", async () => {
  const env = environment();
  const token = await login(env);
  let calls = 0;
  globalThis.fetch = async () => { calls++; return Response.json({ workflow_runs: [{ id: 234, status: "in_progress" }] }); };
  const response = await call(env, "/refresh", { token, body: {} });
  assert.equal((await response.json()).existing, true);
  assert.equal(calls, 1);
  env.DISPATCH_LIMIT.limit = async () => ({ success: false });
  assert.equal((await call(env, "/refresh", { token, body: {} })).status, 429);
  assert.equal(calls, 1);
});

test("returns limited run metadata and hides upstream errors and secrets", async () => {
  const env = environment();
  const token = await login(env);
  globalThis.fetch = async () => Response.json({ workflow_runs: [{ id: 345, status: "completed", conclusion: "success", created_at: "2026-10-30T00:00:00Z", secret: "private", html_url: "https://evil.example" }] });
  const response = await call(env, "/runs", { token });
  const data = await response.json();
  assert.equal(data.runs[0].url, "https://github.com/diogobas/gymrats/actions/runs/345");
  assert.equal(JSON.stringify(data).includes("private"), false);
  globalThis.fetch = async () => new Response(env.GITHUB_TOKEN, { status: 403 });
  const failure = await call(env, "/runs", { token });
  assert.equal(failure.status, 502);
  assert.equal((await failure.text()).includes(env.GITHUB_TOKEN), false);
});
