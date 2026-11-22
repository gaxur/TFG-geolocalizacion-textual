const sha256 = /^[0-9a-f]{64}$/;
export const questionChecks={grounded:'Tiene apoyo en las imágenes',discriminative:'Distingue ubicaciones candidatas',user_answerable:'El usuario puede responderla',novel:'No repite el historial',single_clear_question:'Es una sola pregunta clara',no_internal_reference:'No incluye referencias internas'};

export function validateDQEvidence(session) {
  const replay = session.historical_replay;
  const isHistorical = session.execution_mode === 'historical_replay';
  if (Boolean(replay) !== isHistorical || (isHistorical && (
    session.supervised !== false || session.gpu_used !== false || session.search_executed !== false ||
    session.stage_snapshots.length !== 1 || session.stage_snapshots[0].candidate_count !== 253 ||
    replay.provenance?.sha256?.ranking !== session.stage_snapshots[0].ranking_sha256 ||
    !sha256.test(replay.provenance?.sha256?.ranking || '') || !sha256.test(replay.provenance?.sha256?.question || '') ||
    typeof replay.original_en !== 'string' || !sha256.test(replay.source_question_sha256 || '') ||
    !Array.isArray(session.visual_evidence) || session.visual_evidence.length !== 4
  ))) throw new TypeError('Procedencia de reproducción incompatible.');
  if (session.visual_evidence !== undefined) {
    const prefix = `/dialogue-freetext/sessions/${encodeURIComponent(session.session_id)}/`;
    if (!Array.isArray(session.visual_evidence) || session.visual_evidence.some(row => (
      typeof row?.candidate_id !== 'string' || !Number.isInteger(row.rank) || row.rank < 1 || row.rank > 20 ||
      !sha256.test(row.sha256 || '') || typeof row.media_path !== 'string' || !row.media_path.startsWith(prefix) ||
      !/^(?:historical-media|visual-media)\/[A-Za-z0-9_-]+$/.test(row.media_path.slice(prefix.length)) ||
      !/^https:\/\/www\.mapillary\.com\/app\/\?pKey=[0-9]+$/.test(row.source_url || '')
    ))) throw new TypeError('Evidencia Mapillary incompatible.');
  }
  const visual=session.visual_review;
  if(visual && (!session.supervised || isHistorical || !['real','cpu_fixture'].includes(session.execution_mode) ||
    visual.ranking_sha256!==session.stage_snapshots.at(-1)?.ranking_sha256 || !sha256.test(visual.panel_sha256) ||
    session.visual_evidence?.length!==4 || !Array.isArray(visual.image_sha256s) || visual.image_sha256s.length!==4 ||
    session.visual_evidence.some((r,i)=>r.sha256!==visual.image_sha256s[i] || !r.media_path.endsWith(`/visual-media/E${session.round_index}-I${i+1}`)) ||
    (visual.original_en!==undefined && (typeof visual.original_en!=='string' || !sha256.test(visual.generation_sha256) ||
    !sha256.test(visual.source_question_sha256) || visual.question_provenance!==(session.execution_mode==='real'?'official_supervised':'cpu_fixture'))))) {
    throw new TypeError('Evidencia supervisada no ligada al ranking vigente.');
  }
  return session;
}

export function dqEvidenceMarkup(session, apiBaseUrl, esc) {
  const replay = session.historical_replay;
  const visual = session.visual_review;
  const fixture = session.execution_mode==='cpu_fixture';
  const photos = session.visual_evidence || [];
  if (!replay && !photos.length) return '';
  return `<section class="dq-replay-evidence" aria-label="Evidencia visual y procedencia">
    ${replay ? `<h4>Reproducción histórica · ${esc(replay.provenance.source_run)}</h4>
    <p>Ranking y pregunta archivados. No se ha ejecutado ningún modelo en esta sesión.</p>
    <p><strong>Pregunta original EN (archivo)</strong><br>${esc(replay.original_en)}</p>
    ${replay.translation_es ? `<p><strong>Traducción ES manual (no Qwen)</strong><br>${esc(replay.translation_es)}</p>` : ''}
    ${replay.decision ? `<p>Decisión humana registrada: ${esc({accept_for_this_technical_pilot:'aceptada solo para esta reproducción',reject:'rechazada',unresolved:'no resuelta'}[replay.decision] || 'no confirmada')}.</p>` : ''}
    <details><summary>Hashes de origen</summary><ul>${Object.entries(replay.provenance.sha256).map(([key,value])=>`<li>${esc(key)}: <code>${esc(value)}</code></li>`).join('')}</ul></details>` : ''}
    ${visual ? `<h4>${fixture?'Evidencia simulada · fixture CPU':'Evidencia Mapillary · operación supervisada'}</h4>
    ${visual.original_en?`<p><strong>Pregunta original EN ${fixture?'(fixture; no salida del modelo)':'(DQ-Pilot oficial)'}</strong><br>${esc(visual.original_en)}</p>`:''}
    ${session.pending_translation_review?.translator?.author?`<p>Autor declarado del borrador: ${esc(session.pending_translation_review.translator.author)}</p>`:''}
    ${visual.translation_decision?`<p><strong>Traducción ES · ${esc(visual.translator.translator_id)}</strong>${visual.translator.author?` · ${esc(visual.translator.author)}`:''}<br>${esc(visual.translation_es)}</p><p>Decisión humana: ${esc({accept_for_this_technical_pilot:'aceptada solo para este piloto',reject:'rechazada',unresolved:'no resuelta'}[visual.translation_decision])}.</p>`:''}`:''}
    ${photos.length ? `<div class="dq-evidence-grid">${photos.map(row=>`<figure><img src="${esc(apiBaseUrl.replace(/\/$/,'')+row.media_path)}" alt="${fixture?'Imagen de prueba':'Evidencia Mapillary'} de la celda en puesto ${row.rank}"><figcaption><strong>Puesto ${row.rank}</strong> · ${row.role==='proxy_external'?'vista externa asociada':row.role==='strict_interior'?'interior de la celda':'evidencia asociada'}<br><code>${esc(row.candidate_id)}</code>${fixture?'':`<br><a href="${esc(row.source_url)}" target="_blank" rel="noopener noreferrer">Fuente Mapillary</a> · <a href="https://creativecommons.org/licenses/by-sa/4.0/" target="_blank" rel="noopener noreferrer">CC BY-SA 4.0</a>`}</figcaption></figure>`).join('')}</div>` : ''}
    ${visual?visualControls(session.controller_state,esc,fixture):''}
    ${session.controller_state==='AWAITING_REPLAY_TRANSLATION' ? '<p>No hay traducción histórica Qwen verificada. Puedes aportar una traducción manual solo para esta reproducción; seguirá pendiente de aprobación.</p><label for="historical-translation-es">Traducción manual ES</label><textarea id="historical-translation-es" maxlength="500"></textarea><button type="button" class="secondary" data-action="save-historical-translation">Guardar traducción para revisión</button>' : ''}
  </section>`;
}

function visualControls(state,esc,fixture){
  if(state==='AWAITING_TRANSLATION'&&!fixture)return '<p>Pendiente de traducción supervisada con Qwen.</p>';
  if(state==='AWAITING_TRANSLATION')return `<p>Falta una traducción ES supervisada. Puedes registrar un borrador manual, identificado por su autor y sujeto a aprobación.</p><label>Autor declarado<input id="visual-translation-author" maxlength="150"></label><label>Traducción manual ES<textarea id="visual-translation-text" maxlength="500"></textarea></label><button type="button" data-action="save-supervised-translation">Guardar borrador manual</button>`;
  if(!['AWAITING_PANEL_REVIEW','AWAITING_QUESTION_REVIEW'].includes(state))return '';
  const question=state==='AWAITING_QUESTION_REVIEW', kind=question?'question':'panel';
  return `<fieldset><legend>${question?'Revisión de la pregunta con las cuatro fotos':'Revisión del panel asociado al ranking'}</legend>
  ${question?Object.entries(questionChecks).map(([key,text])=>`<label><input type="checkbox" data-dq-check="${esc(key)}"> ${esc(text)}</label>`).join(''):''}
  <label>Declaración de revisión<textarea id="dq-visual-declaration" maxlength="1000"></textarea></label>
  <button type="button" data-action="review-dq-visual" data-kind="${kind}" data-approved="true">${question?'Aceptar pregunta para traducir':'Aceptar panel (no ejecuta modelos)'}</button>
  <button type="button" class="secondary" data-action="review-dq-visual" data-kind="${kind}" data-approved="false">Rechazar</button></fieldset>`;
}
