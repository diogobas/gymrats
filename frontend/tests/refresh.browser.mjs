// Browser checks with a fictitious service: never closes or updates real data.
import assert from 'node:assert/strict';
import { readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const document = JSON.parse(readFileSync(new URL('../public/data/months/2026-06.json', import.meta.url)));
const month = { ...document, month: '2026-07', provisional: true, pending_review: true, data_through: '2026-07-31' };
const publicIndex = JSON.parse(readFileSync(new URL('../public/data/index.json', import.meta.url)));
const tabs = await (await fetch((process.env.CDP_URL ?? 'http://127.0.0.1:9222') + '/json')).json();
const ws = new WebSocket(tabs.find(tab => tab.type === 'page').webSocketDebuggerUrl);
await new Promise(resolve => ws.addEventListener('open', resolve, { once: true }));
let sequence = 0, stale = true, attempts = 0, started = false;
const pending = new Map(), errors = [];
function send(method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = ++sequence; pending.set(id, { resolve, reject });
    ws.send(JSON.stringify({ id, method, params }));
  });
}
ws.addEventListener('message', async event => {
  const message = JSON.parse(event.data);
  if (message.id) {
    const callback = pending.get(message.id); pending.delete(message.id);
    message.error ? callback.reject(message.error) : callback.resolve(message.result);
    return;
  }
  if (message.method === 'Runtime.exceptionThrown') errors.push(message.params);
  if (message.method !== 'Fetch.requestPaused') return;
  const { requestId, request } = message.params;
  const url = new URL(request.url);
  let body = {}, status = 200;
  try {
    if (url.pathname.endsWith('/data/index.json')) {
      body = structuredClone(publicIndex);
      body.latest_month = '2026-07';
      body.latest_completed_month = started ? '2026-07' : '2026-06';
      const entry = body.months.find(item => item.month === '2026-07');
      delete entry.provisional; delete entry.pending_review; delete entry.data_through;
      if (!started) Object.assign(entry, { provisional: true, pending_review: true, data_through: '2026-07-31' });
    }
    else if (url.pathname.endsWith('/data/months/2026-07.json')) {
      body = { ...month };
      if (started) { delete body.provisional; delete body.pending_review; delete body.data_through; }
    }
    else if (request.method === 'OPTIONS') status = 204;
    else if (url.pathname === '/login') body = { token: 'offline-session', expires_in: 900 };
    else {
      assert.equal(request.headers.Authorization ?? request.headers.authorization, 'Bearer offline-session');
      if (url.pathname === '/runs') body = { runs: started ? [{ id: 1, status: 'queued', conclusion: null, created_at: '2026-08-01T03:00:00Z', url: 'https://github.com/diogobas/gymrats/actions/runs/1' }] : [] };
      else if (url.pathname === '/review') body = {
        revision: (stale ? 'a' : 'b').repeat(40), months: [{ month: '2026-07', provisional: true, pending_review: true }],
        ...(url.searchParams.has('month') ? { month } : {}),
      };
      else if (url.pathname === '/close') {
        attempts++;
        const payload = JSON.parse(request.postData);
        assert.equal(payload.month, '2026-07'); assert.equal(payload.confirmed, true);
        assert.equal(payload.revision, (stale ? 'a' : 'b').repeat(40));
        if (stale) { stale = false; status = 409; body = { error: 'Os dados mudaram. Reabra a conferência e confirme novamente.' }; }
        else { started = true; body = { run: { id: 1, status: 'queued', conclusion: null, created_at: '2026-08-01T03:00:00Z', url: 'https://github.com/diogobas/gymrats/actions/runs/1' } }; }
      } else throw Error('Unexpected service request: ' + url.pathname);
    }
  } catch (error) { errors.push(String(error)); status = 500; body = { error: String(error) }; }
  await send('Fetch.fulfillRequest', { requestId, responseCode: status,
    responseHeaders: [{ name: 'Content-Type', value: 'application/json' }, { name: 'Access-Control-Allow-Origin', value: '*' }, { name: 'Access-Control-Allow-Headers', value: '*' }, { name: 'Access-Control-Allow-Methods', value: '*' }],
    body: status === 204 ? '' : Buffer.from(JSON.stringify(body)).toString('base64') });
});
async function evaluate(expression) {
  const result = await send('Runtime.evaluate', { expression, returnByValue: true });
  assert.equal(result.exceptionDetails, undefined);
  return result.result.value;
}
async function until(expression) {
  for (let i = 0; i < 100; i++) {
    if (await evaluate(expression)) return;
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  throw Error('Timed out: ' + expression + '\n' + await evaluate('document.body.innerText'));
}
async function click(text) {
  await evaluate(`Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes(${JSON.stringify(text)})).click()`);
}
try {
  await send('Page.enable'); await send('Runtime.enable');
  await send('Fetch.enable', { patterns: [{ urlPattern: 'https://refresh.test/*' }, { urlPattern: '*/data/index.json' }, { urlPattern: '*/data/months/2026-07.json' }] });
  for (const [label, width, height] of [['desktop', 1440, 1000], ['mobile', 390, 844]]) {
    stale = true; attempts = 0; started = false;
    await send('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile: label === 'mobile' });
    await send('Page.navigate', { url: (process.env.ADMIN_URL ?? 'http://127.0.0.1:5173/') + '?refresh-test=' + Date.now() + '#/mes/2026-07' });
    await until("document.querySelector('.picker .is-current')?.textContent.includes('revisar')");
    await evaluate("location.hash = '#/atualizar'");
    await until("!!document.querySelector('input[name=password]')");
    await evaluate(`['username','password'].forEach(name => {
      const e = document.querySelector('input[name='+name+']');
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(e,'offline-test');
      e.dispatchEvent(new Event('input',{bubbles:true}));
    }); document.querySelector('form').requestSubmit()`);
    await until("!!document.querySelector('.close-month select')");
    await click('Abrir / atualizar');
    await until("!!document.querySelector('.close-month__confirmation input')");
    assert.equal(await evaluate("Array.from(document.querySelectorAll('button')).find(b=>b.textContent.startsWith('Confirmar e fechar')).disabled"), true);
    await click('Confirmar e fechar'); assert.equal(attempts, 0);
    await evaluate("document.querySelector('.close-month .standings button.row').click()");
    await until("!!document.querySelector('.close-month .detail')");
    assert.equal(await evaluate('document.documentElement.scrollWidth > innerWidth'), false);
    const screenshot = await send('Page.captureScreenshot', { format: 'png' });
    writeFileSync(join(tmpdir(), `gymrats-fechamento-${label}.png`), Buffer.from(screenshot.data, 'base64'));
    await evaluate("document.querySelector('.close-month__confirmation input').click()");
    await click('Confirmar e fechar');
    await until("document.querySelector('.close-month [role=alert]')?.textContent.includes('Os dados mudaram')");
    assert.equal(await evaluate("!!document.querySelector('.close-month__confirmation input')"), false);
    await click('Abrir / atualizar');
    await until("!!document.querySelector('.close-month__confirmation input')");
    assert.equal(await evaluate("document.querySelector('.close-month__confirmation input').checked"), false);
    await evaluate("document.querySelector('.close-month__confirmation input').click()");
    await click('Confirmar e fechar');
    await until("document.body.textContent.includes('Fechamento solicitado.')");
    assert.equal(attempts, 2); assert.equal(started, true);
    assert.equal(await evaluate("JSON.stringify(localStorage).includes('offline-session') || JSON.stringify(sessionStorage).includes('offline-session')"), false);
    await click('Sair'); await until("!!document.querySelector('input[name=password]')");
    await evaluate("location.hash = '#/mes/2026-07'");
    await until("document.querySelector('.picker .is-current')?.getAttribute('href') === '#/mes/2026-07' && !document.querySelector('.picker .is-current')?.textContent.includes('revisar')");
    assert.equal(await evaluate("document.body.textContent.includes('Aguardando fechamento')"), false);
  }
  assert.deepEqual(errors, []);
  console.log('Protected monthly closing passed on desktop and mobile, including stale review rejection and fresh results on return.');
} finally { await send('Fetch.disable'); ws.close(); }
