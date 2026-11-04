#!/usr/bin/env python3
"""Finaliza decisiones humanas sobre propuestas IA; no acepta pending implícitos."""
from __future__ import annotations
import argparse,json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.tfg_phase0.i20_assisted_annotation import content_id,normalize_annotation_draft,validate_human_decisions
from src.tfg_phase0.i20_preparation import canonical_bytes
def load(path):return json.loads(path.read_text(encoding='utf-8'))
def main():
 p=argparse.ArgumentParser();p.add_argument('--draft',type=Path,required=True);p.add_argument('--scene-proposals',type=Path,required=True);p.add_argument('--annotation-proposals',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();draft=load(a.draft);scenes=load(a.scene_proposals);annotations=load(a.annotation_proposals);rows=[]
 for source in draft.get('decisions',[]):
  row=json.loads(json.dumps(source,ensure_ascii=False));row.pop('decision_id',None)
  if row.get('status')=='corrected' and row.get('target_kind')=='annotation':row['human_revision']=normalize_annotation_draft(row['human_revision'])
  row['decision_id']=content_id('i20-assist-human-decision-sha256-',row,'decision_id');rows.append(row)
 document={'schema_version':'1.0','contract_version':'i20-assisted-human-decisions-v1','artifact_id':'','plan_id':draft['plan_id'],'decisions':rows};document['artifact_id']=content_id('i20-assist-human-decisions-sha256-',document,'artifact_id');counts=validate_human_decisions(document,scene_proposals=scenes,annotation_proposals=annotations);a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_bytes(canonical_bytes(document)+b'\n');print(json.dumps({'artifact_id':document['artifact_id'],'counts':counts},sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
