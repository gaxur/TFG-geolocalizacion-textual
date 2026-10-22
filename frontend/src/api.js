const DEFAULT_BASE_URL = '/api/v1';

export class AtlasApiError extends Error {
  constructor(message, { code = 'NETWORK_ERROR', status = 0, requestId = '', cause } = {}) {
    super(message, { cause });
    this.name = 'AtlasApiError';
    this.code = code;
    this.status = status;
    this.requestId = requestId;
  }
}

const trimSlash = value => String(value || DEFAULT_BASE_URL).replace(/\/$/, '');

async function parseJsonResponse(response) {
  const requestId = response.headers?.get?.('x-request-id') || '';
  let body;
  try { body = await response.json(); }
  catch (cause) {
    throw new AtlasApiError('El servicio devolvió una respuesta que no es JSON válido.', { code: 'INVALID_API_RESPONSE', status: response.status, requestId, cause });
  }
  if (!response.ok) {
    const error = body?.error;
    throw new AtlasApiError(error?.message || 'El servicio no pudo completar la petición.', {
      code: error?.code || `HTTP_${response.status}`,
      status: response.status,
      requestId: error?.request_id || requestId,
    });
  }
  return body;
}

async function fetchJson(path, { baseUrl = DEFAULT_BASE_URL, method = 'GET', body, signal, timeoutMs = 20000, fetchImpl = fetch } = {}) {
  const timeout = new AbortController();
  const timer = setTimeout(() => timeout.abort('timeout'), timeoutMs);
  const combined = signal ? AbortSignal.any([signal, timeout.signal]) : timeout.signal;
  try {
    const response = await fetchImpl(`${trimSlash(baseUrl)}${path}`, {
      method,
      signal: combined,
      headers: { Accept: 'application/json', ...(body ? { 'Content-Type': 'application/json' } : {}) },
      ...(body ? { body: JSON.stringify(body) } : {}),
    });
    return await parseJsonResponse(response);
  } catch (error) {
    if (error?.name === 'AbortError') {
      const timedOut = timeout.signal.aborted && !signal?.aborted;
      if (timedOut) throw new AtlasApiError('La petición ha superado el tiempo de espera.', { code: 'TIMEOUT', cause: error });
      throw error;
    }
    if (error instanceof AtlasApiError) throw error;
    throw new AtlasApiError('No se pudo conectar con el servicio de recuperación.', { code: 'NETWORK_ERROR', cause: error });
  } finally {
    clearTimeout(timer);
  }
}

export function getCapabilities(options = {}) {
  return fetchJson('/capabilities', options).then(validateCapabilities);
}

export function retrieve(request, options = {}) {
  return fetchJson('/retrievals', { ...options, method: 'POST', body: request });
}

export const apiBaseUrl = import.meta.env?.VITE_ATLAS_API_BASE_URL || DEFAULT_BASE_URL;

function validateCapabilities(document) {
  if (document?.schema_version !== '1.0' || document?.api_version !== 'v2-experimental' || !Array.isArray(document.retrievers) || !Array.isArray(document.galleries) || !Array.isArray(document.processing_modes)) throw new AtlasApiError('La respuesta de capacidades no es válida.', { code: 'INVALID_API_RESPONSE' });
  const bbox = document.search_area?.bbox;
  if (document.search_area?.crs !== 'EPSG:4326' || typeof document.search_area.region_id !== 'string' || !bbox || !['north', 'south', 'east', 'west'].every(key => Number.isFinite(bbox[key])) || !(bbox.south < bbox.north && bbox.west < bbox.east) || bbox.south < -90 || bbox.north > 90 || bbox.west < -180 || bbox.east > 180) throw new AtlasApiError('La respuesta de capacidades no contiene un ámbito geográfico válido.', { code: 'INVALID_API_RESPONSE' });
  const galleries = document.galleries.map(item => {
    if (!item || typeof item.gallery_id !== 'string' || !item.gallery_id || !Number.isInteger(item.candidate_count) || item.candidate_count < 1) throw new AtlasApiError('La respuesta de capacidades contiene una galería inválida.', { code: 'INVALID_API_RESPONSE' });
    return item;
  });
  if (new Set(galleries.map(item => item.gallery_id)).size !== galleries.length) throw new AtlasApiError('La respuesta de capacidades contiene galerías duplicadas.', { code: 'INVALID_API_RESPONSE' });
  const modes = document.processing_modes;
  if (modes.length !== 2 || new Set(modes.map(item => item?.id)).size !== 2 || modes.some(item => !['no_llm','with_llm'].includes(item?.id) || typeof item.available !== 'boolean' || !['es_original','en_cartographic'].includes(item.variant))) throw new AtlasApiError('La respuesta de capacidades contiene modos inválidos.', { code: 'INVALID_API_RESPONSE' });
  return document;
}
