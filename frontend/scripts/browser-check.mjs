// Comprobación E2E sin dependencias de test: build Vite + API fake + Chrome CDP.
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import http from 'node:http';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const projectRoot = path.resolve(root, '..');
const dist = path.join(root, 'dist');
const configuredMapAssets = process.env.MVP_MAP_ASSETS_DIR || './data/processed/map-assets';
const mapAssetsRoot = path.isAbsolute(configuredMapAssets)
  ? configuredMapAssets
  : path.resolve(projectRoot, configuredMapAssets);
const localPmtilesPath = path.join(mapAssetsRoot, 'madrid.pmtiles');
const localPmtilesProvenancePath = `${localPmtilesPath}.provenance.json`;
const hasLocalPmtiles = fs.existsSync(localPmtilesPath) && fs.statSync(localPmtilesPath).isFile();
const localPmtilesTileDataOffset = hasLocalPmtiles
  ? Number(fs.readFileSync(localPmtilesPath).readBigUInt64LE(56))
  : null;
const output = path.join(root, 'test-results');
fs.mkdirSync(output, { recursive: true });
const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'atlas-browser-'));
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
const types = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml', '.png': 'image/png', '.json': 'application/json', '.geojson': 'application/geo+json' };
const apiRequests = [];
const externalMapRequests = [];
const pmtilesRangeRequests = [];
const progressConnections = new Map();
const progressSequences = new Map();
const cellCollections = new Map();
const localMapManifestPath = path.join(mapAssetsRoot, 'map-assets.json');
const hasLocalCells = fs.existsSync(localMapManifestPath) &&
  fs.existsSync(path.join(mapAssetsRoot, 'cells-25m.geojson')) &&
  fs.existsSync(path.join(mapAssetsRoot, 'cells-50m.geojson'));
const realMapManifest = hasLocalCells ? JSON.parse(fs.readFileSync(localMapManifestPath, 'utf8')) : null;

function testCells(galleryId) {
  if (cellCollections.has(galleryId)) return cellCollections.get(galleryId);
  const size = galleryId === 'madrid-25m' ? 25 : 50;
  const count = size === 25 ? 1115 : 253;
  const step = 0.00016;
  const features = Array.from({ length: count }, (_, index) => {
    const candidateId = `${galleryId}-candidate-${index + 1}`;
    const candidateKey = `${galleryId}:${candidateId}`;
    const west = -3.7088 + (index % 50) * step;
    const south = 40.4121 + Math.floor(index / 50) * step;
    const east = west + 0.00006;
    const north = south + 0.00006;
    return {
      type: 'Feature', id: candidateKey,
      properties: {
        candidate_key: candidateKey, candidate_id: candidateId, gallery_id: galleryId, cell_size_m: size,
        center_latitude: south + 0.00003, center_longitude: west + 0.00003,
      },
      geometry: { type: 'Polygon', coordinates: [[[west, south], [east, south], [east, north], [west, north], [west, south]]] },
    };
  });
  const collection = { type: 'FeatureCollection', name: `${galleryId}-synthetic-browser-fixture`, features };
  cellCollections.set(galleryId, collection);
  return collection;
}

function cellsForGallery(galleryId) {
  if (!realMapManifest) return testCells(galleryId);
  if (!cellCollections.has(galleryId)) {
    const gallery = realMapManifest.galleries[galleryId];
    const file = path.join(mapAssetsRoot, gallery.geojson_file);
    cellCollections.set(galleryId, JSON.parse(fs.readFileSync(file, 'utf8')));
  }
  return cellCollections.get(galleryId);
}

const syntheticMapAssets = {
  schema_version: '1.0', contract_version: 'madrid-map-assets-v1', region_id: 'madrid_pilot',
  region_bbox_wgs84: { north: 40.42, south: 40.412, east: -3.699, west: -3.709 },
  catalog_version: 'madrid-pilot-grid-v1', catalog_config_file: 'test-fixture',
  catalog_config_sha256: 'a'.repeat(64), osm_snapshot_id: null,
  source_mode: 'browser-test-only-synthetic-fixture',
  galleries: Object.fromEntries(['madrid-25m', 'madrid-50m'].map((galleryId, index) => {
    const size = index === 0 ? 25 : 50;
    const geojson = testCells(galleryId);
    return [galleryId, {
      candidate_count: geojson.features.length, cell_size_m: size, grid_hash: 'a467049559fd',
      manifest_id: `madrid-pilot-grid-v1-s${size}-l${size}`, manifest_sha256: 'b'.repeat(64),
      expected_f4_manifest_sha256: 'b'.repeat(64), f4_manifest_sha256: null,
      osm_snapshot_id: null, geojson_file: `cells-${size}m.geojson`, geojson_sha256: 'c'.repeat(64),
      geometry_crs: 'EPSG:4326', construction_crs: 'EPSG:25830', canonical_f1_geometry_match: true,
    }];
  })),
  geometry_attribution: 'Fixture sintética solo para pruebas de software.',
  basemap_attribution_required: '© OpenStreetMap contributors · ODbL 1.0',
  basemap: { file: 'madrid.pmtiles', expected_tile_schema: 'madrid-osm-explicit-height-v1', status: 'not-included-in-test-fixture', offline_only: true },
};
const mapAssets = realMapManifest || syntheticMapAssets;
const candidateAt = (galleryId, index) => cellsForGallery(galleryId).features[index];
const candidateKeyAt = (galleryId, index) => `${galleryId}:${candidateAt(galleryId, index).properties.candidate_id}`;

function publishProgress(queryId, eventType, stageId, status, message, extra = {}) {
  const response = progressConnections.get(queryId);
  if (!response || response.destroyed || response.writableEnded) return;
  const sequence = (progressSequences.get(queryId) || 0) + 1;
  progressSequences.set(queryId, sequence);
  response.write(`data: ${JSON.stringify({ schema_version: '1.0', event_type: eventType, query_id: queryId, sequence, stage_id: stageId, state: status, message, ...extra })}\n\n`);
}

function simulateProgressForTest(body, { complete = true } = {}) {
  const queryId = body.query.query_id;
  publishProgress(queryId, 'pipeline', 'pipeline', 'running', 'Fixture de eventos de prueba.');
  publishProgress(queryId, 'stage', 'llm', body.processing_mode === 'with_llm' ? 'running' : 'skipped', body.processing_mode === 'with_llm' ? 'Qwen de prueba está activo.' : 'Fixture: consulta sin LLM.');
  if (body.processing_mode === 'with_llm') publishProgress(queryId, 'stage', 'llm', 'completed', 'Transformación fake de prueba terminada.');
  publishProgress(queryId, 'stage', 'crosstext2loc', 'running', 'CT2L fake de prueba en curso.');
  publishProgress(queryId, 'stage', 'crosstext2loc', 'running', 'Codificación fake de prueba.', { subphase: { id: 'text_encoding', state: 'running' } });
  if (!complete) return;
  finishProgressForTest(body);
}

function finishProgressForTest(body) {
  const queryId = body.query.query_id;
  publishProgress(queryId, 'stage', 'crosstext2loc', 'running', 'Codificación fake de prueba terminada.', { subphase: { id: 'text_encoding', state: 'completed', elapsed_ms: 0.4 } });
  publishProgress(queryId, 'stage', 'crosstext2loc', 'running', 'Ranking fake de prueba.', { subphase: { id: 'ranking', state: 'running', gallery_id: body.gallery_id } });
  publishProgress(queryId, 'stage', 'crosstext2loc', 'running', 'Ranking fake de prueba terminado.', { subphase: { id: 'ranking', state: 'completed', elapsed_ms: 0.3, gallery_id: body.gallery_id } });
  publishProgress(queryId, 'stage', 'crosstext2loc', 'completed', 'Top-10 fake de prueba listo.', { elapsed_ms: 1 });
  publishProgress(queryId, 'stage', 'vlm', 'skipped', 'Fixture: postprocesado visual omitido.');
  publishProgress(queryId, 'stage', 'dialoguevpr', 'unavailable', 'Fixture: DialogueVPR no integrado.');
  publishProgress(queryId, 'pipeline', 'pipeline', 'completed', 'Fixture de pipeline de prueba completada.', { elapsed_ms: 2 });
}

function fakeRetrieval(body) {
  const galleryCount = mapAssets.galleries[body.gallery_id]?.candidate_count || (body.gallery_id === 'madrid-25m' ? 1115 : 253);
  const collection = cellsForGallery(body.gallery_id);
  const results = Array.from({ length: body.top_k }, (_, index) => {
    const properties = collection.features[index].properties;
    return {
      rank: index + 1,
      candidate_id: properties.candidate_id,
      latitude: properties.center_latitude,
      longitude: properties.center_longitude,
      cosine_similarity: .31 - index * .01,
    };
  });
  const effectiveQuery = { ...body.query, text: body.processing_mode === 'with_llm' ? 'In a mapped square near a station.' : body.query.text, language: body.processing_mode === 'with_llm' ? 'en' : body.query.language };
  const processing = {
    mode: body.processing_mode,
    variant: body.processing_mode === 'with_llm' ? 'en_cartographic' : 'es_original',
    effective_query: effectiveQuery,
    transformer: body.processing_mode === 'with_llm' ? { model_id: 'Qwen/Qwen3-8B', revision: 'b968826d9c46dd6066d109eabc6255188de91218', prompt_version: 'f53b-text-transform-v2' } : null,
  };
  return {
    schema_version: '1.0', contract_version: 'atlas-experimental-retrieval-response-v3', query: body.query,
    processing,
    model: { name: 'CLIP-L/14@336', checkpoint_sha256: 'd'.repeat(64) },
    retrievals: [{
      gallery_id: body.gallery_id, visual_dataset_id: `visual-${body.gallery_id}`, embedding_dataset_id: `embedding-${body.gallery_id}`,
      gallery_count: galleryCount, requested_k: body.top_k, effective_k: body.top_k,
      ranking_method: 'exhaustive_cosine', tie_break: 'candidate_id_ascending',
      results,
    }],
    timings_ms: { transformation: body.processing_mode === 'with_llm' ? 3500 : 0, text_encoding: 10, ranking_by_gallery: { [body.gallery_id]: 1 }, total: body.processing_mode === 'with_llm' ? 3512 : 12 },
    visual_postprocessing: { status: 'disabled', source: 'precomputed', request_id: `browser-${body.query.query_id}`, reason: null, model: null, policy_id: null, baseline_results: results, final_results: results, evidence: [] },
  };
}

const server = http.createServer((request, response) => {
  const url = new URL(request.url, 'http://localhost');
  if (url.pathname === '/map-assets/map-assets.json') {
    response.writeHead(200, { 'Content-Type': 'application/json' });
    response.end(JSON.stringify(mapAssets));
    return;
  }
  const cellsFile = /^\/map-assets\/cells-(25|50)m\.geojson$/.exec(url.pathname);
  if (cellsFile) {
    const galleryId = `madrid-${cellsFile[1]}m`;
    response.writeHead(200, { 'Content-Type': 'application/geo+json' });
    response.end(JSON.stringify(cellsForGallery(galleryId)));
    return;
  }
  if (url.pathname === '/map-assets/madrid.pmtiles') {
    if (!hasLocalPmtiles) {
      response.writeHead(404, { 'Content-Type': 'text/plain' });
      response.end('PMTiles real ausente; prueba limitada a la ruta sin basemap');
      return;
    }
    const size = fs.statSync(localPmtilesPath).size;
    const match = /^bytes=(\d+)-(\d*)$/.exec(request.headers.range || '');
    if (request.headers.range && !match) {
      response.writeHead(416, { 'Accept-Ranges': 'bytes', 'Content-Range': `bytes */${size}` }).end();
      return;
    }
    const start = match ? Number(match[1]) : 0;
    const end = match ? Math.min(match[2] ? Number(match[2]) : size - 1, size - 1) : size - 1;
    if (start >= size || end < start) {
      response.writeHead(416, { 'Accept-Ranges': 'bytes', 'Content-Range': `bytes */${size}` }).end();
      return;
    }
    const status = match ? 206 : 200;
    const headers = {
      'Accept-Ranges': 'bytes',
      'Content-Type': 'application/vnd.pmtiles',
      'Content-Length': end - start + 1,
    };
    if (match) {
      headers['Content-Range'] = `bytes ${start}-${end}/${size}`;
      pmtilesRangeRequests.push({ start, end });
    }
    response.writeHead(status, headers);
    if (request.method === 'HEAD') response.end();
    else fs.createReadStream(localPmtilesPath, { start, end }).pipe(response);
    return;
  }
  if (url.pathname === '/map-assets/madrid.pmtiles.provenance.json') {
    if (!hasLocalPmtiles || !fs.existsSync(localPmtilesProvenancePath)) {
      response.writeHead(404, { 'Content-Type': 'text/plain' });
      response.end('Provenance PMTiles no incluida en fixture de navegador');
      return;
    }
    response.writeHead(200, { 'Content-Type': 'application/json' });
    response.end(fs.readFileSync(localPmtilesProvenancePath));
    return;
  }
  const progressPath = /^\/api\/v1\/progress\/(.+)$/.exec(url.pathname);
  if (progressPath && request.method === 'GET') {
    const queryId = decodeURIComponent(progressPath[1]);
    response.writeHead(200, {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache, no-transform',
      'X-Accel-Buffering': 'no',
    });
    progressConnections.set(queryId, response);
    response.on('close', () => {
      if (progressConnections.get(queryId) === response) progressConnections.delete(queryId);
    });
    response.write(`data: ${JSON.stringify({ schema_version: '1.0', event_type: 'connected', query_id: queryId, sequence: 0 })}\n\n`);
    return;
  }
  if (url.pathname === '/api/v1/capabilities') {
    response.writeHead(200, { 'Content-Type': 'application/json' });
     response.end(JSON.stringify({ schema_version: '1.0', api_version: 'v3-experimental', retrievers: [{ id: 'crosstext2loc', available: true, scores_are_probabilities: false }], processing_modes:[{id:'no_llm',available:true,variant:'es_original'},{id:'with_llm',available:true,variant:'en_cartographic',experimental:true}], postprocessing_capabilities:[{id:'topn_visual_promotion',available:false,enabled:false,source:null,online_inference:false}], pipeline_progress:{transport:'sse',endpoint_template:'/api/v1/progress/{query_id}',stages:[{id:'llm',available:true},{id:'crosstext2loc',available:true},{id:'vlm',available:false,online_inference:false},{id:'dialoguevpr',available:false,reason:'not_integrated_in_mvp_endpoint'}]}, galleries: [{ gallery_id: 'madrid-50m', candidate_count: 253 }, { gallery_id: 'madrid-25m', candidate_count: 1115 }], search_area: { region_id: 'madrid_pilot', crs: 'EPSG:4326', bbox: { north: 40.42, south: 40.412, east: -3.699, west: -3.709 } }, supported_languages: { policy_status: 'experimental', accepted_codes: ['es'] } }));
    return;
  }
  if (url.pathname === '/api/v1/retrievals' && request.method === 'POST') {
      let raw = '';
      request.on('data', chunk => raw += chunk);
      request.on('end', () => {
      const body = JSON.parse(raw); apiRequests.push(body);
      if (body.query.text === 'trigger-busy') {
        publishProgress(body.query.query_id, 'pipeline', 'pipeline', 'failed', 'Fixture: runtime ocupado.', { outcome: 'RUNTIME_BUSY' });
        response.writeHead(503, { 'Content-Type': 'application/json' });
        response.end(JSON.stringify({ error: { code: 'RUNTIME_BUSY', message: 'busy', request_id: body.query.query_id } }));
        return;
      }
      const send = () => {
        if (body.query.text === 'trigger-slow') finishProgressForTest(body);
        else simulateProgressForTest(body);
        if (response.destroyed || response.writableEnded) return;
        response.writeHead(200, { 'Content-Type': 'application/json', 'X-Request-ID': body.query.query_id });
        response.end(JSON.stringify(fakeRetrieval(body)));
      };
      if (body.query.text === 'trigger-slow') {
        simulateProgressForTest(body, { complete: false });
        setTimeout(send, 8000);
      } else send();
    });
    return;
  }
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
const browser = spawn(chromePath, ['--headless=new', '--no-sandbox', '--no-first-run', '--no-default-browser-check', '--enable-webgl', '--ignore-gpu-blocklist', '--enable-unsafe-swiftshader', '--use-gl=angle', '--use-angle=swiftshader', '--remote-debugging-port=0', `--user-data-dir=${profile}`, 'about:blank'], { windowsHide: true, stdio: 'ignore' });
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
   const pending = new Map(), errors = [], failedRequests = [], requestUrls = new Map();
   ws.addEventListener('message', event => {
     const data = JSON.parse(event.data);
      if (data.method === 'Runtime.exceptionThrown') errors.push(data.params.exceptionDetails.exception?.description || data.params.exceptionDetails.text);
      if (data.method === 'Network.requestWillBeSent') {
        try {
          const requestUrl = new URL(data.params.request.url);
          requestUrls.set(data.params.requestId, requestUrl.href);
          if (['http:', 'https:'].includes(requestUrl.protocol) && requestUrl.origin !== baseUrl) externalMapRequests.push(requestUrl.href);
        } catch { /* data/blob URLs are not external cartographic requests. */ }
      }
      if (data.method === 'Network.loadingFailed') failedRequests.push({ url: requestUrls.get(data.params.requestId), error: data.params.errorText, canceled: data.params.canceled });
     const item = pending.get(data.id);
     if (item) { pending.delete(data.id); data.error ? item.reject(new Error(JSON.stringify(data.error))) : item.resolve(data.result); }
   });
  const send = (method, params = {}) => new Promise((resolve, reject) => { pending.set(++id, { resolve, reject }); ws.send(JSON.stringify({ id, method, params })); });
   const evaluate = async expression => { const result = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails)); return result.result.value; };
   const click = selector => evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`);
   const fill = text => evaluate(`document.querySelector('#description').value=${JSON.stringify(text)};document.querySelector('#description').dispatchEvent(new Event('input',{bubbles:true}))`);
   const capture = async filename => {
     const image = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false });
     fs.writeFileSync(path.join(output, filename), Buffer.from(image.data, 'base64'));
   };
   const waitFor = async expression => { for (let i = 0; i < 120; i++) { if (await evaluate(expression)) return; await delay(100); } throw new Error(`Timeout: ${expression}`); };
   await send('Runtime.enable'); await send('Page.enable'); await send('Network.enable');
  await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1080, deviceScaleFactor: 1, mobile: false });
  await send('Page.navigate', { url: baseUrl });
  await waitFor(`!!document.querySelector('#description') && !document.querySelector('[data-dropdown="gallery"]').disabled`);
  assert.match(await evaluate(`document.querySelector('.service-badge').textContent`), /CrossText2Loc/);
  assert.equal(await evaluate(`document.querySelectorAll('.result-card').length`), 0);
  await fill('Una plaza amplia rodeada de edificios y calles estrechas');
   await click('.search-button');
     await waitFor(`document.querySelectorAll('.result-card').length === 10`);
     await waitFor(`document.querySelector('.pipeline-panel')?.dataset.pipelineOverall === 'completed'`);
     assert.equal(await evaluate(`document.querySelector('.result-card h3').textContent`), candidateAt('madrid-50m', 0).properties.candidate_id);
     assert.equal(await evaluate(`document.querySelector('.pipeline-query p').textContent`), 'Una plaza amplia rodeada de edificios y calles estrechas', 'la descripción enviada sigue visible junto al progreso');
   assert.match(await evaluate(`document.querySelector('.score-row').textContent`), /Similitud coseno\s*0\.3100/);
   assert.equal(await evaluate(`document.querySelector('.score-row').textContent.includes('%')`), false, 'la similitud coseno se presenta como puntuación, no como porcentaje');
    assert.match(await evaluate(`document.querySelector('.results-footnote').textContent`), /no (?:representa|es) una probabilidad/);
    assert.equal(await evaluate(`document.querySelector('[data-stage="llm"]').classList.contains('state-skipped')`), true);
    assert.equal(await evaluate(`document.querySelector('[data-stage="crosstext2loc"]').classList.contains('state-completed')`), true);
    assert.equal(await evaluate(`document.querySelector('[data-stage="dialoguevpr"]').classList.contains('state-unavailable')`), true);
   await waitFor(`document.querySelectorAll('.map-result-marker').length === 10`);
   assert.ok(['maplibre', 'leaflet-2d'].includes(await evaluate(`document.querySelector('#results-map').dataset.renderer`)));
   assert.equal(await evaluate(`document.querySelectorAll('.map-result-marker').length`), 10);
   assert.equal(await evaluate(`document.querySelector('#results-map').dataset.mapCandidateCount`), '10');
    assert.equal(await evaluate(`document.querySelector('#results-map').dataset.mapCellCount`), '10');
    assert.match(await evaluate(`document.querySelector('.cell-legend').textContent`), /50 × 50 m/);
      assert.equal(await evaluate(`document.querySelectorAll('.map-result-marker.is-top-result').length`), 1);
      if (hasLocalPmtiles) {
        try {
          await waitFor(`document.querySelector('#results-map').dataset.mapBasemap === 'ready' && !document.querySelector('[data-map-action="mode-3d"]').disabled`);
        } catch (error) {
          const mapState = await evaluate(`({dataset:{...document.querySelector('#results-map').dataset},status:document.querySelector('#map-data-status')?.textContent,mode3dDisabled:document.querySelector('[data-map-action="mode-3d"]')?.disabled})`);
          throw new Error(`${error.message}; estado local del mapa: ${JSON.stringify(mapState)}; fallos de red: ${JSON.stringify(failedRequests)}; errores JS: ${JSON.stringify(errors)}`);
        }
       assert.ok(pmtilesRangeRequests.length > 0, 'MapLibre lee PMTiles real mediante HTTP Range local');
       assert.ok(pmtilesRangeRequests.some(range => range.end >= localPmtilesTileDataOffset), 'MapLibre leyó bytes de teselas, no solo la cabecera/metadata');
       assert.match(await evaluate(`document.querySelector('#map-data-status').textContent`), /6\/3517.*105\/2510.*no es una medición independiente/i);
       assert.match(await evaluate(`document.querySelector('.maplibregl-ctrl-attrib').textContent`), /OpenStreetMap contributors/);
       await click('[data-map-action="mode-3d"]');
       assert.equal(await evaluate(`document.querySelector('#results-map').dataset.mapMode`), '3d');
       assert.equal(await evaluate(`document.querySelector('#results-map').dataset.mapBuilding3dLayer`), 'ready');
       assert.equal(await evaluate(`document.querySelector('#results-map').dataset.mapBuilding3dVisibility`), 'visible');
       await waitFor(`Number(document.querySelector('#results-map').dataset.mapBuilding3dRenderedFeatureCount) > 0`);
       await click('[data-map-action="mode-2d"]');
       assert.equal(await evaluate(`document.querySelector('#results-map').dataset.mapMode`), '2d');
       assert.equal(await evaluate(`document.querySelector('#results-map').dataset.mapBuilding3dVisibility`), 'none');
     } else {
       assert.equal(await evaluate(`document.querySelector('[data-map-action="mode-3d"]').disabled`), true);
     }
    await click('[data-map-action="grid"]');
    assert.equal(await evaluate(`document.querySelector('[data-map-action="grid"]').getAttribute('aria-pressed')`), 'true');
    await click('[data-map-action="grid"]');
    await click('[data-map-action="north"]');
    await click('[data-map-action="reset"]');
    const mapInstance = await evaluate(`document.querySelector('#results-map').dataset.mapInstanceId`);
   await click(`[data-select="${candidateKeyAt('madrid-50m', 1)}"]`);
   assert.equal(await evaluate(`document.querySelector('#results-map').dataset.mapInstanceId`), mapInstance, 'el renderer permanece montado entre actualizaciones');
    assert.equal(await evaluate(`document.querySelector('[data-select="${candidateKeyAt('madrid-50m', 1)}"]').getAttribute('aria-pressed')`), 'true');
    assert.equal(await evaluate(`document.querySelector('.map-result-marker[data-candidate-key="${candidateKeyAt('madrid-50m', 1)}"]').getAttribute('aria-pressed')`), 'true');
    await click(`.map-result-marker[data-candidate-key="${candidateKeyAt('madrid-50m', 2)}"]`);
    assert.equal(await evaluate(`document.querySelector('[data-select="${candidateKeyAt('madrid-50m', 2)}"]').getAttribute('aria-pressed')`), 'true');
  assert.equal(apiRequests.length, 1);
  assert.equal(apiRequests[0].contract_version, 'atlas-experimental-retrieval-request-v2');
  assert.equal(apiRequests[0].gallery_id, 'madrid-50m'); assert.equal(apiRequests[0].processing_mode,'no_llm');
  assert.ok(!Object.hasOwn(apiRequests[0], 'ground_truth'));
  await click('[data-dropdown="gallery"]');
  await waitFor(`!!document.querySelector('[data-select-id="gallery"][data-select-value="madrid-25m"]')`);
   await click('[data-select-id="gallery"][data-select-value="madrid-25m"]');
   assert.match(await evaluate(`document.querySelector('#gallery-value').textContent`), /25 m/);
   await fill('Una plaza madrileña junto a calles peatonales');
    await click('.search-button');
    await waitFor(`document.querySelectorAll('.result-card').length === 10 && document.querySelector('#results-map').dataset.mapCellCount === '10'`);
    await waitFor(`document.querySelector('.pipeline-panel')?.dataset.pipelineOverall === 'completed'`);
    assert.equal(await evaluate(`document.querySelectorAll('.map-result-marker').length`), 10);
    await click('[data-dropdown="processing"]'); await click('[data-select-id="processing"][data-select-value="with_llm"]');
   assert.match(await evaluate(`document.querySelector('#processing-value').textContent`), /Con LLM/);
    assert.match(await evaluate(`document.querySelector('.cell-legend').textContent`), /25 × 25 m/);
   await fill('Una descripción con una plaza y una estación cercana');
   await click('.search-button');
   await waitFor(`document.querySelectorAll('.result-card').length === 10 && document.querySelector('.pipeline-panel')?.dataset.pipelineOverall === 'completed'`);
   assert.equal(await evaluate(`document.querySelector('[data-stage="llm"]').classList.contains('state-completed')`), true);
   assert.equal(await evaluate(`document.querySelector('[data-stage="crosstext2loc"]').classList.contains('state-completed')`), true);
   await fill('trigger-busy');
   await click('.search-button');
   await waitFor(`document.querySelector('.service-state.error')?.textContent.includes('ocupado')`);
   assert.equal(await evaluate(`document.querySelector('.pipeline-panel')?.dataset.pipelineOverall`), 'failed');
   await fill('trigger-slow');
   const mapInstanceBeforeSlow = await evaluate(`document.querySelector('#results-map').dataset.mapInstanceId`);
   await click('.search-button');
   await waitFor(`!!document.querySelector('[data-action="cancel"]')`);
   await waitFor(`document.querySelector('[data-stage="crosstext2loc"]')?.classList.contains('state-running')`);
   const slowQueryId = await evaluate(`document.querySelector('.pipeline-panel')?.dataset.queryId`);
   assert.match(await evaluate(`document.querySelector('.pipeline-subphase')?.textContent || ''`), /Codificando/);
   assert.equal(await evaluate(`document.querySelector('.pipeline-panel').getAttribute('aria-busy')`), 'true');
   assert.equal(await evaluate(`document.querySelector('[data-stage="crosstext2loc"]').getAttribute('aria-current')`), 'step');
   assert.equal(await evaluate(`document.querySelector('.pipeline-steps').getAttribute('aria-label')`), 'Etapas del procesamiento');
   assert.equal(await evaluate(`document.querySelector('#results-map').dataset.mapInstanceId`), mapInstanceBeforeSlow, 'los eventos activos de progreso no reconstruyen MapLibre');
   assert.equal(await evaluate(`document.querySelector('#description').value`), 'trigger-slow', 'la descripción permanece en el campo durante la ejecución');
   await capture('pipeline-progress-desktop.png');
   await click('[data-action="cancel"]');
   await waitFor(`document.querySelector('#toast')?.textContent.includes('cancelada')`);
   assert.equal(await evaluate(`document.querySelector('.pipeline-panel')?.dataset.pipelineOverall`), 'cancelled');
   await fill('trigger-busy');
   await click('.search-button');
   await waitFor(`document.querySelector('.service-state.error')?.textContent.includes('ocupado')`);
   const latestQueryId = await evaluate(`document.querySelector('.pipeline-panel')?.dataset.queryId`);
   assert.notEqual(latestQueryId, slowQueryId, 'una consulta nueva obtiene su propio identificador');
   await delay(8200);
   assert.equal(await evaluate(`document.querySelector('.pipeline-panel')?.dataset.queryId`), latestQueryId, 'la respuesta/evento tardío anterior no cambia la consulta nueva');
   assert.equal(await evaluate(`document.querySelector('.pipeline-panel')?.dataset.pipelineOverall`), 'failed');
   await send('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: true });
   await delay(250);
   assert.equal(await evaluate('document.documentElement.scrollWidth <= window.innerWidth'), true);
    assert.equal(await evaluate(`document.querySelector('[data-mobile="results"]').getAttribute('aria-pressed')`), 'true', 'la consulta abre el panel de progreso/mapa en móvil');
    assert.equal(await evaluate(`document.querySelectorAll('.pipeline-step').length`), 4);
    assert.equal(await evaluate(`getComputedStyle(document.querySelector('.pipeline-steps')).gridTemplateColumns.split(' ').length`), 1, 'la cronología compacta móvil mantiene una columna legible');
    await click('[data-mobile="description"]');
    assert.equal(await evaluate(`document.querySelector('[data-mobile="description"]').getAttribute('aria-pressed')`), 'true');
    await click('[data-mobile="results"]');
    assert.equal(await evaluate(`document.querySelector('[data-mobile="results"]').getAttribute('aria-pressed')`), 'true');
   const renderer = await evaluate(`document.querySelector('#results-map').dataset.renderer`);
   const localBasemap = await evaluate(`document.querySelector('#results-map').dataset.mapBasemap`);
  await send('Page.navigate', { url: `${baseUrl}/?legacy=1#explore` });
  await waitFor(`!!document.querySelector('#description')`);
  assert.match(await evaluate(`document.querySelector('.service-badge').textContent`), /CrossText2Loc/);
  assert.equal(await evaluate(`document.querySelectorAll('.result-card').length`), 0, 'El parámetro antiguo no activa datos sintéticos');
  assert.deepEqual(errors, []);
   assert.equal(externalMapRequests.length, 0, 'la vista cartográfica no contacta proveedores externos');
     console.log(`OK: contrato HTTP, renderer ${renderer}, PMTiles ${localBasemap}, rangos ${pmtilesRangeRequests.length}, celdas ${hasLocalCells ? 'F1 reales' : 'sintéticas'}, sincronización, responsive y cero proveedores externos.`);
} finally {
  ws?.close(); browser.kill(); server.close();
}
