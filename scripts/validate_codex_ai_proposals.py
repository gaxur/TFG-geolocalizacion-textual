#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path
from jsonschema import Draft202012Validator
def main():
 p=argparse.ArgumentParser();p.add_argument('--package-root',type=Path,required=True);p.add_argument('--proposals',type=Path,required=True);a=p.parse_args();fixture=json.loads((a.package_root/'fixture.json').read_text());doc=json.loads(a.proposals.read_text());schema=json.loads((a.package_root/'schemas/visual_atomic_ai_proposals.schema.json').read_text());Draft202012Validator(schema,format_checker=Draft202012Validator.FORMAT_CHECKER).validate(doc);assert doc['fixture_id']==fixture['source_fixture_id'] and doc['provenance']['annotation_kind']=='AI-proposed' and doc['provenance']['human_validated'] is False;expected={(r['query_id'],r['candidate_id'],r['image_id'],r['claim_id']) for r in fixture['expected_records']};actual={(r['query_id'],r['candidate_id'],r['image_id'],r['claim_id']) for r in doc['records']};assert expected==actual and len(actual)==len(doc['records'])==72;assert all(r['proposal_status']=='AI-proposed' for r in doc['records']);print(json.dumps({'valid':True,'records':72,'provenance':'AI-proposed'},sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
