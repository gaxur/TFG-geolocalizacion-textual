// Comprobación E2E sin dependencias de test: build Vite + API fake + Chrome CDP.
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import http from 'node:http';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const dist = path.join(root, 'dist');
const output = path.join(root, 'test-results');
fs.mkdirSync(output, { recursive: true });
const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'atlas-browser-'));
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
const types = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml', '.png': 'image/png' };
const apiRequests = [];

function fakeRetrieval(body) {
  return {
    schema_version: '1.0', contract_version: 'crosstext2loc-retrieval-response-v1', query: body.query,
    model: { name: 'CLIP-L/14@336', checkpoint_sha256: 'd'.repeat(64) },
    retrievals: body.gallery_ids.map((galleryId, galleryIndex) => ({
      gallery_id: galleryId, visual_dataset_id: `visual-${galleryId}`, embedding_dataset_id: `embedding-${galleryId}`,
      gallery_count: galleryId === 'madrid-25m' ? 1115 : 253, requested_k: body.top_k, effective_k: body.top_k,
      ranking_method: 'exhaustive_cosine', tie_break: 'candidate_id_ascending',
      results: Array.from({ length: body.top_k }, (_, index) => ({ rank: index + 1, candidate_id: `${galleryId}-candidate-${index + 1}`, latitude: 40.414 + (index + galleryIndex) * .0003, longitude: -3.705 + index * .0002, cosine_similarity: .31 - index * .01 })),
    })),
    timings_ms: { text_encoding: 10, ranking_by_gallery: Object.fromEntries(body.gallery_ids.map(id => [id, 1])), total: 12 },
  };
}

const server = http.createServer((request, response) => {
  const url = new URL(request.url, 'http://localhost');
  if (url.pathname === '/api/v1/capabilities') {
    response.writeHead(200, { 'Content-Type': 'application/json' });
    response.end(JSON.stringify({ schema_version: '1.0', api_version: 'v1', retrievers: [{ id: 'crosstext2loc', available: true, scores_are_probabilities: false }], galleries: [{ gallery_id: 'madrid-50m', candidate_count: 253 }, { gallery_id: 'madrid-25m', candidate_count: 1115 }], search_area: { region_id: 'madrid_pilot', crs: 'EPSG:4326', bbox: { north: 40.42, south: 40.412, east: -3.699, west: -3.709 } }, supported_languages: { policy_status: 'pending', accepted_codes: ['es', 'en'] } }));
    return;
  }
  if (url.pathname === '/api/v1/retrievals' && request.method === 'POST') {
    let raw = '';
    request.on('data', chunk => raw += chunk);
    request.on('end', () => {
      const body = JSON.parse(raw); apiRequests.push(body);
      if (body.query.text === 'trigger-busy') { response.writeHead(503, { 'Content-Type': 'application/json' }); response.end(JSON.stringify({ error: { code: 'RUNTIME_BUSY', message: 'busy', request_id: body.query.query_id } })); return; }
      const send = () => { response.writeHead(200, { 'Content-Type': 'application/json', 'X-Request-ID': body.query.query_id }); response.end(JSON.stringify(fakeRetrieval(body))); };
      body.query.text === 'trigger-slow' ? setTimeout(send, 800) : send();
    });
    return;
  }
  if (url.pathname.startsWith('/tiles/')) { response.writeHead(204); response.end(); return; }
  const relative = decodeURIComponent(url.pathname);
  const file = path.resolve(dist, '.' + (relative === '/' ? '/index.html' : relative));
  if (!file.startsWith(dist + path.sep) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) { response.writeHead(404); response.end(); return; }
  response.writeHead(200, { 'Content-Type': types[path.extname(file)] || 'application/octet-stream' });
  fs.createReadStream(file).pipe(response);
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const baseUrl = `http://127.0.0.1:${server.address().port}`;
const candidates = process.platform === 'win32' ? ['C:/Program Files/Google/Chrome/Application/chrome.exe'] : ['/usr/bin/google-chrome', '/usr/bin/chromium', '/usr/bin/chromium-browser'];
const chromePath = process.env.CHROME_PATH || candidates.find(candidate => fs.existsSync(candidate));
if (!chromePath) throw new Error('No se encontró Chrome/Chromium. Define CHROME_PATH.');
const browser = spawn(chromePath, ['--headless=new', '--disable-gpu', '--no-sandbox', '--no-first-run', '--no-default-browser-check', '--remote-debugging-port=0', `--user-data-dir=${profile}`, 'about:blank'], { windowsHide: true, stdio: 'ignore' });
let launchError, ws;
browser.on('error', error => { launchError = error; });
try {
  for (let i = 0; i < 100 && !fs.existsSync(path.join(profile, 'DevToolsActivePort')); i++) { if (launchError) throw launchError; await delay(100); }
  if (!fs.existsSync(path.join(profile, 'DevToolsActivePort'))) throw new Error('Chromium no publicó el puerto de DevTools.');
  const port = fs.readFileSync(path.join(profile, 'DevToolsActivePort'), 'utf8').split('\n')[0];
  const pages = await (await fetch(`http://127.0.0.1:${port}/json`)).json();
  ws = new WebSocket(pages.find(page => page.type === 'page').webSocketDebuggerUrl);
  await new Promise(resolve => ws.addEventListener('open', resolve, { once: true }));
  let id = 0;
  const pending = new Map(), errors = [];
  ws.addEventListener('message', event => { const data = JSON.parse(event.data); if (data.method === 'Runtime.exceptionThrown') errors.push(data.params.exceptionDetails.exception?.description || data.params.exceptionDetails.text); const item = pending.get(data.id); if (item) { pending.delete(data.id); data.error ? item.reject(new Error(JSON.stringify(data.error))) : item.resolve(data.result); } });
  const send = (method, params = {}) => new Promise((resolve, reject) => { pending.set(++id, { resolve, reject }); ws.send(JSON.stringify({ id, method, params })); });
  const evaluate = async expression => { const result = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails)); return result.result.value; };
  const click = selector => evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`);
  const fill = text => evaluate(`document.querySelector('#description').value=${JSON.stringify(text)};document.querySelector('#description').dispatchEvent(new Event('input',{bubbles:true}))`);
  const waitFor = async expression => { for (let i = 0; i < 60; i++) { if (await evaluate(expression)) return; await delay(100); } throw new Error(`Timeout: ${expression}`); };
  await send('Runtime.enable'); await send('Page.enable');
  await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1080, deviceScaleFactor: 1, mobile: false });
  await send('Page.navigate', { url: baseUrl });
  await waitFor(`!!document.querySelector('#description') && !document.querySelector('[data-dropdown="gallery"]').disabled`);
  assert.match(await evaluate(`document.querySelector('.service-badge').textContent`), /CrossText2Loc/);
  assert.equal(await evaluate(`document.querySelectorAll('.result-card').length`), 0);
  await fill('Una plaza amplia rodeada de edificios y calles estrechas');
  await click('.search-button');
  await waitFor(`document.querySelectorAll('.result-card').length === 5`);
  assert.match(await evaluate(`document.querySelector('.result-card h3').textContent`), /madrid-50m-candidate-1/);
  assert.match(await evaluate(`document.querySelector('.results-footnote').textContent`), /no (?:representa|es) una probabilidad/);
  assert.equal(await evaluate(`document.querySelectorAll('.leaflet-container').length`), 1);
  assert.equal(await evaluate(`document.querySelectorAll('.candidate-marker').length`), 5);
  assert.equal(await evaluate(`document.querySelectorAll('.candidate-cell').length`), 5);
  assert.match(await evaluate(`document.querySelector('.cell-legend').textContent`), /50 × 50 m/);
  assert.equal(await evaluate(`document.querySelectorAll('.candidate-marker.top-result').length`), 1);
  await click('[data-select="madrid-50m:madrid-50m-candidate-2"]');
  assert.equal(await evaluate(`document.querySelectorAll('.leaflet-container').length`), 1, 'Leaflet sin contenedores duplicados');
  assert.equal(await evaluate(`document.querySelector('[data-select="madrid-50m:madrid-50m-candidate-2"]').getAttribute('aria-pressed')`), 'true');
  assert.equal(await evaluate(`document.querySelectorAll('.candidate-cell.selected').length`), 1);
  await click('.candidate-marker-shell:nth-of-type(3) .candidate-marker');
  assert.equal(await evaluate(`document.querySelector('[data-select="madrid-50m:madrid-50m-candidate-3"]').getAttribute('aria-pressed')`), 'true');
  assert.equal(apiRequests.length, 1);
  assert.equal(apiRequests[0].contract_version, 'crosstext2loc-retrieval-request-v1');
  assert.deepEqual(apiRequests[0].gallery_ids, ['madrid-50m']);
  assert.ok(!Object.hasOwn(apiRequests[0], 'ground_truth'));
  await click('[data-dropdown="gallery"]');
  await waitFor(`!!document.querySelector('[data-select-id="gallery"][data-select-value="madrid-25m"]')`);
  await click('[data-select-id="gallery"][data-select-value="madrid-25m"]');
  await click('[data-dropdown="top-k"]');
  await click('[data-select-id="top-k"][data-select-value="3"]');
  assert.match(await evaluate(`document.querySelector('#gallery-value').textContent`), /25 m/);
  assert.match(await evaluate(`document.querySelector('#top-k-value').textContent`), /Top-3/);
  assert.match(await evaluate(`document.querySelector('.cell-legend').textContent`), /25 × 25 m/);
  await fill('trigger-busy');
  await click('.search-button');
  await waitFor(`document.querySelector('.service-state.error')?.textContent.includes('ocupado')`);
  await fill('trigger-slow');
  await click('.search-button');
  await waitFor(`!!document.querySelector('[data-action="cancel"]')`);
  await click('[data-action="cancel"]');
  await waitFor(`document.querySelector('#toast')?.textContent.includes('cancelada')`);
  await send('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: true });
  await delay(250);
  assert.equal(await evaluate('document.documentElement.scrollWidth <= window.innerWidth'), true);
  assert.equal(await evaluate(`document.querySelector('[data-mobile="description"]').getAttribute('aria-pressed')`), 'true');
  await click('[data-mobile="results"]');
  assert.equal(await evaluate(`document.querySelector('[data-mobile="results"]').getAttribute('aria-pressed')`), 'true');
  await send('Page.navigate', { url: `${baseUrl}/?legacy=1#explore` });
  await waitFor(`!!document.querySelector('#description')`);
  assert.match(await evaluate(`document.querySelector('.service-badge').textContent`), /CrossText2Loc/);
  assert.equal(await evaluate(`document.querySelectorAll('.result-card').length`), 0, 'El parámetro antiguo no activa datos sintéticos');
  assert.deepEqual(errors, []);
  console.log('OK: contrato HTTP, Leaflet, responsive y ausencia del modo sintético.');
} finally {
  ws?.close(); browser.kill(); server.close();
}
