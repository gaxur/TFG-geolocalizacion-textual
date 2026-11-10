import './minimal.css';
import { icon } from './visuals.js';
import { AtlasApiError, answerDialogue, apiBaseUrl, getCapabilities, getDialogueQueries,getDialogueVariants, retrieve, startDialogue } from './api.js';
import { buildDialogueAnswer, buildDialogueStart, validateDialogueSession } from './dialogue.js';
import { experimentalSessionId,getDescriptionVariant,validateDescriptionVariantManifest } from './description-variants.js';
import {
  adaptRetrievalResponse,
  buildRetrievalRequest,
  createQueryId,
  createRequestGuard,
  galleryLabel,
  processingLabel,
} from './retrieval.js';
import {
  cancelPipeline,
  completePipelineFromResponse,
  createPipelineState,
  failPipeline,
  markProgressUnavailable,
  reducePipelineEvent,
} from './pipeline.js';
import { openProgressStream } from './progress-stream.js';

const $ = selector => document.querySelector(selector);
const escapeHtml = value => String(value).replace(/[&<>"']/g, character => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
}[character]));
const examples = [
  { label: 'Plaza y reloj', text: 'Estoy en una plaza peatonal amplia. Veo un edificio claro con un reloj en lo alto y varias calles que salen de la plaza.' },
  { label: 'Soportales y estatua', text: 'Estoy en una plaza rodeada de edificios rojizos con soportales. En el centro hay una estatua de una persona a caballo.' },
  { label: 'Parque y estanque', text: 'Estoy en un parque y delante de mí hay un estanque. Al otro lado veo un monumento grande rodeado de columnas.' },
];

const state = {
  page: 'explore',
  mobileView: 'description',
  text: examples[0].text,
  language: 'es',
  topK: 10,
  galleryIds: ['madrid-50m'],
  processingMode: 'no_llm',
  capabilities: { status: 'loading', data: null, error: null },
  request: { status: 'idle', error: null, requestId: null, response: null },
  pipeline: null,
  results: [],
  selected: '',
  hasRun: false,
  last: null,
  mapView: null,
  mapMode: '2d',
  showGrid: false,
  showBuildings: true,
  mapAssets: {
    renderer: 'loading',
    basemap: 'loading',
    cells: 'loading',
    buildings3dAvailable: false,
    missingCellCount: 0,
    message: 'Comprobando recursos cartográficos locales…',
  },
  openSelect: '',
  dialogue: { catalogue: null, variants:null, mode: 'official', queryId: 'H27', variantQueryId:'H27', length:'short', session: null, answer: '', answerKind: 'negation', status: 'idle', error: null },
};

let toastTimer;
let activeController = null;
let activeProgressStream = null;
let pipelineClockTimer = null;
let mapHandle = null;
let mapMountPromise = null;
let mapMountGeneration = 0;
const requestGuard = createRequestGuard();
let history = [];

try {
  const stored = JSON.parse(localStorage.getItem('atlas-history') || '[]');
  history = Array.isArray(stored) ? stored.filter(item =>
    item?.mode === 'real' && typeof item.text === 'string' && item.text.length <= 1200 &&
    typeof item.date === 'string' && Array.isArray(item.galleryIds) && item.galleryIds.length > 0 &&
    item.galleryIds.every(id => typeof id === 'string') && item.topK === 10 && ['no_llm', 'with_llm'].includes(item.processingMode)
  ).slice(0, 12) : [];
} catch { /* La aplicación también funciona sin almacenamiento local. */ }

function toast(message) {
  const element = $('#toast');
  if (!element) return;
  element.textContent = message;
  element.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => element.classList.remove('show'), 3600);
}

function persist() {
  try { localStorage.setItem('atlas-history', JSON.stringify(history)); }
  catch { toast('El historial solo estará disponible durante esta sesión.'); }
}

function destroyMap() {
  mapMountGeneration += 1;
  mapMountPromise = null;
  mapHandle?.destroy();
  mapHandle = null;
}

function currentMapState() {
  return {
    retrievals: state.results,
    selectedKey: state.selected,
    galleryId: state.galleryIds[0],
    mode: state.mapMode,
    gridVisible: state.showGrid,
    buildingsVisible: state.showBuildings,
  };
}

function updateMapStatus(status) {
  state.mapAssets = status;
  const mapElement = $('#results-map');
  if (mapElement) {
    mapElement.dataset.mapBasemap = status.basemap || 'unknown';
    mapElement.dataset.mapCells = status.cells || 'unknown';
    mapElement.dataset.mapRenderer = status.renderer || 'unknown';
  }
  const label = $('#map-data-status');
  if (label) {
    label.textContent = status.message || 'Estado cartográfico no disponible.';
    label.dataset.state = status.basemap === 'ready' && status.cells === 'ready' ? 'ready' : 'partial';
    label.title = status.detail || '';
  }
  const mode3d = document.querySelector('[data-map-action="mode-3d"]');
  if (mode3d) mode3d.disabled = !status.buildings3dAvailable;
  const buildings = document.querySelector('[data-map-action="buildings"]');
  if (buildings) buildings.disabled = !status.buildings3dAvailable;
  const grid = document.querySelector('[data-map-action="grid"]');
  if (grid) grid.disabled = status.cells !== 'ready';
  const cellLegend = document.querySelector('.cell-legend');
  if (cellLegend) cellLegend.hidden = status.cells !== 'ready';
  const footnote = $('#results-footnote-text');
  if (footnote) {
    footnote.textContent = status.cells === 'ready'
      ? 'Se usan polígonos canónicos de las celdas; el centro no confirma la posición del observador. La similitud coseno no es una probabilidad.'
      : 'Sin geometría canónica disponible, el mapa no dibuja celdas aproximadas. La lista conserva los centros y el ranking; la similitud coseno no es una probabilidad.';
  }
}

function selectCandidate(key, { flyTo = false } = {}) {
  const candidate = allCandidates().find(item => item.key === key);
  if (!candidate) return;
  state.selected = key;
  if (flyTo) mapHandle?.flyTo(candidate);
  render();
}

function cancelSearch() {
  requestGuard.cancel();
  activeController?.abort();
  activeController = null;
  activeProgressStream?.close();
  activeProgressStream = null;
  if (state.pipeline) state.pipeline = cancelPipeline(state.pipeline);
  stopPipelineClock();
  state.request = { status: 'cancelled', error: null, requestId: null, response: null };
}

function clearResults() {
  cancelSearch();
  state.request = { status: 'idle', error: null, requestId: null, response: null };
  state.pipeline = null;
  state.results = [];
  state.selected = '';
  state.hasRun = false;
  state.last = null;
  state.mobileView = 'description';
  state.mapView = null;
  state.openSelect = '';
}

function shell() {
  $('#app').innerHTML = `<div class="app-body">
    <a class="skip-link" href="#main">Saltar al contenido principal</a>
    <header class="header"><a class="wordmark" href="#explore" aria-label="Inicio">${icon('compass', 27)}<span>Geolocalización textual</span></a><nav class="top-nav" aria-label="Vistas"><button data-page="explore" class="active">Explorar</button><button data-page="history">Historial</button></nav><div class="header-right"><span class="service-badge"><i></i>CrossText2Loc</span><button class="icon-button" data-action="help" aria-label="Ayuda">${icon('info')}</button></div></header>
    <main id="main" tabindex="-1"></main>
    <footer class="footer"><span>Geolocalización textual <span class="footer-dot">/</span> Madrid</span><span>TFG <span class="footer-dot">/</span> Scores no calibrados</span></footer>
  </div><dialog id="modal" aria-labelledby="modal-title"></dialog>`;
  $('#app').addEventListener('click', handleClick);
  $('#modal').addEventListener('click', event => { if (event.target === $('#modal')) $('#modal').close(); });
  document.addEventListener('click', event => {
    if (state.openSelect && !event.target.closest('.custom-select')) {
      state.openSelect = '';
      render();
    }
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && state.openSelect) {
      const id = state.openSelect;
      state.openSelect = '';
      render();
      queueMicrotask(() => document.querySelector(`[data-dropdown="${id}"]`)?.focus());
    }
  });
  window.addEventListener('hashchange', () => {
    const page = location.hash.slice(1);
    if (['explore', 'history'].includes(page)) navigate(page);
  });
  window.addEventListener('resize', () => mapHandle?.resize());
  render();
  loadCapabilities();
  loadDialogueCatalogue();
}

function navigate(page) {
  state.page = page;
  if (location.hash !== `#${page}`) window.history.replaceState(null, '', `#${page}`);
  render();
  window.scrollTo(0, 0);
}

function render() {
  const previousMapElement = $('#results-map');
  const preserveMapElement = state.page === 'explore' && Boolean(previousMapElement) && Boolean(mapHandle || mapMountPromise);
  if (state.page !== 'explore') destroyMap();
  document.querySelectorAll('[data-page]').forEach(element => {
    element.classList.toggle('active', element.dataset.page === state.page);
    if (element.dataset.page === state.page) element.setAttribute('aria-current', 'page');
    else element.removeAttribute('aria-current');
  });
  $('#main').innerHTML = state.page === 'explore' ? explorePage() : historyPage();
  if (state.page !== 'explore') return;

  const nextMapElement = $('#results-map');
  if (preserveMapElement && nextMapElement && nextMapElement !== previousMapElement) {
    nextMapElement.replaceWith(previousMapElement);
    mapHandle?.update(currentMapState());
    requestAnimationFrame(() => mapHandle?.resize());
  }
  $('#description')?.addEventListener('input', event => {
    state.text = event.target.value;
    $('#char-count').textContent = `${state.text.length} / 1.200`;
    $('#form-error').textContent = '';
  });
  $('#search-form')?.addEventListener('submit', event => { event.preventDefault(); runSearch(); });
  $('#dialogue-form')?.addEventListener('submit', event => { event.preventDefault(); startDialogueSession(); });
  $('#dialogue-answer-form')?.addEventListener('submit', event => { event.preventDefault(); submitDialogueAnswer(); });
  $('#dialogue-query')?.addEventListener('change', event => { state.dialogue.queryId=event.target.value;state.dialogue.session=null;state.dialogue.error=null;render(); });
  $('#dialogue-mode')?.addEventListener('change', event => { state.dialogue.mode=event.target.value;state.dialogue.queryId=event.target.value==='official'?'H27':'X-prueba';state.dialogue.session=null;render(); });
  $('#dialogue-variant-query')?.addEventListener('change',event=>{state.dialogue.variantQueryId=event.target.value;render();});
  $('#dialogue-length')?.addEventListener('change',event=>{state.dialogue.length=event.target.value;render();});
  renderDialogueVariantPanel();
  $('#dialogue-answer')?.addEventListener('input', event => { state.dialogue.answer=event.target.value; });
  $('#dialogue-answer-kind')?.addEventListener('change', event => { state.dialogue.answerKind=event.target.value; });
  document.querySelectorAll('.select-trigger').forEach(trigger => trigger.addEventListener('keydown', handleSelectKeydown));
  document.querySelectorAll('.select-menu [role="option"]').forEach(option => option.addEventListener('keydown', handleOptionKeydown));
  updateMapStatus(state.mapAssets);

  const mapIsVisible = state.mobileView === 'results' || !window.matchMedia('(max-width: 720px)').matches;
  if ($('#results-map') && state.capabilities.data?.search_area && mapIsVisible && !mapHandle && !mapMountPromise) {
    queueMicrotask(mountMap);
  }
}

async function loadCapabilities() {
  const epoch = requestGuard.next();
  state.capabilities = { status: 'loading', data: null, error: null };
  render();
  try {
    const data = await getCapabilities({ baseUrl: apiBaseUrl, timeoutMs: 12000 });
    if (!requestGuard.isCurrent(epoch)) return;
    const dialogueAvailable=data?.pipeline_progress?.stages?.some(item=>item.id==='dialoguevpr'&&item.available);
    if ((!data?.retrievers?.some(item => item.id === 'crosstext2loc' && item.available) && !dialogueAvailable) || !Array.isArray(data.galleries) || !data.galleries.length) throw new TypeError('CrossText2Loc y DialogueVPR no están disponibles.');
    state.capabilities = { status: 'ready', data, error: null };
    const available = new Set(data.galleries.map(item => item.gallery_id));
    state.galleryIds = state.galleryIds.filter(id => available.has(id));
    if (!state.galleryIds.length) state.galleryIds = [available.has('madrid-50m') ? 'madrid-50m' : data.galleries[0].gallery_id];
    const availableModes = new Set(data.processing_modes.filter(item => item.available).map(item => item.id));
    if (!availableModes.has(state.processingMode)) state.processingMode = 'no_llm';
  } catch (error) {
    if (!requestGuard.isCurrent(epoch)) return;
    state.capabilities = { status: 'error', data: null, error: normalizeUiError(error) };
  }
  if (requestGuard.isCurrent(epoch)) render();
}

async function loadDialogueCatalogue() {
  try { const [catalogue,variants]=await Promise.all([getDialogueQueries({baseUrl:apiBaseUrl,timeoutMs:12000}),getDialogueVariants({baseUrl:apiBaseUrl,timeoutMs:12000})]);state.dialogue.catalogue=catalogue;state.dialogue.variants=validateDescriptionVariantManifest(variants); }
  catch { state.dialogue.catalogue={available:false,queries:[]}; }
  render();
}

async function startDialogueSession() {
  if (state.dialogue.status==='loading') return;
  try {
    state.dialogue.status='loading';state.dialogue.error=null;render();
    const request=buildDialogueStart({mode:state.dialogue.mode,queryId:state.dialogue.queryId,description:state.text});
    state.dialogue.session=validateDialogueSession(await startDialogue(request,{baseUrl:apiBaseUrl,timeoutMs:300000}));state.dialogue.status='ready';
  } catch(error) { state.dialogue.status='error';state.dialogue.error=normalizeUiError(error); }
  render();
}

async function submitDialogueAnswer() {
  const session=state.dialogue.session;if (!session||state.dialogue.status==='loading') return;
  try {
    state.dialogue.status='loading';state.dialogue.error=null;render();
    const request=buildDialogueAnswer({literal:state.dialogue.answer,kind:state.dialogue.answerKind});
    state.dialogue.session=validateDialogueSession(await answerDialogue(session.session_id,request,{baseUrl:apiBaseUrl,timeoutMs:300000}));state.dialogue.answer='';state.dialogue.status='ready';
  } catch(error) { state.dialogue.status='error';state.dialogue.error=normalizeUiError(error); }
  render();
}

function normalizeUiError(error) {
  if (error?.name === 'AbortError') return { code: 'CANCELLED', message: 'La espera se ha cancelado. La inferencia iniciada puede continuar en el servidor.', requestId: '' };
  if (error instanceof AtlasApiError) {
    const messages = {
      RUNTIME_BUSY: 'El recuperador está ocupado. Espera un momento antes de reintentar.',
      RUNTIME_NOT_READY: 'El servicio todavía no está preparado.',
      LLM_NOT_READY: 'El modo Con LLM no está disponible en este arranque.',
      TRANSFORMATION_FAILED: 'Qwen no pudo transformar la descripción.',
      TRANSFORMATION_REJECTED: 'La transformación no superó los controles automáticos.',
      INFERENCE_FAILED: 'CrossText2Loc no pudo completar la consulta.',
      TIMEOUT: 'La consulta tardó más de lo esperado.',
    };
    return { code: error.code, message: messages[error.code] || error.message, requestId: error.requestId };
  }
  return { code: 'INVALID_API_RESPONSE', message: error?.message || 'La respuesta del servicio no es válida.', requestId: '' };
}

async function runSearch() {
  if (state.request.status === 'loading' || state.capabilities.status !== 'ready') return;
  const text = state.text.trim();
  if (text.length < 3) { $('#form-error').textContent = 'Escribe una descripción antes de buscar.'; $('#description').focus(); return; }
  const epoch = requestGuard.next();
  const controller = new AbortController();
  const queryId = createQueryId();
  activeController = controller;
  state.request = { status: 'loading', error: null, requestId: queryId, response: null };
  state.pipeline = createPipelineState({
    queryId,
    processingMode: state.processingMode,
    capabilities: state.capabilities.data,
    startedAt: performance.now(),
  });
  state.pipeline.queryText = text;
  state.results = [];
  state.selected = '';
  state.hasRun = false;
  state.mapView = null;
  state.mobileView = 'results';
  render();
  startPipelineClock(queryId, epoch);
  try {
    const request = buildRetrievalRequest({ text, language: state.language, galleryId: state.galleryIds[0], processingMode: state.processingMode, topK: 10, queryId });
    const progressStream = openProgressStream(queryId, {
      baseUrl: apiBaseUrl,
      onEvent: event => applyProgressEvent(event, epoch, queryId),
      onDisconnect: error => progressDisconnected(error, epoch, queryId),
    });
    activeProgressStream = progressStream;
    const progressAvailable = await progressStream.ready;
    if (!requestGuard.isCurrent(epoch)) return;
    if (!progressAvailable) {
      state.pipeline = markProgressUnavailable(state.pipeline);
      render();
    }
    const raw = await retrieve(request, { baseUrl: apiBaseUrl, signal: controller.signal, timeoutMs: state.processingMode === 'with_llm' ? 90000 : 30000 });
    if (!requestGuard.isCurrent(epoch)) return;
    const response = adaptRetrievalResponse(raw, request);
    state.pipeline = completePipelineFromResponse(state.pipeline, response);
    state.request = { status: 'success', error: null, requestId: queryId, response };
    state.results = response.retrievals;
    state.selected = response.retrievals[0]?.results[0]?.key || '';
    state.hasRun = true;
    state.mobileView = 'results';
    state.mapView = null;
    state.last = { mode: 'real', text, language: state.language, galleryIds: [...state.galleryIds], processingMode: state.processingMode, topK: 10, date: new Date().toISOString() };
    history.unshift({ ...state.last });
    history = history.slice(0, 12);
    persist();
  } catch (error) {
    if (!requestGuard.isCurrent(epoch)) return;
    state.request = { status: error?.name === 'AbortError' ? 'cancelled' : 'error', error: normalizeUiError(error), requestId: error?.requestId || queryId, response: null };
    state.pipeline = error?.name === 'AbortError'
      ? cancelPipeline(state.pipeline)
      : failPipeline(state.pipeline, state.request.error);
  } finally {
    if (requestGuard.isCurrent(epoch)) {
      activeController = null;
      activeProgressStream?.close();
      activeProgressStream = null;
      stopPipelineClock();
      render();
    }
  }
}

const pipelineStagePresentation = {
  llm: { title: 'LLM', subtitle: 'Transformación textual' },
  crosstext2loc: { title: 'CrossText2Loc', subtitle: 'Codificación y ranking exhaustivo' },
  vlm: { title: 'VLM', subtitle: 'Evidencia visual precalculada' },
  dialoguevpr: { title: 'DialogueVPR', subtitle: 'Aclaración interactiva' },
};
const pipelineStatusLabels = {
  pending: 'Pendiente', running: 'En curso', completed: 'Finalizada', failed: 'Error',
  skipped: 'Omitida', unavailable: 'No disponible', waiting_for_user: 'Espera tu respuesta', unknown: 'Progreso desconocido',
};

function formatElapsed(milliseconds) {
  const seconds = Math.max(0, Math.floor((Number(milliseconds) || 0) / 1000));
  return `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
}

function pipelinePanel() {
  const pipeline = state.pipeline;
  if (!pipeline) return '';
  const active = pipeline.stages.find(item => ['running', 'waiting_for_user'].includes(item.state));
  const overallLabel = pipeline.overall === 'completed' ? 'Consulta completada'
    : pipeline.overall === 'failed' ? 'Consulta finalizada con error'
      : pipeline.overall === 'cancelled' ? 'Espera cancelada'
        : pipeline.overall === 'unknown' ? 'Estado de ejecución desconocido'
          : active ? `${pipelineStagePresentation[active.id].title} en curso` : 'Consulta en curso';
  const marker = (item, index) => item.state === 'completed' ? '✓'
    : item.state === 'failed' ? '!'
      : item.state === 'running' ? '<span class="pipeline-spinner" aria-hidden="true"></span>'
        : item.state === 'waiting_for_user' ? '?'
          : item.state === 'unknown' ? '?'
            : item.state === 'unavailable' ? '—'
              : item.state === 'skipped' ? '–'
                : String(index + 1);
  const stages = pipeline.stages.map((item, index) => {
    const presentation = pipelineStagePresentation[item.id] || { title: item.id, subtitle: '' };
    const current = ['running', 'waiting_for_user'].includes(item.state) ? ' aria-current="step"' : '';
    const subphase = item.subphase
      ? `<small class="pipeline-subphase">${escapeHtml(item.subphase.id === 'text_encoding' ? 'Codificando representación textual' : item.subphase.id === 'ranking' ? `Ranking ${item.subphase.gallery_id || 'de la galería'}` : item.subphase.id)}${item.subphase.elapsed_ms != null ? ` · ${Number(item.subphase.elapsed_ms).toFixed(0)} ms` : ''}</small>`
      : '';
    return `<li class="pipeline-step state-${escapeHtml(item.state)}" data-stage="${escapeHtml(item.id)}"${current}><span class="pipeline-marker" aria-hidden="true">${marker(item, index)}</span><div class="pipeline-step-copy"><div class="pipeline-step-head"><h3>${escapeHtml(presentation.title)}</h3><span class="pipeline-state-label">${escapeHtml(pipelineStatusLabels[item.state] || item.state)}</span></div><p>${escapeHtml(item.message || presentation.subtitle)}</p>${subphase}</div></li>`;
  }).join('');
  return `<section class="pipeline-panel panel" aria-labelledby="pipeline-heading" aria-busy="${pipeline.overall === 'running'}" data-pipeline-overall="${escapeHtml(pipeline.overall)}" data-query-id="${escapeHtml(pipeline.queryId)}"><header class="pipeline-panel-header"><div><span class="panel-kicker">Ejecución</span><h2 id="pipeline-heading">Progreso de la consulta</h2><p id="pipeline-summary" role="status" aria-live="polite" aria-atomic="true">${escapeHtml(pipeline.message || overallLabel)}</p></div><div class="pipeline-clock"><span>Desde el envío</span><time id="pipeline-elapsed">${formatElapsed(pipeline.elapsedMs)}</time></div></header>${pipeline.queryText ? `<div class="pipeline-query"><strong>Descripción enviada</strong><p>${escapeHtml(pipeline.queryText)}</p></div>` : ''}<ol class="pipeline-steps" aria-label="Etapas del procesamiento">${stages}</ol>${pipeline.transport === 'unavailable' ? '<p class="pipeline-note">El endpoint síncrono sigue funcionando; no hay eventos intermedios. El estado final se confirmará con la respuesta.</p>' : ''}${pipeline.overall === 'cancelled' ? '<p class="pipeline-note">Cancelar la espera del navegador no detiene necesariamente el proceso que ya comenzó en el servidor.</p>' : ''}</section>`;
}

function updatePipelineElapsed() {
  const pipeline = state.pipeline;
  if (pipeline?.startedAt == null || pipeline.overall !== 'running') return;
  pipeline.elapsedMs = Math.max(0, performance.now() - pipeline.startedAt);
  const element = $('#pipeline-elapsed');
  if (element) element.textContent = formatElapsed(pipeline.elapsedMs);
}

function startPipelineClock(queryId, epoch) {
  clearInterval(pipelineClockTimer);
  pipelineClockTimer = setInterval(() => {
    if (!requestGuard.isCurrent(epoch) || state.pipeline?.queryId !== queryId || state.request.status !== 'loading') {
      clearInterval(pipelineClockTimer);
      pipelineClockTimer = null;
      return;
    }
    updatePipelineElapsed();
  }, 1000);
}

function stopPipelineClock() {
  clearInterval(pipelineClockTimer);
  pipelineClockTimer = null;
  updatePipelineElapsed();
}

function applyProgressEvent(event, epoch, queryId) {
  if (!requestGuard.isCurrent(epoch) || state.pipeline?.queryId !== queryId) return;
  const next = reducePipelineEvent(state.pipeline, event);
  if (next === state.pipeline) return;
  state.pipeline = next;
  if (state.page === 'explore') render();
}

function progressDisconnected(error, epoch, queryId) {
  if (!requestGuard.isCurrent(epoch) || state.pipeline?.queryId !== queryId || state.pipeline.transport === 'unavailable') return;
  state.pipeline = markProgressUnavailable(state.pipeline, 'Se perdió el canal SSE; las etapas en curso quedan sin confirmar.');
  if (state.page === 'explore') render();
  if (error) console.info('Seguimiento SSE no disponible; continúa el POST síncrono.');
}

function selectControl({ id, label, iconName, disabled, value, options }) {
  const selected = options.find(option => option.value === value) || options[0];
  const open = state.openSelect === id;
  return `<div class="select-field"><span class="field-label" id="${id}-label">${label}</span><div class="custom-select ${open ? 'open' : ''} ${disabled ? 'disabled' : ''}"><button type="button" id="${id}" class="select-trigger" data-dropdown="${id}" aria-labelledby="${id}-label ${id}-value" aria-haspopup="listbox" aria-expanded="${open}" ${disabled ? 'disabled' : ''}>${icon(iconName, 17)}<span id="${id}-value">${escapeHtml(selected?.label || 'No disponible')}</span><span class="select-chevron">${icon('down', 15)}</span></button>${open ? `<div class="select-menu" role="listbox" aria-labelledby="${id}-label">${options.map(option => `<button type="button" role="option" data-select-id="${id}" data-select-value="${escapeHtml(option.value)}" aria-selected="${option.value === value}"><span>${escapeHtml(option.label)}</span>${option.value === value ? icon('check', 15) : ''}</button>`).join('')}</div>` : ''}</div></div>`;
}

function explorePage() {
  const ready = state.capabilities.status === 'ready' && state.capabilities.data?.retrievers?.some(item=>item.id==='crosstext2loc'&&item.available)===true;
  const loading = state.request.status === 'loading';
  const galleries = state.capabilities.data?.galleries || [];
  const count = state.results.reduce((total, row) => total + row.results.length, 0);
  const status = state.capabilities.status === 'loading'
    ? '<div class="service-state">Comprobando disponibilidad del servicio…</div>'
    : state.capabilities.status === 'error'
      ? `<div class="service-state error"><strong>Backend no disponible</strong><span>${escapeHtml(state.capabilities.error.message)}</span><button type="button" class="secondary" data-action="retry-capabilities">Reintentar conexión</button></div>`
      : '';
  const requestError = state.request.error
    ? `<div class="service-state ${state.request.status === 'cancelled' ? '' : 'error'}" role="alert"><strong>${state.request.status === 'cancelled' ? 'Petición cancelada' : 'No se pudo completar la búsqueda'}</strong><span>${escapeHtml(state.request.error.message)}</span>${state.request.error.requestId ? `<small>Referencia: ${escapeHtml(state.request.error.requestId)}</small>` : ''}</div>`
    : '';
  const galleryOptions = galleries.map(gallery => ({ value: gallery.gallery_id, label: `${galleryLabel(gallery.gallery_id)} · ${gallery.candidate_count} candidatos` }));
  const modeOptions = (state.capabilities.data?.processing_modes || []).filter(mode => mode.available).map(mode => ({
    value: mode.id,
    label: mode.id === 'with_llm' ? 'Con LLM · en_cartographic (experimental)' : 'Sin LLM · texto original',
  }));
  const selectedCellSize = /-(25|50)m$/.exec(state.galleryIds[0])?.[1] || '';
  const mapReady = state.mapAssets.cells === 'ready';
  const mapMessage = state.mapAssets.message || 'Comprobando recursos cartográficos locales…';

  return `<section class="page-heading"><div><div class="eyebrow">RECUPERACIÓN CROSSTEXT2LOC</div><h1>Explora los lugares que describes.</h1><p>Revisa el Top-10 dentro de la región piloto de Madrid.</p></div><div class="location-pill">${icon('pin', 16)} Madrid · D004</div></section>
  <div class="mobile-view-switch" role="group" aria-label="Vista de exploración"><button data-mobile="description" aria-pressed="${state.mobileView === 'description'}">${icon('chat', 16)} Descripción</button><button data-mobile="results" aria-pressed="${state.mobileView === 'results'}">${icon('pin', 16)} Mapa y resultados</button></div>
  <div class="workspace" data-mobile-view="${state.mobileView}">
    <section class="search-panel panel"><div class="panel-heading"><span class="panel-kicker">Consulta</span><h2>¿Qué ves a tu alrededor?</h2><p>Incluye edificios, espacios abiertos y detalles distintivos.</p></div>${status}<form id="search-form"><label for="description" class="field-label">Descripción del entorno</label><div class="textarea-wrap"><textarea id="description" name="description" autocomplete="off" maxlength="1200" rows="4" placeholder="Veo una plaza amplia rodeada de edificios…" ${loading ? 'disabled' : ''}>${escapeHtml(state.text)}</textarea><div class="textarea-footer"><span>Idioma: español</span><span id="char-count">${state.text.length} / 1.200</span></div></div><div class="example-label">Prueba una descripción</div><div class="example-chips">${examples.map((example, index) => `<button type="button" class="example-chip" data-example="${index}" ${loading ? 'disabled' : ''}>${escapeHtml(example.label)}</button>`).join('')}</div>${selectControl({ id: 'gallery', label: 'Galería', iconName: 'layers', disabled: !ready || loading, value: state.galleryIds[0], options: galleryOptions })}${selectControl({ id: 'processing', label: 'Procesamiento', iconName: 'chat', disabled: !ready || loading, value: state.processingMode, options: modeOptions })}<div class="unknown-note">${state.processingMode === 'with_llm' ? 'Con LLM transforma una vez con Qwen en_cartographic. No implica superioridad científica.' : 'Sin LLM envía el texto español directamente a CrossText2Loc.'}</div><p class="form-error" id="form-error" role="alert"></p><button class="primary search-button" type="submit" ${!ready || loading ? 'disabled' : ''}>${loading ? '<span class="spinner"></span> ' + (state.processingMode === 'with_llm' ? 'Transformando y recuperando…' : 'Recuperando candidatos…') : icon('search', 18) + ' Buscar Top-10 ' + icon('arrow', 18)}</button></form>${loading ? '<button class="cancel-button" data-action="cancel">Cancelar espera</button>' : ''}${requestError}<p class="privacy-note">${icon('info', 13)} La descripción se envía al servicio local del TFG. No introduzcas datos personales.</p></section>
    <section class="exploration" aria-label="Mapa y ranking de resultados">
      ${dialogueControls()}
      ${pipelinePanel()}
      <section class="map-panel panel" aria-labelledby="map-heading">
        <div class="map-top"><div class="map-title"><span class="panel-kicker">Madrid · región piloto</span><strong id="map-heading">Mapa de candidatos</strong></div><div class="map-legend"><span class="evaluation-legend"><i></i> D004</span>${selectedCellSize ? `<span class="cell-legend"><i></i> Celda ${selectedCellSize} × ${selectedCellSize} m</span>` : ''}<span class="map-meta">WGS84</span></div></div>
        <div class="map-toolbar" role="toolbar" aria-label="Controles del mapa"><div class="map-mode-group" role="group" aria-label="Perspectiva"><button type="button" data-map-action="mode-2d" aria-pressed="${state.mapMode === '2d'}">2D</button><button type="button" data-map-action="mode-3d" aria-pressed="${state.mapMode === '3d'}" ${state.mapAssets.buildings3dAvailable ? '' : 'disabled title="Requiere teselas locales de edificios"'}>3D visual</button></div><button type="button" class="map-tool" data-map-action="buildings" aria-pressed="${state.showBuildings}" ${state.mapAssets.buildings3dAvailable ? '' : 'disabled'}>${icon('building', 15)} Extrusiones</button><button type="button" class="map-tool" data-map-action="grid" aria-pressed="${state.showGrid}" ${mapReady ? '' : 'disabled'}>${icon('layers', 15)} Cuadrícula</button><button type="button" class="map-tool" data-map-action="north" aria-label="Orientar al norte">${icon('compass', 15)} Norte</button><button type="button" class="map-tool" data-map-action="reset" aria-label="Centrar región evaluada">${icon('target', 15)} Centrar región evaluada</button></div>
        <p id="map-data-status" class="map-data-status" role="status" aria-live="polite" data-state="partial">${escapeHtml(mapMessage)}</p>
        <div id="results-map" class="real-map" aria-label="Mapa interactivo de la región D004 y los candidatos del Top-10" aria-describedby="map-description"></div>
        <p id="map-description" class="sr-only">El mapa complementa la lista textual de resultados. Las celdas representan candidatos del catálogo, no la posición confirmada del observador.</p>
      </section>
      <div class="results-heading"><div><span class="panel-kicker">Ranking</span><h2>${count ? 'Resultados de la consulta' : 'Aún no hay resultados'}</h2></div><span class="result-count">${count} candidatos</span></div>
      ${state.results.length ? state.results.map(galleryResults).join('') : `<div class="empty-state compact">${icon('search', 26)}<h3>${state.hasRun ? 'La respuesta no contiene candidatos' : 'Describe tu entorno para comenzar'}</h3><p>Los candidatos aparecerán aquí y se sincronizarán con el mapa.</p></div>`}
      <div class="results-footnote">${icon('info', 13)} <span id="results-footnote-text">${mapReady ? 'Se usan polígonos canónicos de las celdas; el centro no confirma la posición del observador. La similitud coseno no es una probabilidad.' : 'Sin geometría canónica disponible, el mapa no dibuja celdas aproximadas. La lista conserva los centros y el ranking; la similitud coseno no es una probabilidad.'}</span></div>
    </section>
  </div>`;
}

function dialogueControls() {
  const dialogue=state.dialogue;const available=dialogue.catalogue?.available===true;const official=(dialogue.catalogue?.queries||[]).filter(item=>!item.completed);const session=dialogue.session;const imageUrl=dialogue.mode==='official'&&dialogue.queryId?`${apiBaseUrl}/dialogue/queries/${encodeURIComponent(dialogue.queryId)}/image`:null;const question=session?.current_question;
  const selectedOfficial=official.find(row=>row.query_id===dialogue.queryId);
  return `<section class="dialogue-controls panel" aria-labelledby="dialogue-heading"><div class="section-label">DIALOGUEVPR</div><h3 id="dialogue-heading">Sesión interactiva</h3><p class="small muted">Escribe la descripción tú mismo. Las sesiones oficiales exigen coincidencia exacta con el texto congelado.</p><form id="dialogue-form"><label class="field-label" for="dialogue-mode">Tipo</label><select id="dialogue-mode"><option value="official" ${dialogue.mode==='official'?'selected':''}>Cohorte oficial</option><option value="exploratory" ${dialogue.mode==='exploratory'?'selected':''}>Exploratoria separada</option></select><label class="field-label" for="dialogue-query">Identificador</label>${dialogue.mode==='official'?`<select id="dialogue-query">${official.map(row=>`<option value="${escapeHtml(row.query_id)}" ${row.query_id===dialogue.queryId?'selected':''} ${!row.image_available?'disabled':''}>${escapeHtml(row.query_id)}${row.image_available?'':' · sin imagen'}</option>`).join('')}</select>`:`<input id="dialogue-query" value="${escapeHtml(dialogue.queryId)}" placeholder="X-prueba">`}${selectedOfficial?`<small class="dialogue-hash">Descripción oficial SHA-256: ${escapeHtml(selectedOfficial.description_sha256)}</small>`:''}${imageUrl?`<img class="dialogue-reference" src="${imageUrl}" alt="Fotografía original de ${escapeHtml(dialogue.queryId)}">`:''}<button class="secondary full-width" type="submit" ${!available||dialogue.status==='loading'||session?.status==='awaiting_answer'?'disabled':''}>Iniciar DialogueVPR</button></form>${!available?'<p class="service-state">Runtime DialogueVPR no configurado en este arranque.</p>':''}${dialogue.error?`<p class="service-state error">${escapeHtml(dialogue.error.message)}</p>`:''}${question?`<form id="dialogue-answer-form" class="dialogue-question"><strong>Pregunta ${question.turn_index}</strong><p>${escapeHtml(question.question)}</p><textarea id="dialogue-answer" rows="2" maxlength="600" placeholder="Respuesta literal">${escapeHtml(dialogue.answer)}</textarea><select id="dialogue-answer-kind"><option value="affirmation">Sí / afirmación</option><option value="negation" ${dialogue.answerKind==='negation'?'selected':''}>No / negación</option><option value="unknown">Desconocida</option><option value="unobservable">No observable</option><option value="ambiguous">Ambigua</option><option value="stop">Detener</option></select><button class="primary full-width" type="submit" ${dialogue.status==='loading'?'disabled':''}>Guardar respuesta y continuar</button></form>`:''}${session?.status==='completed'?`<p class="service-state"><strong>Sesión completada</strong><span>${escapeHtml(session.stop_reason||'Criterio de parada alcanzado')}</span><small>SHA-256: ${escapeHtml(session.session_sha256)}</small></p>`:''}</section>`;
}

function renderDialogueVariantPanel(){
  if(state.dialogue.mode!=='exploratory')return;
  const form=$('#dialogue-form');const mode=$('#dialogue-mode');if(!form||!mode)return;
  const variant=getDescriptionVariant(state.dialogue.variants,state.dialogue.variantQueryId,state.dialogue.length);if(!variant)return;
  const fieldset=document.createElement('fieldset');fieldset.className='dialogue-variants';fieldset.innerHTML=`<legend>Descripción experimental</legend><label class="field-label" for="dialogue-variant-query">HXX de origen</label><select id="dialogue-variant-query">${state.dialogue.variants.scope_query_ids.map(id=>`<option value="${id}" ${id===state.dialogue.variantQueryId?'selected':''}>${id}</option>`).join('')}</select><label class="field-label" for="dialogue-length">Longitud</label><select id="dialogue-length">${[['short','Corta'],['medium','Media'],['long','Larga']].map(([id,label])=>`<option value="${id}" ${id===state.dialogue.length?'selected':''}>${label}</option>`).join('')}</select><div class="dialogue-preview"><strong>${variant.word_count} palabras</strong><p>${escapeHtml(variant.text_es)}</p><small>${variant.text_sha256}</small></div><img class="dialogue-reference" src="${apiBaseUrl}/dialogue/queries/${variant.source_query_id}/image" alt="Fotografía original de ${variant.source_query_id}"><button class="secondary full-width" type="button" data-action="load-dialogue-variant">Cargar descripción seleccionada</button>`;mode.insertAdjacentElement('afterend',fieldset);
  $('#dialogue-variant-query')?.addEventListener('change',event=>{state.dialogue.variantQueryId=event.target.value;render();});
  $('#dialogue-length')?.addEventListener('change',event=>{state.dialogue.length=event.target.value;render();});
}

function selectValue(id, value) {
  state.openSelect = '';
  if (id === 'gallery') state.galleryIds = [value];
  else if (id === 'processing') state.processingMode = value;
  clearResults();
  render();
}

function handleSelectKeydown(event) {
  const id = event.currentTarget.dataset.dropdown;
  if (['ArrowDown', 'ArrowUp', 'Enter', ' '].includes(event.key)) {
    event.preventDefault();
    if (state.openSelect !== id) { state.openSelect = id; render(); queueMicrotask(() => document.querySelector(`[data-select-id="${id}"]`)?.focus()); }
  } else if (event.key === 'Escape' && state.openSelect) { state.openSelect = ''; render(); queueMicrotask(() => document.querySelector(`[data-dropdown="${id}"]`)?.focus()); }
}

function handleOptionKeydown(event) {
  const options = [...event.currentTarget.parentElement.querySelectorAll('[role="option"]')];
  const index = options.indexOf(event.currentTarget);
  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault();
    options[(index + (event.key === 'ArrowDown' ? 1 : -1) + options.length) % options.length].focus();
  } else if (event.key === 'Home' || event.key === 'End') {
    event.preventDefault();
    options[event.key === 'Home' ? 0 : options.length - 1].focus();
  }
}

function galleryResults(retrieval) {
  const visual = state.request.response?.visualPostprocessing;
  const status = visual?.status === 'applied' ? 'Evidencia visual experimental aplicada'
    : visual?.status === 'fallback_baseline' ? 'Sin evidencia compatible · ranking CT2L'
      : 'Ranking CrossText2Loc';
  return `<section class="gallery-results"><header><div><p>${retrieval.galleryCount} candidatos evaluados · Top-${retrieval.effectiveK}</p><small>${escapeHtml(status)}</small></div></header><div class="result-grid real-results">${retrieval.results.map(candidate => resultCard(candidate, candidate.key === state.selected)).join('')}</div></section>`;
}

function resultCard(candidate, selected) {
  return `<article class="result-card real-card ${selected ? 'selected' : ''}" id="card-${escapeHtml(candidate.key)}"><button class="card-select" data-select="${escapeHtml(candidate.key)}" aria-label="Seleccionar candidato ${escapeHtml(candidate.id)}" aria-pressed="${selected}"><div class="card-content"><span class="rank-badge">${String(candidate.rank).padStart(2, '0')}</span><div class="card-title"><h3>${escapeHtml(candidate.id)}</h3>${icon('chevron', 15)}</div><p>${escapeHtml(galleryLabel(candidate.galleryId))}</p><div class="coordinate-compact">${candidate.lat.toFixed(6)}, ${candidate.lon.toFixed(6)}</div><div class="score-row"><span>Similitud coseno</span><strong>${candidate.similarity.toFixed(4)}</strong></div></div></button><button class="card-detail" data-detail="${escapeHtml(candidate.key)}">Ver datos ${icon('chevron', 13)}</button></article>`;
}

function allCandidates() { return state.results.flatMap(row => row.results); }

async function mountMap() {
  if (mapHandle || mapMountPromise || state.page !== 'explore') return;
  const generation = ++mapMountGeneration;
  const task = (async () => {
    const { createResultsMap } = await import('./map.js');
    if (generation !== mapMountGeneration || state.page !== 'explore') return;
    const element = $('#results-map');
    const searchArea = state.capabilities.data?.search_area;
    if (!element || !searchArea) return;
    const handle = await createResultsMap({
      element,
      ...currentMapState(),
      view: state.mapView,
      searchArea,
      onSelect: key => selectCandidate(key, { flyTo: true }),
      onViewChange: view => { state.mapView = view; },
      onStatus: updateMapStatus,
    });
    if (!handle) return;
    if (generation !== mapMountGeneration || state.page !== 'explore' || element !== $('#results-map')) {
      handle.destroy();
      return;
    }
    mapHandle = handle;
    mapHandle.update(currentMapState());
    updateMapStatus(handle.status || state.mapAssets);
    requestAnimationFrame(() => mapHandle?.resize());
    if (!allCandidates().length) state.mapView = null;
  })();
  mapMountPromise = task;
  try {
    await task;
  } catch (error) {
    if (generation === mapMountGeneration) {
      updateMapStatus({ renderer: 'unavailable', basemap: 'error', cells: 'error', buildings3dAvailable: false, message: 'No se pudo iniciar el mapa local.', detail: error?.message || String(error) });
    }
  } finally {
    if (generation === mapMountGeneration) mapMountPromise = null;
  }
}

function historyPage() {
  return `<section class="page-heading"><div><div class="eyebrow">HISTORIAL LOCAL</div><h1>Consultas recientes.</h1><p>Se conservan únicamente los ajustes de las últimas búsquedas en este navegador.</p></div><button class="secondary" data-action="clear-history" ${history.length ? '' : 'disabled'}>${icon('trash', 16)} Borrar historial</button></section><section class="history-list panel">${history.length ? history.map((item, index) => `<article class="history-item"><div class="history-item-icon">${icon('history', 23)}</div><div><span class="section-label">${escapeHtml(new Date(item.date).toLocaleString('es-ES', { dateStyle: 'medium', timeStyle: 'short' }))}</span><h3>${escapeHtml(item.text)}</h3><p>${escapeHtml(item.galleryIds.join(', '))} · ${escapeHtml(processingLabel(item.processingMode))} · Top-10</p></div><button class="secondary" data-restore="${index}">Recuperar ${icon('arrow', 15)}</button></article>`).join('') : `<div class="empty-state">${icon('history', 38)}<h2>Aún no hay consultas</h2><p>Haz una búsqueda para poder recuperarla después.</p><button class="primary" data-page="explore">Empezar a explorar ${icon('arrow', 17)}</button></div>`}</section>`;
}

function openModal(content) {
  $('#modal').innerHTML = `<button class="modal-close icon-button" data-action="close-modal" aria-label="Cerrar ventana">${icon('close')}</button>${content}`;
  $('#modal').showModal();
}

function showDetail(key) {
  const candidate = allCandidates().find(row => row.key === key);
  if (!candidate) return;
  const response = state.request.response;
  const visual = response?.visualPostprocessing;
  const visualText = visual?.status === 'applied'
    ? 'El postprocesador experimental aplicó evidencia Qwen3-VL precalculada; no ejecutó el modelo visual en línea.'
    : visual?.status === 'fallback_baseline'
      ? 'Sin evidencia precalculada compatible: se conserva exactamente el ranking CrossText2Loc.'
      : 'Postprocesamiento visual no configurado: se conserva CrossText2Loc.';
  openModal(`<div class="modal-content settings-content"><span class="section-label">CANDIDATO RECUPERADO · TOP-${candidate.rank}</span><h2 id="modal-title">${escapeHtml(candidate.id)}</h2><p class="muted">${escapeHtml(galleryLabel(candidate.galleryId))}</p><div class="coordinate-row">${icon('pin', 16)} <code>${candidate.lat.toFixed(7)}, ${candidate.lon.toFixed(7)}</code><button class="text-button" data-copy="${escapeHtml(candidate.key)}">${icon('copy', 14)} Copiar</button></div><h3>Puntuación de similitud coseno CT2L</h3><div class="similarity-detail"><strong>${candidate.similarity.toFixed(6)}</strong></div><div class="unknown-note">${icon('info', 17)} La puntuación expresa similitud coseno; no es una probabilidad de acierto ni una confianza calibrada.</div><div class="visual-status">${icon('layers', 19)}<div><strong>CrossText2Loc + evidencia visual</strong><p>${escapeHtml(visualText)} Tiempo interno: ${Number(response?.timingsMs?.total || 0).toFixed(2)} ms.</p></div></div><a class="secondary full-width" href="https://www.openstreetmap.org/?mlat=${candidate.lat}&mlon=${candidate.lon}#map=18/${candidate.lat}/${candidate.lon}" target="_blank" rel="noopener noreferrer">Abrir en OpenStreetMap ${icon('arrow', 16)}</a></div>`);
}

function updateMapAction(action) {
  switch (action) {
    case 'mode-2d':
      state.mapMode = '2d';
      mapHandle?.setMode('2d');
      break;
    case 'mode-3d':
      if (!state.mapAssets.buildings3dAvailable) return;
      state.mapMode = '3d';
      mapHandle?.setMode('3d');
      break;
    case 'buildings':
      if (!state.mapAssets.buildings3dAvailable) return;
      state.showBuildings = !state.showBuildings;
      mapHandle?.setBuildings(state.showBuildings);
      break;
    case 'grid':
      if (state.mapAssets.cells !== 'ready') return;
      state.showGrid = !state.showGrid;
      mapHandle?.setGrid(state.showGrid);
      break;
    case 'north':
      mapHandle?.north();
      break;
    case 'reset':
      mapHandle?.reset();
      break;
    default:
      return;
  }
  render();
}

async function handleClick(event) {
  const button = event.target.closest('button');
  if (!button || button.disabled) return;
  const data = button.dataset;
  if (data.mobile) { state.mobileView = data.mobile; render(); document.querySelector(`[data-mobile="${data.mobile}"]`).focus({ preventScroll: true }); return; }
  if (data.mapAction) return updateMapAction(data.mapAction);
  if(data.action==='load-dialogue-variant'){const variant=getDescriptionVariant(state.dialogue.variants,state.dialogue.variantQueryId,state.dialogue.length);if(!variant)return;state.dialogue.queryId=experimentalSessionId(variant.source_query_id,variant.length);state.text=variant.text_es;clearResults();render();toast('Variante experimental cargada; requiere autorización separada.');return;}
  if (data.dropdown) { state.openSelect = state.openSelect === data.dropdown ? '' : data.dropdown; render(); queueMicrotask(() => (state.openSelect ? document.querySelector(`[data-select-id="${data.dropdown}"]`) : document.querySelector(`[data-dropdown="${data.dropdown}"]`))?.focus()); return; }
  if (data.selectId) { selectValue(data.selectId, data.selectValue); return; }
  if (data.page) return navigate(data.page);
  if (data.example !== undefined) { state.text = examples[Number(data.example)].text; clearResults(); render(); return; }
  if (data.select) { selectCandidate(data.select, { flyTo: true }); return; }
  if (data.detail) return showDetail(data.detail);
  if (data.restore !== undefined) {
    const item = history[Number(data.restore)];
    if (!item) return;
    clearResults();
    state.text = item.text;
    const available = new Set(state.capabilities.data?.galleries?.map(gallery => gallery.gallery_id) || []);
    const restored = item.galleryIds.filter(id => available.has(id));
    if (!restored.length) { toast('La galería guardada ya no está disponible.'); return; }
    state.galleryIds = restored;
    state.processingMode = item.processingMode;
    state.topK = 10;
    navigate('explore');
    toast('Consulta recuperada.');
    return;
  }
  if (data.copy) {
    const candidate = allCandidates().find(item => item.key === data.copy);
    if (!candidate) return;
    try { await navigator.clipboard.writeText(`${candidate.lat}, ${candidate.lon}`); toast('Coordenadas copiadas.'); }
    catch { toast(`Coordenadas: ${candidate.lat}, ${candidate.lon}`); }
    return;
  }
  switch (data.action) {
    case 'close-modal': $('#modal').close(); break;
    case 'cancel': cancelSearch(); render(); toast('Espera cancelada. La inferencia del servidor puede continuar.'); break;
    case 'retry-capabilities': loadCapabilities(); break;
    case 'clear-history': openModal('<div class="modal-content settings-content"><h2 id="modal-title">¿Borrar el historial local?</h2><p class="muted">Se eliminarán las consultas guardadas en este navegador.</p><div class="modal-actions"><button class="secondary" data-action="close-modal">Conservar</button><button class="primary" data-action="confirm-clear">Borrar historial</button></div></div>'); break;
    case 'confirm-clear': history = []; persist(); $('#modal').close(); render(); toast('Historial borrado.'); break;
    case 'help': openModal(`<div class="modal-content settings-content"><span class="section-label">SOBRE EL SISTEMA</span><h2 id="modal-title">Geolocalización textual</h2><p>La descripción se codifica con CrossText2Loc y se compara con la galería OSM de Madrid.</p><div class="help-step"><span>01</span><p>Describe el entorno y selecciona la resolución.</p></div><div class="help-step"><span>02</span><p>Revisa candidatos, celdas y coordenadas WGS84.</p></div><div class="unknown-note">${icon('info', 18)} La similitud coseno no es una probabilidad y el Top-1 no confirma tu ubicación.</div><p class="small muted">El mapa es una herramienta de exploración; las celdas no son ground truth.</p></div>`); break;
  }
}

state.page = ['explore', 'history'].includes(location.hash.slice(1)) ? location.hash.slice(1) : 'explore';
shell();
