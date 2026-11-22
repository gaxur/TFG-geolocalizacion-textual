"""Contratos de panel, pregunta y traducción para el supervisor externo (solo CPU)."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Literal

from research.dq_pilot_iterative_controller_v1 import canonical, dialogue_history, digest, digest_text
from research.dq_pilot_real_adapters_v1 import QWEN_IDENTITY, PreparedDQPilotQuestionerAdapter, native_round_request
from research.dq_pilot_supervised_v1 import HEX, OPERATION, ContractError, Mode, StrictModel, make_terminal, validate_terminal
from research.dq_pilot_translation_v1 import validate_translation

PANEL_CONTRACT = 'atlas-dq-supervised-panel-v1'
VISUAL_STAGES = ('E0', 'E1', 'E2')
HEX_RE = re.compile(r'[0-9a-f]{64}')
QUESTION_CHECKS = frozenset({'grounded', 'discriminative', 'user_answerable', 'novel', 'single_clear_question', 'no_internal_reference'})
MAX_IMAGE_BYTES = 8 * 1024 * 1024
TRANSLATION_MANIFEST_SHA = 'd95b2ee5a666c88adcb53094740c1002718f28e0dcabad56a508a9c66dce1570'
TRANSLATION_PROMPT = ('Translate the following visual question from English to Spanish. Preserve exactly the meaning, negation, alternatives, '
                      'spatial relations, uncertainty, numbers, and proper names. Do not answer the question, explain it, repair it, or add '
                      'visual facts. Output only one Spanish question.')


class ProcessorExpectation(StrictModel):
    profile: str
    preprocessing: Literal['rgb-convert-no-exif-transpose']
    image_order: list[str]
    input_tokens: int
    pixel_values_shape: list[int]
    image_grid_thw: list[list[int]]


class PanelEnvelope(StrictModel):
    contract_version: Literal[PANEL_CONTRACT]
    mode: Mode
    session_id: str
    stage: Literal['E0', 'E1', 'E2']
    ranking_sha256: HEX
    reserve_sha256: HEX
    ct2l_terminal_sha256: HEX
    accumulated_description_sha256: HEX
    panel_sha256: HEX
    panel: dict
    processor_expectation: ProcessorExpectation


def file_digest(blob):
    return hashlib.sha256(blob).hexdigest()


def native_bytes(document):
    return canonical(document) + b'\n'


def require(value, message):
    if not value:
        raise ContractError(message)


def check_image(blob, row):
    require(0 < len(blob) == row['size_bytes'] <= MAX_IMAGE_BYTES and file_digest(blob) == row['sha256']
            and blob.startswith(b'\xff\xd8\xff') and blob.endswith(b'\xff\xd9'), 'JPEG Mapillary divergente')
    return blob


def panel_rows(envelope, context):
    for key in ('mode', 'session_id', 'stage', 'ranking_sha256', 'reserve_sha256', 'ct2l_terminal_sha256', 'accumulated_description_sha256'):
        require(envelope[key] == context[key], 'panel de otro ranking, ronda o sesión')
    panel, expectation = envelope['panel'], envelope['processor_expectation']
    require(envelope['panel_sha256'] == digest(panel) and panel['source_ranking_sha256'] == context['ranking_sha256']
            and panel['ground_truth_used'] is False and panel['round_index'] == int(context['stage'][1:])
            and panel['contract_version'] == 'dq-pilot13-mapillary-panel-v1'
            and panel['status'] == 'prepared_pending_review' and panel['review_required'] is True,
            'identidad del panel divergente')
    require(isinstance(expectation['profile'], str) and expectation['profile'].strip() and expectation['input_tokens'] > 0
            and expectation['image_order'] == ['I1','I2','I3','I4']
            and len(expectation['pixel_values_shape']) == 2 and min(expectation['pixel_values_shape']) > 0
            and len(expectation['image_grid_thw']) == 4 and all(len(x) == 3 and min(x) > 0 for x in expectation['image_grid_thw']),
            'expectativa CPU del processor inválida')
    candidates, images = panel['candidates'], panel['images']
    require(len(candidates) == len(images) == 4 and panel['candidate_ids'] == [r['candidate_id'] for r in candidates], 'panel no es 4/4')
    reserve = context['reserve']['results']
    rows = []
    for index, (candidate, image) in enumerate(zip(candidates, images), 1):
        rank, cid, iid = candidate['source_rank'], candidate['candidate_id'], image['image_id']
        ref, alias = f'I{index}', f'C{index}'
        association = image['association']
        require(type(rank) is int and 1 <= rank <= 20 and reserve[rank-1]['candidate_id'] == cid
                and candidate['candidate_ref'] == image['candidate_ref'] == alias and image['image_ref'] == ref
                and re.fullmatch(r'[0-9]{1,40}', iid) and HEX_RE.fullmatch(image['sha256'])
                and type(image['size_bytes']) is int and 0 < image['size_bytes'] <= MAX_IMAGE_BYTES
                and (association['candidate_id'], association['candidate_rank'], association['image_id']) == (cid, rank, iid)
                and association['within_round'] is True, 'asociación foto/candidato no corresponde a Top-20')
        rows.append(dict(ref=ref, candidate_id=cid, rank=rank, sha256=image['sha256'], size_bytes=image['size_bytes'],
                         role='mapillary_associated', source_url=f'https://www.mapillary.com/app/?pKey={iid}'))
    for key in ('rank', 'source_url', 'sha256'):
        require(len({row[key] for row in rows}) == 4, 'panel contiene celdas o fotografías duplicadas')
    return rows


def visual_operation(registration, state, component, op_id, *, context, visual):
    stage = context['stage']
    require(stage in VISUAL_STAGES and registration.get(component) is not None, 'etapa visual no configurada')
    common = {k: context[k] for k in ('ranking_sha256', 'reserve_sha256', 'ct2l_terminal_sha256', 'accumulated_description_sha256')}
    common.update(description_sha256=registration['description_sha256'])
    if component == 'dq_pilot':
        model = PreparedDQPilotQuestionerAdapter.identity
        panel = visual['approved_panel']
        blind = [dict(candidate_ref=f'C{i}', image_ref=row['ref'], logical_path=f"media/{row['ref']}.jpg",
                      sha256=row['sha256'], size_bytes=row['size_bytes']) for i, row in enumerate(visual['rows'], 1)]
        request = native_round_request(session_id=registration['session_id'], query_id=f"{registration['session_id']}-{stage}",
            round_index=state['round_index'], panel=panel, blind_images=blind, original_description=state['original_description'],
            dialogue_history=dialogue_history(state['turns']), expectation=visual['envelope']['processor_expectation'])
        common.update(panel_sha256=digest(panel), panel_envelope_sha256=digest(visual['envelope']),
            candidates_and_photos_sha256=digest(visual['rows']), request=request, request_sha256=file_digest(native_bytes(request)))
    elif component == 'qwen_translation':
        model = {'model_id': QWEN_IDENTITY['model_id'], 'revision': QWEN_IDENTITY['revision'], 'task': 'en-es-question-pending-human-review'}
        question = visual['generation']['question']
        translator = dict(translator_id=model['model_id'], version=model['revision'], local=True,
                          artifact_manifest_sha256=TRANSLATION_MANIFEST_SHA)
        prompt = f'{TRANSLATION_PROMPT}\nEnglish question:\n{question}'
        common.update(source_question=question, source_question_sha256=digest_text(question), translator=translator,
            prompt=prompt, prompt_sha256=digest_text(prompt), generation=dict(do_sample=False, temperature=None,
                maximum_new_tokens=128, automatic_retries=0, fallbacks=0, seed=0, enable_thinking=False),
            source_language='en', target_language='es', dq_terminal_sha256=visual['dq_terminal_sha256'],
            panel_sha256=digest(visual['approved_panel']), question_review_sha256=digest(visual['question_review']))
    else:
        raise ContractError('componente visual inválido')
    return dict(contract_version=OPERATION, session_id=registration['session_id'], operation_id=op_id, stage=stage,
                mode=registration['mode'], component=component, model=model, model_revision=model['revision'],
                **registration[component], input=common, input_sha256=digest(common), ground_truth_used=False)


def project_question(expected, result):
    inp = expected['input']
    required = {'schema_version', 'contract_version', 'status', 'request_id', 'request_sha256', 'panel_sha256',
                'source_ranking_sha256', 'question', 'raw_output_sha256', 'private_output_retained', 'private_output_sha256',
                'raw_commit_sha256', 'host_decision_sha256', 'reasoning_public', 'ground_truth_used', 'host_validation',
                'telemetry_sha256', 'release_sha256'}
    require(set(result) == required and result['schema_version'] == '1.0'
            and result['request_id'] == inp['request']['request_id'] and result['ground_truth_used'] is False
            and result['status'] == 'generated' and result['host_validation'] == {'format': True, 'text_safety': True, 'exact_redundancy': True},
            'proyección nativa DQ incompleta')
    require(result['contract_version'] == 'dq-pilot14-public-generation-v1' and result['request_sha256'] == inp['request_sha256']
            and result['panel_sha256'] == inp['panel_sha256'] and result['source_ranking_sha256'] == inp['ranking_sha256']
            and result['reasoning_public'] is False and result['private_output_retained'] is True
            and all(HEX_RE.fullmatch(result[key] or '') for key in required if key.endswith('_sha256')), 'ligadura o privacidad DQ inválida')
    question = result['question']
    require(isinstance(question, str) and question == question.strip() and 1 <= len(question) <= 500
            and '\n' not in question and '<' not in question and '>' not in question and question.count('?') == 1 and question.endswith('?')
            and question.casefold() not in {s.casefold() for s in inp['request']['history']['prior_questions']}, 'pregunta DQ inválida o repetida')
    return dict(result)


def project_translation(expected, result):
    inp = expected['input']
    return validate_translation(result, round_index=int(expected['stage'][1:]), source_question=inp['source_question'],
                                translator_identity=inp['translator'])


def from_visual_postflight(expected, *, commit, postflight, output_bytes=None, native_commit_bytes=None, worker_release_bytes=None):
    """Proyección sin GPU; llamada por el supervisor que custodia el buzón y el lease."""
    component, status, inp = expected['component'], commit.get('status'), expected['input']
    require(component in {'dq_pilot', 'qwen_translation'} and status in {'SUCCEEDED', 'FAILED', 'TIMED_OUT', 'STOPPED_MEMORY'}
            and all(commit.get(k) == expected[k] for k in ('session_id','operation_id','configuration_sha256'))
            and commit.get('operation_sha256') == digest(expected) and commit.get('postflight_sha256') == digest(postflight)
            and postflight.get('contract_version') == 'atlas-dq-visual-postflight-v1' and postflight.get('policy_sha256') == expected['policy_sha256'],
            'commit/postflight visual no ligado a la operación')
    result, allocated, reserved, release_sha = None, None, None, None
    if status == 'SUCCEEDED':
        require(output_bytes and worker_release_bytes and commit.get('result_sha256') == file_digest(output_bytes)
                and postflight.get('stop_reason') is None and 'stop_reason' in postflight and postflight.get('timed_out') is False
                and postflight.get('exclusive_lease_verified') is True and postflight.get('lease_operation_sha256') == digest(expected),
                'salida parcial, STOP, timeout o lease no comprobado')
        result = json.loads(output_bytes)
        release = json.loads(worker_release_bytes)
        release_sha = file_digest(worker_release_bytes)
        require(commit.get('worker_release_sha256') == release_sha, 'release de otro worker')
        if component == 'dq_pilot':
            project_question(expected, result)
            native = json.loads(native_commit_bytes or b'{}')
            refs = native.get('refs', {})
            require(native_commit_bytes and commit.get('native_commit_sha256') == file_digest(native_commit_bytes)
                    and native.get('contract_version') == 'dq-pilot-generation-terminal-commit-v1' and native.get('status') == 'PUBLISHED'
                    and native.get('automatic_retry_permitted') is False and native.get('request_sha256') == inp['request_sha256']
                    and refs.get('projection_sha256') == file_digest(output_bytes)
                    and all(refs.get(k) == result[k] for k in ('raw_commit_sha256','host_decision_sha256','raw_output_sha256'))
                    and result['release_sha256'] == release_sha and release.get('contract_version') == 'dq-pilot14-release-v1'
                    and release.get('reason') == 'one_shot_complete' and release.get('runtime_state') == 'CLOSED',
                    'commit nativo DQ o cierre one-shot inválido')
            allocated, reserved = release['cuda_allocated_after_release_bytes'], release['cuda_reserved_after_release_bytes']
            residual = bool(allocated or reserved)
            require(type(allocated) is int and type(reserved) is int and 0 <= allocated <= reserved
                and release.get('exit_required') is (allocated > 0) and (
                release.get('status') == ('IN_PROCESS_RESIDUAL_ALLOCATIONS' if residual else 'IN_PROCESS_RELEASE_COMPLETE')
                or expected['mode'] == 'cpu_fixture' and not residual and 'status' not in release),
                'medición de cierre DQ incoherente')
        else:
            project_translation(expected, result)
            require(release.get('operation_sha256') == digest(expected), 'release de otra traducción')
            allocated, reserved = release['allocated_bytes'], release['reserved_bytes']
    else:
        require(output_bytes is None and commit.get('result_sha256') is None, 'fallo no admite salida')
    safety = {k:postflight[k] for k in ('exclusive_lease_verified','timed_out','stop_reason')} if status == 'SUCCEEDED' else None
    if safety is not None and component == 'dq_pilot' and 'dq_post_exit' in postflight:
        safety['dq_post_exit'] = postflight['dq_post_exit']
    terminal = make_terminal(expected, status=status, result=result, process=postflight['process'], release=dict(
        verified=postflight.get('resource_release_verified') is True, policy_compliant=postflight.get('policy_compliant') is True,
        cuda_released=postflight.get('cuda_pids') == [], worker_released=postflight.get('worker_close_verified') is True,
        policy_sha256=postflight['policy_sha256'], torch_allocated_bytes=allocated, torch_reserved_bytes=reserved),
        evidence=dict(supervisor_commit_sha256=digest(commit), postflight_sha256=digest(postflight), worker_release_sha256=release_sha),
        visual_safety=safety)
    validate_terminal(expected, terminal)
    return terminal
