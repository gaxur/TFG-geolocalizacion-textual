// Comprobación de la build mediante Chrome DevTools Protocol, sin librerías de test adicionales.
// Ejecutar después de npm run build. CHROME_PATH permite indicar otro Chromium compatible.
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
const types = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml' };
const server = http.createServer((request, response) => {
  const relative = decodeURIComponent(new URL(request.url, 'http://localhost').pathname);
  const file = path.resolve(dist, '.' + (relative === '/' ? '/index.html' : relative));
  if (!file.startsWith(dist + path.sep) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) { response.writeHead(404); response.end(); return; }
  response.writeHead(200, { 'Content-Type': types[path.extname(file)] || 'application/octet-stream' });
  fs.createReadStream(file).pipe(response);
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const baseUrl = `http://127.0.0.1:${server.address().port}`;
const browser = spawn(process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe', [
  '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
  '--remote-debugging-port=0', `--user-data-dir=${profile}`, 'about:blank',
], { windowsHide: true, stdio: 'ignore' });
let launchError;
browser.on('error', error => { launchError = error; });
let ws;
try {
  for (let i = 0; i < 100 && !fs.existsSync(path.join(profile, 'DevToolsActivePort')); i++) { if (launchError) throw launchError; await delay(100); }
  const port = fs.readFileSync(path.join(profile, 'DevToolsActivePort'), 'utf8').split('\n')[0];
  const pages = await (await fetch(`http://127.0.0.1:${port}/json`)).json();
  ws = new WebSocket(pages.find(p => p.type === 'page').webSocketDebuggerUrl);
  await new Promise(resolve => ws.addEventListener('open', resolve, { once: true }));
  let id = 0;
  const pending = new Map(), errors = [];
  ws.addEventListener('message', event => {
    const data = JSON.parse(event.data);
    if (data.method === 'Runtime.exceptionThrown') errors.push(data.params.exceptionDetails.text);
    const item = pending.get(data.id);
    if (item) { pending.delete(data.id); data.error ? item.reject(new Error(JSON.stringify(data.error))) : item.resolve(data.result); }
  });
  const send = (method, params = {}) => new Promise((resolve, reject) => { pending.set(++id, { resolve, reject }); ws.send(JSON.stringify({ id, method, params })); });
  const evaluate = async expression => {
    const result = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
    if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails));
    return result.result.value;
  };
  const click = selector => evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`);
  const fill = text => evaluate(`document.querySelector('#description').value=${JSON.stringify(text)};document.querySelector('#description').dispatchEvent(new Event('input',{bubbles:true}))`);
  const screenshot = async name => {
    const { cssContentSize } = await send('Page.getLayoutMetrics');
    const shot = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true, clip: { x: 0, y: 0, width: cssContentSize.width, height: cssContentSize.height, scale: 1 } });
    fs.writeFileSync(path.join(output, name), Buffer.from(shot.data, 'base64'));
  };
  await send('Runtime.enable'); await send('Page.enable');
  await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1080, deviceScaleFactor: 1, mobile: false });
  await send('Page.navigate', { url: baseUrl });
  for (let i = 0; i < 50 && !await evaluate(`!!document.querySelector('#description')`); i++) await delay(100);
  await delay(800);
  assert.equal(await evaluate(`document.querySelectorAll('.rail').length`), 0, 'Una sola navegación');
  assert.equal(await evaluate(`document.querySelector('.search-options').open`), false, 'Opciones técnicas plegadas inicialmente');
  assert.equal(await evaluate('document.documentElement.scrollWidth <= window.innerWidth'), true, 'Sin overflow en escritorio');
  await screenshot('desktop.png');
  await fill('Corto'); await click('.search-button');
  assert.match(await evaluate(`document.querySelector('#form-error').textContent`), /20 caracteres/);
  await click('[data-example="0"]'); await click('.search-button'); await delay(200); await click('[data-action="cancel"]');
  await delay(1800); assert.equal(await evaluate(`document.querySelectorAll('.dialogue-panel').length`), 0, 'La cancelación no publica resultados tardíos');
  await click('.search-button'); await delay(2000);
  assert.equal(await evaluate(`document.querySelectorAll('.result-card').length`), 3);
  assert.match(await evaluate(`document.querySelector('.result-card h3').textContent`), /Puerta del Sol/);
  await click('[data-answer="Sí"]');
  assert.match(await evaluate(`document.querySelector('.dialogue-content').textContent`), /Tu respuesta/);
  await click('[data-detail="sol"]');
  assert.equal(await evaluate(`document.querySelector('#modal').open`), true);
  assert.match(await evaluate(`document.querySelector('#modal').textContent`), /no es una captura de Street View/);
  await send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 });
  await send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 });
  assert.equal(await evaluate(`document.querySelector('#modal').open`), false);
  await click('[data-page="compare"]');
  assert.equal(await evaluate(`document.querySelectorAll('.comparison-column').length`), 2);
  await screenshot('comparison.png');
  await evaluate(`window.exported=null;const original=URL.createObjectURL;URL.createObjectURL=function(blob){window.exported=blob.text();return original.call(this,blob)}`);
  await click('[data-action="export"]');
  const exported = JSON.parse(await evaluate('window.exported'));
  assert.equal(exported.prototype, true); assert.equal(exported.candidates.length, 3);
  await click('[data-page="history"]');
  assert.equal(await evaluate(`document.querySelectorAll('.history-item').length`), 1);
  await click('[data-restore="0"]');
  await click('[data-example="2"]'); await click('.search-button'); await delay(2000);
  assert.equal(await evaluate(`document.querySelectorAll('.result-card').length`), 1);
  assert.match(await evaluate(`document.querySelector('.result-card h3').textContent`), /Retiro/);
  await fill('Estoy delante de una montaña nevada muy grande'); await click('.search-button'); await delay(2000);
  assert.match(await evaluate(`document.querySelector('.empty-state').textContent`), /Sin coincidencias/);
  await click('.search-options summary');
  await click('[data-action="settings"]');
  await evaluate(`document.querySelector('#topk').value='5';document.querySelector('#dialogue-toggle').checked=false;document.querySelector('#settings-form').requestSubmit()`);
  await click('[data-example="0"]'); await click('.search-button'); await delay(2000);
  assert.equal(await evaluate(`document.querySelectorAll('.result-card').length`), 4);
  assert.equal(await evaluate(`document.querySelectorAll('.dialogue-panel').length`), 0);
  await click('[data-model="gotpr"]'); await click('.search-button'); await delay(2000);
  assert.match(await evaluate(`document.querySelector('.method-note').textContent`), /Grafo/);
  await send('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: true });
  await delay(300);
  assert.equal(await evaluate('document.documentElement.scrollWidth <= window.innerWidth'), true, 'Sin overflow en móvil');
  await screenshot('mobile.png');
  assert.equal(await evaluate(`getComputedStyle(document.querySelector('.search-panel')).display`), 'none', 'Resultados en su propia vista móvil');
  await click('[data-mobile="description"]');
  assert.equal(await evaluate(`getComputedStyle(document.querySelector('.exploration')).display`), 'none');
  await screenshot('mobile-description.png');
  await click('.search-button'); await delay(2000);
  assert.equal(await evaluate(`document.querySelector('[data-mobile="results"]').getAttribute('aria-pressed')`), 'true', 'Búsqueda cambia a resultados');
  for (const width of [320, 768]) {
    await send('Emulation.setDeviceMetricsOverride', { width, height: 900, deviceScaleFactor: 1, mobile: width < 720 });
    assert.equal(await evaluate('document.documentElement.scrollWidth <= window.innerWidth'), true, `Sin overflow a ${width}px`);
  }
  await send('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: true });
  await click('[data-page="compare"]');
  assert.equal(await evaluate('document.documentElement.scrollWidth <= window.innerWidth'), true, 'Comparación móvil sin overflow');
  await click('[data-page="history"]'); await click('[data-action="clear-history"]'); await click('[data-action="confirm-clear"]');
  assert.equal(await evaluate(`document.querySelectorAll('.history-item').length`), 0);
  await send('Page.reload'); await delay(500);
  assert.equal(await evaluate(`document.querySelectorAll('.history-item').length`), 0);
  assert.deepEqual(errors, [], 'Sin excepciones de JavaScript en el navegador');
  console.log('OK: escritorio y móvil, validación, cancelación, búsqueda, evidencias, diálogo, comparación, exportación, ajustes, ausencia de resultados e historial.');
  console.log(`Capturas: ${output}`);
} finally {
  ws?.close(); browser.kill(); server.close();
}
