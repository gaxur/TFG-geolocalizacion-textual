"""Transiciones visuales del snapshot supervisado; ninguna lanza modelos."""
from __future__ import annotations

import fcntl
import json
import re
from uuid import uuid4

from research.dq_pilot_iterative_controller_v1 import accumulated_description, digest, digest_text
from research.dq_pilot_supervised_v1 import operation
from research.dq_pilot_supervised_visual_v1 import (
    PanelEnvelope, QUESTION_CHECKS, VISUAL_STAGES, check_image, panel_rows, require, visual_operation,
)
from .dq_iterative_sessions import DQIterativeConflict, DQIterativeUnavailable, utcnow


class SupervisedVisual:
    def _persist_reserve_geometry(self, bridge, ranking):
        if self.cells_geojson is None:
            return  # El ranking ya conserva los centros WGS84.
        from src.tfg_phase0.mapillary_visual_pilot import reject_ground_truth
        data = json.loads(self.cells_geojson.read_text())
        reject_ground_truth(data)
        ids = {row['candidate_id'] for row in ranking['results']}
        gallery = ranking.get('gallery_id', 'madrid-50m')
        geometries = {f['properties']['candidate_id']: f['geometry'] for f in data['features']
                      if f['properties']['candidate_key'] == f"{gallery}:{f['properties']['candidate_id']}"
                      and f['properties']['candidate_id'] in ids and f['geometry']['type'] == 'Polygon'}
        bridge['reserve_geometry'] = {'source_sha256': digest(data), 'geometries': geometries}

    def _final_input(self, meta, bridge):
        state = bridge['state']
        require(meta['status'] == 'completed' and state['controller_state'] == 'COMPLETED'
                and bridge['expected'] is None and state['rounds'], 'el diálogo aún no tiene ranking terminal')
        row = state['rounds'][-1]
        ranking = bridge['artifacts'][row['ranking_ref']]
        require(row['round_index'] == state['round_index'] == sum(bool(t.get('answer')) for t in state['turns'])
                and digest(ranking) == row['ranking_sha256'] and row['accumulated_description_sha256'] ==
                digest_text(state['accumulated_description']), 'ranking terminal no incorpora la última respuesta')
        depth = bridge.get('final_visual', {}).get('request', {}).get('depth', self.final_visual_depth)
        return ranking, state['accumulated_description'], depth

    def final_visual_context(self, session_id):
        from src.tfg_phase0.final_visual_ranking import visual_request
        try:
            meta = self.service.load(session_id)
            bridge = self._bridge(meta)
            ranking, description, depth = self._final_input(meta, bridge)
            request = visual_request(ranking=ranking, description=description, depth=depth)
            geometries = bridge.get('reserve_geometry', {})
            return dict(request=request, description=description, candidates=ranking['results'][:depth],
                        geometry_source_sha256=geometries.get('source_sha256'),
                        geometries={cid: geometries['geometries'][cid] for cid in request['candidate_ids']
                                    if cid in geometries.get('geometries', {})})
        except (ValueError, KeyError, TypeError) as exc:
            raise DQIterativeConflict('contexto visual final no disponible') from exc

    def apply_final_visual(self, session_id, evidence):
        # El buzón solo aporta resultados de un runner externo autorizado, nunca inicia inferencia.
        def apply(meta, bridge):
            previous = bridge.get('final_visual_evidence')
            if previous is not None:
                require(previous == evidence, 'resultado visual final divergente')
                return False
            require(isinstance(evidence, dict), 'evidencia visual inválida')
            self._set_final_visual(meta, bridge, evidence=evidence)
            bridge['final_visual_evidence'] = evidence
            self._event(bridge, 'final_visual', 'completed', 'Resultado visual final registrado.')
            return True
        return self._change(session_id, apply)

    def _set_final_visual(self, meta, bridge, *, evidence=None):
        from src.tfg_phase0.final_visual_ranking import final_visual_ranking
        ranking, description, depth = self._final_input(meta, bridge)
        bridge['final_visual'] = final_visual_ranking(ranking=ranking, description=description,
                                                     depth=depth, evidence=evidence, mode=self.mode)

    def _bridge(self, meta):
        bridge = meta.get('supervised')
        if not bridge or bridge['registration']['mode'] != self.mode:
            raise DQIterativeConflict('sesión sin puente de este modo')
        return bridge

    def visual_context(self, session_id):
        meta = self.service.load(session_id)
        try:
            return self._visual_context(self._bridge(meta))
        except (ValueError, TypeError, KeyError) as exc:
            raise DQIterativeConflict('sin ranking vigente para preparar un panel DQ') from exc

    def _visual_context(self, bridge):
        state, artifacts = bridge['state'], bridge['artifacts']
        index = state['round_index']
        stage = f'E{index}'
        require(stage in VISUAL_STAGES and bridge['registration'].get('dq_pilot') is not None, 'DQ no configurado para la etapa')
        require(len(state['rounds']) == index + 1 and len(state['turns']) == index and all(t.get('answer') for t in state['turns']),
                'ranking no posterior a la última respuesta')
        record = state['rounds'][-1]
        ranking, reserve = artifacts[record['ranking_ref']], artifacts[record['reserve_ref']]
        require(record['round_index'] == record['source_answer_count'] == index and digest(ranking) == record['ranking_sha256']
            and digest(reserve) == record['reserve_sha256'] and reserve['source_ranking_sha256'] == record['ranking_sha256']
            and len(reserve['results']) == 20 and reserve['results'] == ranking['results'][:20]
            and record['accumulated_description_sha256'] == digest_text(state['accumulated_description']), 'reserva o ranking no vigentes')
        receipts = [r for r in bridge['receipts'].values() if r['terminal']['stage'] == stage
                    and r['terminal']['component'] == 'crosstext2loc' and r['terminal']['status'] == 'SUCCEEDED']
        require(len(receipts) == 1, 'falta terminal CT2L de esta ronda')
        self._check_host_release(receipts[0]['operation'], receipts[0]['terminal'])
        return dict(session_id=bridge['registration']['session_id'], mode=self.mode, stage=stage,
            **{k: record[k] for k in ('ranking_sha256','reserve_sha256','accumulated_description_sha256')},
             ct2l_terminal_sha256=receipts[0]['terminal_sha256'], ranking=ranking, reserve=reserve,
            original_description=state['original_description'], turns=state['turns'])

    def _status(self, meta, state, controller, status, current_stage, *, stop=None):
        state['controller_state'] = controller
        meta.update(status=status, current_stage=current_stage, stop_reason=stop)
        if status == 'completed':
            self._set_final_visual(meta, meta['supervised'])

    def _change(self, session_id, apply, *, operation_id=None, body=None, answer=False):
        try:
            self.service.load(session_id)
            with (self.service._path(session_id) / '.transition.lock').open('a+b') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                meta = self.service.load(session_id)
                bridge = self._bridge(meta)
                index = bridge['state']['round_index']
                ledger = bridge.setdefault('visual_actions', {})
                if operation_id is not None:
                    require(1 <= len(operation_id) <= 200 and operation_id == operation_id.strip(), 'ID de transición visual inválido')
                    key, sha = digest_text(operation_id), digest({'session_id': session_id, 'body':body})
                    if key in ledger:
                        require(ledger[key]['sha256'] == sha and index <= ledger[key]['round'] + int(answer), 'operación humana divergente o antigua')
                        return meta, False
                if not apply(meta, bridge):
                    return meta, False
                if operation_id is not None:
                    ledger[key] = dict(sha256=sha, round=index)
                    meta['current_operation'] = operation_id
                return self.service._persist_meta(meta), True
        except (DQIterativeConflict, DQIterativeUnavailable):
            raise
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            raise DQIterativeConflict(f'transición visual rechazada: {exc}') from exc

    def receive_panel(self, session_id, stage):
        if stage not in VISUAL_STAGES:
            raise DQIterativeConflict('etapa sin pregunta')
        def apply(meta, bridge):
            state = bridge['state']
            context = self._visual_context(bridge)
            require(context['stage'] == stage, 'panel atrasado')
            visual = bridge.setdefault('visual', {})
            envelope = self._file('panels', f'{session_id}-{stage}.json', PanelEnvelope, allow_missing=stage in visual)
            if stage in visual:
                require(envelope is None or envelope == visual[stage]['envelope'], 'panel congelado divergente')
                return False
            require(state['controller_state'] == 'AWAITING_DQ_AUTHORIZATION' and bridge['expected'] is None, 'no se espera un panel')
            rows = panel_rows(envelope, context)
            for row in rows:
                self._read_visual_blob(row)
            visual[stage] = dict(envelope=envelope, rows=rows)
            self._status(meta, state, 'AWAITING_PANEL_REVIEW', 'waiting_review', f'PANEL_{stage}')
            self._event(bridge, f'{stage}_panel', 'waiting_review', 'Panel Mapillary verificado; pendiente de revisión humana.')
            return True
        return self._change(session_id, apply)

    def panel_review(self, session_id, *, approved, review, operation_id):
        def apply(meta, bridge):
            state = bridge['state']
            context = self._visual_context(bridge)
            stage = context['stage']
            visual = bridge['visual'][stage]
            envelope = visual['envelope']
            require(state['controller_state'] == 'AWAITING_PANEL_REVIEW' and review.get('panel_sha256') == envelope['panel_sha256']
                    and review.get('source_ranking_sha256') == context['ranking_sha256'], 'revisión de otro panel')
            check_review(review, {'panel_sha256','source_ranking_sha256'})
            visual['panel_review'] = dict(approved=approved, **review)
            if not approved:
                self._status(meta, state, 'COMPLETED', 'completed', None, stop='panel_rejected_by_independent_review')
                self._event(bridge, stage, 'completed', 'Panel rechazado; no se prepara DQ-Pilot.')
                return True
            for row in visual['rows']:
                self._read_visual_blob(row)
            visual['approved_panel'] = {**envelope['panel'], 'status':'ready', 'review_required':False,
                                       'panel_review_sha256':digest(visual['panel_review'])}
            bridge['expected'] = visual_operation(bridge['registration'], state, 'dq_pilot', str(uuid4()), context=context, visual=visual)
            self._status(meta, state, 'DQ_SUPERVISED_PENDING', 'pending', f'DQ_{stage}')
            self._event(bridge, f'{stage}_dq_pilot', 'pending', 'Petición oficial preparada; falta autorización externa y terminal one-shot.')
            return True
        return self._change(session_id, apply, operation_id=operation_id, body=['panel', approved, review])[0]

    def question_review(self, session_id, *, approved, review, operation_id):
        def apply(meta, bridge):
            state = bridge['state']
            stage = f"E{state['round_index']}"
            visual = bridge['visual'][stage]
            checks = review.get('checks', {})
            check_review(review, {'generation_sha256','panel_sha256','image_sha256s','checks'})
            require(state['controller_state'] == 'AWAITING_QUESTION_REVIEW'
                    and review['generation_sha256'] == digest(visual['generation']) and review['panel_sha256'] == digest(visual['approved_panel'])
                    and review['image_sha256s'] == [row['sha256'] for row in visual['rows']]
                    and set(checks) == QUESTION_CHECKS and all(type(x) is bool for x in checks.values()), 'rúbrica de otra pregunta o incompleta')
            accepted = approved and all(checks.values())
            visual['question_review'] = dict(approved=accepted, **review)
            if accepted:
                self._status(meta, state, 'AWAITING_TRANSLATION', 'waiting_review', f'TRANSLATION_{stage}')
                self._event(bridge, f'{stage}_translation', 'waiting_review', 'Pregunta EN revisada. Falta una traducción ES y su revisión.')
            else:
                self._status(meta, state, 'COMPLETED', 'completed', None, stop='question_rejected_by_independent_review')
                self._event(bridge, stage, 'completed', 'Pregunta DQ rechazada; no se habilita respuesta.')
            return True
        return self._change(session_id, apply, operation_id=operation_id, body=['question', approved, review])[0]

    def prepare_translation(self, session_id, stage, question_sha256):
        def apply(meta, bridge):
            state = bridge['state']
            context = self._visual_context(bridge)
            require(stage == context['stage'], 'traducción para ronda anterior')
            visual = bridge['visual'][stage]
            require(question_sha256 == digest_text(visual['generation']['question']), 'traducción para otra pregunta')
            if state['controller_state'] == 'TRANSLATION_SUPERVISED_PENDING':
                return False
            require(state['controller_state'] == 'AWAITING_TRANSLATION' and bridge['expected'] is None, 'ya existe una traducción o no se espera')
            bridge['expected'] = visual_operation(bridge['registration'], state, 'qwen_translation', str(uuid4()), context=context, visual=visual)
            self._status(meta, state, 'TRANSLATION_SUPERVISED_PENDING', 'pending', f'TRANSLATION_{stage}')
            self._event(bridge, f'{stage}_translation', 'pending', 'Traducción Qwen preparada; falta autorización independiente y terminal.')
            return True
        return self._change(session_id, apply)

    def manual_translation(self, session_id, *, text, source_hash, generation_sha, author, operation_id):
        if self.mode == 'real':
            raise DQIterativeConflict('el pipeline real requiere traducción Qwen supervisada')
        def apply(meta, bridge):
            state = bridge['state']
            stage = f"E{state['round_index']}"
            visual = bridge['visual'][stage]
            question = visual['generation']['question']
            require(state['controller_state'] == 'AWAITING_TRANSLATION' and bridge['expected'] is None
                    and digest_text(question) == source_hash and digest(visual['generation']) == generation_sha
                    and 1 <= len(author.strip()) <= 150 and author == author.strip()
                    and 3 <= len(text) <= 500 and text == text.strip() and text.startswith('¿') and text.endswith('?')
                    and text.count('?') == 1 and not any(c in text for c in ('<','>','\n')), 'borrador manual inválido o de otra pregunta')
            translation = dict(source_question=question, source_question_sha256=source_hash, translated_question=text,
                translated_question_sha256=digest_text(text), translator=dict(translator_id='Traducción manual (no Qwen)', author=author, origin='human_manual'))
            self.save_translation(meta, bridge, stage, translation, origin='human_manual')
            return True
        return self._change(session_id, apply, operation_id=operation_id, body=['manual', text, source_hash, generation_sha, author])[0]

    def save_translation(self, meta, bridge, stage, translation, *, origin):
        state, visual = bridge['state'], bridge['visual'][stage]
        path = f"rounds/round-{state['round_index']}/spanish-translation.json"
        translator = ({**translation['translator'], 'translator_id':'Fixture CPU (no Qwen)', 'origin':'cpu_fixture'}
                      if origin == 'cpu_fixture' else translation['translator'])
        bridge['artifacts'][path] = {**translation, 'translator':translator, 'origin':origin, 'session_id':meta['session_id'], 'stage':stage,
                                    'generation_sha256':digest(visual['generation'])}
        state['rounds'][-1]['translation_ref'] = path
        state['pending_translation'] = True
        self._status(meta, state, 'AWAITING_TRANSLATION_REVIEW', 'waiting_review', f'TRANSLATION_REVIEW_{stage}')
        self._event(bridge, f'{stage}_translation', 'waiting_review', 'Borrador ES persistido; requiere aceptación humana para esta pregunta.')

    def translation_decision(self, session_id, *, decision, review, operation_id):
        def apply(meta, bridge):
            state = bridge['state']
            stage = f"E{state['round_index']}"
            visual = bridge['visual'][stage]
            translation = bridge['artifacts'][state['rounds'][-1]['translation_ref']]
            require(self.mode != 'real' or translation['origin'] == 'supervised_qwen', 'traducción Qwen supervisada obligatoria')
            check_review(review, {'translation_sha256','source_question_sha256','translated_question_sha256'})
            require(state['controller_state'] == 'AWAITING_TRANSLATION_REVIEW'
                    and review['translation_sha256'] == digest(translation)
                    and all(review[k] == translation[k] for k in ('source_question_sha256','translated_question_sha256'))
                    and decision in ('accept_for_this_technical_pilot','reject','unresolved'), 'decisión de otra traducción')
            visual['translation_review'] = dict(decision=decision, formal_translation_validated=False, **review)
            state.pop('pending_translation', None)
            if decision != 'accept_for_this_technical_pilot':
                self._status(meta, state, 'COMPLETED', 'completed', None, stop='pilot_translation_rejected_or_unresolved')
                self._event(bridge, stage, 'completed', 'Traducción no aprobada; no se habilita la respuesta.')
                return True
            question = dict(turn_index=state['round_index']+1, question_es=translation['translated_question'],
                            question_id=digest({'session_id':session_id, 'translation_sha256':digest(translation)}))
            state['pending_question'] = question
            state['turns'].append(dict(index=question['turn_index'], question_original=translation['source_question'],
                question_es=question['question_es'], question_id=question['question_id'],
                question_es_sha256=translation['translated_question_sha256'], answer=None))
            self._status(meta, state, 'AWAITING_USER', 'waiting_user', None)
            self._event(bridge, stage, 'waiting_user', 'Pregunta ES aprobada para este piloto. Se admite respuesta.')
            return True
        return self._change(session_id, apply, operation_id=operation_id, body=['translation', decision, review])[0]

    def answer(self, session_id, *, answer, turn_index, question_id, question_sha256, operation_id, user_requests_stop):
        def apply(meta, bridge):
            state = bridge['state']
            q, turn = state['pending_question'], state['turns'][-1]
            require(state['controller_state'] == 'AWAITING_USER' and turn['answer'] is None and bridge['expected'] is None
                    and turn_index == q['turn_index'] == state['round_index'] + 1 and turn_index <= 3
                    and question_id == q['question_id'] and question_sha256 == digest_text(q['question_es']), 'respuesta ligada a otra sesión o pregunta')
            turn['answer'] = dict(literal=answer, sha256=digest_text(answer), human_attested=True, user_requests_stop=user_requests_stop,
                                  created_at_utc=utcnow())
            state.pop('pending_question')
            state['round_index'] = turn_index
            state['accumulated_description'] = accumulated_description(state['original_description'], state['turns'])
            stage = f'E{turn_index}'
            bridge['expected'] = operation(bridge['registration'], state, 'qwen', str(uuid4()))
            self._status(meta, state, 'LLM_INTERPRETATION', 'pending', f'QWEN_{stage}')
            self._event(bridge, f'{stage}_qwen', 'pending', 'Respuesta persistida; nueva interpretación Qwen pendiente de autorización.')
            return True
        return self._change(session_id, apply, operation_id=operation_id,
            body=['answer', answer, turn_index, question_id, question_sha256, user_requests_stop], answer=True)[0]

    def media(self, session_id, ref):
        if not re.fullmatch(r'E[0-2]-I[1-4]', ref):
            raise DQIterativeConflict('medio inexistente')
        bridge = self._bridge(self.service.load(session_id))
        visual = bridge.get('visual', {}).get(ref[:2])
        if visual is None:
            raise DQIterativeConflict('medio inexistente')
        return self._read_visual_blob(visual['rows'][int(ref[-1])-1])


def check_review(review, keys):
    require(set(review) == keys | {'ground_truth_used','reviewer_declaration'} and review['ground_truth_used'] is False
            and isinstance(review['reviewer_declaration'], str) and 1 <= len(review['reviewer_declaration'].strip()) <= 1000,
            'declaración humana o campos de revisión inválidos')


def visual_public(meta, bridge):
    state = bridge['state']
    stage = f"E{state['round_index']}"
    visual = bridge.get('visual', {}).get(stage)
    waiting_panel = (bridge['state']['controller_state'] == 'AWAITING_DQ_AUTHORIZATION'
                     and bridge['registration'].get('dq_pilot') is not None)
    if not visual:
        return {'waiting_supervised_panel': True} if waiting_panel else {}
    envelope, generation = visual['envelope'], visual.get('generation')
    review = dict(panel_sha256=envelope['panel_sha256'], ranking_sha256=envelope['ranking_sha256'],
                  image_sha256s=[r['sha256'] for r in visual['rows']])
    if generation:
        review.update(original_en=generation['question'], generation_sha256=digest(generation),
                      source_question_sha256=digest_text(generation['question']), panel_sha256=digest(visual['approved_panel']),
                      question_provenance='official_supervised' if meta['execution_mode'] == 'real' else 'cpu_fixture')
    if visual.get('translation_review'):
        translation = bridge['artifacts'][bridge['state']['rounds'][-1]['translation_ref']]
        review.update(translation_es=translation['translated_question'], translator=translation['translator'],
                      translation_decision=visual['translation_review']['decision'])
    return dict(visual_review=review, waiting_supervised_translation=(state['controller_state'] == 'AWAITING_TRANSLATION'
        and bridge['registration'].get('qwen_translation') is not None), visual_evidence=[{**row, 'media_path':
        f"/dialogue-freetext/sessions/{meta['session_id']}/visual-media/{stage}-{row['ref']}"} for row in visual['rows']])
