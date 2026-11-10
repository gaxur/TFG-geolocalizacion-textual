import test from 'node:test';
import assert from 'node:assert/strict';
import { buildDialogueAnswer, buildDialogueStart, officialDescriptionMatches, validateDialogueSession } from '../src/dialogue.js';
import { experimentalSessionId,getDescriptionVariant,validateDescriptionVariantManifest } from '../src/description-variants.js';
import manifest from '../../results/generated/description-length-experiments/manifest.json' with {type:'json'};

test('construye start oficial sin normalizar el texto humano', () => {
  const text='Descripción exacta.\nSegunda línea.';const request=buildDialogueStart({mode:'official',queryId:'H27',description:text});assert.equal(request.description_es,text);assert.equal(request.query_id,'H27');
});
test('separa exploratorio y valida literal de respuesta', () => {
  assert.equal(buildDialogueStart({mode:'exploratory',queryId:'X-prueba',description:'Texto libre'}).mode,'exploratory');assert.equal(buildDialogueAnswer({literal:'No, no veo una iglesia.',kind:'negation'}).answer_literal,'No, no veo una iglesia.');
});
test('compara descripciones oficiales byte a byte', () => {
  const query={description_es:'Exacta'};assert.equal(officialDescriptionMatches(query,'Exacta'),true);assert.equal(officialDescriptionMatches(query,'Exacta '),false);
});
test('valida sesión waiting sin exponer rankings', () => {
  const value=validateDialogueSession({contract_version:'atlas-dialogue-session-public-v1',session_id:'dialogue-x',status:'awaiting_answer',current_question:{turn_index:1,question:'¿Ves una plaza?'}});assert.equal(value.current_question.turn_index,1);assert.equal(Object.hasOwn(value,'ranking'),false);
});
test('expone 24 variantes equilibradas y genera IDs exploratorios',()=>{
  const document=validateDescriptionVariantManifest(manifest);assert.equal(document.variant_count,24);assert.equal(document.condition_count,48);
  for(const length of ['short','medium','long'])assert.equal(document.variants.filter(row=>row.length===length).length,8);
  const variant=getDescriptionVariant(document,'H27','short');assert.equal(variant.word_count,24);assert.equal(experimentalSessionId('H27','short'),'X-H27-short');assert.throws(()=>experimentalSessionId('H38','short'));
});
