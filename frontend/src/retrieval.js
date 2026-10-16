const REQUEST_VERSION = '1.0';
const REQUEST_CONTRACT = 'crosstext2loc-retrieval-request-v1';
const RESPONSE_CONTRACT = 'crosstext2loc-retrieval-response-v1';

export function createQueryId() {
  const id = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `browser-${id}`;
}

export function createRequestGuard() {
  let current = 0;
  return { next: () => ++current, cancel: () => ++current, isCurrent: value => value === current, value: () => current };
}

export function buildRetrievalRequest({ text, language = 'es', galleryIds, topK, queryId = createQueryId() }) {
  const cleanText = String(text || '').trim();
  if (!cleanText) throw new TypeError('La descripción no puede estar vacía.');
  if (!Array.isArray(galleryIds) || !galleryIds.length || new Set(galleryIds).size !== galleryIds.length) throw new TypeError('Selecciona al menos una galería válida.');
  if (!Number.isInteger(topK) || topK < 1) throw new TypeError('Top-K debe ser un entero positivo.');
  return {
    schema_version: REQUEST_VERSION,
    contract_version: REQUEST_CONTRACT,
    query: { query_id: queryId, text: cleanText, language },
    gallery_ids: [...galleryIds],
    top_k: topK,
  };
}

function validCandidate(row, expectedRank) {
  return row && row.rank === expectedRank && typeof row.candidate_id === 'string' && row.candidate_id && Number.isFinite(row.latitude) && row.latitude >= -90 && row.latitude <= 90 && Number.isFinite(row.longitude) && row.longitude >= -180 && row.longitude <= 180 && Number.isFinite(row.cosine_similarity) && row.cosine_similarity >= -1 && row.cosine_similarity <= 1;
}

export function adaptRetrievalResponse(document, request) {
  const requestedGalleryIds = request.gallery_ids;
  if (document?.schema_version !== '1.0' || document?.contract_version !== RESPONSE_CONTRACT || !document.query || document.query.query_id !== request.query.query_id || document.query.text !== request.query.text || document.query.language !== request.query.language || document.model?.name !== 'CLIP-L/14@336' || !/^[0-9a-f]{64}$/.test(document.model.checkpoint_sha256 || '') || !document.timings_ms || !Array.isArray(document.retrievals) || !document.retrievals.length) throw new TypeError('Respuesta de recuperación incompatible.');
  const requested = new Set(requestedGalleryIds);
  const seen = new Set();
  const retrievals = document.retrievals.map(retrieval => {
    if (!retrieval || typeof retrieval.gallery_id !== 'string' || !requested.has(retrieval.gallery_id) || seen.has(retrieval.gallery_id) || typeof retrieval.visual_dataset_id !== 'string' || !retrieval.visual_dataset_id || typeof retrieval.embedding_dataset_id !== 'string' || !retrieval.embedding_dataset_id || !Number.isInteger(retrieval.gallery_count) || retrieval.gallery_count < 1 || retrieval.requested_k !== request.top_k || retrieval.effective_k !== retrieval.results?.length || retrieval.effective_k !== Math.min(request.top_k, retrieval.gallery_count) || retrieval.ranking_method !== 'exhaustive_cosine' || retrieval.tie_break !== 'candidate_id_ascending' || !Array.isArray(retrieval.results) || !retrieval.results.length) throw new TypeError('Galería inesperada en la respuesta.');
    seen.add(retrieval.gallery_id);
    const results = retrieval.results.map((row, index) => {
      if (!validCandidate(row, index + 1)) throw new TypeError('Candidato inválido en la respuesta.');
      return { key: `${retrieval.gallery_id}:${row.candidate_id}`, id: row.candidate_id, rank: row.rank, lat: row.latitude, lon: row.longitude, similarity: row.cosine_similarity, galleryId: retrieval.gallery_id };
    });
    return { galleryId: retrieval.gallery_id, galleryCount: retrieval.gallery_count, requestedK: retrieval.requested_k, effectiveK: retrieval.effective_k, visualDatasetId: retrieval.visual_dataset_id, embeddingDatasetId: retrieval.embedding_dataset_id, results };
  });
  if (seen.size !== requested.size) throw new TypeError('Faltan galerías solicitadas en la respuesta.');
  if (!Number.isFinite(document.timings_ms.text_encoding) || document.timings_ms.text_encoding < 0 || !Number.isFinite(document.timings_ms.total) || document.timings_ms.total < 0 || !document.timings_ms.ranking_by_gallery || Object.keys(document.timings_ms.ranking_by_gallery).length !== requested.size || [...requested].some(id => !Number.isFinite(document.timings_ms.ranking_by_gallery[id]) || document.timings_ms.ranking_by_gallery[id] < 0)) throw new TypeError('Tiempos inválidos en la respuesta.');
  return { query: document.query, model: document.model, retrievals, timingsMs: document.timings_ms, raw: document };
}

export function galleryLabel(galleryId) {
  return galleryId === 'madrid-25m' ? 'Madrid · cuadrícula 25 m' : galleryId === 'madrid-50m' ? 'Madrid · cuadrícula 50 m' : galleryId;
}
