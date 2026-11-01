const REPO = "diogobas/gymrats";
const WORKFLOW = "refresh-data.yml";
const TTL = 15 * 60;
const encoder = new TextEncoder();

async function key(secret) {
  return crypto.subtle.importKey("raw", encoder.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign", "verify"]);
}

function hex(bytes) {
  return Array.from(new Uint8Array(bytes), byte => byte.toString(16).padStart(2, "0")).join("");
}

async function issueToken(env) {
  const payload = `${Math.floor(Date.now() / 1000) + TTL}.${crypto.randomUUID()}`;
  const signature = await crypto.subtle.sign("HMAC", await key(env.SESSION_SECRET), encoder.encode(payload));
  return `${payload}.${hex(signature)}`;
}

async function authorized(request, env) {
  const token = request.headers.get("Authorization")?.replace(/^Bearer /, "") ?? "";
  const parts = token.split(".");
  if (parts.length !== 3 || !/^\d+$/.test(parts[0]) || !/^[a-f0-9]{64}$/.test(parts[2])) return false;
  const expires = Number(parts[0]);
  const now = Math.floor(Date.now() / 1000);
  if (expires <= now || expires > now + TTL) return false;
  const signature = Uint8Array.from(parts[2].match(/../g), byte => parseInt(byte, 16));
  return crypto.subtle.verify("HMAC", await key(env.SESSION_SECRET), signature, encoder.encode(`${parts[0]}.${parts[1]}`));
}

async function credentialsMatch(username, password, env) {
  // HMAC verification avoids timing-sensitive comparisons of either secret.
  const credentialsKey = await key(env.SESSION_SECRET);
  const expected = await crypto.subtle.sign("HMAC", credentialsKey, encoder.encode(JSON.stringify([env.ADMIN_USERNAME, env.ADMIN_PASSWORD])));
  return crypto.subtle.verify("HMAC", credentialsKey, expected, encoder.encode(JSON.stringify([username, password])));
}

async function github(env, path, init = {}) {
  const response = await fetch(`https://api.github.com/repos/${REPO}/actions/${path}`, {
    ...init,
    headers: {
      Accept: "application/vnd.github+json",
      Authorization: `Bearer ${env.GITHUB_TOKEN}`,
      "Content-Type": "application/json",
      "User-Agent": "gymrats-manual-refresh",
      "X-GitHub-Api-Version": "2026-03-10",
    },
    signal: AbortSignal.timeout(15000),
  });
  if (!response.ok) throw new Error("GitHub request failed");
  return response.json();
}

function publicRun(run) {
  return { id: run.id, status: run.status, conclusion: run.conclusion, url: `https://github.com/${REPO}/actions/runs/${run.id}`, created_at: run.created_at };
}

export default {
  async fetch(request, env) {
    const headers = { "Cache-Control": "no-store", "Vary": "Origin", "X-Content-Type-Options": "nosniff" };
    const json = (data, status = 200) => Response.json(data, { status, headers });
    if (request.headers.get("Origin") !== env.SITE_ORIGIN) return json({ error: "Origem não permitida." }, 403);
    headers["Access-Control-Allow-Origin"] = env.SITE_ORIGIN;
    headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS";
    headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type";
    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers });
    if (![env.ADMIN_USERNAME, env.ADMIN_PASSWORD, env.SESSION_SECRET, env.GITHUB_TOKEN].every(Boolean)) {
      return json({ error: "Serviço de atualização ainda não configurado." }, 503);
    }
    const path = new URL(request.url).pathname;
    try {
      if (path === "/login" && request.method === "POST") {
        const limited = await env.LOGIN_LIMIT.limit({ key: `login:${request.headers.get("CF-Connecting-IP") ?? "unknown"}` });
        if (!limited.success) return json({ error: "Muitas tentativas. Aguarde um minuto." }, 429);
        if (!request.headers.get("Content-Type")?.startsWith("application/json")) return json({ error: "Formato inválido." }, 415);
        // Bound credential bodies even when Content-Length is absent or untrusted.
        const reader = request.body?.getReader();
        if (!reader) return json({ error: "Informe usuário e senha." }, 400);
        const chunks = [];
        let size = 0;
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          size += value.byteLength;
          if (size > 4096) { await reader.cancel(); return json({ error: "Requisição muito grande." }, 413); }
          chunks.push(value);
        }
        let body;
        try { body = JSON.parse(await new Blob(chunks).text()); }
        catch { return json({ error: "Formato inválido." }, 400); }
        if (!body || typeof body.username !== "string" || typeof body.password !== "string") return json({ error: "Informe usuário e senha." }, 400);
        if (!await credentialsMatch(body.username, body.password, env)) return json({ error: "Usuário ou senha inválidos." }, 401);
        return json({ token: await issueToken(env), expires_in: TTL });
      }
      if (!await authorized(request, env)) return json({ error: "Entre novamente para continuar." }, 401);
      if (path === "/runs" && request.method === "GET") {
        const result = await github(env, `workflows/${WORKFLOW}/runs?branch=master&per_page=10`);
        return json({ runs: result.workflow_runs.map(publicRun) });
      }
      if (path === "/refresh" && request.method === "POST") {
        if (!(await env.DISPATCH_LIMIT.limit({ key: "manual-refresh" })).success) return json({ error: "Aguarde um minuto antes de tentar novamente." }, 429);
        const result = await github(env, `workflows/${WORKFLOW}/runs?branch=master&per_page=100`);
        const active = result.workflow_runs.find(run => run.status !== "completed");
        if (active) return json({ run: publicRun(active), existing: true });
        const run = await github(env, `workflows/${WORKFLOW}/dispatches`, {
          method: "POST",
          body: JSON.stringify({ ref: "master", return_run_details: true }),
        });
        if (!Number.isSafeInteger(run.workflow_run_id) || run.workflow_run_id <= 0) throw new Error("Invalid dispatch response");
        return json({ run: publicRun({ id: run.workflow_run_id, status: "queued", conclusion: null, created_at: new Date().toISOString() }), existing: false }, 202);
      }
      return json({ error: "Rota não encontrada." }, 404);
    } catch {
      // Never relay upstream bodies, tokens, credentials, or request headers.
      return json({ error: "Não foi possível consultar ou iniciar a atualização. Confira o GitHub Actions antes de tentar novamente." }, 502);
    }
  },
};
