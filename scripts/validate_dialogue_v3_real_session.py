#!/usr/bin/env python3
"""Valida en CPU una sesión DialogueVPR v3 preparada; nunca ejecuta modelos."""
import argparse,hashlib,json,sys
from datetime import date
from pathlib import Path
from jsonschema import Draft202012Validator

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.run_interactive_dialogue import load_multiturn_policy
from src.tfg_phase0.dialogue_visual_evidence import load_observer_image_manifest
from src.tfg_phase0.interactive_dialogue import F3EvidenceIndex
from src.tfg_phase0.interactive_dialogue_multiturn import multiturn_session_id

def main():
    p=argparse.ArgumentParser();p.add_argument('--config',type=Path,required=True);p.add_argument('--output',type=Path);p.add_argument('--deep-model-identity',action='store_true');a=p.parse_args();document=json.loads(a.config.read_text());schema=json.loads((ROOT/'schemas/dialogue_v3_real_session_preparation.schema.json').read_text());errors=list(Draft202012Validator(schema).iter_errors(document))
    if errors:raise ValueError('configuración de sesión inválida: '+errors[0].message)
    required=('session_label','initial_description','intent_family','observer_manifest','clip_weights','visual_model_dir')
    missing=[key for key in required if not document.get(key)]
    _,config=load_multiturn_policy(ROOT/document['dialogue_policy'],document['max_questions']);identity_ready=bool(document.get('session_label') and document.get('initial_description'));expected=multiturn_session_id(session_label=document['session_label'],description=document['initial_description'],language=document['language'],gallery_id=document['gallery_id'],config=config) if identity_ready else None
    checks={'operator_fields_complete':not missing,'session_id':False,'session_config':False,'ct2l_config':False,'ct2l_checkpoint':False,'f3_bundle':False,'observer_manifest':False,'observer_restrictions':False,'snapshot':False,'docker_identity':False,'clip_weights':False,'clip_gallery_compatibility':False}
    if expected:checks['session_id']=document.get('session_id')==expected
    region=json.loads((ROOT/document['region_config']).read_text());ct2l=json.loads((ROOT/document['ct2l_config']).read_text());policy=json.loads((ROOT/document['dialogue_policy']).read_text());checks['session_config']=region['region']['name']==document['region'] and policy['gallery_id']==document['gallery_id'] and policy['max_questions']==document['max_questions'] and policy['reserve_size']==document['reserve_size'] and policy['cluster_radius_m']==document['cluster_radius_m'];checks['ct2l_config']=document['gallery_id'] in ct2l['galleries']
    f3=ROOT/document['f3_bundle']
    if f3.is_dir():
        try:F3EvidenceIndex.load_bundle(f3);checks['f3_bundle']=True
        except Exception:checks['f3_bundle']=False
    snapshot=Path(document['visual_model_dir']) if document.get('visual_model_dir') else None;checks['snapshot']=bool(snapshot and snapshot.is_dir())
    clip=Path(document['clip_weights']) if document.get('clip_weights') else None
    if clip and clip.is_file():
        from src.tfg_phase0.crosstext2loc_runtime import EXPECTED_CLIP_WEIGHTS_NAME,EXPECTED_CLIP_WEIGHTS_SHA256,EXPECTED_CLIP_WEIGHTS_SIZE
        digest=hashlib.sha256()
        with clip.open('rb') as stream:
            for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
        checks['clip_weights']=clip.name==EXPECTED_CLIP_WEIGHTS_NAME and clip.stat().st_size==EXPECTED_CLIP_WEIGHTS_SIZE and digest.hexdigest()==EXPECTED_CLIP_WEIGHTS_SHA256
        if checks['ct2l_config']:
            gallery=ct2l['galleries'][document['gallery_id']];embedding=json.loads(((ROOT/gallery['embedding_bundle'])/'manifest.json').read_text());model=embedding['model'];checks['clip_gallery_compatibility']=model['architecture']=='ViT-L/14@336px' and model['openai_clip_weights_sha256']==EXPECTED_CLIP_WEIGHTS_SHA256 and model['text_context_length']==document['text_token_budget']
    from src.tfg_phase0.crosstext2loc_runtime import EXPECTED_CHECKPOINT_NAME,EXPECTED_CHECKPOINT_SHA256,EXPECTED_CHECKPOINT_SIZE
    checkpoint=ROOT/ct2l['model']['checkpoint']
    if checkpoint.is_file():
        checkpoint_digest=hashlib.sha256()
        with checkpoint.open('rb') as stream:
            for block in iter(lambda:stream.read(1024*1024),b''):checkpoint_digest.update(block)
        checks['ct2l_checkpoint']=checkpoint.name==EXPECTED_CHECKPOINT_NAME and checkpoint.stat().st_size==EXPECTED_CHECKPOINT_SIZE and checkpoint_digest.hexdigest()==EXPECTED_CHECKPOINT_SHA256
    integration=json.loads((ROOT/'results/generated/dialogue-v3-real-visual-integration-cpu-v1/report.json').read_text());checks['docker_identity']=document['visual_docker_image_id']==integration['security']['docker_image_id_expected'] and document['visual_docker_image']=='qwen3-vl-dialogue-worker:lmfe-0.11.3-tf5.9-v1'
    if document.get('observer_manifest'):
        manifest,reference=load_observer_image_manifest(ROOT/document['observer_manifest'],ROOT/'schemas/dialogue_observer_image_manifest.schema.json');checks['observer_manifest']=manifest['session_id']==expected and manifest['intent_family']==document['intent_family'];restrictions=set(manifest['usage_restrictions']);checks['observer_restrictions']=any('2027-06-30' in value for value in restrictions) and any('one local inference' in value.lower() for value in restrictions) and any('no training' in value.lower() for value in restrictions) and any('no automatic publication' in value.lower() for value in restrictions) and any(all(term in value.lower() for term in ('known','location','prompt','ct2l','rankings')) for value in restrictions) and date.today()<=date(2027,6,30)
    if a.deep_model_identity and checks['snapshot']:
        from scripts.run_qwen3_vl_8b_memory_smoke import verify_model
        checks['model_identity']=verify_model(snapshot)['revision']=='0c351dd01ed87e9c1b53cbc748cba10e6187ff3b'
    status='SESSION_CPU_VALIDATION_PASS' if all(checks.values()) else 'SESSION_PREPARATION_PENDING';report={'schema_version':'1.0','contract_version':'dialogue-v3-real-session-validation-v1','status':status,'missing_operator_fields':missing,'derived_session_id':expected,'checks':checks,'gpu_used':False,'worker_executed':False}
    if a.output:
        if a.output.exists():raise ValueError('output ya existe')
        a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False,sort_keys=True));return 0 if status=='SESSION_CPU_VALIDATION_PASS' else 2
if __name__=='__main__':raise SystemExit(main())
