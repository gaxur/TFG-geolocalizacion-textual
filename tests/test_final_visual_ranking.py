"""Fixtures CPU. No cargan modelos ni usan imágenes o datos de evaluación reales."""

import json
from hashlib import sha256

import pytest

from src.tfg_phase0.final_visual_ranking import CONTRACT, MODEL, digest, final_visual_ranking, visual_request
from src.tfg_phase0.final_visual_v4 import associations_from_d112, evidence_from_v4, prepare_v4
from src.tfg_phase0.visual_reranking import compile_atomic_claims_v2
from src.tfg_phase0.visual_verifier import SUPPORTED_LOCAL_MODELS
from tests import test_dq_pilot52_supervised_visual as dq


def observation(context, index, verdict):
    return dict(candidate_id=context['request']['candidate_ids'][index], image_id=f'fixture-{index}',
                image_sha256='a'*64, sequence_id=None, status='valid', verdict=verdict,
                claim=compile_atomic_claims_v2(context['description'])['claims'][0])


def test_final_reranking_after_supervised_answer_and_restart(tmp_path):
    client, service, sid = dq.start(tmp_path)
    private = dq.private(sid) + '/final-visual'
    polygon = {'type': 'Polygon', 'coordinates': [[[-3.71, 40], [-3.69, 40], [-3.69, 40.01], [-3.71, 40]]]}
    service.supervisor.cells_geojson = tmp_path / 'cells.geojson'
    service.supervisor.cells_geojson.write_text(json.dumps({'features': [dict(geometry=polygon,
        properties=dict(candidate_id='c012', candidate_key='madrid-50m:c012'))]}))
    initial = dq.retrieve(client, tmp_path, sid, 'E0')
    dq.call(client, private + '/context', method='GET', code=409)
    dq.receive_panel(client, tmp_path, sid, 'E0')
    dq.panel_review(client, sid)
    op = dq.base.expected(client, sid)
    assert op['model_revision'] == 'cf5c7b8a79ce055a83706fcbe0b94edf31b1cb40'
    dq.consume(client, tmp_path, sid, dq.visual_terminal(op))
    dq.question_review(client, sid)
    dq.manual(client, sid, 'E0')
    active = dq.translation_review(client, sid)
    body = dq.answer_body(active['current_question'], 'Veo una torre junto a una iglesia.')
    body['user_requests_stop'] = True
    posted = dq.answer(client, sid, body)
    assert posted['accumulated_description_es'].endswith(body['answer_literal'])
    assert posted['status'] == 'pending'
    dq.call(client, private + '/context', method='GET', code=409)
    terminal = dq.retrieve(client, tmp_path, sid, 'E1')
    assert terminal['status'] == 'completed' and terminal['current_question'] is None
    first, latest = terminal['stage_snapshots']
    assert first == initial['stage_snapshots'][0]
    final = latest['visual_postprocessing']
    assert final['status'] == 'fallback_baseline' and final['final_results'] == latest['results']
    assert final['mode'] == 'cpu_fixture'
    context = dq.call(client, private + '/context', method='GET')
    assert context['geometries']['c012'] == polygon
    assert context['request']['candidate_ids'] == [f'c{i:03}' for i in range(2, 52)]
    assert context['description'] == terminal['accumulated_description_es']
    before = service.load(sid)['supervised']
    doc = dict(contract_version=CONTRACT, request=context['request'], model=MODEL, mode='cpu_fixture',
               observations=[observation(context, 10, 'supported'), observation(context, 20, 'unverifiable')], provenance={})
    destination = tmp_path / 'inbox' / 'final-visual' / f'{sid}.json'
    stale = {**doc, 'request': {**doc['request'], 'ranking_sha256': first['ranking_sha256']}}
    dq.base.sessions.atomic(destination, stale)
    dq.call(client, private, code=409)
    dq.base.sessions.atomic(destination, {**doc, 'ground_truth': {'candidate_id': 'c012'}})
    dq.call(client, private, code=409)
    assert dq.get(client, sid) == terminal
    dq.base.sessions.atomic(destination, doc)
    assert dq.call(client, private)['applied']
    assert not dq.call(client, private)['applied']
    fresh_app, fresh_service = dq.base.fixture_app(tmp_path)
    after = fresh_service.load(sid)['supervised']
    assert after['artifacts'] == before['artifacts'] and after['reserve_geometry'] == before['reserve_geometry']
    result = after['final_visual']
    assert {r['candidate_id'] for r in result['combined_ranking']} == {f'c{i:03}' for i in range(1, 254)}
    assert result['combined_ranking'][50:] == before['final_visual']['combined_ranking'][50:]
    latest = dq.get(dq.base.client_for(fresh_app), sid)['stage_snapshots'][-1]
    assert latest['results'] == result['baseline_results']
    applied = latest['visual_postprocessing']
    assert 'c012' in {r['candidate_id'] for r in applied['final_results']}
    assert 'c012' not in {r['candidate_id'] for r in latest['results']}
    decisions = {r['candidate_id']: r for r in applied['evidence']}
    assert decisions['c012']['visual_score'] == 1
    assert decisions['c022']['abstention'] == 'no_verifiable_observation'
    assert decisions['c002']['abstention'] == 'no_mapillary_evidence'
    assert decisions['c022']['visual_score'] is decisions['c002']['visual_score'] is None


@pytest.mark.parametrize('depth', [10, 50, 100])
def test_standalone_ct2l_visual_exact_fallback(depth):
    ranking = dq.base.CT2LPort().retrieve(stage='E0', query_id='fixture', text='Veo una torre.')['retrievals'][0]
    desc = 'Veo una torre.'
    request = visual_request(ranking=ranking, description=desc, depth=depth)
    context = {'request': request, 'description': desc}
    evidence = dict(contract_version=CONTRACT, request=request, model=MODEL, mode='cpu_fixture', provenance={},
                    observations=[observation(context, 2, 'unverifiable')])
    out = final_visual_ranking(ranking=ranking, description=desc, depth=depth, mode='cpu_fixture', evidence=evidence)
    assert len(request['candidate_ids']) == depth
    assert out['combined_ranking'] == ranking['results'] and out['final_results'] == ranking['results'][:10]
    assert all(row['visual_score'] is None for row in out['evidence'])


def test_v4_bridge_verifies_existing_runner_contract(tmp_path):
    ranking = dq.base.CT2LPort().retrieve(stage='E0', query_id='fixture', text='Veo una torre.')['retrievals'][0]
    desc = 'Veo una torre.'
    context = {'description': desc, 'request': visual_request(ranking=ranking, description=desc)}
    obs = observation(context, 10, 'supported')
    associations = [dict(provider='mapillary', candidate_id=obs['candidate_id'], image_id=obs['image_id'], image_sha256=obs['image_sha256']),
                    dict(provider='mapillary', candidate_id='c051', image_id='outside-top50')]
    fixture = prepare_v4(context, associations)
    assert len(fixture['associations']) == 1 and not fixture['associations'][0]['orientation_comparable']
    def save(name, value):
        path = tmp_path / name
        path.write_text(json.dumps(value))
        return path, sha256(path.read_bytes()).hexdigest()
    fixture_path, fsha = save('fixture', fixture)
    assets_path, asha = save('assets', {'assets': [dict(image_id=obs['image_id'], sha256=obs['image_sha256'], status='reused')]})
    claim = obs.pop('claim')
    review_path, rsha = save('review', dict(fixture_id=fixture['fixture_id'], review_status='complete',
        records=[dict(claim=c, decision='approved' if c == claim else 'rejected') for c in fixture['claims']['claims']]))
    run = dict(contract_version='visual-fixture-run-v4', fixture_id=fixture['fixture_id'], model=dict(MODEL,
        files={str(i): {'sha256': value} for i, value in enumerate(SUPPORTED_LOCAL_MODELS['qwen3-vl-8b']['weight_sha256'])}),
        generation={'contract': 'verdict_only_v4', 'do_sample': False},
        inputs=dict(fixture_sha256=fsha, asset_manifest_sha256=asha, reviewed_claims_sha256=rsha),
        protocol={k: False for k in ('ground_truth_used', 'baseline_rank_sent_to_vlm', 'scores_sent_to_vlm', 'coordinates_sent_to_vlm', 'reranking_performed')},
        approved_claims=[claim], records=[dict(obs, claim_id=claim['claim_id'], raw_output='{"verdict":"supported"}')])
    run_path, _ = save('run', run)
    kwargs = dict(fixture_path=fixture_path, assets_path=assets_path, review_path=review_path, run_path=run_path)
    payload = evidence_from_v4(context, **kwargs)
    assert payload['observations'][0]['verdict'] == 'supported'  # JSON fabricado del contrato real, no inferencia.
    run['records'][0]['raw_output'] = '{"verdict":"unverifiable"}'
    save('run', run)
    with pytest.raises(ValueError, match='veredicto'):
        evidence_from_v4(context, **kwargs)


def test_d112_associations_retain_geometry_and_ignore_rejected_candidates():
    primary = {'image_id': '123', 'image_sha256': 'a' * 64}
    geometry = {'classification': 'camera_outside_view_compatible', 'surface_distance_m': 7.5}
    accepted = dict(primary, eligible=True, geometry=geometry)
    d112 = dict(contract_version='mapillary-evidence-selector-v2-result-v1', protocol={'ground_truth_used': False},
                records=[dict(candidate_id='c012', status='selected', primary=primary, considered=[accepted]),
                         dict(candidate_id='c013', status='insufficient_visual_evidence', primary=None)])
    d112['selector_run_id'] = 'mapillary-selector-v2-sha256-' + digest(d112)
    rows = associations_from_d112(d112)
    assert len(rows) == 1 and rows[0]['provider'] == 'mapillary' and rows[0]['geometry'] == geometry
    d112['protocol']['ground_truth_used'] = True
    with pytest.raises(ValueError, match='incompatible'):
        associations_from_d112(d112)
