#!/usr/bin/env python3
"""Runtime por fases reanudables para DialogueVPR v3."""
from __future__ import annotations
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
from jsonschema import Draft202012Validator

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.run_dialogue_v3_visual_worker_smoke import STABLE_SWAP_INTERVAL_SECONDS,STABLE_SWAP_SAMPLES,collect_stable_swap_samples,evaluate_memory_gate,run_supervised
from scripts.run_interactive_dialogue import load_multiturn_policy
from scripts.run_qwen3_vl_8b_memory_smoke import atomic_write_json,compute_processes,utc_now
from src.tfg_phase0.dialogue_phased_runtime import PhasedRunStore,PhasedRuntimeError,ReplayRetriever,RunLock,status_document
from src.tfg_phase0.ct2l_isolated_environment import CT2LEnvironmentError,validate_ct2l_environment
from src.tfg_phase0.dialogue_visual_evidence import RealQwen3VLDialogueEvidenceProvider,VisualEvidencePolicy,load_observer_image_manifest
from src.tfg_phase0.interactive_dialogue import F3EvidenceIndex
from src.tfg_phase0.interactive_dialogue_multiturn import MultiTurnDialogueOrchestrator,RetrievalDeferred,multiturn_session_id,validate_multiturn_session
from src.tfg_phase0.interactive_dialogue_visual import VisualMultiTurnConfig,VisualMultiTurnDialogueOrchestrator,validate_visual_session

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def runtime_args(config):
    class Args:pass
    value=Args();value.f3_bundle=ROOT/config['f3_bundle'];value.cvg_utils_sha256=config['cvg_utils_sha256'];value.clip_weights=Path(config['clip_weights']);value.ct2l_config=ROOT/config['ct2l_config'];value.qwen_model_dir=None;return value

class DeferredRetriever:
    def __init__(self,metadata,gallery):self._metadata=metadata;self.gallery_id=gallery
    @property
    def metadata(self):return self._metadata
    def count_tokens(self,text):return None
    def retrieve_full(self,**kwargs):raise RetrievalDeferred('retrieval aislado requerido')

class NoopVisualProvider:
    def __init__(self,reference,manifest,metadata=None):self.reference=reference;self.manifest=manifest;self._metadata=metadata
    @property
    def metadata(self):return self._metadata or {'adapter':'qwen3-vl-dialogue-worker-v2','model_id':'Qwen/Qwen3-VL-8B-Instruct','revision':'0c351dd01ed87e9c1b53cbc748cba10e6187ff3b','real_model_inference':True,'runtime_status':'phased_pending','calls':[]}
    def has_image_for(self,feature):return feature==self.manifest['intent_family']
    def image_for(self,feature):return self.reference
    def inspect(self,request):raise PhasedRuntimeError('fase visual no ejecutada')

def visual_engine(store,provider):
    config=store.configuration();gallery,multi=load_multiturn_policy(ROOT/config['dialogue_policy'],config['max_questions']);evidence=F3EvidenceIndex.load_bundle(ROOT/config['f3_bundle']);checkpoint=store.load_checkpoint(store.load_state()['retrieval_checkpoint']);retriever=DeferredRetriever(checkpoint['session_v2']['models']['retrieval'],gallery);return VisualMultiTurnDialogueOrchestrator(retriever=retriever,evidence=evidence,config=VisualMultiTurnConfig(multi,VisualEvidencePolicy(enabled=True,maximum_calls=1)),text_adapter=None,visual_provider=provider)

def prepare(args):
    config=json.loads(args.config.read_text());schema=json.loads((ROOT/'schemas/dialogue_v3_real_session_preparation.schema.json').read_text());Draft202012Validator(schema).validate(config);gallery,multi=load_multiturn_policy(ROOT/config['dialogue_policy'],config['max_questions']);expected=multiturn_session_id(session_label=config['session_label'],description=config['initial_description'],language=config['language'],gallery_id=gallery,config=multi)
    if expected!=config['session_id']:raise PhasedRuntimeError('session_id congelado divergente')
    manifest,_=load_observer_image_manifest(ROOT/config['observer_manifest'],ROOT/'schemas/dialogue_observer_image_manifest.schema.json')
    if manifest['session_id']!=expected or manifest['intent_family']!=config['intent_family']:raise PhasedRuntimeError('manifest visual incompatible')
    store=PhasedRunStore.prepare(args.run_root,config);print(json.dumps(status_document(store)));return 0
def retrieve(args):
    store=PhasedRunStore(args.run_root)
    with RunLock(store.root):
        state=store.load_state();config=store.configuration();authorization=json.loads(args.authorization.read_text())
        required={"schema_version","contract_version","status","session_id","authorized_actions","stable_swap_required","automatic_retries","authorization_source"}
        if set(authorization)!=required or authorization["contract_version"]!="dialogue-v3-phased-ct2l-gpu-authorization-v1" or authorization["status"]!="OPERATOR_AUTHORIZED" or authorization["session_id"]!=config["session_id"] or "isolated CT2L retrieval on NVIDIA GB10" not in authorization["authorized_actions"] or authorization["stable_swap_required"] is not True or authorization["automatic_retries"]!=0:raise PhasedRuntimeError("autorización CT2L GPU ausente o incompatible")
        if state['phase'] not in {'prepared','retrieved'} or (state['phase']=='retrieved' and not state['pending_answer']):raise PhasedRuntimeError('retrieval no requerida o intento previo no reintentable')
        environment=validate_ct2l_environment(ROOT/config['ct2l_isolated_runtime'],ROOT,session_config=store.root/'configuration.json');ollama=subprocess.run(['ollama','ps'],capture_output=True,text=True,timeout=10);ollama_status='no_model_resident' if ollama.returncode==0 and len(ollama.stdout.splitlines())<=1 else 'model_resident_or_unverified';samples=collect_stable_swap_samples(count=STABLE_SWAP_SAMPLES,interval_seconds=STABLE_SWAP_INTERVAL_SECONDS);gate=evaluate_memory_gate(policy='stable-swap',host_compute_process_count=len(compute_processes()),host_ollama_status=ollama_status,samples=samples)
        if not gate['passed']:raise PhasedRuntimeError('stable-swap-v1 bloquea CT2L: '+','.join(gate['blocking_reasons']))
        answer=state['pending_answer']['literal'] if state['pending_answer'] else None;store.transition(expected={state['phase']},phase='retrieval_reserved',next_action='review');attempt_root=store.root/'attempts'/f'retrieval-{state["generation"]+1:03d}';attempt_root.mkdir();atomic_write_json(attempt_root/'preflight.json',{'schema_version':'1.0','contract_version':'dialogue-v3-phased-ct2l-preflight-v1','memory_policy':'stable-swap-v1','ollama':ollama_status,'gate':gate,'samples':samples,'environment':environment,'environment_manifest_sha256':digest(ROOT/config['ct2l_isolated_runtime']),'authorization_sha256':digest(args.authorization)});child=attempt_root/'result.json';python_entrypoint=environment['python_entrypoint'];command=args.child_command or [python_entrypoint,str(ROOT/'scripts/run_ct2l_isolated_child.py'),'--run-root',str(store.root),'--output',str(child),*(['--answer',answer] if answer else [])];result=run_supervised(command,args.timeout,attempt_root)
        if result['timed_out'] or (result['returncode']==0 and not child.is_file()):store.transition(expected={'retrieval_reserved'},phase='retrieval_uncertain',next_action='review');return 2
        if result['returncode']:store.transition(expected={'retrieval_reserved'},phase='retrieval_failed',next_action='review');return 2
        if compute_processes():store.transition(expected={'retrieval_reserved'},phase='retrieval_uncertain',next_action='review');return 2
        document=json.loads(child.read_text());document['contract_version']='dialogue-v3-retrieval-checkpoint-v1';document['checkpoint_id']='';document['configuration_sha256']=store.load_state()['configuration_sha256'];relative,checkpoint=store.checkpoint(document);store.transition(expected={'retrieval_reserved'},phase='retrieved',next_action='resume',retrieval_checkpoint=relative,pending_answer=None);print(json.dumps(status_document(store)));return 0
def resume(args):
    store=PhasedRunStore(args.run_root)
    with RunLock(store.root):
        state=store.load_state();config=store.configuration()
        if args.answer is not None:
            if state['phase']!='awaiting_answer':raise PhasedRuntimeError('sesión no espera respuesta')
            previous=store.load_snapshot(state['session_snapshot']);manifest,reference=load_observer_image_manifest(ROOT/config['observer_manifest'],ROOT/'schemas/dialogue_observer_image_manifest.schema.json');provider=NoopVisualProvider(reference,manifest,metadata=previous['models']['vlm'].get('provider'));engine=visual_engine(store,provider)
            from src.tfg_phase0.interactive_dialogue_visual import _as_v2
            try:base_result=engine._base.answer(_as_v2(previous),args.answer);result=engine.from_base_answer_result(previous,base_result,inspect_pending=False)
            except RetrievalDeferred:store.transition(expected={'awaiting_answer'},phase='retrieved',next_action='retrieve',pending_answer={'literal':args.answer,'sha256':hashlib.sha256(args.answer.encode()).hexdigest(),'turn_index':previous['turns'][-1]['index']});return 0
            snapshot=store.snapshot(result);phase='completed' if result['status']=='completed' else 'awaiting_visual';store.transition(expected={'awaiting_answer'},phase=phase,next_action='none' if phase=='completed' else 'visual',session_snapshot=snapshot);return 0
        if state['phase']!='retrieved':raise PhasedRuntimeError('no hay recuperación pendiente de reanudación')
        checkpoint=store.load_checkpoint(state['retrieval_checkpoint']);manifest,reference=load_observer_image_manifest(ROOT/config['observer_manifest'],ROOT/'schemas/dialogue_observer_image_manifest.schema.json');previous=store.load_snapshot(state['session_snapshot']) if state['session_snapshot'] else None;provider=NoopVisualProvider(reference,manifest,metadata=previous['models']['vlm'].get('provider') if previous else None);engine=visual_engine(store,provider)
        if checkpoint['session_v2']['session_id']!=config['session_id']:raise PhasedRuntimeError('sesión CT2L incompatible')
        session=engine.from_base_session(checkpoint['session_v2']) if previous is None else engine.from_base_answer_result(previous,checkpoint['session_v2'])
        snapshot=store.snapshot(session);feature=session['turns'][-1]['question']['feature'] if session['status']=='awaiting_answer' else None;phase='awaiting_visual' if feature==config['intent_family'] and not session['visual_evidence'] else 'awaiting_answer' if session['status']=='awaiting_answer' else 'completed';next_action='visual' if phase=='awaiting_visual' else 'answer' if phase=='awaiting_answer' else 'none';store.transition(expected={'retrieved'},phase=phase,next_action=next_action,session_snapshot=snapshot);print(json.dumps(status_document(store)));return 0
def visual(args):
    store=PhasedRunStore(args.run_root)
    with RunLock(store.root):
        state=store.load_state()
        if state['phase']!='awaiting_visual' or state['visual_attempt'] is not None:raise PhasedRuntimeError('presupuesto visual no disponible')
        if not args.authorize_gpu:raise PhasedRuntimeError('fase visual requiere autorización GPU explícita')
        attempt={'attempt_id':'visual-attempt-'+hashlib.sha256((state['session_id']+str(state['generation'])).encode()).hexdigest(),'status':'reserved','authorized':args.authorize_gpu,'reserved_at_utc':utc_now()};store.transition(expected={'awaiting_visual'},phase='visual_reserved',next_action='review',visual_attempt=attempt)
        # La llamada real se habilita solo mediante una autorización explícita en este subcomando.
        config=store.configuration();manifest,reference=load_observer_image_manifest(ROOT/config['observer_manifest'],ROOT/'schemas/dialogue_observer_image_manifest.schema.json');from scripts.run_dialogue_visual_worker import ExternalQwen3VLWorkerExecutor
        executor=ExternalQwen3VLWorkerExecutor(output_root=Path(config['visual_worker_output']),model_dir=Path(config['visual_model_dir']),docker_image=config['visual_docker_image'])
        class TrackingExecutor:
            invoked=False;failed=False
            def __call__(self,request,reference):
                self.invoked=True
                try:return executor(request,reference)
                except Exception:self.failed=True;raise
        tracking=TrackingExecutor();provider=RealQwen3VLDialogueEvidenceProvider(manifest=manifest,reference=reference,executor=tracking);engine=visual_engine(store,provider)
        try:session=engine.inspect_pending(store.load_snapshot(store.load_state()['session_snapshot']))
        except Exception:
            attempt={**attempt,'status':'uncertain'};store.transition(expected={'visual_reserved'},phase='visual_uncertain',next_action='review',visual_attempt=attempt);raise
        snapshot=store.snapshot(session)
        if tracking.failed:attempt={**attempt,'status':'failed','completed_at_utc':utc_now()};store.transition(expected={'visual_reserved'},phase='visual_failed',next_action='review',visual_attempt=attempt,session_snapshot=snapshot);return 2
        attempt={**attempt,'status':'completed','completed_at_utc':utc_now()};store.transition(expected={'visual_reserved'},phase='awaiting_answer',next_action='answer',visual_attempt=attempt,session_snapshot=snapshot);return 0
def status(args):print(json.dumps(status_document(PhasedRunStore(args.run_root)),ensure_ascii=False,sort_keys=True));return 0
def fork_recovery(args):
    store,created=PhasedRunStore.fork_recovery(args.source_run,args.target_run,args.reason);document=status_document(store);document['fork_created']=created;document['lineage']='lineage.json';print(json.dumps(document,ensure_ascii=False,sort_keys=True));return 0

def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
    q=sub.add_parser('prepare');q.add_argument('--config',type=Path,required=True);q.add_argument('--run-root',type=Path,required=True);q.set_defaults(func=prepare)
    q=sub.add_parser('retrieve');q.add_argument('--run-root',type=Path,required=True);q.add_argument('--authorization',type=Path,required=True,help='Autorización GPU específica e inmutable para esta fase CT2L.');q.add_argument('--timeout',type=int,default=240);q.set_defaults(func=retrieve,child_command=None)
    q=sub.add_parser('resume');q.add_argument('--run-root',type=Path,required=True);q.add_argument('--answer');q.set_defaults(func=resume)
    q=sub.add_parser('visual');q.add_argument('--run-root',type=Path,required=True);q.add_argument('--authorize-gpu',action='store_true');q.set_defaults(func=visual)
    q=sub.add_parser('status');q.add_argument('--run-root',type=Path,required=True);q.set_defaults(func=status)
    q=sub.add_parser('fork-recovery');q.add_argument('--source-run',type=Path,required=True);q.add_argument('--target-run',type=Path,required=True);q.add_argument('--reason',required=True);q.set_defaults(func=fork_recovery)
    a=p.parse_args();return a.func(a)
if __name__=='__main__':raise SystemExit(main())
