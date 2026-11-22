"""DQ52: fixtures CPU de operadores, workers, postflight y fotos, no resultados reales."""
from copy import deepcopy
from io import BytesIO
from hashlib import sha256
import os
from uuid import uuid4

from PIL import Image
import pytest

from research.dq_pilot_supervised_visual_v1 import (
    PANEL_CONTRACT, QUESTION_CHECKS, TRANSLATION_PROMPT, ContractError, digest, digest_text,
    file_digest, from_visual_postflight, native_bytes,
)
from scripts.prepare_dq_pilot52_visual import materialize_native
from tests import test_dq_pilot46_supervised_sessions as base


DECLARATION = 'Declaración ficticia CPU, no corresponde a una revisión humana real.'
AUTHOR = 'Identidad de prueba CPU'
fixture_es = lambda index: f'¿Se ve el rasgo de prueba número {index+1}?'


def call(client, url, *, data=None, code=200, method='POST', **kwargs):
    response = client.request(method, url, json=data, **kwargs)
    assert response.status_code == code, response.text
    return response.json()


def start(tmp, value=None, *, dq_policy='e'*64):
    app, service = base.fixture_app(tmp)
    client = base.client_for(app)
    sid, registration = base.prepare(client, tmp, value or f'dq-iterative-{uuid4()}')
    registration.update(dq_pilot=dict(configuration_sha256='d'*64, policy_sha256=dq_policy),
                        qwen_translation=dict(configuration_sha256='f'*64, policy_sha256='9'*64))
    base.sessions.atomic(tmp/'inbox'/'registrations'/f'{sid}.json', registration)
    base.register(client, sid)
    return client, service, sid


def public(sid):
    return f'{base.PUBLIC}/sessions/{sid}'


def private(sid):
    return f'{base.PRIVATE}/{sid}'


def get(client, sid):
    return call(client, public(sid), method='GET')


def consume(client, tmp, sid, terminal, *, code=200):
    base.publish(tmp, terminal)
    return call(client, private(sid)+'/terminals/'+terminal['operation_id'], code=code)


def retrieve(client, tmp, sid, stage):
    qwen = base.expected(client,sid)
    assert (qwen['stage'],qwen['component']) == (stage,'qwen')
    consume(client,tmp,sid,base.qwen_terminal(qwen))
    ct = base.expected(client,sid)
    assert (ct['stage'],ct['component']) == (stage,'crosstext2loc')
    assert ct['input']['accumulated_description_sha256'] == qwen['input']['accumulated_description_sha256']
    consume(client,tmp,sid,base.ct2l_terminal(ct))
    return get(client,sid)


def panel_for(context, tmp):
    stage = context['stage']
    candidates, images = [], []
    folder = tmp/'inbox'/'visual-media'
    folder.mkdir(parents=True,exist_ok=True)
    for index,row in enumerate(context['reserve']['results'][:4],1):
        cid, rank, iid = row['candidate_id'], row['rank'], f'123{stage[1]}{index}'
        buffer = BytesIO()
        Image.new('RGB',(10,10),(30*index,50*int(stage[1]),30)).save(buffer,format='JPEG')
        photo = buffer.getvalue()
        sha = file_digest(photo)
        (folder/f'{sha}.jpg').write_bytes(photo)
        candidates.append(dict(candidate_ref=f'C{index}',candidate_id=cid, source_rank=rank))
        images.append(dict(candidate_ref=f'C{index}',image_ref=f'I{index}',image_id=iid,size_bytes=len(photo),sha256=sha,
            association=dict(candidate_id=cid,candidate_rank=rank,image_id=iid,within_round=True)))
    panel = dict(contract_version='dq-pilot13-mapillary-panel-v1', status='prepared_pending_review', review_required=True,
        round_index=int(stage[1:]), source_ranking_sha256=context['ranking_sha256'], ground_truth_used=False,
        candidate_ids=[r['candidate_id'] for r in candidates], candidates=candidates, images=images)
    return dict(contract_version=PANEL_CONTRACT,panel=panel,panel_sha256=digest(panel),
        **{k:context[k] for k in ('mode','session_id','stage','ranking_sha256','reserve_sha256','ct2l_terminal_sha256','accumulated_description_sha256')},
        processor_expectation=dict(profile='fixture-cpu',preprocessing='rgb-convert-no-exif-transpose',image_order=['I1','I2','I3','I4'],
            input_tokens=101,pixel_values_shape=[16,1176],image_grid_thw=[[1,2,2]]*4))


def receive_panel(client,tmp,sid,stage,*,envelope=None,code=200):
    context = call(client,private(sid)+'/visual-context',method='GET')
    envelope = envelope if envelope is not None else panel_for(context,tmp)
    assert stage == context['stage']
    path = tmp/'inbox'/'panels'/f'{sid}-{stage}.json'
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(native_bytes(envelope))
    return call(client,private(sid)+'/panels/'+stage,code=code)


def review_body(**info):
    return dict(approved=True,client_operation_id=str(uuid4()),review=dict(ground_truth_used=False,reviewer_declaration=DECLARATION,**info))


def panel_review(client,sid):
    row=get(client,sid)['visual_review']
    return call(client,public(sid)+'/panel-reviews',data=review_body(panel_sha256=row['panel_sha256'],source_ranking_sha256=row['ranking_sha256']))


def question_review(client,sid):
    row=get(client,sid)['visual_review']
    return call(client,public(sid)+'/question-reviews',data=review_body(**{k:row[k] for k in ('generation_sha256','panel_sha256','image_sha256s')}, checks={k:True for k in QUESTION_CHECKS}))


def test_translation_prompt_uses_the_documented_dq25_contract():
    assert sha256(TRANSLATION_PROMPT.encode()).hexdigest() == '92932151922ae229ed4631e1f432b1313064afa75720edd676ae87e9d216064f'


def visual_postflight_fixture(expected, status='SUCCEEDED'):
    inp, component = expected['input'], expected['component']
    stage = int(expected['stage'][1:])
    postflight = dict(contract_version='atlas-dq-visual-postflight-v1',policy_sha256=expected['policy_sha256'],
        resource_release_verified=True,policy_compliant=status=='SUCCEEDED',cuda_pids=[],worker_close_verified=True,
        exclusive_lease_verified=True,lease_operation_sha256=digest(expected),
        stop_reason='psi-fixture' if status=='STOPPED_MEMORY' else None,timed_out=status=='TIMED_OUT',
        process=dict(execution_id='fixture-only',terminated=True,running=False,restarting=False,pid=0,
            exit_code=0 if status=='SUCCEEDED' else 1,oom_killed=False))
    raw = output = worker_release = None
    if status == 'SUCCEEDED' and component == 'dq_pilot':
        worker_release = native_bytes(dict(contract_version='dq-pilot14-release-v1',reason='one_shot_complete',runtime_state='CLOSED',
            exit_required=False,cuda_allocated_after_release_bytes=0,cuda_reserved_after_release_bytes=0))
        result = dict(schema_version='1.0',contract_version='dq-pilot14-public-generation-v1',status='generated',
            request_id=inp['request']['request_id'],request_sha256=inp['request_sha256'],panel_sha256=inp['panel_sha256'],
            source_ranking_sha256=inp['ranking_sha256'],question=f'Is test feature number {stage+1} visible?',
            raw_output_sha256='1'*64,private_output_retained=True,private_output_sha256='2'*64,raw_commit_sha256='3'*64,
            host_decision_sha256='4'*64,reasoning_public=False,ground_truth_used=False,
            host_validation=dict(format=True,text_safety=True,exact_redundancy=True),telemetry_sha256='5'*64,
            release_sha256=file_digest(worker_release))
        output = native_bytes(result)
        raw = native_bytes(dict(contract_version='dq-pilot-generation-terminal-commit-v1',status='PUBLISHED',
            automatic_retry_permitted=False,request_sha256=inp['request_sha256'],refs=dict(projection_sha256=file_digest(output),
                **{k:result[k] for k in ('raw_output_sha256','raw_commit_sha256','host_decision_sha256')})))
    elif status == 'SUCCEEDED':
        worker_release = native_bytes(dict(operation_sha256=digest(expected),allocated_bytes=0,reserved_bytes=0))
        output = native_bytes(dict(schema_version='1.0', contract_version='dq-pilot-translation-result-v1',
            status='translated_pending_human_review', round_index=stage, source_language='en',target_language='es',
            source_question=inp['source_question'],source_question_sha256=inp['source_question_sha256'],
            translated_question=fixture_es(stage),translated_question_sha256=digest_text(fixture_es(stage)),translator=inp['translator'],
            semantic_repair_performed=False,automatic_retries=0,fallback_used=False,network_used=False,
            validation=dict(structural='passed',semantic='pending_human_review',source_question_preserved=True,human_review_required=True)))
    commit=dict(**{k:expected[k] for k in ('session_id','operation_id','configuration_sha256')},operation_sha256=digest(expected),
        status=status,postflight_sha256=digest(postflight),result_sha256=file_digest(output) if output else None,
        worker_release_sha256=file_digest(worker_release) if worker_release else None,native_commit_sha256=file_digest(raw) if raw else None)
    return dict(commit=commit,postflight=postflight,output_bytes=output,native_commit_bytes=raw,worker_release_bytes=worker_release)


def visual_terminal(expected,status='SUCCEEDED'):
    return from_visual_postflight(expected,**visual_postflight_fixture(expected,status))


def manual(client,sid,stage):
    row=get(client,sid)['visual_review']
    return call(client,public(sid)+'/visual-translation',data=dict(client_operation_id=str(uuid4()),author=AUTHOR,
        translated_question_es=fixture_es(int(stage[1:])),source_question_sha256=row['source_question_sha256'],generation_sha256=row['generation_sha256']))


def translation_review(client,sid,*,decision='accept_for_this_technical_pilot',code=200,body=None):
    if body is None:
        row=get(client,sid)['pending_translation_review']
        body=review_body(**{k:row[k] for k in ('translation_sha256','source_question_sha256','translated_question_sha256')})
        body.pop('approved')
        body['decision']=decision
    return call(client,public(sid)+'/pilot-translation-decisions',data=body,code=code)


def answer_body(q,literal):
    return dict(schema_version='1.0',contract_version='atlas-dialogue-freetext-answer-request-v2',
        **{k:q[k] for k in ('question_id','question_sha256','turn_index')},answer_literal=literal,
        human_attested=True,external_context_used=False,client_operation_id=f'dq-iterative-answer-{uuid4()}',user_requests_stop=False)


def answer(client,sid,body,code=200):
    return call(client,public(sid)+'/answers',data=body,headers={'Idempotency-Key':body['client_operation_id']},code=code)


@pytest.mark.parametrize('only_supervised_translation', [False, True])
def test_full_supervised_loop_e0_e3(tmp_path, only_supervised_translation):
    client,service,sid=start(tmp_path)
    previous=None
    for index in range(4):
        stage=f'E{index}'
        snap=retrieve(client,tmp_path,sid,stage)
        rank=snap['stage_snapshots'][-1]
        assert rank['candidate_count']==253 and rank['results'][0]['candidate_id']==f'c{index+1:03d}'
        assert snap['description_es']==base.DESCRIPTION
        if index==3:
            assert snap['status']=='completed' and snap['stop_reason']=='max_questions_reached_after_e3'
            assert snap['current_question'] is None and len(snap['turns'])==3 and 'visual_evidence' not in snap
            call(client,private(sid)+'/panels/E3',code=409)
            call(client,private(sid)+'/expected',method='GET',code=409)
            break
        assert snap['waiting_supervised_panel']
        if previous:
            call(client,private(sid)+'/terminals/'+previous['operation_id'],code=409)
            call(client,private(sid)+f'/panels/E{index-1}',code=409)
        received=receive_panel(client,tmp_path,sid,stage)
        assert received['session']['controller_state']=='AWAITING_PANEL_REVIEW'
        assert call(client,private(sid)+'/panels/'+stage)['applied'] is False
        for photo in received['session']['visual_evidence']:
            media=client.get('/api/v1'+photo['media_path'])
            assert media.status_code==200 and file_digest(media.content)==photo['sha256']
        panel_review(client,sid)
        expected=base.expected(client,sid)
        assert expected['model_revision']=='cf5c7b8a79ce055a83706fcbe0b94edf31b1cb40'
        assert expected['input']['ranking_sha256']==rank['ranking_sha256']
        request=expected['input']['request']
        assert request['history']['turn_count']==index and all(v is False for v in request['constraints'].values())
        assert all(set(row)=={'candidate_ref','image_ref','logical_path','sha256','size_bytes'} for row in request['images'])
        assert materialize_native(expected,media=tmp_path/'inbox'/'visual-media',output=tmp_path/f'native-{stage}').is_file()
        previous=visual_terminal(expected)
        generated=consume(client,tmp_path,sid,previous)['session']
        assert consume(client,tmp_path,sid,previous)['applied'] is False
        assert generated['current_question'] is None and generated['visual_review']['question_provenance']=='cpu_fixture'
        qrev=question_review(client,sid)
        assert qrev['controller_state']=='AWAITING_TRANSLATION' and qrev['pending_translation_review'] is None
        if only_supervised_translation or index==1:
            sha=qrev['visual_review']['source_question_sha256']
            path=private(sid)+f'/translation-operations/{stage}/{sha}'
            assert call(client,path)['applied'] and not call(client,path)['applied']
            operation=base.expected(client,sid)
            assert operation['component']=='qwen_translation' and operation['input']['dq_terminal_sha256']==digest(previous)
            review=consume(client,tmp_path,sid,visual_terminal(operation))['session']
            assert review['pending_translation_review']['translator']['translator_id']=='Fixture CPU (no Qwen)'
        else:
            review=manual(client,sid,stage)
            assert review['pending_translation_review']['translator']['author']==AUTHOR
        assert review['current_question'] is None and not review['pending_translation_review']['formal_translation_validated']
        if index==0:
            client=base.client_for(base.fixture_app(tmp_path)[0])
            assert get(client,sid)==review
        active=translation_review(client,sid)
        reply=answer_body(active['current_question'],f"Respuesta fixture en español: {('reloj','arco','torre')[index]}.")
        updated=answer(client,sid,reply)
        assert answer(client,sid,reply)==updated
        assert not updated.get('visual_evidence') and updated['accumulated_description_es'].endswith(reply['answer_literal'])
        assert active['current_question']['question_id'] != active['current_question']['question_sha256']
    result=get(client,sid)
    assert [r['stage'] for r in result['stage_snapshots']]==['E0','E1','E2','E3']
    stream=client.get(public(sid)+'/events/stream').text
    assert stream.count('Pregunta EN y liberación verificadas.')==3 and 'Ranking final disponible.' in stream
    assert len(service.load(sid)['supervised']['visual']) == 3


@pytest.mark.parametrize('status',['STOPPED_MEMORY','TIMED_OUT','FAILED'])
def test_dq_failure_is_terminal_without_question(tmp_path,status):
    client,_,sid=start(tmp_path)
    retrieve(client,tmp_path,sid,'E0');receive_panel(client,tmp_path,sid,'E0');panel_review(client,sid)
    operation=base.expected(client,sid)
    stopped=consume(client,tmp_path,sid,visual_terminal(operation,status))['session']
    assert stopped['status']=='failed' and stopped['stop_reason']==f'supervised_dq_pilot_{status.lower()}'
    assert stopped['current_question'] is stopped['pending_translation_review'] is None
    assert 'original_en' not in stopped['visual_review'] and len(stopped['stage_snapshots'])==1
    call(client,private(sid)+'/expected',method='GET',code=409)


def test_reject_crossed_panel_photo_operation_and_postflight(tmp_path):
    client,_,sid=start(tmp_path)
    retrieve(client,tmp_path,sid,'E0')
    context=call(client,private(sid)+'/visual-context',method='GET')
    valid=panel_for(context,tmp_path)
    for changes in ('session','association','media','reserve'):
        bad=deepcopy(valid)
        if changes=='session': bad['session_id']='other'
        if changes=='association': bad['panel']['images'][0]['association']['candidate_id']='c253'
        if changes=='media': bad['panel']['images'][0]['sha256']='9'*64
        if changes=='reserve': bad['reserve_sha256']='8'*64
        bad['panel_sha256']=digest(bad['panel'])
        receive_panel(client,tmp_path,sid,'E0',envelope=bad,code=409)
    receive_panel(client,tmp_path,sid,'E0',envelope=valid);panel_review(client,sid)
    operation=base.expected(client,sid)
    terminal=visual_terminal(operation)
    for key,replacement in [('session_id','other'),('mode','real'),('input_sha256','0'*64),('model_revision','other'),('visual_safety',None)]:
        consume(client,tmp_path,sid,{**terminal,key:replacement},code=409)
    consume(client,tmp_path,sid,{**terminal,'release':{**terminal['release'],'verified':False}},code=409)
    with pytest.raises(ContractError):
        fixture=visual_postflight_fixture(operation)
        fixture['postflight']['stop_reason']='psi'
        fixture['commit']['postflight_sha256']=digest(fixture['postflight'])
        from_visual_postflight(operation,**fixture)
    assert get(client,sid)['controller_state']=='DQ_SUPERVISED_PENDING'
    consume(client,tmp_path,sid,terminal)
    assert get(client,sid)['controller_state']=='AWAITING_QUESTION_REVIEW'


@pytest.mark.skipif(os.environ.get('ATLAS_TEST_EXTERNAL_STAGELEASE') != '1', reason='requiere StageLease externo autorizado')
def test_exclusive_lease_survives_restart_and_requires_release(tmp_path):
    from research.dq_pilot_stage_lease_v1 import StageLease

    root=tmp_path/'permits'
    a=dict(session_id='one-fixture',operation_id=str(uuid4()))
    b=dict(session_id='two-fixture',operation_id=str(uuid4()))
    lease=StageLease(root).claim(a,authorization_sha256='a'*64)
    resumed=StageLease(root)
    with pytest.raises(ContractError,match='ocupado'):
        resumed.claim(b,authorization_sha256='b'*64)
    postflight=dict(lease_operation_sha256=digest(a),exclusive_lease_verified=True,resource_release_verified=True,
        worker_close_verified=True,cuda_pids=[],process=dict(execution_id='fixture-pid',terminated=True,running=False,restarting=False,pid=0))
    with pytest.raises(ContractError,match='otra operación'):
        resumed.release(b,lease=lease,postflight=postflight)
    with pytest.raises(ContractError,match='no acreditada'):
        resumed.release(a,lease=lease,postflight={**postflight,'cuda_pids':[1]})
    resumed.release(a,lease=lease,postflight=postflight)
    with pytest.raises(ContractError,match='consumido'):
        resumed.claim(a,authorization_sha256='c'*64)
    assert resumed.claim(b,authorization_sha256='b'*64)['operation_sha256']==digest(b)
