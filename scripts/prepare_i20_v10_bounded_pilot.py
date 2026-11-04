#!/usr/bin/env python3
"""Congela el piloto I02-I04 v10 sin abrir imágenes ni cargar modelos."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from src.tfg_phase0.append_jsonl_checkpoint import canonical_bytes
from src.tfg_phase0.bounded_annotation_pilot import TARGET_IDS
from src.tfg_phase0.i20_assisted_annotation import content_id


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,document):path.write_bytes(canonical_bytes(document)+b"\n")


def main():
    p=argparse.ArgumentParser();p.add_argument('--source-plan',type=Path,required=True);p.add_argument('--annotation-fixture',type=Path,required=True);p.add_argument('--scene-fixture',type=Path,required=True);p.add_argument('--instructions',type=Path,required=True);p.add_argument('--output-root',type=Path,required=True);a=p.parse_args()
    source=json.loads(a.source_plan.read_text());fixture=json.loads(a.annotation_fixture.read_text());scene=json.loads(a.scene_fixture.read_text())
    if source.get('contract_version')!='i20-assisted-annotation-plan-v1' or tuple(source.get('jobs',{}).get('annotation_order',[])[1:4])!=TARGET_IDS:raise ValueError('plan fuente v10 u orden I02-I04 incompatible')
    if digest(a.source_plan)!='3198a0c5c6518c3bea054c05fa6ef720c579a033b82fdc5c8e998682ac55b199':raise ValueError('hash del plan fuente v10 incompatible')
    if a.output_root.exists():raise ValueError('output de preparación ya existe')
    if not a.output_root.parent.is_dir():raise ValueError('padre de output ausente')
    a.output_root.mkdir()
    script=ROOT/'scripts/run_i20_v10_bounded_pilot.py';orchestrator=ROOT/'src/tfg_phase0/bounded_annotation_pilot.py';validator=ROOT/'src/tfg_phase0/i20_assisted_annotation.py';ledger=ROOT/'src/tfg_phase0/immutable_attempt_ledger.py';guidance=ROOT/'src/tfg_phase0/xgrammar_guidance.py'
    xspec=importlib.util.find_spec('xgrammar');xroot=Path(next(iter(xspec.submodule_search_locations)))
    fixture_by={row['observation_id']:row for row in fixture['observations']}
    targets=[{"observation_id":target,"reference_asset_id":fixture_by[target]['reference_asset_id'],"reference_asset_sha256":fixture_by[target]['reference_asset_sha256'],"reference_asset_path":fixture_by[target]['reference_asset_path']} for target in TARGET_IDS]
    plan={
      "schema_version":"1.0","contract_version":"i20-assisted-v10-bounded-pilot-plan-v2","plan_id":"","status":"prepared_not_authorized","run_id":"i20-v10-bounded-pilot-i02-i04-v2","runtime_relative_path":"runtime-v2","source":{"plan_id":source['plan_id'],"plan_sha256":digest(a.source_plan),"annotation_fixture_sha256":digest(a.annotation_fixture),"scene_fixture_sha256":digest(a.scene_fixture),"instructions_sha256":digest(a.instructions)},
      "targets":targets,"ordered_target_ids":list(TARGET_IDS),
      "generator":{"model_id":source['generator']['model_id'],"model_revision":source['generator']['model_revision'],"weight_sha256":source['generator']['weight_sha256'],"processor_policy":source['generator']['processor_policy'],"decoding":source['generator']['decoding'],"structured_engine":"xgrammar-0.2.1","text_vocab_size":151936,"eos_token_ids":[151645,151643],"annotation_prompt_sha256":source['generator']['annotation_prompt_sha256'],"annotation_schema_sha256":source['generator']['annotation_schema_sha256'],"source_runner_sha256":source['generator']['runner_sha256'],"pilot_runner_sha256":digest(script),"orchestrator_sha256":digest(orchestrator),"validation_materializer_sha256":digest(validator),"ledger_sha256":digest(ledger),"guidance_sha256":digest(guidance),"xgrammar_version":importlib.metadata.version('xgrammar'),"xgrammar_bindings_sha256":digest(xroot/'libxgrammar_bindings.so'),"xgrammar_hf_adapter_sha256":digest(xroot/'contrib/hf.py')},
      "budget":{"maximum_model_loads":1,"maximum_scene_calls":0,"maximum_annotation_calls":3,"maximum_total_future_calls":3,"maximum_calls_per_observation":1,"maximum_new_tokens_per_call":2048,"maximum_generated_tokens_total":6144,"retry_permitted":False,"resume_permitted":False},
      "execution_policy":{"ordered":True,"continue_after_failure":False,"fresh_runtime_required":True,"single_process":True,"all_outputs_pending_human_review":True,"automatic_canonical_materialization":False},
      "blinding":{"ground_truth_permitted":False,"coordinates_permitted":False,"osm_permitted":False,"rankings_permitted":False,"ct2l_permitted":False,"reranking_permitted":False,"h38_h61_permitted":False,"network_permitted":False,"downloads_permitted":False},
      "stop_policy":{"operational":"stop_immediately","contractual_or_materialization":"persist_failure_and_stop_immediately","coverage":"evaluate_only_after_three_successes_no_mid_pilot_changes"}
    }
    plan['plan_id']=content_id('i20-v10-bounded-pilot-plan-sha256-',plan,'plan_id');write(a.output_root/'plan.json',plan)
    auth={"schema_version":"1.0","contract_version":"i20-assisted-v10-bounded-pilot-authorization-v2","authorization_id":"i20-v10-bounded-pilot-i02-i04-v2","approved":False,"gpu_authorized":False,"approved_by":None,"approved_at_utc":None,"plan_id":plan['plan_id'],"plan_sha256":digest(a.output_root/'plan.json'),"run_id":plan['run_id'],"runtime_relative_path":plan['runtime_relative_path'],"target_ids":list(TARGET_IDS),"ordered_execution":True,"maximum_model_loads":1,"maximum_scene_calls":0,"maximum_annotation_calls":3,"maximum_total_future_calls":3,"maximum_calls_per_observation":1,"retry_permitted":False,"resume_permitted":False,"continue_after_failure":False,"human_review_required":True,"network_permitted":False,"downloads_permitted":False,"ground_truth_permitted":False,"coordinates_permitted":False,"osm_permitted":False,"rankings_permitted":False,"ct2l_permitted":False,"reranking_permitted":False,"h38_h61_permitted":False,"pilot_runner_sha256":plan['generator']['pilot_runner_sha256'],"orchestrator_sha256":plan['generator']['orchestrator_sha256'],"validation_materializer_sha256":plan['generator']['validation_materializer_sha256'],"ledger_sha256":plan['generator']['ledger_sha256'],"guidance_sha256":plan['generator']['guidance_sha256']};write(a.output_root/'authorization.request.json',auth)
    evaluation={"schema_version":"1.0","contract_version":"i20-assisted-v10-bounded-pilot-evaluation-v1","status":"template_not_reviewed","target_ids":list(TARGET_IDS),"automatic_metrics":["description_characters","generated_token_count","generation_seconds","claim_count","distinct_claim_kind_count","unique_evidence_quote_count","absent_evidence_quote_count","ambiguous_evidence_quote_count","visible_text_count","visible_text_requires_ocr_coherence","uncertainty_count"],"human_metrics":["visually_supported_claim_count","semantically_strengthened_claim_count","potentially_omitted_discriminative_evidence_count","description_faithfulness","claim_atomicity","visual_text_fidelity"],"same_vlm_is_independent_evaluator":False,"human_reviews":[]};write(a.output_root/'evaluation-template.json',evaluation)
    print(json.dumps({'plan_id':plan['plan_id'],'targets':list(TARGET_IDS),'approved':False},sort_keys=True));return 0

if __name__=='__main__':raise SystemExit(main())
