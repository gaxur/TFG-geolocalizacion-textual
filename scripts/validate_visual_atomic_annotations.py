#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path
from jsonschema import Draft202012Validator

def main():
 p=argparse.ArgumentParser();p.add_argument('--annotations',type=Path,required=True);p.add_argument('--fixture',type=Path,required=True);p.add_argument('--schema',type=Path,default=Path(__file__).resolve().parents[1]/'schemas/visual_atomic_human_annotations.schema.json');a=p.parse_args();doc=json.loads(a.annotations.read_text());fixture=json.loads(a.fixture.read_text());Draft202012Validator(json.loads(a.schema.read_text()),format_checker=Draft202012Validator.FORMAT_CHECKER).validate(doc);expected={(r['candidate_id'],r['image_id'],r['claim_id']) for r in fixture['annotation_template']['records']};actual={(r['candidate_id'],r['image_id'],r['claim_id']) for r in doc['records']};assert expected==actual and len(actual)==len(doc['records']);assert all(r['review_status']=='reviewed' and r['human_verdict'] for r in doc['records']);missing=[r for r in doc['records'] if r['human_verdict'] in {'supported','contradicted'} and not r['observed_evidence']];assert not missing,f"{len(missing)} etiquetas supported/contradicted sin evidencia observable";print(json.dumps({'valid':True,'reviewed':len(actual)},sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
