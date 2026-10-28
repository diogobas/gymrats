/** Verify every published month and the season in a real browser, without API mocks. */
import assert from 'node:assert/strict';
import { readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const load = path => JSON.parse(readFileSync(new URL(path, import.meta.url), 'utf8'));
const index = load('../public/data/index.json');
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
  throw Error('Timed out waiting for ' + expression);
}
await send('Page.enable');
await send('Runtime.enable');
await send('Network.enable');
for (const [label, width, height] of [['desktop', 1440, 1000], ['mobile', 390, 844]]) {
  await send('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile: label === 'mobile' });
  await send('Page.navigate', { url: siteUrl + '?season-test=' + Date.now() + '#/mes/2026-01' });
  for (const entry of index.months) {
    const doc = load(`../public/data/months/${entry.month}.json`);
    await evaluate(`location.hash = '#/mes/${entry.month}'`);
    const ready = doc.ranked_count > 0
      ? `document.querySelector('.standings button.row .cell--name')?.textContent.startsWith(${JSON.stringify(doc.standings[0].name)})`
      : `document.body.textContent.includes('Nenhum classificado:')`;
    await until(`document.querySelector('.picker .is-current')?.getAttribute('href') === '#/mes/${entry.month}' && document.querySelectorAll('.standings button.row').length === ${doc.ranked_count} && (${ready})`);
    assert.equal(await evaluate("document.querySelectorAll('.picker a').length"), index.months.filter(item => item.year === entry.year).length);
    assert.equal(await evaluate("document.body.textContent.includes('Apurado à mão')"), false);
    assert.equal(await evaluate("document.body.textContent.includes('Mês em andamento')"), !!entry.provisional && !entry.pending_review);
    assert.equal(await evaluate("document.body.textContent.includes('Hustle desconsiderado neste mês.')"), !!doc.ignore_hustle);
    if (doc.ranked_count > 0) {
      await evaluate("(() => { const row = document.querySelector('.standings button.row'); if (row.getAttribute('aria-expanded') !== 'true') row.click(); })()");
      await until("!!document.querySelector('.detail')");
      assert.equal(await evaluate("document.querySelector('.detail').textContent.includes('Calorias')"), true);
      if (doc.ignore_hustle) {
        assert.equal(await evaluate("document.querySelector('.detail').textContent.includes('Hustle · desconsiderado')"), true);
        assert.equal(await evaluate("document.querySelector('.standings .row .cell--part').textContent"), '—');
      }
    }
    assert.equal(await evaluate('document.documentElement.scrollWidth > innerWidth'), false, label + ' ' + entry.month);
    if (entry.provisional || entry.month === '2026-09') {
      const screenshot = await send('Page.captureScreenshot', { format: 'png' });
      writeFileSync(join(tmpdir(), `gymrats-${entry.month}-${label}.png`), Buffer.from(screenshot.data, 'base64'));
    }
  }
  for (const year of index.years) {
    await evaluate(`location.hash = '#/ano/${year}'`);
    const season = load(`../public/data/season/${year}.json`);
    await until(`document.querySelector('.title')?.textContent === 'Acumulado de ${year}' && document.querySelector('.season tbody tr .col--name')?.textContent === ${JSON.stringify(season.standings[0].name)} && document.querySelectorAll('.season thead th').length === ${season.months.length + 3}`);
    assert.equal(await evaluate("document.querySelector('.season tbody tr .col--total').textContent"), String(season.standings[0].total));
    assert.equal(await evaluate("document.body.textContent.includes('Acumulado provisório')"), !!season.provisional);
    assert.equal(await evaluate("document.body.textContent.includes('Acumulado incompleto')"), !!season.missing_months?.length);
    assert.equal(await evaluate('document.documentElement.scrollWidth > innerWidth'), false, label + ' season ' + year);
  }
  console.log(`${label}: all published monthly tables, expanded values and annual snapshot verified`);
}
assert.deepEqual(exceptions, []);
assert.deepEqual(apiCalls, []);
ws.close();
