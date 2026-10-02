import './minimal.css';
import { places, examples, simulateSearch, extractClues, regionNames } from './demo.js';
import { icon, scene, mapArtwork } from './visuals.js';

const $ = (selector) => document.querySelector(selector);
const escapeHtml = value => String(value).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const modelName = model => model === 'gotpr' ? 'GOTPR' : 'CrossText2Loc';
const score = value => value.toFixed(2).replace('.', ',');
const state = { page: 'explore', mobileView: 'description', optionsOpen: false, text: examples[0].text, region: 'centro', model: 'cross', topK: 3, visual: true, dialogue: true, results: [], selected: 'sol', busy: false, step: 0, hasRun: false, answered: '', last: null, zoom: 1, layer: true, revision: 0 };
let timers = [], toastTimer;
let history = [];
try {
  const stored = JSON.parse(localStorage.getItem('atlas-history') || '[]');
  history = Array.isArray(stored) ? stored.filter(x => typeof x?.text === 'string' && x.text.length <= 1200 && Object.hasOwn(regionNames, x.region) && ['cross', 'gotpr'].includes(x.model) && typeof x.date === 'string').slice(0, 12) : [];
} catch { /* El prototipo también funciona sin almacenamiento. */ }

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
function cancel() { timers.forEach(clearTimeout); timers = []; state.busy = false; }
function clearResults() { cancel(); state.results = []; state.hasRun = false; state.last = null; state.answered = ''; state.revision = 0; state.mobileView = 'description'; }
function getResults(model = state.model) {
  return simulateSearch(state.text, state.region, model, state.topK);
}
function shell() {
  $('#app').innerHTML = `
    <div class="app-body">
      <header class="header"><a class="wordmark" href="#explore" aria-label="Atlas, inicio">${icon('compass', 27)}atlas</a><nav class="top-nav" aria-label="Vistas"><button data-page="explore" class="active">Explorar</button><button data-page="compare">Comparar modelos</button><button data-page="history">Historial</button></nav><div class="header-right"><span class="demo-badge"><i></i> Demo</span><button class="icon-button" data-action="help" aria-label="Ayuda">${icon('info')}</button></div></header>
      <main id="main"></main>
      <footer class="footer"><span>ATLAS <span class="footer-dot">/</span> Geolocalización con lenguaje natural</span><span>TFG · Madrid <span class="footer-dot">/</span> Datos de demostración</span></footer>
    </div>
    <dialog id="modal" aria-labelledby="modal-title"></dialog>`;
  $('#app').addEventListener('click', handleClick);
  $('#modal').addEventListener('click', e => { if (e.target === $('#modal')) $('#modal').close(); });
  window.addEventListener('hashchange', () => { const page = location.hash.slice(1); if (['explore', 'compare', 'history'].includes(page)) navigate(page); });
  render();
}
function navigate(page) {
  state.page = page;
  if (location.hash !== `#${page}`) window.history.replaceState(null, '', `#${page}`);
  render();
  window.scrollTo(0, 0);
}
function render() {
  document.querySelectorAll('[data-page]').forEach(el => { el.classList.toggle('active', el.dataset.page === state.page); if (el.dataset.page === state.page) el.setAttribute('aria-current', 'page'); else el.removeAttribute('aria-current'); });
  $('#main').innerHTML = state.page === 'explore' ? explorePage() : state.page === 'compare' ? comparePage() : historyPage();
  if (state.page === 'explore') {
    $('#description').addEventListener('input', e => { state.text = e.target.value; $('#char-count').textContent = `${state.text.length} / 1.200`; $('#form-error').textContent = ''; });
    $('#region').addEventListener('change', e => { state.region = e.target.value; clearResults(); render(); });
    $('#search-form').addEventListener('submit', e => { e.preventDefault(); runSearch(); });
    $('.search-options').addEventListener('toggle', e => { state.optionsOpen = e.target.open; });
  }
}
function explorePage() {
  const results = state.hasRun ? state.results : simulateSearch(examples[0].text, 'centro', 'cross', 3);
  const selected = results.find(p => p.id === state.selected) || results[0];
  return `<section class="page-heading"><div><div class="eyebrow">GEOLOCALIZACIÓN CON LENGUAJE NATURAL</div><h1>Encuentra tu lugar.</h1><p>Describe lo que ves y explora las ubicaciones que encajan.</p></div><div class="location-pill">${icon('pin', 16)} Madrid, España</div></section>
  <div class="mobile-view-switch" role="group" aria-label="Vista de exploración"><button data-mobile="description" aria-controls="search-panel" aria-pressed="${state.mobileView === 'description'}">${icon('chat', 16)} Descripción</button><button data-mobile="results" aria-controls="exploration" aria-pressed="${state.mobileView === 'results'}">${icon('pin', 16)} Mapa y resultados</button></div>
  <div class="workspace" data-mobile-view="${state.mobileView}">
    <section id="search-panel" class="search-panel panel" aria-labelledby="search-title">
      <h2 id="search-title">¿Qué ves a tu alrededor?</h2><p class="muted small">Los edificios, las plazas y los pequeños detalles pueden ayudar.</p>
      <form id="search-form"><label for="description" class="field-label">Tu descripción</label><div class="textarea-wrap"><textarea id="description" maxlength="1200" rows="4" placeholder="Veo una plaza con una fuente. A mi derecha hay una iglesia…" ${state.busy ? 'disabled' : ''}>${escapeHtml(state.text)}</textarea><div class="textarea-footer"><span>Con tus palabras</span><span id="char-count">${state.text.length} / 1.200</span></div></div>
      <div class="example-label">Prueba un ejemplo</div><div class="example-chips">${examples.map((x, i) => `<button type="button" class="example-chip" data-example="${i}" ${state.busy ? 'disabled' : ''}>${x.label} ${icon('arrow', 12)}</button>`).join('')}</div>
      <label for="region" class="field-label">Zona aproximada <span>Ámbito de búsqueda</span></label><div class="select-wrap">${icon('pin', 17)}<select id="region" ${state.busy ? 'disabled' : ''}>${Object.entries(regionNames).map(([key, name]) => `<option value="${key}" ${key === state.region ? 'selected' : ''}>${name}, Madrid${key === 'madrid' ? ' · toda la demo' : ''}</option>`).join('')}</select></div>
      <details class="search-options" ${state.optionsOpen ? 'open' : ''}><summary>${icon('settings', 15)} Opciones de búsqueda <span>${modelName(state.model)}</span>${icon('down', 14)}</summary><div class="model-label"><span class="field-label">Método de recuperación</span><button type="button" class="text-button" data-action="settings" ${state.busy ? 'disabled' : ''}>Ajustes</button></div><div class="segmented" role="group" aria-label="Método de recuperación"><button type="button" data-model="cross" class="${state.model === 'cross' ? 'selected' : ''}" ${state.busy ? 'disabled' : ''}>CrossText2Loc</button><button type="button" data-model="gotpr" class="${state.model === 'gotpr' ? 'selected' : ''}" ${state.busy ? 'disabled' : ''}>GOTPR</button></div><p class="method-note">${state.model === 'cross' ? 'Texto + imágenes de mapa' : 'Grafo del texto + grafos de OpenStreetMap'} <span>· Pesos fijos</span></p></details>
      <p class="form-error" id="form-error" role="alert"></p><button class="primary search-button" type="submit" ${state.busy ? 'disabled' : ''}>${state.busy ? '<span class="spinner"></span> Explorando el escenario…' : icon('search', 18) + ' Buscar lugares posibles ' + icon('arrow', 18)}</button></form>
      ${state.busy ? '<button class="cancel-button" data-action="cancel">Cancelar búsqueda</button>' : ''}
      <div class="privacy-note">${icon('info', 15)}<span>Resultados simulados. Tu descripción permanece en este navegador.</span></div>
    </section>
    <section id="exploration" class="exploration" aria-label="Mapa y resultados">
      <div class="map-panel panel"><div class="map-top"><div class="map-title">${icon('layers', 17)} Explorar el entorno <span class="map-divider"></span><span>${state.hasRun ? regionNames[state.region] : 'Distrito Centro'}</span></div><span class="map-demo">Mapa ilustrativo</span></div>
        <div class="map-canvas" id="map-canvas"><div class="map-world" style="transform: scale(${state.zoom})">${mapArtwork()}${state.layer ? '<div class="search-boundary"><span>ÁMBITO ILUSTRATIVO</span></div>' : ''}${results.map((p, i) => marker(p, i, p.id === selected?.id)).join('')}</div>
          <div class="map-caption"><span class="live-dot"></span>${state.hasRun ? `${results.length} candidatos de demostración` : 'Vista previa · ejecuta tu primera búsqueda'}</div>
          <div class="map-controls"><button data-action="zoom-in" aria-label="Acercar mapa">${icon('plus', 18)}</button><button data-action="zoom-out" aria-label="Alejar mapa">${icon('minus', 18)}</button><span></span><button data-action="reset-map" aria-label="Restablecer vista">${icon('target', 18)}</button><button data-action="layer" aria-label="Mostrar ámbito ilustrativo" aria-pressed="${state.layer}">${icon('layers', 18)}</button></div>
          <div class="north-arrow"><span>N</span><svg viewBox="0 0 20 30"><path d="m10 2 8 23-8-5Z" fill="#46635a"/><path d="M10 2 2 25l8-5Z" fill="#a4b2a2"/></svg></div>
          ${selected ? `<button class="map-popup" data-detail="${selected.id}"><span class="popup-pin">${icon('pin', 18)}</span><span><strong>${selected.name}</strong><small>${selected.kind} · Ver detalles</small></span>${icon('chevron', 16)}</button>` : ''}
          <div class="map-attribution">Esquema de Madrid · posiciones orientativas · sin cartografía en directo</div>
        </div>
      </div>
      ${progressPanel()}
      <div class="results-heading"><div><h2>${state.hasRun ? results.length ? 'Lugares compatibles' : 'Necesitamos alguna pista más' : 'Explora los candidatos'}</h2></div><span class="result-count">${results.length} ${state.hasRun ? 'resultados demo' : 'ejemplos'}</span></div>
      <div class="result-grid">${results.length ? results.map((p, i) => resultCard(p, i, p.id === selected?.id)).join('') : '<div class="empty-state compact">' + icon('search', 28) + '<h3>Sin coincidencias en esta demo</h3><p>Describe una plaza, un edificio o un parque, o prueba uno de los ejemplos. Esto no indica que el lugar no exista.</p></div>'}</div>
      <div class="results-footnote">${icon('info', 13)} Puntuaciones sintéticas de similitud; no son probabilidades de acierto.<button class="text-button" data-page="compare">Comparar métodos ${icon('arrow', 14)}</button></div>
      ${state.hasRun && results.length && state.dialogue ? dialoguePanel() : ''}
    </section>
  </div>`;
}
function marker(p, i, selected) {
  // Proyección solo para el esquema ilustrativo, no para navegación.
  const x = 7 + (p.lon + 3.719) / 0.041 * 88, y = 8 + (40.435 - p.lat) / 0.031 * 83;
  return `<button class="map-marker ${selected ? 'selected' : ''}" style="left:${x}%;top:${y}%" data-select="${p.id}" aria-label="Seleccionar ${p.name}" aria-pressed="${selected}"><span>${i + 1}</span></button>`;
}
function resultCard(p, i, selected) {
  return `<article class="result-card ${selected ? 'selected' : ''}"><button class="card-select" data-select="${p.id}" aria-label="Seleccionar ${p.name}" aria-pressed="${selected}"><div class="card-image">${scene(p, 'card')}<span class="rank-badge">0${i + 1}</span><span class="illustration-label">Ilustración</span></div><div class="card-content"><div class="card-title"><h3>${p.name}</h3>${icon('arrow', 15)}</div><p>${p.area}</p><div class="feature-list">${p.features.slice(0, 2).map(f => `<span>${f}</span>`).join('')}</div><div class="score-row"><span>Similitud demo</span><strong>${score(p.value)}</strong></div><div class="score-track"><i style="width:${p.value * 100}%"></i></div></div></button><button class="card-detail" data-detail="${p.id}">Ver evidencias ${icon('chevron', 13)}</button></article>`;
}
function progressPanel() {
  if (!state.busy) return '';
  const labels = ['Interpretar', 'Consultar OSM', 'Recuperar', 'Ordenar'];
  return `<div class="pipeline-strip" aria-label="Estado de la búsqueda" aria-live="polite"><span class="pipeline-label">${state.busy ? '<span class="spinner small-spinner"></span> Simulando' : icon('spark', 15) + (state.hasRun ? ' Demo completada' : ' Así funciona')}</span>${labels.map((label, i) => `<span class="pipeline-step ${state.busy && i === state.step ? 'current' : state.hasRun || state.busy && i < state.step ? 'done' : ''}"><i>${state.hasRun || state.busy && i < state.step ? icon('check', 10) : i + 1}</i>${label}</span>${i < 3 ? '<span class="pipeline-dash"></span>' : ''}`).join('')}</div>`;
}
function dialoguePanel() {
  const isPark = state.results[0]?.id === 'retiro';
  return `<section class="dialogue-panel panel"><div class="dialogue-icon">${icon('chat', 21)}</div><div class="dialogue-content"><span class="section-label">UNA PISTA MÁS · DIÁLOGO SIMULADO</span><h3>${state.answered ? 'Tu respuesta se ha añadido al contexto.' : isPark ? '¿Ves barcas sobre el agua?' : '¿El edificio que ves tiene un reloj en lo alto?'}</h3><p>${state.answered ? `Respuesta: «${escapeHtml(state.answered)}». ${state.answered === 'Sí' ? 'Se ha aplicado un reordenamiento ilustrativo.' : 'Mantenemos los candidatos: esta respuesta no basta para descartarlos.'}` : 'Esta pregunta ilustra cómo podríamos distinguir los candidatos.'}</p>${!state.answered ? '<div class="answer-options"><button data-answer="Sí">Sí, lo veo</button><button data-answer="No">No</button><button data-answer="No estoy seguro">No estoy seguro</button></div>' : '<button class="text-button" data-action="retry-answer">Cambiar respuesta</button>'}</div><span class="optional-badge">Extensión</span></section>`;
}
function comparisonColumn(model) {
  const input = state.last || { text: examples[0].text, region: 'centro', topK: state.topK };
  const rows = simulateSearch(input.text, input.region, model, input.topK);
  return `<section class="comparison-column panel"><div class="comparison-title"><span class="model-symbol">${icon(model === 'cross' ? 'layers' : 'compare', 24)}</span><div><h2>${modelName(model)}</h2><p>${model === 'cross' ? 'Descripción + imágenes de mapa' : 'Grafo de descripción + grafos OSM'}</p></div><span class="optional-badge">Demo</span></div><div class="representation">${model === 'cross' ? '<div class="mini-map">' + mapArtwork() + '</div><span>Representación visual del entorno</span>' : '<svg viewBox="0 0 260 110" aria-label="Grafo ilustrativo"><g stroke="#a7bcb0" stroke-width="2"><path d="m45 56 82-34 89 36-89 31-82-33m82-34v67"/></g><g fill="#e2eddb" stroke="#779582"><circle cx="45" cy="56" r="20"/><circle cx="127" cy="22" r="16"/><circle cx="216" cy="58" r="22"/><circle cx="127" cy="89" r="15"/></g><g fill="#385449" font-size="9" text-anchor="middle"><text x="45" y="59">Plaza</text><text x="127" y="25">Torre</text><text x="216" y="61">Edificio</text><text x="127" y="92">Reloj</text></g></svg><span>Representación de objetos y relaciones</span>'}</div><div class="comparison-ranking">${rows.map((p, i) => `<button class="comparison-row" data-detail="${p.id}"><span class="comparison-rank">0${i + 1}</span><span><strong>${p.name}</strong><small>${p.kind}</small></span><div class="comparison-score"><strong>${score(p.value)}</strong><div class="score-track"><i style="width:${p.value * 100}%"></i></div></div>${icon('chevron', 15)}</button>`).join('') || '<p class="muted">Sin candidatos para esta consulta de demostración.</p>'}</div><div class="comparison-meta"><span>Pesos <strong>Sin ejecución real</strong></span><span>Latencia <strong>No medida</strong></span></div></section>`;
}
function comparePage() {
  const input = state.last || { text: examples[0].text, region: 'centro' };
  return `<section class="page-heading"><div><div class="eyebrow">DOS ENFOQUES, EL MISMO ENTORNO</div><h1>Compara las posibilidades.</h1><p>Una consulta común. Dos formas de representar un lugar.</p></div><button class="secondary" data-action="export" ${!state.last ? 'disabled' : ''}>${icon('download', 17)} Exportar sesión</button></section><section class="comparison-query panel"><div class="query-icon">${icon('chat', 22)}</div><div><span class="section-label">${state.last ? 'ÚLTIMA CONSULTA' : 'CONSULTA DE EJEMPLO'}</span><p>«${escapeHtml(input.text)}»</p><span class="location-inline">${icon('pin', 13)} ${regionNames[input.region]}</span></div><button class="text-button" data-page="explore">Editar consulta ${icon('arrow', 15)}</button></section><div class="comparison-grid">${comparisonColumn('cross')}${comparisonColumn('gotpr')}</div><div class="comparison-notice">${icon('info', 19)}<div><strong>Comparación ilustrativa, no un resultado experimental.</strong><p>Ambas columnas comparten consulta y ubicaciones disponibles. Las puntuaciones son sintéticas y no comparables como probabilidades. Recall, latencia y error geográfico se medirán al conectar los modelos y las ubicaciones de referencia.</p></div></div><section class="next-steps panel"><div><span class="section-label">AMPLIACIONES DEL SISTEMA</span><h2>Más contexto, mejores preguntas.</h2></div><div class="extension-item">${icon('chat', 22)}<strong>Diálogo</strong><span>Preguntas para resolver ambigüedades</span><span class="status-tag">Interacción simulada</span></div><div class="extension-item">${icon('eye', 22)}<strong>Street View + VLM</strong><span>Contraste de evidencias visuales</span><span class="status-tag">Vista de prototipo</span></div><div class="extension-item">${icon('target', 22)}<strong>TOLoc</strong><span>Refinamiento de posición</span><span class="status-tag neutral">Trabajo futuro</span></div></section>`;
}
function historyPage() {
  return `<section class="page-heading"><div><div class="eyebrow">TU CUADERNO DE EXPLORACIÓN</div><h1>Vuelve sobre tus pistas.</h1><p>Consultas guardadas en este navegador. Sin cuenta ni sincronización.</p></div><button class="secondary" data-action="clear-history" ${history.length ? '' : 'disabled'}>${icon('trash', 16)} Borrar historial</button></section><section class="history-list panel">${history.length ? history.map((item, i) => `<article class="history-item"><div class="history-item-icon">${icon('history', 23)}</div><div><span class="section-label">${escapeHtml(new Date(item.date).toLocaleString('es-ES', { dateStyle: 'medium', timeStyle: 'short' }))} · DEMO</span><h3>${escapeHtml(item.text)}</h3><p>${regionNames[item.region]} <span>·</span> ${modelName(item.model)}</p></div><button class="secondary" data-restore="${i}">Recuperar ${icon('arrow', 15)}</button></article>`).join('') : `<div class="empty-state">${icon('history', 38)}<h2>Aún no hay exploraciones.</h2><p>Haz una búsqueda de demostración y podrás recuperarla desde aquí.</p><button class="primary" data-page="explore">Empezar a explorar ${icon('arrow', 17)}</button></div>`}</section>`;
}
function runSearch() {
  if (state.busy) return;
  if (state.text.trim().length < 20) { $('#form-error').textContent = 'Añade algo más de detalle: al menos 20 caracteres.'; $('#description').focus(); return; }
  state.busy = true; state.step = 0; state.hasRun = false; state.answered = ''; state.revision = 0;
  render();
  [1, 2, 3].forEach((step) => timers.push(setTimeout(() => { state.step = step; if (state.page === 'explore') render(); }, step * 420)));
  timers.push(setTimeout(() => {
    state.busy = false; state.hasRun = true; state.results = getResults(); state.selected = state.results[0]?.id || ''; state.mobileView = 'results';
    state.last = { text: state.text, region: state.region, model: state.model, topK: state.topK, date: new Date().toISOString() };
    history.unshift({ ...state.last }); history = history.slice(0, 12); persist(); render();
    if (state.page === 'explore' && window.matchMedia('(max-width: 720px)').matches) {
      $('[data-mobile="results"]').focus({ preventScroll: true });
      $('.mobile-view-switch').scrollIntoView({ block: 'start' });
    }
    toast(state.results.length ? 'Búsqueda de demostración completada.' : 'Esta demo no tiene coincidencias para la descripción.');
  }, 1750));
}
function openModal(content) { $('#modal').innerHTML = `<button class="modal-close icon-button" data-action="close-modal" aria-label="Cerrar ventana">${icon('close')}</button>${content}`; $('#modal').showModal(); }
function showDetail(id) {
  const p = state.results.find(p => p.id === id) || places.find(p => p.id === id);
  if (!p) return;
  const clues = extractClues(state.last?.text || examples[0].text);
  openModal(`<div class="detail-hero">${scene(p, 'modal')}<span class="detail-hero-label">Ilustración · no es una captura de Street View</span></div><div class="modal-content"><span class="section-label">FICHA DE CANDIDATO · DEMOSTRACIÓN</span><h2 id="modal-title">${p.name}</h2><p class="muted">${p.area}</p><div class="coordinate-row">${icon('pin', 16)} <code>${p.lat.toFixed(5)}, ${p.lon.toFixed(5)}</code><button class="text-button" data-copy="${p.id}">${icon('copy', 14)} Copiar</button></div><h3>Pistas de la descripción</h3><div class="clue-list">${clues.map(c => `<span>${escapeHtml(c)}</span>`).join('') || '<span>Sin pistas reconocidas en la demo</span>'}</div><h3>Evidencias del escenario</h3><ul class="evidence-list">${p.evidence.map(e => `<li>${icon('check', 16)}${e}</li>`).join('')}</ul><div class="unknown-note">${icon('info', 17)}${p.unknown}</div><div class="visual-status">${icon('eye', 19)}<div><strong>Verificación visual ${state.visual ? 'prevista' : 'desactivada'}</strong><p>${state.visual ? 'Sin Street View ni VLM conectados. Las evidencias anteriores son parte del escenario de demostración.' : 'La sesión utiliza únicamente los candidatos ilustrativos del recuperador.'}</p></div></div><a class="secondary full-width" href="https://www.openstreetmap.org/?mlat=${p.lat}&mlon=${p.lon}#map=18/${p.lat}/${p.lon}" target="_blank" rel="noopener noreferrer">Abrir ubicación en OpenStreetMap ${icon('arrow', 16)}</a></div>`);
}
function settings() {
  openModal(`<div class="modal-content settings-content"><span class="section-label">PERSONALIZA LA EXPLORACIÓN</span><h2 id="modal-title">Ajustes de la sesión</h2><p class="muted">Configura la experiencia de demostración.</p><form id="settings-form"><label class="field-label" for="topk">Número máximo de candidatos</label><select class="settings-select" id="topk">${[3, 5].map(n => `<option value="${n}" ${state.topK === n ? 'selected' : ''}>Top-${n}</option>`).join('')}</select><p class="small muted">La demo contiene seis lugares; algunas zonas tienen menos candidatos.</p><label class="switch-row"><span><strong>Diálogo de aclaración</strong><small>Una pregunta de ejemplo tras buscar.</small></span><input type="checkbox" id="dialogue-toggle" ${state.dialogue ? 'checked' : ''}><span class="switch" aria-hidden="true"></span></label><label class="switch-row"><span><strong>Verificación visual</strong><small>Muestra el estado previsto en las fichas.</small></span><input type="checkbox" id="visual-toggle" ${state.visual ? 'checked' : ''}><span class="switch" aria-hidden="true"></span></label><div class="unknown-note">${icon('info', 17)}TOLoc no está implementado en este prototipo. No se estima una posición precisa del observador.</div><button type="submit" class="primary full-width">Guardar ajustes ${icon('check', 17)}</button></form></div>`);
  $('#settings-form').addEventListener('submit', e => { e.preventDefault(); state.topK = Number($('#topk').value); state.dialogue = $('#dialogue-toggle').checked; state.visual = $('#visual-toggle').checked; clearResults(); $('#modal').close(); render(); toast('Ajustes guardados. Ejecuta una búsqueda para aplicarlos.'); });
}
function exportSession() {
  if (!state.last) return;
  const payload = { prototype: true, disclaimer: 'Datos sintéticos. No se han ejecutado modelos ni medido rendimiento.', query: state.last, settings: { dialogue: state.dialogue, visual: state.visual }, answer: state.answered || null, candidates: state.results.map(({ id, name, lat, lon, value }) => ({ id, name, lat, lon, syntheticScore: value })), comparison: Object.fromEntries(['cross', 'gotpr'].map(m => [modelName(m), simulateSearch(state.last.text, state.last.region, m, state.last.topK).map(({ id, value }) => ({ id, syntheticScore: value }))])) };
  const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' }));
  const a = document.createElement('a'); a.href = url; a.download = 'atlas-sesion-demo.json'; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); toast('Sesión exportada como JSON de demostración.');
}
async function handleClick(e) {
  const button = e.target.closest('button');
  if (!button || button.disabled) return;
  const d = button.dataset;
  if (d.mobile) { state.mobileView = d.mobile; render(); document.querySelector(`[data-mobile="${d.mobile}"]`).focus({ preventScroll: true }); return; }
  if (d.page) return navigate(d.page);
  if (d.example !== undefined) { const ex = examples[Number(d.example)]; state.text = ex.text; state.region = ex.region; clearResults(); render(); return; }
  if (d.model) { state.model = d.model; clearResults(); render(); return; }
  if (d.select) { state.selected = d.select; const scroll = window.scrollY; render(); window.scrollTo(0, scroll); return; }
  if (d.detail) return showDetail(d.detail);
  if (d.restore !== undefined) { const item = history[Number(d.restore)]; if (!item) return; clearResults(); state.text = item.text; state.region = item.region; state.model = item.model; navigate('explore'); toast('Consulta recuperada. Puedes editarla o volver a buscar.'); return; }
  if (d.answer) {
    state.answered = d.answer; state.revision++;
    if (d.answer === 'Sí') { const preferred = state.results.find(p => p.id === 'sol' || p.id === 'retiro'); if (preferred) state.results = [preferred, ...state.results.filter(p => p.id !== preferred.id)]; }
    state.selected = state.results[0]?.id || ''; render(); toast('Respuesta incorporada a la sesión de demostración.'); return;
  }
  if (d.copy) { const p = places.find(x => x.id === d.copy); try { await navigator.clipboard.writeText(`${p.lat}, ${p.lon}`); toast('Coordenadas copiadas.'); } catch { toast(`Coordenadas: ${p.lat}, ${p.lon}`); } return; }
  switch (d.action) {
    case 'settings': settings(); break;
    case 'close-modal': $('#modal').close(); break;
    case 'cancel': cancel(); render(); toast('Búsqueda cancelada.'); break;
    case 'export': exportSession(); break;
    case 'zoom-in': state.zoom = Math.min(1.6, state.zoom + .2); render(); break;
    case 'zoom-out': state.zoom = Math.max(.8, state.zoom - .2); render(); break;
    case 'reset-map': state.zoom = 1; render(); break;
    case 'layer': state.layer = !state.layer; render(); break;
    case 'retry-answer': state.answered = ''; if (state.last) state.results = simulateSearch(state.last.text, state.last.region, state.last.model, state.last.topK); render(); break;
    case 'clear-history': openModal('<div class="modal-content settings-content"><h2 id="modal-title">¿Borrar el historial local?</h2><p class="muted">Se eliminarán las consultas guardadas en este navegador.</p><div class="modal-actions"><button class="secondary" data-action="close-modal">Conservar</button><button class="primary" data-action="confirm-clear">Borrar historial</button></div></div>'); break;
    case 'confirm-clear': history = []; persist(); $('#modal').close(); render(); toast('Historial borrado.'); break;
    case 'help': openModal(`<div class="modal-content settings-content"><span class="section-label">ACERCA DE ATLAS</span><h2 id="modal-title">De lo que ves<br>a dónde podrías estar.</h2><p>Atlas es un prototipo de interfaz para un TFG sobre geolocalización mediante lenguaje natural.</p><div class="help-step"><span>01</span><p>Describe el entorno y elige una zona aproximada.</p></div><div class="help-step"><span>02</span><p>Explora candidatos y sus evidencias ilustrativas.</p></div><div class="help-step"><span>03</span><p>Responde a una pregunta o compara las dos variantes.</p></div><div class="unknown-note">${icon('info', 18)}No hay conexión con Azure, OSM, Street View ni modelos. Mapa, ilustraciones y puntuaciones son de demostración. Los enlaces externos sí abren OpenStreetMap.</div><p class="small muted">Las últimas 12 consultas se guardan solo en este navegador. Puedes borrarlas desde Historial. No utilices datos sensibles.</p></div>`); break;
  }
}
state.page = ['explore', 'compare', 'history'].includes(location.hash.slice(1)) ? location.hash.slice(1) : 'explore';
shell();
