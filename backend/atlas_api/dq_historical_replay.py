"""Reproducción local del caso H27; nunca emite ni consume terminales de workers."""
from __future__ import annotations

import fcntl
import hashlib
import json
from pathlib import Path
import uuid

from research.ct2l_supervisor_v3 import validate_ranking
from .dq_iterative_sessions import DQIterativeConflict, digest, digest_text, utcnow, POLICY_ID


CT = 'dq-dev59-h26-bundle-cohort-v1/pending/H27/A0-R0'
PKG = 'dq-pilot17-h27-phase-a-v2'
RUN = 'dq-pilot17-h27-phase-a-run-v2'
SOURCES = {
    'plan': (f'{CT}/plan.json', 'd8f3126642624ea4823aab23ff7bb296ccb2fe0ca846af6852d7b89309f23b3e'),
    'supervisor': (f'{CT}/run/supervisor.json', 'ce6ae903ff0eb9a6fa0a27592cb55cbed7367f76547a04fe91a62a42fe22bbcc'),
    'ranking': (f'{CT}/run/ranking.json', 'ef27a1e149d9fec21ba90bf7cf3a65718a4c7970ee7ac9d0b3bd9ecd89d8806f'),
    'package': (f'{PKG}/package-manifest.json', '99632f6dfc3bbeb03fe22c349dd55342f1f8fb4861047dfa607df39ca0851239'),
    'panel': (f'{PKG}/source-panel.json', 'db118bd4f3977aa1f67b9aa1eb6a965e06a5bda7234206159375a0d664d4df60'),
    'lineage': (f'{PKG}/source-private-lineage.json', '876f287f4ba0d1aa3b3d475baaf9c0701cfe81abab991ad6a04c722e2df2c34b'),
    'request': (f'{PKG}/request.json', 'bc0552fc3c15262c82dd171706e1a30e3ae03415fbb6e382a92960c29ec18fad'),
    'runtime': (f'{PKG}/runtime-normalized-v2.json', '52eb8f0c4ce7a83f31110b6f8eb48b081e85b2da295fecffb8c8dd1f8c2fea13'),
    'final': (f'{RUN}/final-manifest.json', '4730d13ab2e1742997cb05c9b016a19711b147089282712fc75070a89fd90fb1'),
    'question': (f'{RUN}/public-result.json', 'b606016e38b75d9a827f4a3047114a363cc373f513bed409b3035495702d9523'),
}
CASE = 'h27-a0-r0-dq18'
MODE = 'historical_replay'


def replay_session_id(operation_id):
    return f'dq-iterative-{uuid.uuid5(uuid.NAMESPACE_URL, f"atlas-replay:{CASE}:{operation_id}")}'


def require(condition, message):
    if not condition:
        raise DQIterativeConflict(message)


def verified_bytes(root, relative, sha):
    path = (root / relative).resolve(strict=True)
    require(path.is_relative_to(root) and path.is_file(), 'ruta de replay inválida')
    blob = path.read_bytes()
    require(hashlib.sha256(blob).hexdigest() == sha, 'hash de artefacto histórico divergente')
    return blob


def validate_media(panel, lineage, requested, package_images, rows):
    require(len(panel) == len(lineage) == len(requested) == 4, 'panel histórico incompleto')
    result = []
    for index, (image, bound, binding) in enumerate(zip(panel, lineage, requested), 1):
        ref, candidate = f'I{index}', f'C{index}'
        rank, image_id, sha = bound['ct2l_rank'], bound['image_id'], image['sha256']
        require(1 <= rank <= 20 and rows[rank-1]['candidate_id'] == bound['candidate_id'], 'foto de otra celda o fuera de la reserva')
        expected = dict(image_ref=ref, candidate_ref=candidate, logical_path=f'media/{ref}.jpg', sha256=sha, size_bytes=image['size_bytes'])
        require(binding == expected and all(image[k] == v for k, v in expected.items())
                and (bound['image_ref'], bound['candidate_ref'], bound['image_sha256']) == (ref, candidate, sha)
                and package_images[f'{ref}.jpg'] == sha and image_id.isascii() and image_id.isdecimal(), 'enlace de foto histórica divergente')
        result.append(dict(ref=ref, candidate_id=bound['candidate_id'], rank=rank, sha256=sha,
                           size_bytes=image['size_bytes'], role=bound['d112_evidence_role'],
                           source_url=f'https://www.mapillary.com/app/?pKey={image_id}'))
    require(len({r['rank'] for r in result}) == len({r['source_url'] for r in result}) == 4, 'panel histórico duplicado')
    return result


class HistoricalReplay:
    def __init__(self, root: Path):
        root = root.resolve(strict=True)
        sha = {k: spec[1] for k, spec in SOURCES.items()}
        docs = {k: json.loads(verified_bytes(root, *spec)) for k, spec in SOURCES.items()}
        plan, supervisor, ranking = docs['plan'], docs['supervisor'], docs['ranking']
        package, panel, lineage, req = docs['package'], docs['panel'], docs['lineage'], docs['request']
        runtime, final, question = docs['runtime'], docs['final'], docs['question']
        call = plan['calls'][0]
        description = plan['retrieval_input']['text']
        require(plan['query_id'] == panel['query_id'] == lineage['query_id'] == req['query_id'] == 'H27'
                and plan['evaluation_arm'] == 'A0' and plan['target_round'] == req['round_index'] == 0
                and plan['restrictions']['ground_truth'] is False and plan['restrictions']['h38_h61'] is False
                and rank_protocol_ok(ranking) and digest_text(description) == call['input_sha256']
                and plan['retrieval_input']['language'] == 'es' and req['history']['native_text'] == f'Witness: {description}'
                and ranking['identities']['checkpoint_sha256'] == call['model_artifact_sha256'], 'origen CT2L incompatible')
        check = validate_ranking(ranking, call_id=supervisor['call_id'],
                                 expected_candidate_set_sha256=plan['candidate_universe']['candidate_id_set_sha256'])
        require(supervisor['status'] == 'SUCCEEDED' and supervisor['returncode'] == 0 and supervisor['validation'] == check
                and supervisor['artifacts']['ranking']['sha256'] == sha['ranking'], 'supervisión CT2L histórica incoherente')
        require(all(x['ground_truth_used'] is False for x in (panel, lineage, req['constraints'], question))
                and all(req['constraints'][k] is False for k in ('coordinates_sent', 'scores_sent', 'ranks_sent'))
                and package['artifacts']['runtime-normalized-v2.json'] == sha['runtime']
                and lineage['source_ranking_sha256'] == req['source_ranking_sha256'] == question['source_ranking_sha256'] == final['ranking_sha256'] == sha['ranking']
                and req['projection']['source_lineage_sha256'] == final['lineage_sha256'] == sha['lineage']
                and req['source_panel_sha256'] == question['panel_sha256'] == final['panel_sha256'] == sha['panel']
                and question['request_id'] == req['request_id'] and question['request_sha256'] == final['request_sha256'] == sha['request']
                and final['public_result_sha256'] == sha['question'] and final['status'] == 'GPU_PHASE_A_COMPLETED'
                and final['inferences'] == 1 and final['h33_used'] is False and final['h38_h61_opened'] is False
                and question['status'] == 'generated' and question['reasoning_public'] is False
                and question['question'] == final['question'], 'linaje de la pregunta oficial incompatible')
        self.description = description
        self.rows = ranking['results']
        self.images = validate_media(panel['images'], lineage['records'], req['images'], package['images'], self.rows)
        self.media = {}
        for img in self.images:
            data = verified_bytes(root, f"{PKG}/media/{img['ref']}.jpg", img['sha256'])
            require(len(data) == img['size_bytes'] and data.startswith(b'\xff\xd8'), 'JPEG histórico inválido')
            self.media[img['ref']] = data
        self.provenance = dict(case_id=CASE, source_run='DQ-DEV.60 / DQ-PILOT.18', sha256=sha,
                               source_call_id=supervisor['call_id'], source_request_id=req['request_id'],
                                model_id=runtime['model']['model_id'], model_revision=runtime['model']['revision'],
                                candidate_set_sha256=check['candidate_id_set_sha256'], scores_sha256=check['scores_sha256'],
                                ranking_order_sha256=check['ranking_order_sha256'],
                               top20_sha256=digest({'ranking_sha256': sha['ranking'], 'results': self.rows[:20]}))
        self.original = question['question']
        self.original_sha = digest_text(self.original)

    def start(self, service, operation_id, idempotency_key):
        require(operation_id == idempotency_key, 'identificador de alta divergente')
        # El slot de alta identifica la sesión incluso si se pierde el ACK del primer write.
        session_id = replay_session_id(operation_id)
        root = service._path(session_id)
        root.mkdir(mode=0o700, exist_ok=True)
        with (root / '.transition.lock').open('a+b') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if service._metadata(session_id).exists():
                meta = service.load(session_id)
                require(meta.get('execution_mode') == MODE and meta['historical']['start_operation'] == operation_id, 'operación de alta cruzada')
                return meta
            meta = dict(schema_version='1.0', contract_version='atlas-dq-iterative-session-v1', session_id=session_id,
                        policy_id=POLICY_ID, description_es=self.description, description_sha256=digest_text(self.description),
                        controller_root=None, execution_mode=MODE, status='waiting_review', stop_reason=None,
                        created_at_utc=utcnow(), current_operation=operation_id, current_stage='HISTORICAL_REPLAY',
                        expected_generation=0, gpu_used=False, search_executed=False, rankings_available=True)
            meta['historical'] = dict(provenance=self.provenance, images=self.images, start_operation=operation_id,
                                      events=[], receipts={}, ranking=self.rows, reserve=self.rows[:20],
                                      original_en=self.original, original_sha256=self.original_sha,
                                      translation=None, decision=None, answer=None, state='AWAITING_REPLAY_TRANSLATION')
            event(meta, 'E0_ranking', 'completed', 'Ranking CT2L histórico verificado y guardado; no se ejecutó búsqueda.')
            event(meta, 'replay', 'waiting_review', 'Pregunta oficial histórica; falta traducción histórica verificable.')
            return service._persist_meta(meta)


def rank_protocol_ok(ranking):
    return (ranking['query_id'] == 'H27-A00' and ranking['arm'] == 'A0' and ranking['round_index'] == 0
            and all(ranking['protocol'][key] is False for key in ('ground_truth_used', 'h38_h61_used', 'references_used')))


def event(meta, stage, state, message):
    rows = meta['historical']['events']
    rows.append(dict(event_id=str(len(rows)+1), stage=stage, state=state, message=message,
                     error_code=None, created_at_utc=utcnow()))


def mutate(service, session_id, operation_id, kind, body, apply):
    require(1 <= len(operation_id) <= 200 and operation_id == operation_id.strip(), 'identificador de operación inválido')
    require(service.load(session_id).get('execution_mode') == MODE, 'la sesión no es una reproducción histórica')
    with (service._path(session_id) / '.transition.lock').open('a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        meta = service.load(session_id)
        history = meta['historical']
        key, receipt = digest_text(operation_id), digest({'session_id': session_id, 'kind': kind, 'body': body})
        if key in history['receipts']:
            require(history['receipts'][key] == receipt, 'operación histórica repetida con otro contenido')
            return meta
        apply(meta, history)
        history['receipts'][key] = receipt
        meta['current_operation'] = operation_id
        return service._persist_meta(meta)


def record_translation(service, session_id, *, text, source_hash, operation_id):
    def apply(meta, h):
        require(h['state'] == 'AWAITING_REPLAY_TRANSLATION' and h['original_sha256'] == source_hash
                and text == text.strip() and 3 <= len(text) <= 500 and text.startswith('¿') and text.endswith('?'),
                'traducción manual inválida o de otra pregunta')
        h['translation'] = dict(source_question=h['original_en'], source_question_sha256=source_hash,
                                translated_question=text, translated_question_sha256=digest_text(text),
                                translator={'translator_id': 'Traducción manual de reproducción (no Qwen)'},
                                session_id=session_id, source_question_artifact_sha256=h['provenance']['sha256']['question'])
        h['state'] = 'AWAITING_TRANSLATION_REVIEW'
        event(meta, 'replay_translation', 'waiting_review', 'Traducción manual guardada; falta aprobación humana.')
    return mutate(service, session_id, operation_id, 'translation', [text, source_hash], apply)


def decide_translation(service, session_id, *, decision, review, operation_id):
    def apply(meta, h):
        translation = h['translation'] or {}
        declaration = review.get('reviewer_declaration')
        require(h['state'] == 'AWAITING_TRANSLATION_REVIEW' and review.get('ground_truth_used') is False
                and set(review) == {'ground_truth_used', 'reviewer_declaration', 'translation_sha256',
                                    'source_question_sha256', 'translated_question_sha256'}
                and isinstance(declaration, str) and 1 <= len(declaration.strip()) <= 1000
                and decision in {'accept_for_this_technical_pilot', 'reject', 'unresolved'}
                and review.get('translation_sha256') == digest(translation)
                and all(review.get(k) == translation.get(k) for k in ('source_question_sha256', 'translated_question_sha256')),
                'revisión de reproducción no ligada a esta traducción')
        h['decision'] = dict(decision=decision, review=dict(review), formal_translation_validated=False)
        accepted = decision == 'accept_for_this_technical_pilot'
        h['state'] = 'AWAITING_USER' if accepted else 'COMPLETED'
        meta['status'] = 'waiting_user' if accepted else 'completed'
        meta['stop_reason'] = None if accepted else 'historical_translation_not_accepted'
        event(meta, 'replay_review', meta['status'], 'Decisión humana sobre la traducción histórica guardada.')
    return mutate(service, session_id, operation_id, 'decision', [decision, review], apply)


def record_answer(service, session_id, *, answer, turn_index, question_id, question_sha256,
                  client_operation_id, idempotency_key, user_requests_stop=False):
    require(client_operation_id == idempotency_key and not user_requests_stop, 'operación de respuesta histórica inválida')
    def apply(meta, h):
        require(h['state'] == 'AWAITING_USER' and turn_index == 1 and question_id == replay_question_id(meta)
                and question_sha256 == h['translation']['translated_question_sha256'] and 1 <= len(answer.strip()) <= 1200,
                'respuesta de otra pregunta o sesión histórica')
        h['answer'] = dict(literal=answer, question_sha256=question_sha256, sha256=digest_text(answer))
        h['state'] = 'COMPLETED'
        meta.update(status='completed', stop_reason='historical_replay_answer_saved_no_new_inference')
        event(meta, 'replay_answer', 'completed', 'Respuesta guardada. No se ejecutó otra recuperación ni se generó otra pregunta.')
    return mutate(service, session_id, client_operation_id, 'answer', [answer, turn_index, question_id, question_sha256], apply)


def replay_question_id(meta):
    return digest({'session_id': meta['session_id'], 'translation': meta['historical']['translation']})


def project(meta):
    h = meta['historical']
    translation, decision = h['translation'], h['decision']
    pending = None
    if h['state'] == 'AWAITING_TRANSLATION_REVIEW':
        pending = dict(mode='PILOT_TRANSLATION_UNVALIDATED', source_question_en=h['original_en'],
                       source_question_sha256=h['original_sha256'], translated_question_es=translation['translated_question'],
                       translated_question_sha256=translation['translated_question_sha256'], translation_sha256=digest(translation),
                       translator=translation['translator'], formal_translation_validated=False, human_decision_required=True)
    turns, current = [], None
    if decision and decision['decision'] == 'accept_for_this_technical_pilot':
        qid, text, text_hash = replay_question_id(meta), translation['translated_question'], translation['translated_question_sha256']
        turns = [dict(index=1, question=text, question_id=qid, question_sha256=text_hash,
                      answer_literal=h['answer']['literal'] if h['answer'] else None)]
        if h['state'] == 'AWAITING_USER':
            current = dict(turn_index=1, question=text, question_id=qid, question_sha256=text_hash)
    history = dict(provenance=h['provenance'], original_en=h['original_en'],
                   source_question_sha256=h['original_sha256'], translation_es=translation and translation['translated_question'],
                   decision=decision and decision['decision'])
    images = [{**row, 'media_path': f"/dialogue-freetext/sessions/{meta['session_id']}/historical-media/{row['ref']}"}
              for row in h['images']]
    return dict(schema_version='1.0', contract_version='atlas-dq-iterative-session-public-v1',
                session_id=meta['session_id'], policy_id=POLICY_ID, description_es=meta['description_es'],
                accumulated_description_es=meta['description_es'], execution_mode=MODE, supervised=False,
                status=meta['status'], stop_reason=meta['stop_reason'], turns=turns, current_question=current,
                pending_translation_review=pending, historical_replay=history, visual_evidence=images,
                stage_snapshots=[dict(stage='E0', gallery_id='madrid-50m', candidate_count=len(h['ranking']),
                                      ranking_sha256=h['provenance']['sha256']['ranking'], results=h['ranking'][:10])],
                final_stage='E0', maximum_questions=1, controller_state=h['state'], round_index=0,
                current_stage=meta['current_stage'], gpu_used=False, search_executed=False, rankings_available=True,
                session_sha256=meta['session_sha256'], updated_at_utc=meta['updated_at_utc'])
