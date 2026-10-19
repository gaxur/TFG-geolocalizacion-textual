import './minimal.css';
import { icon } from './visuals.js';
import { AtlasApiError, apiBaseUrl, getCapabilities, retrieve } from './api.js';
import { adaptRetrievalResponse, buildRetrievalRequest, createQueryId, createRequestGuard, galleryLabel } from './retrieval.js';
import { createResultsMap } from './map.js';

const $ = selector => document.querySelector(selector);
const escapeHtml = value => String(value).replace(/[&<>"']/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character]));
const similarityPercent = value => `${(value * 100).toFixed(2).replace('.', ',')} %`;
const examples = [
  { label: 'Plaza y reloj', text: 'Estoy en una plaza peatonal amplia. Veo un edificio claro con un reloj en lo alto y varias calles que salen de la plaza.' },
  { label: 'Soportales y estatua', text: 'Estoy en una plaza rodeada de edificios rojizos con soportales. En el centro hay una estatua de una persona a caballo.' },
  { label: 'Parque y estanque', text: 'Estoy en un parque y delante de mí hay un estanque. Al otro lado veo un monumento grande rodeado de columnas.' },
];
const state = {
  page: 'explore', mobileView: 'description', text: examples[0].text, language: 'es', topK: 5,
  galleryIds: ['madrid-50m'], capabilities: { status: 'loading', data: null, error: null },
  request: { status: 'idle', error: null, requestId: null, response: null },
  results: [], selected: '', hasRun: false, last: null, mapView: null, openSelect: '',
};
let toastTimer;
let activeController = null;
let mapHandle = null;
const requestGuard = createRequestGuard();
let history = [];

try {
  const stored = JSON.parse(localStorage.getItem('atlas-history') || '[]');
  history = Array.isArray(stored) ? stored.filter(item =>
    item?.mode === 'real' && typeof item.text === 'string' && item.text.length <= 1200 &&
    typeof item.date === 'string' && Array.isArray(item.galleryIds) && item.galleryIds.length > 0 &&
    item.galleryIds.every(id => typeof id === 'string') && [3, 5, 10].includes(item.topK)
  ).slice(0, 12) : [];
} catch { /* La aplicación también funciona sin almacenamiento local. */ }

function toast(message) {
  $('#toast').textContent = message;
  $('#toast').classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => $('#toast').classList.remove('show'), 3600);
}

function persist() {
  try { localStorage.setItem('atlas-history', JSON.stringify(history)); }
  catch { toast('El historial solo estará disponible durante esta sesión.'); }
}

function destroyMap() { mapHandle?.destroy(); mapHandle = null; }

function cancelSearch() {
  requestGuard.cancel();
  activeController?.abort();
  activeController = null;
  state.request = { status: 'cancelled', error: null, requestId: null, response: null };
}

function clearResults() {
  cancelSearch();
  state.request = { status: 'idle', error: null, requestId: null, response: null };
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
    <header class="header"><a class="wordmark" href="#explore" aria-label="Inicio">${icon('compass', 27)}<span>Geolocalización textual</span></a><nav class="top-nav" aria-label="Vistas"><button data-page="explore" class="active">Explorar</button><button data-page="history">Historial</button></nav><div class="header-right"><span class="service-badge"><i></i>CrossText2Loc</span><button class="icon-button" data-action="help" aria-label="Ayuda">${icon('info')}</button></div></header>
    <main id="main"></main>
    <footer class="footer"><span>Geolocalización textual <span class="footer-dot">/</span> Madrid</span><span>TFG <span class="footer-dot">/</span> Similitudes no calibradas</span></footer>
  </div><dialog id="modal" aria-labelledby="modal-title"></dialog>`;
  $('#app').addEventListener('click', handleClick);
  $('#modal').addEventListener('click', event => { if (event.target === $('#modal')) $('#modal').close(); });
  document.addEventListener('click', event => { if (state.openSelect && !event.target.closest('.custom-select')) { state.openSelect = ''; render(); } });
  document.addEventListener('keydown', event => { if (event.key === 'Escape' && state.openSelect) { const id = state.openSelect; state.openSelect = ''; render(); queueMicrotask(() => document.querySelector(`[data-dropdown="${id}"]`)?.focus()); } });
  window.addEventListener('hashchange', () => { const page = location.hash.slice(1); if (['explore', 'history'].includes(page)) navigate(page); });
  render();
  loadCapabilities();
}

function navigate(page) {
  state.page = page;
  if (location.hash !== `#${page}`) window.history.replaceState(null, '', `#${page}`);
  render();
  window.scrollTo(0, 0);
}

function render() {
  destroyMap();
  document.querySelectorAll('[data-page]').forEach(element => {
    element.classList.toggle('active', element.dataset.page === state.page);
    if (element.dataset.page === state.page) element.setAttribute('aria-current', 'page');
    else element.removeAttribute('aria-current');
  });
  $('#main').innerHTML = state.page === 'explore' ? explorePage() : historyPage();
  if (state.page !== 'explore') return;
  $('#description').addEventListener('input', event => { state.text = event.target.value; $('#char-count').textContent = `${state.text.length} / 1.200`; $('#form-error').textContent = ''; });
  $('#search-form').addEventListener('submit', event => { event.preventDefault(); runSearch(); });
  document.querySelectorAll('.select-trigger').forEach(trigger => trigger.addEventListener('keydown', handleSelectKeydown));
  document.querySelectorAll('.select-menu [role="option"]').forEach(option => option.addEventListener('keydown', handleOptionKeydown));
  if ($('#results-map') && state.capabilities.data?.search_area && (state.mobileView === 'results' || !window.matchMedia('(max-width: 720px)').matches)) queueMicrotask(mountMap);
}

async function loadCapabilities() {
  const epoch = requestGuard.next();
  state.capabilities = { status: 'loading', data: null, error: null };
  render();
  try {
    const data = await getCapabilities({ baseUrl: apiBaseUrl, timeoutMs: 12000 });
    if (!requestGuard.isCurrent(epoch)) return;
    if (!data?.retrievers?.some(item => item.id === 'crosstext2loc' && item.available) || !Array.isArray(data.galleries) || !data.galleries.length) throw new TypeError('CrossText2Loc no está disponible.');
    state.capabilities = { status: 'ready', data, error: null };
    const available = new Set(data.galleries.map(item => item.gallery_id));
    state.galleryIds = state.galleryIds.filter(id => available.has(id));
    if (!state.galleryIds.length) state.galleryIds = [available.has('madrid-50m') ? 'madrid-50m' : data.galleries[0].gallery_id];
  } catch (error) {
    if (!requestGuard.isCurrent(epoch)) return;
    state.capabilities = { status: 'error', data: null, error: normalizeUiError(error) };
  }
  if (requestGuard.isCurrent(epoch)) render();
}

function normalizeUiError(error) {
  if (error?.name === 'AbortError') return { code: 'CANCELLED', message: 'La espera se ha cancelado. La inferencia iniciada puede continuar en el servidor.', requestId: '' };
  if (error instanceof AtlasApiError) {
    const messages = { RUNTIME_BUSY: 'El recuperador está ocupado. Espera un momento antes de reintentar.', RUNTIME_NOT_READY: 'El servicio todavía no está preparado.', INFERENCE_FAILED: 'CrossText2Loc no pudo completar la consulta.', TIMEOUT: 'La consulta tardó más de lo esperado.' };
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
  state.results = []; state.selected = ''; state.hasRun = false; state.mapView = null;
  render();
  try {
    const request = buildRetrievalRequest({ text, language: state.language, galleryIds: state.galleryIds, topK: state.topK, queryId });
    const raw = await retrieve(request, { baseUrl: apiBaseUrl, signal: controller.signal, timeoutMs: 30000 });
    if (!requestGuard.isCurrent(epoch)) return;
    const response = adaptRetrievalResponse(raw, request);
    state.request = { status: 'success', error: null, requestId: queryId, response };
    state.results = response.retrievals;
    state.selected = response.retrievals[0]?.results[0]?.key || '';
    state.hasRun = true; state.mobileView = 'results'; state.mapView = null;
    state.last = { mode: 'real', text, language: state.language, galleryIds: [...state.galleryIds], topK: state.topK, date: new Date().toISOString() };
    history.unshift({ ...state.last }); history = history.slice(0, 12); persist();
  } catch (error) {
    if (!requestGuard.isCurrent(epoch)) return;
    state.request = { status: error?.name === 'AbortError' ? 'cancelled' : 'error', error: normalizeUiError(error), requestId: error?.requestId || queryId, response: null };
  } finally {
    if (requestGuard.isCurrent(epoch)) { activeController = null; render(); }
  }
}

function selectControl({ id, label, iconName, disabled, value, options }) {
  const selected = options.find(option => option.value === value) || options[0];
  const open = state.openSelect === id;
  return `<div class="select-field"><span class="field-label" id="${id}-label">${label}</span><div class="custom-select ${open ? 'open' : ''} ${disabled ? 'disabled' : ''}"><button type="button" id="${id}" class="select-trigger" data-dropdown="${id}" aria-labelledby="${id}-label ${id}-value" aria-haspopup="listbox" aria-expanded="${open}" ${disabled ? 'disabled' : ''}>${icon(iconName, 17)}<span id="${id}-value">${escapeHtml(selected?.label || 'No disponible')}</span><span class="select-chevron">${icon('down', 15)}</span></button>${open ? `<div class="select-menu" role="listbox" aria-labelledby="${id}-label">${options.map(option => `<button type="button" role="option" data-select-id="${id}" data-select-value="${escapeHtml(option.value)}" aria-selected="${option.value === value}"><span>${escapeHtml(option.label)}</span>${option.value === value ? icon('check', 15) : ''}</button>`).join('')}</div>` : ''}</div></div>`;
}

function explorePage() {
  const ready = state.capabilities.status === 'ready';
  const loading = state.request.status === 'loading';
  const galleries = state.capabilities.data?.galleries || [];
  const count = state.results.reduce((total, row) => total + row.results.length, 0);
  const status = state.capabilities.status === 'loading' ? '<div class="service-state">Comprobando disponibilidad del servicio...</div>' : state.capabilities.status === 'error' ? `<div class="service-state error"><strong>Backend no disponible</strong><span>${escapeHtml(state.capabilities.error.message)}</span><button type="button" class="secondary" data-action="retry-capabilities">Reintentar conexión</button></div>` : '';
  const requestError = state.request.error ? `<div class="service-state ${state.request.status === 'cancelled' ? '' : 'error'}" role="alert"><strong>${state.request.status === 'cancelled' ? 'Petición cancelada' : 'No se pudo completar la búsqueda'}</strong><span>${escapeHtml(state.request.error.message)}</span>${state.request.error.requestId ? `<small>Referencia: ${escapeHtml(state.request.error.requestId)}</small>` : ''}</div>` : '';
  const galleryOptions = galleries.map(gallery => ({ value: gallery.gallery_id, label: `${galleryLabel(gallery.gallery_id)} · ${gallery.candidate_count} candidatos` }));
  const topKOptions = [3, 5, 10].map(value => ({ value: String(value), label: `Top-${value}` }));
  return `<section class="page-heading"><div><div class="eyebrow">RECUPERACIÓN CROSSTEXT2LOC</div><h1>Encuentra el lugar que describes.</h1><p>Explora ubicaciones compatibles dentro de la región piloto de Madrid.</p></div><div class="location-pill">${icon('pin', 16)} Madrid, España</div></section>
  <div class="mobile-view-switch" role="group" aria-label="Vista de exploración"><button data-mobile="description" aria-pressed="${state.mobileView === 'description'}">${icon('chat', 16)} Descripción</button><button data-mobile="results" aria-pressed="${state.mobileView === 'results'}">${icon('pin', 16)} Mapa y resultados</button></div>
  <div class="workspace" data-mobile-view="${state.mobileView}"><section class="search-panel panel"><div class="panel-heading"><span class="panel-kicker">01 · CONSULTA</span><h2>¿Qué ves a tu alrededor?</h2><p>Incluye edificios, espacios abiertos y detalles distintivos.</p></div>${status}<form id="search-form"><label for="description" class="field-label">Descripción del entorno</label><div class="textarea-wrap"><textarea id="description" maxlength="1200" rows="4" placeholder="Veo una plaza amplia rodeada de edificios..." ${loading ? 'disabled' : ''}>${escapeHtml(state.text)}</textarea><div class="textarea-footer"><span>Idioma: español</span><span id="char-count">${state.text.length} / 1.200</span></div></div><div class="example-label">Consultas de referencia</div><div class="example-chips">${examples.map((example, index) => `<button type="button" class="example-chip" data-example="${index}" ${loading ? 'disabled' : ''}>${escapeHtml(example.label)}</button>`).join('')}</div>${selectControl({ id: 'gallery', label: 'Resolución de la galería', iconName: 'layers', disabled: !ready || loading, value: state.galleryIds[0], options: galleryOptions })}${selectControl({ id: 'top-k', label: 'Número de candidatos', iconName: 'target', disabled: !ready || loading, value: String(state.topK), options: topKOptions })}<p class="form-error" id="form-error" role="alert"></p><button class="primary search-button" type="submit" ${!ready || loading ? 'disabled' : ''}>${loading ? '<span class="spinner"></span> Analizando descripción...' : icon('search', 18) + ' Buscar candidatos ' + icon('arrow', 18)}</button></form>${loading ? '<button class="cancel-button" data-action="cancel">Cancelar espera</button>' : ''}<div class="privacy-note">${icon('info', 15)}<span>La descripción se envía al servicio interno. No introduzcas datos sensibles.</span></div>${requestError}</section>
  <section class="exploration"><div class="map-panel panel"><div class="map-top"><div class="map-title"><span class="panel-kicker">02 · MAPA</span><strong>Candidatos recuperados</strong></div><div class="map-legend"><span><i></i>Área evaluada</span><span class="map-meta">WGS84</span></div></div><div id="results-map" class="real-map" aria-label="Mapa geográfico de candidatos"></div></div>${loading ? '<div class="pipeline-strip" aria-live="polite"><span class="pipeline-label"><span class="spinner small-spinner"></span> Recuperación CrossText2Loc en curso</span></div>' : ''}<div class="results-heading"><div><span class="panel-kicker">03 · RANKING</span><h2>${count ? 'Resultados de la consulta' : 'Aún no hay resultados'}</h2></div><span class="result-count">${count} candidatos</span></div>${state.results.length ? state.results.map(galleryResults).join('') : `<div class="empty-state compact">${icon('search', 26)}<h3>${state.hasRun ? 'La respuesta no contiene candidatos' : 'Describe tu entorno para comenzar'}</h3><p>Los candidatos aparecerán aquí y se sincronizarán con el mapa.</p></div>`}<div class="results-footnote">${icon('info', 13)} La similitud coseno no representa una probabilidad de acierto.</div></section></div>`;
}

function selectValue(id, value) {
  state.openSelect = '';
  if (id === 'gallery') state.galleryIds = [value];
  else if (id === 'top-k') state.topK = Number(value);
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
  return `<section class="gallery-results"><header><div><h3>${escapeHtml(galleryLabel(retrieval.galleryId))}</h3><p>${retrieval.galleryCount} candidatos evaluados · Top-${retrieval.effectiveK}</p></div></header><div class="result-grid real-results">${retrieval.results.map(candidate => resultCard(candidate, candidate.key === state.selected)).join('')}</div></section>`;
}

function resultCard(candidate, selected) {
  return `<article class="result-card real-card ${selected ? 'selected' : ''}" id="card-${escapeHtml(candidate.key)}"><button class="card-select" data-select="${escapeHtml(candidate.key)}" aria-label="Seleccionar candidato ${escapeHtml(candidate.id)}" aria-pressed="${selected}"><div class="card-content"><span class="rank-badge">${String(candidate.rank).padStart(2, '0')}</span><div class="card-title"><h3>${escapeHtml(candidate.id)}</h3>${icon('chevron', 15)}</div><p>${escapeHtml(galleryLabel(candidate.galleryId))}</p><div class="coordinate-compact">${candidate.lat.toFixed(6)}, ${candidate.lon.toFixed(6)}</div><div class="score-row"><span>Similitud coseno</span><strong>${candidate.similarity.toFixed(4)} <small>${similarityPercent(candidate.similarity)}</small></strong></div></div></button><button class="card-detail" data-detail="${escapeHtml(candidate.key)}">Ver datos ${icon('chevron', 13)}</button></article>`;
}

function allCandidates() { return state.results.flatMap(row => row.results); }

function mountMap() {
  const element = $('#results-map');
  const searchArea = state.capabilities.data?.search_area;
  if (!element || !searchArea) return;
  mapHandle = createResultsMap({ element, retrievals: state.results, selectedKey: state.selected, view: state.mapView, searchArea, onSelect: key => { state.selected = key; const scroll = window.scrollY; render(); window.scrollTo(0, scroll); }, onViewChange: view => { state.mapView = view; } });
  if (!allCandidates().length) state.mapView = null;
}

function historyPage() {
  return `<section class="page-heading"><div><div class="eyebrow">HISTORIAL LOCAL</div><h1>Consultas recientes.</h1><p>Se conservan únicamente los ajustes de las últimas búsquedas en este navegador.</p></div><button class="secondary" data-action="clear-history" ${history.length ? '' : 'disabled'}>${icon('trash', 16)} Borrar historial</button></section><section class="history-list panel">${history.length ? history.map((item, index) => `<article class="history-item"><div class="history-item-icon">${icon('history', 23)}</div><div><span class="section-label">${escapeHtml(new Date(item.date).toLocaleString('es-ES', { dateStyle: 'medium', timeStyle: 'short' }))}</span><h3>${escapeHtml(item.text)}</h3><p>${escapeHtml(item.galleryIds.join(', '))} · Top-${item.topK}</p></div><button class="secondary" data-restore="${index}">Recuperar ${icon('arrow', 15)}</button></article>`).join('') : `<div class="empty-state">${icon('history', 38)}<h2>Aún no hay consultas</h2><p>Haz una búsqueda para poder recuperarla después.</p><button class="primary" data-page="explore">Empezar a explorar ${icon('arrow', 17)}</button></div>`}</section>`;
}

function openModal(content) {
  $('#modal').innerHTML = `<button class="modal-close icon-button" data-action="close-modal" aria-label="Cerrar ventana">${icon('close')}</button>${content}`;
  $('#modal').showModal();
}

function showDetail(key) {
  const candidate = allCandidates().find(row => row.key === key);
  if (!candidate) return;
  const response = state.request.response;
  openModal(`<div class="modal-content settings-content"><span class="section-label">CANDIDATO RECUPERADO · TOP-${candidate.rank}</span><h2 id="modal-title">${escapeHtml(candidate.id)}</h2><p class="muted">${escapeHtml(galleryLabel(candidate.galleryId))}</p><div class="coordinate-row">${icon('pin', 16)} <code>${candidate.lat.toFixed(7)}, ${candidate.lon.toFixed(7)}</code><button class="text-button" data-copy="${escapeHtml(candidate.key)}">${icon('copy', 14)} Copiar</button></div><h3>Similitud coseno</h3><div class="similarity-detail"><strong>${candidate.similarity.toFixed(6)}</strong><span>${similarityPercent(candidate.similarity)}</span></div><div class="unknown-note">${icon('info', 17)}El porcentaje es el score multiplicado por 100; no representa probabilidad de acierto ni confianza calibrada.</div><div class="visual-status">${icon('layers', 19)}<div><strong>CrossText2Loc</strong><p>Ranking exhaustivo y desempate determinista por candidate_id. Tiempo interno: ${Number(response?.timingsMs?.total || 0).toFixed(2)} ms.</p></div></div><a class="secondary full-width" href="https://www.openstreetmap.org/?mlat=${candidate.lat}&mlon=${candidate.lon}#map=18/${candidate.lat}/${candidate.lon}" target="_blank" rel="noopener noreferrer">Abrir en OpenStreetMap ${icon('arrow', 16)}</a></div>`);
}

async function handleClick(event) {
  const button = event.target.closest('button');
  if (!button || button.disabled) return;
  const data = button.dataset;
  if (data.mobile) { state.mobileView = data.mobile; render(); document.querySelector(`[data-mobile="${data.mobile}"]`).focus({ preventScroll: true }); return; }
  if (data.dropdown) { state.openSelect = state.openSelect === data.dropdown ? '' : data.dropdown; render(); queueMicrotask(() => (state.openSelect ? document.querySelector(`[data-select-id="${data.dropdown}"]`) : document.querySelector(`[data-dropdown="${data.dropdown}"]`))?.focus()); return; }
  if (data.selectId) { selectValue(data.selectId, data.selectValue); return; }
  if (data.page) return navigate(data.page);
  if (data.example !== undefined) { state.text = examples[Number(data.example)].text; clearResults(); render(); return; }
  if (data.select) { state.selected = data.select; const scroll = window.scrollY; render(); window.scrollTo(0, scroll); return; }
  if (data.detail) return showDetail(data.detail);
  if (data.restore !== undefined) {
    const item = history[Number(data.restore)];
    if (!item) return;
    clearResults(); state.text = item.text;
    const available = new Set(state.capabilities.data?.galleries?.map(gallery => gallery.gallery_id) || []);
    const restored = item.galleryIds.filter(id => available.has(id));
    if (!restored.length) { toast('La galería guardada ya no está disponible.'); return; }
    state.galleryIds = restored; state.topK = item.topK; navigate('explore'); toast('Consulta recuperada.'); return;
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
    case 'help': openModal(`<div class="modal-content settings-content"><span class="section-label">SOBRE EL SISTEMA</span><h2 id="modal-title">Geolocalización textual</h2><p>La descripción se codifica con CrossText2Loc y se compara exhaustivamente con una galería OSM de Madrid.</p><div class="help-step"><span>01</span><p>Describe el entorno y selecciona la resolución.</p></div><div class="help-step"><span>02</span><p>Revisa los candidatos y sus coordenadas WGS84.</p></div><div class="unknown-note">${icon('info', 18)}La similitud coseno no es una probabilidad y el Top-1 no confirma tu ubicación.</div><p class="small muted">No introduzcas datos sensibles en la descripción.</p></div>`); break;
  }
}

state.page = ['explore', 'history'].includes(location.hash.slice(1)) ? location.hash.slice(1) : 'explore';
shell();
