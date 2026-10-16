import test from 'node:test';
import assert from 'node:assert/strict';
import { AtlasApiError, getCapabilities, retrieve } from '../src/api.js';
import { adaptRetrievalResponse, buildRetrievalRequest, createQueryId, createRequestGuard } from '../src/retrieval.js';

const response = (body, status = 200, headers = {}) => ({ ok: status >= 200 && status < 300, status, headers: { get: key => headers[key.toLowerCase()] || null }, json: async () => body });

test('construye exactamente la petición F4.6 y genera query_id', () => {
  const request = buildRetrievalRequest({ text: '  Una plaza  ', galleryIds: ['madrid-50m'], topK: 5 });
  assert.equal(request.schema_version, '1.0');
  assert.equal(request.contract_version, 'crosstext2loc-retrieval-request-v1');
  assert.equal(request.query.text, 'Una plaza');
  assert.match(request.query.query_id, /^browser-/);
  assert.deepEqual(request.gallery_ids, ['madrid-50m']);
  assert.equal(request.top_k, 5);
  assert.ok(!Object.hasOwn(request, 'ground_truth'));
  assert.notEqual(createQueryId(), createQueryId());
});

test('retrieve envía body, base URL y AbortSignal sin duplicar', async () => {
  let calls = 0, captured;
  const controller = new AbortController();
  const request = buildRetrievalRequest({ text: 'Una plaza', galleryIds: ['madrid-25m'], topK: 3, queryId: 'q1' });
  const fetchImpl = async (url, options) => { calls++; captured = { url, options }; return response({ schema_version: '1.0', contract_version: 'crosstext2loc-retrieval-response-v1', retrievals: [] }); };
  await retrieve(request, { baseUrl: '/custom', signal: controller.signal, fetchImpl });
  assert.equal(calls, 1);
  assert.equal(captured.url, '/custom/retrievals');
  assert.deepEqual(JSON.parse(captured.options.body), request);
  assert.ok(captured.options.signal);
});

test('adapta candidatos conservando orden y similitud negativa', () => {
  const document = { schema_version: '1.0', contract_version: 'crosstext2loc-retrieval-response-v1', query: {}, model: {}, timings_ms: { total: 1 }, retrievals: [{ gallery_id: 'madrid-50m', gallery_count: 253, requested_k: 2, effective_k: 2, visual_dataset_id: 'v', embedding_dataset_id: 'e', results: [{ rank: 1, candidate_id: 'b', latitude: 40.4, longitude: -3.7, cosine_similarity: 0.2 }, { rank: 2, candidate_id: 'a', latitude: 40.41, longitude: -3.71, cosine_similarity: -0.1 }] }] };
  document.query = { query_id: 'q', text: 'text', language: 'es' };
  document.model = { name: 'CLIP-L/14@336', checkpoint_sha256: 'd'.repeat(64) };
  document.timings_ms = { text_encoding: 1, ranking_by_gallery: { 'madrid-50m': 1 }, total: 2 };
  document.retrievals[0].visual_dataset_id = 'visual'; document.retrievals[0].embedding_dataset_id = 'embedding'; document.retrievals[0].requested_k = 2; document.retrievals[0].effective_k = 2; document.retrievals[0].ranking_method = 'exhaustive_cosine'; document.retrievals[0].tie_break = 'candidate_id_ascending';
  const adapted = adaptRetrievalResponse(document, { query: document.query, gallery_ids: ['madrid-50m'], top_k: 2 });
  assert.deepEqual(adapted.retrievals[0].results.map(x => x.id), ['b', 'a']);
  assert.equal(adapted.retrievals[0].results[1].similarity, -0.1);
  assert.equal(adapted.retrievals[0].results[0].key, 'madrid-50m:b');
});

test('parsea errores API y request ID', async () => {
  const fetchImpl = async () => response({ error: { code: 'RUNTIME_BUSY', message: 'ocupado', request_id: 'req-1' } }, 503, { 'x-request-id': 'req-header' });
  await assert.rejects(() => getCapabilities({ fetchImpl }), error => error instanceof AtlasApiError && error.code === 'RUNTIME_BUSY' && error.requestId === 'req-1');
});

test('distingue error de red, timeout y cancelación', async () => {
  await assert.rejects(() => getCapabilities({ fetchImpl: async () => { throw new TypeError('offline'); } }), error => error.code === 'NETWORK_ERROR');
  await assert.rejects(() => getCapabilities({ timeoutMs: 5, fetchImpl: (url, options) => new Promise((resolve, reject) => options.signal.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')))) }), error => error.code === 'TIMEOUT');
  const controller = new AbortController(); controller.abort();
  await assert.rejects(() => getCapabilities({ signal: controller.signal, fetchImpl: async (url, options) => { if (options.signal.aborted) throw new DOMException('aborted', 'AbortError'); } }), error => error.name === 'AbortError');
});

test('rechaza respuestas exitosas malformadas y coordenadas inválidas', () => {
  const request = { query: { query_id: 'q', text: 't', language: 'es' }, gallery_ids: ['madrid-50m'], top_k: 1 };
  assert.throws(() => adaptRetrievalResponse({ contract_version: 'otro' }, request));
  const invalid = { schema_version: '1.0', contract_version: 'crosstext2loc-retrieval-response-v1', retrievals: [{ gallery_id: 'madrid-50m', results: [{ rank: 1, candidate_id: 'x', latitude: 200, longitude: -3, cosine_similarity: 0.2 }] }] };
  assert.throws(() => adaptRetrievalResponse(invalid, request));
});

test('rechaza query_id, K y capacidades incompatibles', async () => {
  const request = { query: { query_id: 'q', text: 't', language: 'es' }, gallery_ids: ['madrid-50m'], top_k: 1 };
  const invalid = { schema_version: '1.0', contract_version: 'crosstext2loc-retrieval-response-v1', query: { query_id: 'otra', text: 't', language: 'es' }, model: { name: 'CLIP-L/14@336', checkpoint_sha256: 'd'.repeat(64) }, timings_ms: { text_encoding: 1, ranking_by_gallery: { 'madrid-50m': 1 }, total: 2 }, retrievals: [] };
  assert.throws(() => adaptRetrievalResponse(invalid, request));
  await assert.rejects(() => getCapabilities({ fetchImpl: async () => response({ schema_version: '1.0', api_version: 'v1', retrievers: [], galleries: [{ gallery_id: '<b>x</b>', candidate_count: '253' }] }) }), error => error.code === 'INVALID_API_RESPONSE');
});

test('el guard impide que respuestas canceladas u obsoletas publiquen estado', () => {
  const guard = createRequestGuard();
  const first = guard.next();
  const second = guard.next();
  assert.equal(guard.isCurrent(first), false);
  assert.equal(guard.isCurrent(second), true);
  guard.cancel();
  assert.equal(guard.isCurrent(second), false);
});
