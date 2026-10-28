#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.tfg_phase0.independent_campaign import canonical_bytes,validate_campaign
from src.tfg_phase0.h11_h25_independent import historical_rows
def main():
 p=argparse.ArgumentParser();p.add_argument('--campaign',type=Path,required=True);p.add_argument('--evidence-root',type=Path,required=True);p.add_argument('--schema',type=Path,default=ROOT/'schemas/independent_human_observation.schema.json');p.add_argument('--historical-datasets',nargs='*',type=Path,default=[]);p.add_argument('--output',type=Path,required=True);a=p.parse_args();doc=json.loads(a.campaign.read_text());schema=json.loads(a.schema.read_text());historical=[]
 for path in a.historical_datasets:
  d=json.loads(path.read_text());historical.extend([{'id':r.get('observation_id') or r.get('query_id'),'latitude':(r.get('panorama_coordinate') or r.get('link_coordinate') or r.get('reference'))['latitude'],'longitude':(r.get('panorama_coordinate') or r.get('link_coordinate') or r.get('reference'))['longitude']} for r in d.get('observations',[])])
 report=validate_campaign(doc,schema=schema,evidence_root=a.evidence_root,historical=historical);a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_bytes(canonical_bytes(report)+b'\n');print(json.dumps(report,sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
