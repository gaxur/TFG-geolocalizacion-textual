import test from 'node:test';
import assert from 'node:assert/strict';
import { dqEvidenceMarkup, validateDQEvidence } from '../src/dq-visual-evidence.js';

const hash = 'a'.repeat(64);
const row = {candidate_id:'celda',rank:1,sha256:hash,source_url:'https://www.mapillary.com/app/?pKey=1',
  media_path:'/dialogue-freetext/sessions/session-a/historical-media/I1'};
const session = {session_id:'session-a',execution_mode:'historical_replay',supervised:false,gpu_used:false,search_executed:false,
  stage_snapshots:[{candidate_count:253,ranking_sha256:hash}],
  historical_replay:{original_en:'What is visible?',source_question_sha256:hash,provenance:{sha256:{ranking:hash,question:hash}}},
  visual_evidence:Array.from({length:4},(_,i)=>({...row,rank:i+1,media_path:row.media_path.slice(0,-1)+(i+1)}))};

test('la interfaz rechaza procedencia histórica declarada como nueva o incoherente', () => {
  assert.equal(validateDQEvidence(session),session);
  assert.throws(()=>validateDQEvidence({...session,execution_mode:'real'}),/Procedencia/);
  assert.throws(()=>validateDQEvidence({...session,search_executed:true}),/Procedencia/);
  assert.throws(()=>validateDQEvidence({...session,stage_snapshots:[{candidate_count:253,ranking_sha256:'b'.repeat(64)}]}),/Procedencia/);
});

test('el visor no acepta fotos cruzadas, URL externas de medio ni enlaces arbitrarios', () => {
  for(const bad of [{media_path:row.media_path.replace('session-a','session-b')}, {media_path:'https://example.test/I1'}, {source_url:'javascript:alert(1)'}]) {
    assert.throws(()=>validateDQEvidence({...session,visual_evidence:[...session.visual_evidence.slice(0,3),{...row,...bad}]}),/Mapillary/);
  }
});

test('producción espera Qwen y no ofrece traducción manual de la pregunta oficial', () => {
  const visual = {...session, historical_replay:null, controller_state:'AWAITING_TRANSLATION',
    visual_review:{original_en:'What is visible?'}, execution_mode:'real'};
  const render = data => dqEvidenceMarkup(data, '/api/v1', value => String(value));
  assert.match(render(visual), /traducción supervisada con Qwen/);
  assert.doesNotMatch(render(visual), /save-supervised-translation/);
  assert.match(render({...visual, execution_mode:'cpu_fixture'}), /save-supervised-translation/);
});
