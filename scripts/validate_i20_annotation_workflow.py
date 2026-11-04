#!/usr/bin/env python3
"""Importa exports humanos I20 y emite blockers; no inventa reviews ni ledger."""
from __future__ import annotations
import argparse,json
from pathlib import Path
import sys
import jsonschema
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.tfg_phase0.i20_annotation_workflow import validate_freeze_readiness,validate_scene_review,verify_custodian_response
from src.tfg_phase0.i20_preparation import validate_annotation_package,validate_review_package
from src.tfg_phase0.i20_preparation import canonical_bytes
def load(path):return json.loads(path.read_text(encoding='utf-8'))
def schema(name):return load(ROOT/'schemas'/name)
def main():
 p=argparse.ArgumentParser();p.add_argument('--workflow-root',type=Path,required=True);p.add_argument('--geographic-package',type=Path,required=True);p.add_argument('--annotation',type=Path);p.add_argument('--scene-review',type=Path);p.add_argument('--review',type=Path);p.add_argument('--ledger-submission',type=Path);p.add_argument('--ledger-response',type=Path);p.add_argument('--custodian-public-key',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();fixture=load(a.workflow_root/'annotation/fixture.json');scene_fixture=load(a.workflow_root/'scene-review/fixture.json');geographic=load(a.geographic_package);blockers=[];annotation={"status":"missing","observations":[]};scene={"status":"missing","records":[]};review={"status":"missing","reviews":[],"adjudication":[]};receipt=None
 if a.annotation:
  annotation=load(a.annotation);jsonschema.validate(annotation,schema('i20_annotation_package.schema.json'),format_checker=jsonschema.FormatChecker());validate_annotation_package(annotation,project_root=a.workflow_root/'annotation')
 else:blockers.append('annotation_export_missing')
 if a.scene_review:
  scene=load(a.scene_review);jsonschema.validate(scene,schema('i20_scene_review.schema.json'),format_checker=jsonschema.FormatChecker());validate_scene_review(scene,scene_fixture)
 else:blockers.append('scene_review_export_missing')
 if a.review:
  review=load(a.review);jsonschema.validate(review,schema('i20_review_package.schema.json'),format_checker=jsonschema.FormatChecker());validate_review_package(review,annotation)
 else:blockers.append('independent_reviews_and_adjudication_missing')
 ledger_args=(a.ledger_submission,a.ledger_response,a.custodian_public_key)
 if all(ledger_args):
  submission,response=load(a.ledger_submission),load(a.ledger_response);jsonschema.validate(response,schema('i20_blind_ledger_response.schema.json'),format_checker=jsonschema.FormatChecker());receipt=verify_custodian_response(submission,response,a.custodian_public_key.read_bytes())
 elif any(ledger_args):blockers.append('ledger_inputs_incomplete')
 else:blockers.append('authentic_custodian_response_missing')
 readiness=validate_freeze_readiness(annotation=annotation,scene_review=scene,scene_fixture=scene_fixture,review=review,ledger_receipt=receipt,geographic=geographic);readiness['blockers']=sorted(set(readiness['blockers']+blockers));readiness['ready']=not readiness['blockers'] and readiness['active_observations']>=12;document={'schema_version':'1.0','contract_version':'i20-freeze-readiness-report-v1','ready':readiness['ready'],'active_observations':readiness['active_observations'],'minimum_required':12,'blockers':readiness['blockers'],'ledger_receipt':receipt,'no_state_transition_performed':True};a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_bytes(canonical_bytes(document)+b'\n');print(json.dumps(document,sort_keys=True));return 0 if document['ready'] else 2
if __name__=='__main__':raise SystemExit(main())
