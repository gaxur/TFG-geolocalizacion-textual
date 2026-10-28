#!/usr/bin/env python3
from __future__ import annotations
import argparse,copy,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.tfg_phase0.catalog import build_catalog
def main():
 p=argparse.ArgumentParser();p.add_argument('--options',type=Path,default=ROOT/'config/madrid_expansion_options.json');p.add_argument('--base-config',type=Path,default=ROOT/'config/madrid.yaml');a=p.parse_args();options=json.loads(a.options.read_text());base=json.loads(a.base_config.read_text());rows=[]
 for option in options['options']:
  cfg=copy.deepcopy(base);cfg['region']['name']='proposal_'+option['option_id'];cfg['region']['bbox']=option['bbox_wgs84'];cfg['catalog']['catalog_version']='proposal-grid-v1';counts={}
  for spacing in (25,50):counts[f'{spacing}m']=len(build_catalog(cfg,spacing_m=spacing,cell_size_m=spacing)['candidates'])
  if counts!=option['candidate_counts']:raise RuntimeError(f"conteo no reproducible {option['option_id']}: {counts}")
  rows.append({'option_id':option['option_id'],'candidate_counts':counts})
 print(json.dumps({'verified':True,'options':rows,'no_artifacts_written':True},sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
