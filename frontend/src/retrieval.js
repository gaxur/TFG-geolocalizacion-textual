const REQUEST_VERSION = '1.0';
const REQUEST_CONTRACT = 'atlas-experimental-retrieval-request-v2';
const RESPONSE_CONTRACT = 'atlas-experimental-retrieval-response-v3';

export function createQueryId() {
  const id = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `browser-${id}`;
}

export function createRequestGuard() {
  let current = 0;
  return { next: () => ++current, cancel: () => ++current, isCurrent: value => value === current, value: () => current };
}

export function buildRetrievalRequest({ text, language = 'es', galleryId, processingMode, topK = 10, queryId = createQueryId() }) {
  const cleanText = String(text || '').trim();
  if (!cleanText) throw new TypeError('La descripción no puede estar vacía.');
  if (!['madrid-25m', 'madrid-50m'].includes(galleryId)) throw new TypeError('Selecciona una galería válida.');
  if (!['no_llm', 'with_llm'].includes(processingMode)) throw new TypeError('Selecciona un modo de procesamiento válido.');
  if (topK !== 10) throw new TypeError('El MVP experimental utiliza Top-10.');
  return {
    schema_version: REQUEST_VERSION,
    contract_version: REQUEST_CONTRACT,
    query: { query_id: queryId, text: cleanText, language },
    gallery_id: galleryId,
    processing_mode: processingMode,
    top_k: topK,
  };
}

function validCandidate(row, expectedRank) {
  return row && row.rank === expectedRank && typeof row.candidate_id === 'string' && row.candidate_id && Number.isFinite(row.latitude) && row.latitude >= -90 && row.latitude <= 90 && Number.isFinite(row.longitude) && row.longitude >= -180 && row.longitude <= 180 && Number.isFinite(row.cosine_similarity) && row.cosine_similarity >= -1 && row.cosine_similarity <= 1;
}

export function adaptRetrievalResponse(document, request) {
  const processing = document?.processing;
  const expectedVariant = request.processing_mode === 'with_llm' ? 'en_cartographic' : 'es_original';
  if (document?.schema_version !== '1.0' || document?.contract_version !== RESPONSE_CONTRACT || !document.query || document.query.query_id !== request.query.query_id || document.query.text !== request.query.text || document.query.language !== request.query.language || processing?.mode !== request.processing_mode || processing?.variant !== expectedVariant || processing?.effective_query?.query_id !== request.query.query_id || typeof processing.effective_query.text !== 'string' || !processing.effective_query.text || (request.processing_mode === 'no_llm' && (processing.effective_query.text !== request.query.text || processing.effective_query.language !== request.query.language || processing.transformer !== null)) || (request.processing_mode === 'with_llm' && (processing.effective_query.language !== 'en' || processing.transformer?.model_id !== 'Qwen/Qwen3-8B' || processing.transformer?.prompt_version !== 'f53b-text-transform-v2')) || document.model?.name !== 'CLIP-L/14@336' || !/^[0-9a-f]{64}$/.test(document.model.checkpoint_sha256 || '') || !document.timings_ms || !Array.isArray(document.retrievals) || document.retrievals.length !== 1 || !document.visual_postprocessing) throw new TypeError('Respuesta de recuperación incompatible.');
  const requested = new Set([request.gallery_id]);
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
  if (seen.size !== 1) throw new TypeError('Falta la galería solicitada en la respuesta.');
  const visual = document.visual_postprocessing;
  if (!['applied','fallback_baseline','disabled'].includes(visual.status) || !Array.isArray(visual.baseline_results) || !Array.isArray(visual.final_results) || visual.baseline_results.length !== retrievals[0].results.length || visual.final_results.length !== retrievals[0].results.length) throw new TypeError('Postprocesamiento visual incompatible.');
  const baselineIds = visual.baseline_results.map((row,index) => { if (!validCandidate(row,index+1)) throw new TypeError('Baseline visual inválido.'); return row.candidate_id; });
  if (baselineIds.join('|') !== retrievals[0].results.map(row => row.id).join('|')) throw new TypeError('Baseline visual no coincide con CT2L.');
  const finalResults = visual.final_results.map((row,index) => { if (!validCandidate(row,index+1)) throw new TypeError('Ranking visual inválido.'); return { key: `${request.gallery_id}:${row.candidate_id}`, id: row.candidate_id, rank: row.rank, lat: row.latitude, lon: row.longitude, similarity: row.cosine_similarity, galleryId: request.gallery_id }; });
  if (new Set(finalResults.map(row => row.id)).size !== finalResults.length) throw new TypeError('Ranking visual contiene candidatos duplicados.');
  retrievals[0].baselineResults = retrievals[0].results;
  retrievals[0].results = finalResults;
  if (!Number.isFinite(document.timings_ms.transformation) || document.timings_ms.transformation < 0 || !Number.isFinite(document.timings_ms.text_encoding) || document.timings_ms.text_encoding < 0 || !Number.isFinite(document.timings_ms.total) || document.timings_ms.total < 0 || !document.timings_ms.ranking_by_gallery || Object.keys(document.timings_ms.ranking_by_gallery).length !== 1 || !Number.isFinite(document.timings_ms.ranking_by_gallery[request.gallery_id]) || document.timings_ms.ranking_by_gallery[request.gallery_id] < 0) throw new TypeError('Tiempos inválidos en la respuesta.');
  return { query: document.query, processing, model: document.model, visualPostprocessing: visual, retrievals, timingsMs: document.timings_ms, raw: document };
}

export function processingLabel(mode) { return mode === 'with_llm' ? 'Con LLM · en_cartographic' : 'Sin LLM · texto original'; }

export function galleryLabel(galleryId) {
  return galleryId === 'madrid-25m' ? 'Madrid · cuadrícula 25 m' : galleryId === 'madrid-50m' ? 'Madrid · cuadrícula 50 m' : galleryId;
}
