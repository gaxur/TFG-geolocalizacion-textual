#!/usr/bin/env python3
"""Filtra asociaciones para claims usando solo imágenes ACCEPT congeladas."""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.tfg_phase0.visual_quality_gate import accepted_associations,canonical_bytes
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--quality-result',type=Path,required=True);p.add_argument('--associations',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();quality=json.loads(a.quality_result.read_text());document=json.loads(a.associations.read_text());rows=accepted_associations(quality,document['associations']);result={**document,'contract_version':'quality-filtered-'+document.get('contract_version','visual-associations-v1'),'quality_result_sha256':digest(a.quality_result),'source_associations_sha256':digest(a.associations),'protocol':{**document.get('protocol',{}),'quality_accept_only':True,'review_reject_missing_neutral':True,'reranking_policy_changed':False},'associations':rows,'summary':{'source_associations':len(document['associations']),'accepted_associations':len(rows),'removed_from_claim_calls':len(document['associations'])-len(rows)}};a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_bytes(canonical_bytes(result)+b'\n');print(json.dumps(result['summary'],sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
