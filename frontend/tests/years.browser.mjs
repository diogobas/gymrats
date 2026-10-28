/** Exercise year navigation against a multi-year static-data fixture. */
import assert from 'node:assert/strict';
import { readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const load = path => JSON.parse(readFileSync(new URL(path, import.meta.url), 'utf8'));
const publishedIndex = load('../public/data/index.json');
const index = { ...publishedIndex, years: [2026], months: publishedIndex.months.filter(item => item.year === 2026) };
const debugUrl = process.env.CDP_URL ?? 'http://127.0.0.1:9222';
const siteUrl = process.env.ADMIN_URL ?? 'http://127.0.0.1:5173/';
const tabs = await (await fetch(debugUrl + '/json')).json();
const ws = new WebSocket(tabs.find(tab => tab.type === 'page').webSocketDebuggerUrl);
await new Promise(resolve => ws.addEventListener('open', resolve, { once: true }));
let sequence = 0;
const pending = new Map();
const exceptions = [];
const apiCalls = [];
function send(method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = ++sequence;
    pending.set(id, { resolve, reject });
    ws.send(JSON.stringify({ id, method, params }));
  });
}
ws.addEventListener('message', event => {
  const message = JSON.parse(event.data);
  if (message.id) {
    const handler = pending.get(message.id);
    pending.delete(message.id);
    message.error ? handler.reject(message.error) : handler.resolve(message.result);
  } else if (message.method === 'Runtime.exceptionThrown') exceptions.push(message.params);
  else if (message.method === 'Network.requestWillBeSent' && message.params.request.url.includes('/api/'))
    apiCalls.push(message.params.request.url);
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
  throw Error('Timed out waiting for ' + expression + '\n' + await evaluate('document.body.innerText'));
}
await send('Page.enable');
await send('Runtime.enable');
await send('Network.enable');

const historical = { ...load('../public/data/season/2026.json'), year: 2025, months: ['2025-12'], provisional: false,
  missing_months: Array.from({ length: 11 }, (_, i) => `2025-${String(i + 1).padStart(2, '0')}`),
  standings: [{ position: 1, name: 'Histórico', total: 1, by_month: { '2025-12': 1 }, imputed_months: [], tiebreak: null }], unresolved_ties: [] };
let manifest = { ...index, years: [2025, 2026], months: [{ month: '2025-12', year: 2025, detail: false }, ...index.months] };
const unexpected = [];
ws.addEventListener('message', async event => {
  const message = JSON.parse(event.data);
  if (message.method !== 'Fetch.requestPaused') return;
  const { requestId, request } = message.params;
  const path = new URL(request.url).pathname.split('/data/')[1];
  let doc;
  if (path === 'index.json') doc = manifest;
  else if (path === 'season/2025.json') doc = historical;
  else if (path === 'season/2026.json' || index.months.some(m => path === `months/${m.month}.json`)) doc = load('../public/data/' + path);
  else unexpected.push(path);
  await send('Fetch.fulfillRequest', { requestId, responseCode: doc ? 200 : 404,
    responseHeaders: [{ name: 'Content-Type', value: 'application/json' }], body: Buffer.from(JSON.stringify(doc ?? {})).toString('base64') });
});
await send('Fetch.enable', { patterns: [{ urlPattern: siteUrl + 'data/*' }] });
const select = value => evaluate(`(() => { const s = document.querySelector('.year-picker select'); s.value = '${value}'; s.dispatchEvent(new Event('change', { bubbles: true })); })()`);
const navigate = hash => evaluate(`location.hash = '${hash}'`);
for (const [label, width, height] of [['desktop', 1440, 1000], ['mobile', 390, 844]]) {
  await send('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile: label === 'mobile' });
  await send('Page.navigate', { url: siteUrl + '?years-test=' + Date.now() + '#/' });
  await until("document.querySelector('.standings button.row') !== null");
  assert.deepEqual(await evaluate("Array.from(document.querySelectorAll('.year-picker option'), o => o.value)"), ['2026', '2025']);
  await select(2025);
  await until("document.querySelector('.standings--plain')?.textContent.includes('Histórico')");
  assert.equal(await evaluate("location.hash"), '#/mes/2025-12');
  assert.equal(await evaluate("document.querySelectorAll('.picker a').length"), 1);
  assert.equal(await evaluate("document.querySelector('.tabs a:nth-child(2)').getAttribute('href')"), '#/ano/2025');
  await evaluate("document.querySelector('.tabs a:nth-child(2)').click()");
  await until("document.querySelector('.season')?.textContent.includes('Histórico')");
  assert.equal(await evaluate("document.querySelector('.tabs a').getAttribute('href')"), '#/mes/2025-12');
  assert.equal(await evaluate("document.body.textContent.includes('Acumulado incompleto')"), true);
  await select(2026);
  await until("document.querySelector('.title')?.textContent === 'Acumulado de 2026'");
  await evaluate('history.back()');
  await until("document.querySelector('.title')?.textContent === 'Acumulado de 2025'");
  await evaluate('history.forward()');
  await until("document.querySelector('.title')?.textContent === 'Acumulado de 2026'");
  await evaluate("document.querySelector('.tabs a').click()");
  await until("document.querySelector('.picker .is-current')?.getAttribute('href') === '#/mes/" + index.latest_month + "'");
  assert.equal(await evaluate("document.querySelectorAll('.picker a').length"), index.months.length);
  await select(2025);
  await until("document.querySelector('.standings--plain') !== null");
  await select(2026);
  await until("document.querySelector('.picker .is-current')?.getAttribute('href') === '#/mes/" + index.latest_month + "'");
  await until("document.body.textContent.includes('Mês em andamento') || document.body.textContent.includes('Aguardando fechamento')");
  await evaluate("document.querySelector('.year-picker select').focus()");
  assert.equal(await evaluate("document.activeElement.tagName"), 'SELECT');
  await send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'ArrowDown', code: 'ArrowDown', windowsVirtualKeyCode: 40 });
  await send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'ArrowDown', code: 'ArrowDown', windowsVirtualKeyCode: 40 });
  await send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 });
  await send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 });
  await until("location.hash === '#/mes/2025-12'");
  assert.equal(await evaluate('document.documentElement.scrollWidth > innerWidth'), false);
  await navigate('#/ano/1999');
  await until("document.body.textContent.includes('Esse ano não tem resultados publicados')");
  assert.equal(await evaluate("document.querySelector('.year-picker select').value"), '');
  await select(2025);
  await until("document.querySelector('.season')?.textContent.includes('Histórico')");
  await send('Page.reload');
  await until("document.querySelector('.season')?.textContent.includes('Histórico')");
  await navigate('#/mes/2026-12');
  await until("document.body.textContent.includes('Esse mês ainda não foi apurado')");
  await navigate('#/mes/1999-01');
  await until("document.body.textContent.includes('Esse ano não tem resultados publicados')");
  assert.equal(await evaluate('document.documentElement.scrollWidth > innerWidth'), false);
  console.log(label + ': year selection, tabs, history, reload, unavailable results and layout verified');
}
manifest = { ...index, years: [2026] };
await send('Page.navigate', { url: siteUrl + '?single-year=1#/' });
await until("document.querySelector('.year-picker option') !== null");
assert.equal(await evaluate("document.querySelectorAll('.year-picker option').length"), 1);
manifest = { ...index, years: [], months: [], latest_month: null, latest_year: null };
await send('Page.navigate', { url: siteUrl + '?empty=1#/' });
await until("document.body.textContent.includes('Nenhum resultado publicado')");
assert.equal(await evaluate("document.querySelector('.year-picker')"), null);
assert.deepEqual(unexpected, []);
assert.deepEqual(exceptions, []);
assert.deepEqual(apiCalls, []);
ws.close();
