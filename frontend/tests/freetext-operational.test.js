import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {
  APPLICATION_FREETEXT_POLICY,
  OPERATIONAL_FREETEXT_DESCRIPTION_MAX_LENGTH,
  OPERATIONAL_FREETEXT_POLICY,
  adaptFreeTextStage,
  buildOperationalFreeTextAnswer,
  buildOperationalFreeTextStart,
  buildApplicationFreeTextStart,
  compareFreeTextStages,
  freeTextQuickLiteral,
  freeTextStopPresentation,
  isFreeTextComponentEvent,
  isFreeTextSessionBoundaryEvent,
  normalizeFreeTextEvents,
  normalizeFreeTextStatus,
  recoveryPointer,
  recoveryStorageKey,
  selectPrimaryFreeTextPolicy,
  validateFreeTextPolicyCatalogue,
  validateFreeTextSession,
  validateRecoveryPointer,
} from '../src/dialogue-freetext.js';

const results=()=>Array.from({length:10},(_,i)=>({rank:i+1,candidate_id:`c${i}`,latitude:40+i/100,longitude:-3,cosine_similarity:1-i/10}));

test('valida sesión operacional y adapta E0 al mapa',()=>{
 const session=validateFreeTextSession({schema_version:'1.0',contract_version:'atlas-dialogue-freetext-operational-session-public-v1',session_id:'freetext-operational-00000000-0000-0000-0000-000000000000',policy_id:OPERATIONAL_FREETEXT_POLICY,status:'waiting_user',turns:[{index:1,question:'¿Pregunta?',answer_literal:null}],stage_snapshots:[{stage:'E0',gallery_id:'madrid-50m',candidate_count:253,ranking_sha256:'b'.repeat(64),results:results()}],current_question:{turn_index:1,question_id:'q1',question:'¿Pregunta?',question_sha256:'c'.repeat(64)}});assert.equal(adaptFreeTextStage(session,'E0').results.length,10);
});
test('adapta ranking visual final sin perder baseline CT2L',()=>{
 const baseline=results(),final=results();final[0]={...final[1],rank:1};final[1]={...baseline[0],rank:2};const stage={stage:'E1',gallery_id:'madrid-50m',candidate_count:253,results:baseline,visual_postprocessing:{status:'applied',baseline_results:baseline,final_results:final,evidence:[]}},adapted=adaptFreeTextStage({stage_snapshots:[stage]},'E1');assert.equal(adapted.results[0].id,'c1');assert.equal(adapted.baselineResults[0].candidate_id,'c0');assert.equal(adapted.visualPostprocessing.status,'applied');
});
test('fallback visual conserva exactamente CT2L',()=>{
 const baseline=results(),stage={stage:'E1',gallery_id:'madrid-50m',candidate_count:253,results:baseline,visual_postprocessing:{status:'fallback_baseline',baseline_results:baseline,final_results:baseline,evidence:[]}},adapted=adaptFreeTextStage({stage_snapshots:[stage]},'E1');assert.deepEqual(adapted.results.map(x=>x.id),baseline.map(x=>x.candidate_id));
});

test('selecciona operacional y liga operaciones idempotentes',()=>{
 const catalogue=validateFreeTextPolicyCatalogue({contract_version:'atlas-dialogue-freetext-policy-catalogue-v1',policies:[{policy_id:OPERATIONAL_FREETEXT_POLICY,available:true,enabled:true}]});assert.equal(selectPrimaryFreeTextPolicy(catalogue),OPERATIONAL_FREETEXT_POLICY);const start=buildOperationalFreeTextStart({description:'  Veo una plaza  ',clientOperationId:'start-1'});assert.equal(start.description_es,'Veo una plaza');assert.equal(Object.hasOwn(start,'execution_id'),false);const answer=buildOperationalFreeTextAnswer({literal:' Sí, delante. ',turnIndex:1,questionId:'question-1',clientOperationId:'answer-1'});assert.equal(answer.answer_literal,'Sí, delante.');assert.throws(()=>buildOperationalFreeTextAnswer({literal:'Sí',turnIndex:1}));
});

test('acepta descripciones operacionales hasta 2400 y mantiene respuestas en 1200',()=>{
 assert.equal(OPERATIONAL_FREETEXT_DESCRIPTION_MAX_LENGTH,2400);
 assert.equal(buildOperationalFreeTextStart({description:'x'.repeat(2400),clientOperationId:'start-boundary'}).description_es.length,2400);
 assert.throws(()=>buildOperationalFreeTextStart({description:'x'.repeat(2401),clientOperationId:'start-overflow'}),/2400 caracteres/);
 assert.equal(buildOperationalFreeTextAnswer({literal:'x'.repeat(1200),turnIndex:1,questionId:'q1',clientOperationId:'answer-boundary'}).answer_literal.length,1200);
 assert.throws(()=>buildOperationalFreeTextAnswer({literal:'x'.repeat(1201),turnIndex:1,questionId:'q1',clientOperationId:'answer-overflow'}),/Respuesta operativa FreeText inválida/);
});

test('normaliza eventos y compara rankings sin afirmar mejora geográfica',()=>{
 const session={stage_snapshots:[{stage:'E0',results:[{rank:1,candidate_id:'a'},{rank:2,candidate_id:'b'}]},{stage:'E1',results:[{rank:1,candidate_id:'b'},{rank:2,candidate_id:'a'}]}]};assert.equal(normalizeFreeTextStatus('awaiting_answer'),'waiting_user');assert.deepEqual(compareFreeTextStages(session,'E1').map(x=>x.rank_change),[1,-1]);assert.equal(normalizeFreeTextEvents({events:[{event_id:4,stage:'E1',status:'waiting_user'}]})[0].state,'waiting_user');
});
test('distingue subcomponentes de límites globales SSE en E0-E3',()=>{
 for(const stage of ['E0','E1','E2','E3']){
  for(const component of ['qwen','crosstext2loc']){
   const completed={stage:`${stage}_${component}`,state:'completed'};assert.equal(isFreeTextComponentEvent(completed),true);assert.equal(isFreeTextSessionBoundaryEvent(completed),false);
   assert.equal(isFreeTextSessionBoundaryEvent({...completed,state:'running'}),false);
  }
  assert.equal(isFreeTextSessionBoundaryEvent({stage,state:'waiting_user'}),true);
  assert.equal(isFreeTextSessionBoundaryEvent({stage,state:'completed'}),true);
 }
 assert.equal(isFreeTextSessionBoundaryEvent({stage:'E0',state:'running'}),false);
 assert.equal(isFreeTextSessionBoundaryEvent({stage:'E2',state:'failed'}),true);
 assert.equal(isFreeTextSessionBoundaryEvent({stage:'reconciliation',state:'unknown'}),true);
});

test('recovery queda aislada por policy y prefijo operacional',()=>{
 const session={session_id:'freetext-operational-00000000-0000-0000-0000-000000000000',policy_id:OPERATIONAL_FREETEXT_POLICY,updated_at_utc:'2026-11-15T00:00:00Z'},pointer=recoveryPointer(session);assert.equal(pointer.version,3);assert.deepEqual(validateRecoveryPointer(pointer),pointer);assert.equal(validateRecoveryPointer({...pointer,session_id:'dialogue-freetext-00000000-0000-0000-0000-000000000000'}),null);assert.notEqual(recoveryStorageKey(OPERATIONAL_FREETEXT_POLICY),recoveryStorageKey('dialogue-vpr-freetext-v1'));
});
test('un puntero operacional sigue siendo recuperable tras consumir autorización',()=>{
 const pointer=recoveryPointer({session_id:'freetext-operational-00000000-0000-0000-0000-000000000000',policy_id:OPERATIONAL_FREETEXT_POLICY,updated_at_utc:'2026-11-15T00:00:00Z'}),catalogue=validateFreeTextPolicyCatalogue({contract_version:'atlas-dialogue-freetext-policy-catalogue-v1',policies:[{policy_id:OPERATIONAL_FREETEXT_POLICY,available:false,enabled:true,authorization_status:'consumed'},{policy_id:'dialogue-vpr-freetext-v1',available:true}]});assert.equal(selectPrimaryFreeTextPolicy(catalogue),'dialogue-vpr-freetext-v1');assert.equal(validateRecoveryPointer(pointer).policy_id,OPERATIONAL_FREETEXT_POLICY);
});
test('application usa contrato y recovery propios',()=>{
 const catalogue=validateFreeTextPolicyCatalogue({contract_version:'atlas-dialogue-freetext-policy-catalogue-v1',policies:[{policy_id:APPLICATION_FREETEXT_POLICY,available:true,enabled:true},{policy_id:OPERATIONAL_FREETEXT_POLICY,available:true,enabled:true}]});assert.equal(selectPrimaryFreeTextPolicy(catalogue),APPLICATION_FREETEXT_POLICY);const start=buildApplicationFreeTextStart({description:'Una plaza',clientOperationId:'app-1'});assert.equal(start.policy_id,APPLICATION_FREETEXT_POLICY);const session=validateFreeTextSession({contract_version:'atlas-dialogue-freetext-application-session-public-v1',session_id:'freetext-application-00000000-0000-0000-0000-000000000000',policy_id:APPLICATION_FREETEXT_POLICY,status:'pending',turns:[],stage_snapshots:[]}),pointer=recoveryPointer(session);assert.deepEqual(validateRecoveryPointer(pointer),pointer);assert.equal(validateRecoveryPointer({...pointer,session_id:'freetext-operational-00000000-0000-0000-0000-000000000000'}),null);
});
test('application persiste operation id y reconcilia errores de red ambiguos',async()=>{
 const source=await readFile(new URL('../src/main.js',import.meta.url),'utf8');assert.match(source,/applicationPendingOperationKey/);assert.match(source,/NETWORK_ERROR/);assert.match(source,/getApplicationSessionByOperation/);assert.match(source,/safeLocalStorage\('set',applicationPendingOperationKey,request\.client_operation_id\)/);
});
test('waiting_user exige una pregunta identificada',()=>{
 const base={contract_version:'atlas-dialogue-freetext-application-session-public-v1',session_id:'freetext-application-00000000-0000-0000-0000-000000000000',policy_id:APPLICATION_FREETEXT_POLICY,status:'waiting_user',turns:[{index:1,question:'Pregunta',answer_literal:null}],stage_snapshots:[{stage:'E0',gallery_id:'madrid-50m',candidate_count:253,results:results()}]};assert.throws(()=>validateFreeTextSession(base),/Pregunta FreeText incompatible/);assert.throws(()=>validateFreeTextSession({...base,current_question:{turn_index:1,question:'Pregunta'}}),/Pregunta FreeText incompatible/);
});
test('el límite público gobierna la pregunta sin quedar fijado en la UI',()=>{
 const base={contract_version:'atlas-dialogue-freetext-application-session-public-v1',session_id:'freetext-application-00000000-0000-0000-0000-000000000000',policy_id:APPLICATION_FREETEXT_POLICY,status:'waiting_user',maximum_questions:2,turns:[{index:1,question:'Pregunta',answer_literal:null}],stage_snapshots:[{stage:'E0',gallery_id:'madrid-50m',candidate_count:253,results:results()}],current_question:{turn_index:1,question_id:'q1',question:'Pregunta'}};assert.equal(validateFreeTextSession(base).maximum_questions,2);assert.throws(()=>validateFreeTextSession({...base,maximum_questions:1,current_question:{...base.current_question,turn_index:2}}),/Pregunta FreeText incompatible/);
});
test('la aplicación abre DialogueVPR explícitamente y oculta la lista compacta',async()=>{
 const source=await readFile(new URL('../src/main.js',import.meta.url),'utf8');assert.match(source,/data-action="open-dialogue"/);assert.match(source,/Refinar ubicación/);assert.match(source,/accessible-ranking/);assert.match(source,/rankingOpen/);assert.match(source,/ft\.status==='loading'&&\['pending','running'\]\.includes\(eventState\)/);assert.doesNotMatch(source,/Pregunta \$\{question\.turn_index\} de 3/);
});
test('application reabre SSE al recuperar y permite nueva búsqueda terminal',async()=>{
 const source=await readFile(new URL('../src/main.js',import.meta.url),'utf8');assert.match(source,/async function adoptFreeTextSession/);assert.match(source,/isFreeTextSessionBoundaryEvent\(latest\)[^{]*\{\s*current=validateFreeTextSession\(await getFreeTextSession/);assert.match(source,/freetext\.status=\['pending','running'\]\.includes\(status\)\?'loading':'ready'/);assert.match(source,/function resetFreeTextSession/);assert.match(source,/new-freetext-search/);assert.match(source,/safeLocalStorage\('remove',applicationPendingOperationKey\)/);
});
test('application falla antes del POST si no puede persistir la operación',async()=>{
 const source=await readFile(new URL('../src/main.js',import.meta.url),'utf8');assert.match(source,/LOCAL_RECOVERY_UNAVAILABLE/);assert.match(source,/key===applicationPendingOperationKey.*throw new TypeError/);assert.match(source,/pointer\?\.session_id!==session\.session_id/);
});
test('una respuesta ambigua exige avance durable antes de reconciliar',async()=>{
 const source=await readFile(new URL('../src/main.js',import.meta.url),'utf8');assert.match(source,/answerOperation=.*freetext-answer-/);assert.match(source,/stage_snapshots\.length>previous\.stage_snapshots\.length/);assert.match(source,/answerOperation&&!advanced/);
});
test('accesos rápidos conservan contrato literal y no fingen semántica backend',()=>{
 const literal=freeTextQuickLiteral('unknown');assert.equal(literal,'No lo sé.');const answer=buildOperationalFreeTextAnswer({literal,turnIndex:1,questionId:'q1',clientOperationId:'quick-1'});assert.equal(answer.answer_literal,literal);assert.equal(Object.hasOwn(answer,'answer_kind'),false);assert.throws(()=>freeTextQuickLiteral('invalid'));
});
test('presenta parada temprana sin afirmar mejora geográfica',()=>{
 assert.match(freeTextStopPresentation('no_valid_question').title,/antes del límite/);assert.match(freeTextStopPresentation('max_questions_reached_after_e3').message,/tres preguntas/);assert.match(freeTextStopPresentation('future_reason').message,/último ranking válido/);
});
test('frontend declara visual offline pendiente y no inicia Mapillary',async()=>{
 const source=await readFile(new URL('../src/main.js',import.meta.url),'utf8');assert.match(source,/DialogueVPR visual/);assert.match(source,/pendiente de autorización GPU y perfil nuevo/);assert.doesNotMatch(source,/fetch\([^)]*mapillary/i);assert.match(source,/data-freetext-quick/);
});
