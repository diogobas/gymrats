const REPO = "diogobas/gymrats";
const WORKFLOW = "refresh-data.yml";
const TTL = 15 * 60;
const encoder = new TextEncoder();
const MONTH = /^2026-(0[1-9]|1[0-2])$/;

class ClientError extends Error {
  constructor(message, status = 400) { super(message); this.status = status; }
}

async function readJson(stream, limit = 4096) {
  const reader = stream?.getReader();
  if (!reader) throw new ClientError("Informe os dados da solicitação.");
  const chunks = [];
  let size = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > limit) { await reader.cancel(); throw new ClientError("Requisição muito grande.", 413); }
    chunks.push(value);
  }
  try { return JSON.parse(await new Blob(chunks).text()); }
  catch { throw new ClientError("Formato inválido."); }
}

async function publicJson(url) {
  // This repository and its published results are public. No extra GitHub
  // Contents permission or private token is needed to read the review.
  const response = await fetch(url, { headers: { "User-Agent": "gymrats-manual-refresh" }, signal: AbortSignal.timeout(15000) });
  if (!response.ok) throw new Error("Public review unavailable");
  return readJson(response.body, 512 * 1024);
}

async function reviewState(month) {
  const { sha } = await publicJson(`https://api.github.com/repos/${REPO}/commits/master`);
  if (!/^[a-f0-9]{40}$/.test(sha)) throw new Error("Invalid revision");
  const root = `https://raw.githubusercontent.com/${REPO}/${sha}/frontend/public/data`;
  const index = await publicJson(`${root}/index.json`);
  const months = index.months.filter(item => MONTH.test(item.month) && item.pending_review && item.provisional);
  if (!month) return { revision: sha, months };
  if (!months.some(item => item.month === month)) throw new ClientError("Este mês não está aguardando fechamento. Reabra a conferência.", 409);
  const document = await publicJson(`${root}/months/${month}.json`);
  if (document.month !== month || !document.pending_review || !document.provisional) throw new ClientError("Os dados mudaram. Reabra a conferência.", 409);
  return { revision: sha, months, month: document };
}

function validateClosure(document) {
  const month = document.month;
  const end = new Date(Date.UTC(2026, Number(month.slice(-2)), 0)).toISOString().slice(0, 10);
  const today = new Intl.DateTimeFormat("en-CA", { timeZone: "America/Sao_Paulo", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
  if (document.data_through !== end || today <= end) throw new ClientError("O mês ainda não tem o período completo para fechamento.", 409);
  if (document.unresolved_ties.length) throw new ClientError("Resolva os empates pendentes antes de fechar o mês.", 409);
}

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
  return { id: run.id, title: run.display_title, status: run.status, conclusion: run.conclusion, url: `https://github.com/${REPO}/actions/runs/${run.id}`, created_at: run.created_at };
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
        const body = await readJson(request.body);
        if (!body || typeof body.username !== "string" || typeof body.password !== "string") return json({ error: "Informe usuário e senha." }, 400);
        if (!await credentialsMatch(body.username, body.password, env)) return json({ error: "Usuário ou senha inválidos." }, 401);
        return json({ token: await issueToken(env), expires_in: TTL });
      }
      if (!await authorized(request, env)) return json({ error: "Entre novamente para continuar." }, 401);
      if (path === "/review" && request.method === "GET") {
        const month = new URL(request.url).searchParams.get("month");
        if (month !== null && !MONTH.test(month)) throw new ClientError("Escolha um mês de 2026.");
        return json(await reviewState(month));
      }
      if (path === "/close" && request.method === "POST") {
        if (!request.headers.get("Content-Type")?.startsWith("application/json")) throw new ClientError("Formato inválido.", 415);
        const body = await readJson(request.body);
        if (!body || !MONTH.test(body.month) || !/^[a-f0-9]{40}$/.test(body.revision) || body.confirmed !== true) throw new ClientError("Escolha o mês e confirme a revisão dos resultados.");
        const reviewed = await reviewState(body.month);
        if (body.revision !== reviewed.revision) throw new ClientError("Os dados mudaram. Reabra a conferência e confirme novamente.", 409);
        validateClosure(reviewed.month);
        if (!(await env.DISPATCH_LIMIT.limit({ key: "manual-refresh" })).success) throw new ClientError("Aguarde um minuto antes de tentar novamente.", 429);
        const result = await github(env, `workflows/${WORKFLOW}/runs?branch=master&per_page=100`);
        if (result.workflow_runs.some(run => run.status !== "completed")) throw new ClientError("Há uma atualização ou fechamento em andamento. Aguarde e reabra a conferência.", 409);
        const run = await github(env, `workflows/${WORKFLOW}/dispatches`, {
          method: "POST",
          body: JSON.stringify({ ref: "master", return_run_details: true, inputs: { operation: "close", month: body.month, reviewed_revision: body.revision } }),
        });
        if (!Number.isSafeInteger(run.workflow_run_id) || run.workflow_run_id <= 0) throw new Error("Invalid dispatch response");
        return json({ run: publicRun({ id: run.workflow_run_id, display_title: `Fechar ${body.month}`, status: "queued", conclusion: null, created_at: new Date().toISOString() }) }, 202);
      }
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
    } catch (error) {
      if (error instanceof ClientError) return json({ error: error.message }, error.status);
      // Never relay upstream bodies, tokens, credentials, or request headers.
      return json({ error: "Não foi possível consultar ou iniciar a atualização. Confira o GitHub Actions antes de tentar novamente." }, 502);
    }
  },
};
