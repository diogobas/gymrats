import { readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import assert from 'node:assert/strict';
// All API responses below are offline fixtures. This never contacts GymRats.
const load = path => JSON.parse(readFileSync(new URL(path, import.meta.url), 'utf8'));
const source = load('../../data/months/2026-06.json');
const oldSeason = load('../../tests/fixtures/season-2026.json');
const oldMonths = Object.keys(oldSeason.ranked);
const closedSeason = { schema_version: 1, year: 2026, generated_at: '2026-10-27T16:00:00Z',
  months: oldMonths, unresolved_ties: [], standings: oldSeason.expected.map(row => ({
    ...row, by_month: Object.fromEntries(oldMonths.map((month, i) => [month, row.by_month[i]])),
    imputed_months: oldMonths.filter(month => !oldSeason.ranked[month].includes(row.name)), tiebreak: null,
  })) };
const fixture = {
  participants: load('../../data/participants.json'),
  draft: { run: 'a'.repeat(32), month: '2026-06', revision: 1,
    annual_end_date: '2026-06-30', issues: [],
    tables: Object.entries(source.tables).flatMap(([modality, periods]) =>
      Object.entries(periods).filter(([period, rows]) => Array.isArray(rows) && (period === 'month' || ['distance','duration'].includes(modality)))
        .map(([period, rows]) => ({ key: `${modality}/${period}`, label: `${modality} / ${period}`,
          modality, period, sources: [], rows: rows.map(row => ({ name: row.name,
            raw_value: String(row.value) + (modality === 'duration' ? ' min' : ''),
            value: row.value, resolved_name: row.name, position: row.reported_position ?? null })) }))) },
  preview: { month: load('../public/data/months/2026-06.json'),
    season: closedSeason, issues: [], committed: false,
    replacement: true, revision: 1, preview_token: 'offline-preview',
    annual_end_date: '2026-06-30', differences: [{ name: 'Lorrana', metric: 'hustle',
      period: 'month', previous: 211.31, collected: 217.68260607439217 }] }
};
const adminUrl = process.env.ADMIN_URL ?? 'http://127.0.0.1:5173/';
const debugUrl = process.env.CDP_URL ?? 'http://127.0.0.1:9222';
const tabs = await (await fetch(debugUrl + '/json')).json();
const ws = new WebSocket(tabs.find(tab => tab.type === 'page').webSocketDebuggerUrl);
await new Promise(resolve => ws.addEventListener('open', resolve, { once: true }));
let sequence = 0; const waiting = new Map(); const errors = [];
function send(method, params = {}) { return new Promise((resolve, reject) => {
  const id = ++sequence; waiting.set(id, { resolve, reject }); ws.send(JSON.stringify({ id, method, params }));
}); }
let connected = false, started = false, revision = 1, writes = 0, committing = false, provisional = false;
const run = { id: fixture.draft.run, month: '2026-06', annual_end_date: '2026-06-30', status: 'complete', completed: 7, error: null, created_at: '2026-10-27' };
function previewResponse() {
 const info = provisional ? { provisional: true, data_through: '2026-10-26' } : {};
 return { ...fixture.preview, provisional, revision, replacement: !provisional,
   annual_end_date: run.annual_end_date,
   month: { ...fixture.preview.month, month: run.month, ...info },
   season: provisional ? load('../public/data/season/2026.json') : closedSeason };
}
ws.addEventListener('message', async event => {
 const message = JSON.parse(event.data);
 if (message.id) { const pending = waiting.get(message.id); waiting.delete(message.id); message.error ? pending.reject(message.error) : pending.resolve(message.result); return; }
 if (message.method === 'Runtime.exceptionThrown') errors.push(message.params.exceptionDetails.text);
 if (message.method !== 'Fetch.requestPaused') return;
 const { requestId, request } = message.params; const path = new URL(request.url).pathname.replace('/api', '');
 let body = {};
 if (request.method === 'OPTIONS') body = {};
 else if (path === '/gymrats/session') body = { connected, message: 'Conecte sua conta GymRats.', account: { id: 1, name: 'Admin' } };
 else if (path.endsWith('/session/code')) body = { code_pending: true };
 else if (path.endsWith('/session/verify')) { connected = true; body = { connected: true, account: { id: 1, name: 'Admin' } }; }
 else if (path === '/health') body = { status: 'ok', source: 'upload', ocr_engine: 'manual' };
 else if (path === '/ingest/scan') body = { batches: [] };
 else if (path === '/ingest/upload') body = { batch_id: 'screenshots-test', items: [] };
 else if (path.startsWith('/ocr/')) { const { run, revision, annual_end_date, ...legacy } = fixture.draft; body = legacy; }
 else if (path === '/participants') body = fixture.participants;
 else if (path === '/gymrats/runs' && request.method === 'POST') { assert.equal(JSON.parse(request.postData).provisional, provisional); started = true; body = run; }
 else if (path === '/gymrats/runs') body = { runs: started ? [run] : [] };
 else if (path.endsWith('/draft')) {
  if (request.method === 'PUT') { writes++; revision++; await new Promise(resolve => setTimeout(resolve, 200)); }
  body = { ...fixture.draft, month: run.month, annual_end_date: run.annual_end_date, provisional, revision };
 }
 else if (path.endsWith('/preview')) { assert.equal(JSON.parse(request.postData).revision, revision); body = previewResponse(); }
 else if (path.endsWith('/commit')) { assert.equal(JSON.parse(request.postData).replace, !provisional); committing = true; body = { ...previewResponse(), committed: true, publication: 'pending_git', month_path: provisional ? 'data/previews/2026-10.json' : 'data/months/2026-06.json' }; }
 else { console.log('unhandled', path); }
 await send('Fetch.fulfillRequest', { requestId, responseCode: 200,
  responseHeaders: [{ name: 'Content-Type', value: 'application/json' }, { name: 'Access-Control-Allow-Origin', value: '*' }, { name: 'Access-Control-Allow-Headers', value: '*' }, { name: 'Access-Control-Allow-Methods', value: '*' }], body: Buffer.from(JSON.stringify(body)).toString('base64') });
});
await send('Runtime.enable'); await send('Page.enable');
await send('Fetch.enable', { patterns: [{ urlPattern: '*:8000/api/*' }] });
async function evaluate(expression) { const value = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (value.exceptionDetails) throw Error(JSON.stringify(value.exceptionDetails)); return value.result.value; }
async function until(expression) { for (let i=0; i<100; i++) { if (await evaluate(expression)) return; await new Promise(resolve => setTimeout(resolve, 100)); } throw Error('Timeout: '+expression+'\n'+await evaluate('document.body.innerText')); }
async function click(text) { await evaluate(`(()=>{const b=[...document.querySelectorAll('button')].find(b=>b.textContent.includes(${JSON.stringify(text)})); if(!b)throw Error('Missing button'); b.click()})()`); }
async function input(selector, value) { await evaluate(`(()=>{const e=document.querySelector(${JSON.stringify(selector)}); if(!e) throw Error('Missing input'); Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(e,${JSON.stringify(value)});e.dispatchEvent(new Event('input',{bubbles:true}))})()`); }
const frozenClock = await send('Page.addScriptToEvaluateOnNewDocument', { source: `
 const ActualDate = Date;
 window.Date = class extends ActualDate {
   constructor(...args) { super(...(args.length ? args : ['2026-10-27T16:00:00Z'])); }
   static now() { return new ActualDate('2026-10-27T16:00:00Z').getTime(); }
 };
` });
for (const [label, width, height, partial] of [['desktop',1440,1000,false],['mobile',390,844,false],['partial-mobile',390,844,true]]) {
 provisional = partial;
 run.month = partial ? '2026-10' : '2026-06';
 run.provisional = partial;
 run.annual_end_date = partial ? '2026-10-26' : '2026-06-30';
 connected=false;started=false;committing=false; revision=1;
 await send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:label!=='desktop'});
 await send('Page.navigate',{url:adminUrl+'?test='+Date.now()+'#/admin'});
 await until("document.body.innerText.includes('Solicitar código')");
 await input('input[type=email]','admin@example.test'); await click('Solicitar código');
 await until("!!document.querySelector('input[autocomplete=one-time-code]')");
 await input('input[autocomplete=one-time-code]','123456'); await click('Conectar');
 await until("document.body.innerText.includes('Conectado como Admin')");
 await evaluate(`document.querySelector('select').value='${run.month}';document.querySelector('select').dispatchEvent(new Event('change',{bubbles:true}))`);
 await click('Buscar dados do GymRats'); await until("document.body.innerText.includes('Conferir / retomar')");
 await click('Conferir / retomar'); await until("document.body.innerText.includes('Ver o resultado')");
 assert.equal(await evaluate('document.documentElement.scrollWidth > innerWidth'), false, label + ' review overflow');
 // Force a queued edit and assert the result button stays disabled during save.
 await input('.editor__value','123.456');
 assert.equal(await evaluate("[...document.querySelectorAll('button')].find(b=>b.textContent==='Ver o resultado').disabled"),true);
 await until("![...document.querySelectorAll('button')].find(b=>b.textContent==='Ver o resultado').disabled");
 await click('Ver o resultado'); await until("document.body.innerText.includes('Classificação do mês')");
 if (partial) {
   assert.equal(await evaluate("document.body.textContent.includes('Mês em andamento')"), true);
   assert.equal(await evaluate("[...document.querySelectorAll('button')].some(b=>b.textContent.includes('Fechar o mês'))"), false);
   await click('Salvar prévia do mês');
   await until("document.body.textContent.includes('Prévia salva')");
 } else {
   assert.equal(await evaluate("[...document.querySelectorAll('button')].find(b=>b.textContent.includes('Fechar o mês')).disabled"),true);
   await evaluate("document.querySelector('input[type=checkbox]').click()"); await click('Fechar o mês');
   await until("document.body.textContent.includes('Apuração salva')");
 }
 assert.equal(committing,true);
 const overflow=await evaluate('document.documentElement.scrollWidth > innerWidth'); assert.equal(overflow,false,label+' horizontal overflow');
 const screenshot=await send('Page.captureScreenshot',{format:'png'});writeFileSync(join(tmpdir(), 'gymrats-'+label+'.png'),Buffer.from(screenshot.data,'base64'));
 console.log(label+': login → collect → review/autosave → preview → replace → saved, no horizontal overflow');
}
assert.equal(writes,3);
provisional = false;
// The alternative upload path still reaches the shared review editors.
await send('Page.navigate', { url: adminUrl + '?screenshots=' + Date.now() + '#/admin' });
await until("document.body.innerText.includes('Alternativa: usar screenshots')");
await evaluate("document.querySelector('details').open = true");
await until("!!document.querySelector('input[type=file]')");
await evaluate(`(() => {
 const transfer = new DataTransfer();
 transfer.items.add(new File(['offline-image'], 'screenshot.png', { type: 'image/png' }));
 const input = document.querySelector('input[type=file]'); input.files = transfer.files;
 input.dispatchEvent(new Event('change', { bubbles: true }));
})()`);
await until("document.body.innerText.includes('Enviar 1 print')");
await click('Enviar 1 print');
await until("document.body.innerText.includes('Ver o resultado')");
console.log('screenshots: upload → shared review editors');
await send('Page.removeScriptToEvaluateOnNewDocument', { identifier: frozenClock.identifier });
assert.deepEqual(errors,[]);ws.close();
