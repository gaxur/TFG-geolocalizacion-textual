const STAGE_IDS = Object.freeze(['llm', 'crosstext2loc', 'vlm', 'dialoguevpr']);
const STAGE_STATES = new Set([
  'pending', 'running', 'completed', 'failed', 'skipped', 'unavailable', 'waiting_for_user', 'unknown',
]);

function capabilityStage(capabilities, id) {
  return capabilities?.pipeline_progress?.stages?.find(stage => stage.id === id) || null;
}

function stage(id, state, message, extra = {}) {
  return { id, state, message, subphase: null, elapsedMs: null, outcome: null, ...extra };
}

export function createPipelineState({ queryId, processingMode, capabilities, startedAt }) {
  const llmCapability = capabilityStage(capabilities, 'llm');
  const retrieverAvailable = capabilities?.retrievers?.some(
    retriever => retriever.id === 'crosstext2loc' && retriever.available,
  ) === true;
  const visualCapability = capabilities?.postprocessing_capabilities?.find(
    capability => capability.id === 'topn_visual_promotion',
  );
  const dialogueCapability = capabilityStage(capabilities, 'dialoguevpr');

  const llmState = processingMode === 'no_llm'
    ? stage('llm', 'skipped', 'Omitido: se usa la descripción original.')
    : llmCapability?.available === false
      ? stage('llm', 'unavailable', 'Qwen no está disponible en este arranque.')
      : stage('llm', 'pending', 'Transformación textual experimental en_cartographic.');

  const visualState = visualCapability?.enabled === true
    ? stage('vlm', 'pending', 'Experimental: postprocesado opcional con evidencia Qwen3-VL precalculada; no ejecuta inferencia visual en línea.')
    : visualCapability
      ? stage('vlm', 'skipped', 'Omitido: el postprocesador visual está deshabilitado o no hay bundle disponible.')
      : stage('vlm', 'unknown', 'El backend no publica disponibilidad del postprocesador visual.');

  return {
    queryId,
    processingMode,
    startedAt,
    elapsedMs: 0,
    sequence: 0,
    transport: 'connecting',
    transportGap: false,
    overall: 'running',
    message: 'Conectando con el canal de seguimiento…',
    stages: [
      llmState,
      retrieverAvailable
        ? stage('crosstext2loc', 'pending', 'Codificación textual y ranking exhaustivo de la galería seleccionada.')
        : stage('crosstext2loc', 'unavailable', 'CrossText2Loc no está disponible en este arranque.'),
      visualState,
      dialogueCapability?.available === true
        ? stage('dialoguevpr', 'pending', 'Etapa interactiva disponible; esperará una respuesta si el backend la solicita.')
        : stage('dialoguevpr', 'unavailable', 'No integrado en el endpoint FastAPI de este MVP.'),
    ],
  };
}

function replaceStage(current, replacement) {
  return current.map(item => item.id === replacement.id ? { ...item, ...replacement } : item);
}

export function reducePipelineEvent(current, event) {
  if (!current || !event || event.query_id !== current.queryId) return current;
  if (event.event_type === 'connected') {
    return { ...current, transport: 'connected', message: current.message };
  }
  if (current.overall !== 'running') return current;
  if (!Number.isInteger(event.sequence) || event.sequence <= current.sequence) return current;
  const gap = current.sequence > 0 && event.sequence !== current.sequence + 1;
  let next = { ...current, sequence: event.sequence, transportGap: current.transportGap || gap };

  if (event.event_type === 'pipeline') {
    if (!['running', 'completed', 'failed'].includes(event.state)) return current;
    return {
      ...next,
      overall: event.state,
      elapsedMs: Number.isFinite(event.elapsed_ms) ? event.elapsed_ms : current.elapsedMs,
      message: gap ? 'Faltan eventos de seguimiento; el progreso no es completo.' : (event.message || current.message),
    };
  }

  if (event.event_type !== 'stage' || !STAGE_IDS.includes(event.stage_id) || !STAGE_STATES.has(event.state)) {
    return current;
  }
  const target = current.stages.find(item => item.id === event.stage_id);
  if (!target) return current;
  const updated = {
    ...target,
    state: event.state,
    message: event.message || target.message,
    elapsedMs: Number.isFinite(event.elapsed_ms) ? event.elapsed_ms : target.elapsedMs,
    outcome: event.outcome || target.outcome,
    subphase: event.subphase || target.subphase,
  };
  next.stages = replaceStage(current.stages, updated);
  if (gap) next.message = 'Faltan eventos de seguimiento; el progreso no es completo.';
  else next.message = event.message || current.message;
  if (current.startedAt != null && globalThis.performance?.now) {
    next.elapsedMs = Math.max(0, performance.now() - current.startedAt);
  }
  return next;
}

export function markProgressUnavailable(current, reason = 'El endpoint síncrono no ofrece eventos intermedios.') {
  if (!current) return current;
  const stages = current.stages.map(item => (
    ['pending', 'running'].includes(item.state)
      ? { ...item, state: 'unknown', message: reason, subphase: null }
      : item
  ));
  return {
    ...current,
    stages,
    transport: 'unavailable',
    message: `${reason} Se confirmarán las etapas con la respuesta final.`,
  };
}

export function completePipelineFromResponse(current, response) {
  if (!current) return current;
  const processing = response?.processing;
  const retrieval = response?.retrievals?.[0];
  const visual = response?.visualPostprocessing;
  const stages = current.stages.map(item => {
    if (item.id === 'llm') {
      if (processing?.mode === 'no_llm') return { ...item, state: 'skipped', message: 'Omitido: el recuperador recibió el texto original.' };
      if (processing?.transformer) return { ...item, state: 'completed', message: 'Qwen terminó y la transformación superó la validación.', elapsedMs: response?.timingsMs?.transformation ?? item.elapsedMs };
      return { ...item, state: 'unavailable', message: 'La respuesta no informa una transformación LLM.' };
    }
    if (item.id === 'crosstext2loc') {
      if (retrieval?.results?.length) {
        const rankMs = Object.values(response?.timingsMs?.ranking_by_gallery || {}).reduce((sum, value) => sum + value, 0);
        const textMs = response?.timingsMs?.text_encoding || 0;
        return { ...item, state: 'completed', message: `Ranking exhaustivo terminado: ${retrieval.gallery_count} candidatos; Top-${retrieval.effective_k} recibido.`, elapsedMs: textMs + rankMs };
      }
      return { ...item, state: 'unknown', message: 'La respuesta no confirma resultados CT2L.' };
    }
    if (item.id === 'vlm') {
      if (visual?.status === 'applied') return { ...item, state: 'completed', message: 'Se aplicó el postprocesado experimental con evidencia visual precalculada; no se ejecutó Qwen3-VL en línea.', outcome: 'applied' };
      if (visual?.status === 'fallback_baseline') return { ...item, state: 'completed', message: 'El postprocesador experimental no encontró evidencia compatible; se conservó el ranking CT2L.', outcome: 'fallback_baseline' };
      if (visual?.status === 'disabled') return { ...item, state: 'skipped', message: 'Omitido: postprocesado visual deshabilitado.' };
      return { ...item, state: 'unknown', message: 'La respuesta no informa el postprocesado visual.' };
    }
    return item.id === 'dialoguevpr' && item.state === 'unknown'
      ? { ...item, state: 'unavailable', message: 'No integrado en el endpoint FastAPI de este MVP.' }
      : item;
  });
  return {
    ...current,
    stages,
    overall: 'completed',
    transport: current.transport === 'unavailable' ? 'unavailable' : 'connected',
    elapsedMs: current.startedAt != null && globalThis.performance?.now
      ? Math.max(0, performance.now() - current.startedAt)
      : current.elapsedMs,
    message: current.transport === 'unavailable'
      ? 'Consulta completada; las etapas se confirmaron al recibir la respuesta síncrona.'
      : 'Todas las etapas disponibles finalizaron; el Top-10 está listo.',
  };
}

export function failPipeline(current, error) {
  if (!current) return current;
  const code = error?.code || '';
  const didNotStart = ['RUNTIME_BUSY', 'INVALID_REQUEST', 'INVALID_RETRIEVAL_INPUT'].includes(code);
  const llmFailed = ['TRANSFORMATION_FAILED', 'TRANSFORMATION_REJECTED'].includes(code);
  const llmUnavailable = code === 'LLM_NOT_READY';
  const retrievalFailed = code === 'INFERENCE_FAILED';
  const stages = current.stages.map(item => {
    if (!['pending', 'running', 'unknown'].includes(item.state)) return item;
    if (item.id === 'dialoguevpr') return { ...item, state: 'unavailable', message: 'No integrado en el endpoint FastAPI del MVP.' };
    if (didNotStart) return { ...item, state: 'skipped', message: 'Omitida: la consulta no llegó a iniciar el procesamiento.' };
    if (llmUnavailable && item.id === 'llm') return { ...item, state: 'unavailable', message: 'Qwen no está disponible en este arranque.' };
    if (llmUnavailable && item.id === 'crosstext2loc') return { ...item, state: 'skipped', message: 'Omitido: no se ejecutó CT2L porque el modo solicitado requiere Qwen.' };
    if (llmUnavailable && item.id === 'vlm') return { ...item, state: 'skipped', message: 'Omitido: la consulta no llegó al postprocesado visual.' };
    if (llmFailed && item.id === 'llm') return { ...item, state: 'failed', message: error.message || 'La transformación fue rechazada.' };
    if (llmFailed && item.id === 'crosstext2loc') return { ...item, state: 'skipped', message: 'Omitido: CT2L no se ejecuta tras fallar la transformación.' };
    if (llmFailed && item.id === 'vlm') return { ...item, state: 'skipped', message: 'Omitido: la consulta no llegó al postprocesado visual.' };
    if (retrievalFailed && item.id === 'crosstext2loc') return { ...item, state: 'failed', message: error.message || 'Falló la recuperación CT2L.' };
    if (retrievalFailed && item.id === 'vlm') return { ...item, state: 'skipped', message: 'Omitido: CT2L no produjo resultados para postprocesar.' };
    if (item.state === 'running' || item.state === 'pending') return { ...item, state: 'unknown', message: 'El cliente perdió la espera; no se confirma si el servidor terminó esta etapa.' };
    return item;
  });
  return {
    ...current,
    stages,
    overall: ['TIMEOUT', 'NETWORK_ERROR'].includes(code) ? 'unknown' : 'failed',
    elapsedMs: current.startedAt != null && globalThis.performance?.now
      ? Math.max(0, performance.now() - current.startedAt)
      : current.elapsedMs,
    message: code === 'TIMEOUT'
      ? 'La espera del navegador agotó el tiempo; la inferencia del servidor puede continuar.'
      : (error?.message || 'La consulta no pudo completarse.'),
  };
}

export function cancelPipeline(current) {
  if (!current) return current;
  return {
    ...current,
    stages: current.stages.map(item => item.state === 'running'
      ? { ...item, state: 'unknown', message: 'Se canceló la espera local; el servidor puede continuar.' }
      : item),
    overall: 'cancelled',
    message: 'Espera cancelada localmente; esto no confirma la detención del trabajo en el servidor.',
  };
}

export const pipelineStageIds = STAGE_IDS;
