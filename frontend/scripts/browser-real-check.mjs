// E2E real: Chromium -> Nginx -> FastAPI -> CrossText2Loc -> Leaflet.
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import assert from 'node:assert/strict';

const baseUrl = process.env.MVP_BASE_URL || 'http://127.0.0.1:8080';
const chromePath = process.env.CHROME_PATH || ['/usr/bin/google-chrome', '/usr/bin/chromium', '/usr/bin/chromium-browser'].find(candidate => fs.existsSync(candidate));
if (!chromePath) throw new Error('No se encontró Chrome/Chromium. Define CHROME_PATH.');
const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'atlas-real-browser-'));
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
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
  const waitFor = async (expression, attempts = 400) => { for (let i = 0; i < attempts; i++) { if (await evaluate(expression)) return; await delay(100); } throw new Error(`Timeout: ${expression}`); };
  const choose = async (id, value) => { await click(`[data-dropdown="${id}"]`); await waitFor(`!!document.querySelector('[data-select-id="${id}"][data-select-value="${value}"]')`); await click(`[data-select-id="${id}"][data-select-value="${value}"]`); };
  const run = async (gallery, mode) => {
    await choose('gallery', gallery);
    await choose('processing', mode);
    await fill('Estoy en una plaza urbana amplia rodeada de edificios y calles estrechas');
    await click('.search-button');
    await waitFor(`document.querySelectorAll('.result-card').length === 10`);
    assert.equal(await evaluate(`document.querySelectorAll('.candidate-marker').length`), 10);
    assert.equal(await evaluate(`document.querySelectorAll('.candidate-cell').length`), 10);
    assert.match(await evaluate(`document.querySelector('.cell-legend').textContent`), new RegExp(`${gallery.includes('25m') ? '25' : '50'} × ${gallery.includes('25m') ? '25' : '50'} m`));
    assert.equal(await evaluate(`document.querySelectorAll('.candidate-marker.top-result').length`), 1);
    assert.equal(await evaluate(`[...document.querySelectorAll('.coordinate-compact')].every(x => /^-?\\d+\\.\\d+, -?\\d+\\.\\d+$/.test(x.textContent.trim()))`), true);
    return evaluate(`[...document.querySelectorAll('.result-card')].map(card => ({id:card.querySelector('h3').textContent,score:card.querySelector('.score-row strong').childNodes[0].textContent.trim()}))`);
  };

  await send('Runtime.enable'); await send('Page.enable');
  await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1080, deviceScaleFactor: 1, mobile: false });
  await send('Page.navigate', { url: baseUrl });
  await waitFor(`!!document.querySelector('#description') && !document.querySelector('[data-dropdown="gallery"]').disabled`);
  const rows50 = await run('madrid-50m', 'no_llm');
  await click('.candidate-marker-shell:nth-of-type(2) .candidate-marker');
  assert.equal(await evaluate(`document.querySelectorAll('.result-card.selected').length`), 1);
  const rows25 = await run('madrid-25m', 'no_llm');
  const llm50 = await run('madrid-50m', 'with_llm');
  const llm25 = await run('madrid-25m', 'with_llm');
  await send('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: true });
  await delay(300);
  assert.equal(await evaluate('document.documentElement.scrollWidth <= window.innerWidth'), true);
  assert.deepEqual(errors, []);
  console.log(JSON.stringify({ status: 'pass', base_url: baseUrl, no_llm_50m: rows50, no_llm_25m: rows25, with_llm_50m: llm50, with_llm_25m: llm25, leaflet_markers: true, mobile: true }));
} finally {
  ws?.close(); browser.kill();
}
