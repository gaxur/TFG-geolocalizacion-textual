import test from 'node:test';
import assert from 'node:assert/strict';
import {
  OPERATIONAL_FREETEXT_POLICY,
  adaptFreeTextStage,
  buildOperationalFreeTextAnswer,
  buildOperationalFreeTextStart,
  compareFreeTextStages,
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

test('selecciona operacional y liga operaciones idempotentes',()=>{
 const catalogue=validateFreeTextPolicyCatalogue({contract_version:'atlas-dialogue-freetext-policy-catalogue-v1',policies:[{policy_id:OPERATIONAL_FREETEXT_POLICY,available:true,enabled:true}]});assert.equal(selectPrimaryFreeTextPolicy(catalogue),OPERATIONAL_FREETEXT_POLICY);const start=buildOperationalFreeTextStart({description:'  Veo una plaza  ',clientOperationId:'start-1'});assert.equal(start.description_es,'Veo una plaza');const answer=buildOperationalFreeTextAnswer({literal:' Sí, delante. ',turnIndex:1,questionId:'question-1',clientOperationId:'answer-1'});assert.equal(answer.answer_literal,'Sí, delante.');assert.throws(()=>buildOperationalFreeTextAnswer({literal:'Sí',turnIndex:1}));
});

test('normaliza eventos y compara rankings sin afirmar mejora geográfica',()=>{
 const session={stage_snapshots:[{stage:'E0',results:[{rank:1,candidate_id:'a'},{rank:2,candidate_id:'b'}]},{stage:'E1',results:[{rank:1,candidate_id:'b'},{rank:2,candidate_id:'a'}]}]};assert.equal(normalizeFreeTextStatus('awaiting_answer'),'waiting_user');assert.deepEqual(compareFreeTextStages(session,'E1').map(x=>x.rank_change),[1,-1]);assert.equal(normalizeFreeTextEvents({events:[{event_id:4,stage:'E1',status:'waiting_user'}]})[0].state,'waiting_user');
});

test('recovery queda aislada por policy y prefijo operacional',()=>{
 const session={session_id:'freetext-operational-00000000-0000-0000-0000-000000000000',policy_id:OPERATIONAL_FREETEXT_POLICY,updated_at_utc:'2026-11-15T00:00:00Z'},pointer=recoveryPointer(session);assert.equal(pointer.version,3);assert.deepEqual(validateRecoveryPointer(pointer),pointer);assert.equal(validateRecoveryPointer({...pointer,session_id:'dialogue-freetext-00000000-0000-0000-0000-000000000000'}),null);assert.notEqual(recoveryStorageKey(OPERATIONAL_FREETEXT_POLICY),recoveryStorageKey('dialogue-vpr-freetext-v1'));
});
