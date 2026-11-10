const START_CONTRACT = 'atlas-dialogue-start-request-v1';
const ANSWER_CONTRACT = 'atlas-dialogue-answer-request-v1';

export function buildDialogueStart({ mode, queryId, description }) {
  const text = String(description || '');
  if (!['official', 'exploratory'].includes(mode)) throw new TypeError('Modo DialogueVPR inválido.');
  if (!String(queryId || '').trim()) throw new TypeError('Selecciona un identificador.');
  if (text.trim().length < 3) throw new TypeError('Escribe la descripción original.');
  return { schema_version: '1.0', contract_version: START_CONTRACT, mode, query_id: queryId, description_es: text };
}

export function buildDialogueAnswer({ literal, kind }) {
  const answer = String(literal || '').trim();
  if (!answer) throw new TypeError('Escribe una respuesta literal.');
  if (!['affirmation','negation','unknown','unobservable','ambiguous','stop'].includes(kind)) throw new TypeError('Clase de respuesta inválida.');
  return { schema_version:'1.0', contract_version:ANSWER_CONTRACT, answer_literal:answer, answer_kind:kind, human_attested:true, external_context_used:false };
}

export function officialDescriptionMatches(query, description) {
  return Boolean(query && typeof description === 'string' && query.description_es === description);
}

export function validateDialogueSession(document) {
  if (document?.contract_version !== 'atlas-dialogue-session-public-v1' || typeof document.session_id !== 'string' || !['awaiting_answer','completed'].includes(document.status)) throw new TypeError('Sesión DialogueVPR incompatible.');
  if (document.status === 'awaiting_answer' && (!document.current_question || !Number.isInteger(document.current_question.turn_index))) throw new TypeError('Falta la pregunta actual.');
  return document;
}
