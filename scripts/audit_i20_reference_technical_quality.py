#!/usr/bin/env python3
"""Auditoría CPU descriptiva I20; no VLM, rankings, GT ni sustituciones."""
from __future__ import annotations
import argparse,hashlib,json,statistics
from pathlib import Path
from PIL import Image,ImageFilter,ImageStat
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--assignment-manifest',type=Path,required=True);p.add_argument('--package-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();manifest=json.loads(a.assignment_manifest.read_text());assignments=manifest.get('assignments',manifest.get('observations'))
 if not isinstance(assignments,list) or len(assignments)!=20:raise ValueError('manifest de referencias incompatible')
 rows=[]
 for assignment in assignments:
  path=a.package_root/assignment['reference_asset_path'];raw=path.read_bytes()
  if hashlib.sha256(raw).hexdigest()!=assignment['reference_asset_sha256']:raise ValueError('hash de referencia inválido')
  with Image.open(path) as image:
   image.load();gray=image.convert('L');stat=ImageStat.Stat(gray);mean=float(stat.mean[0]);std=float(stat.stddev[0]);hist=gray.histogram();pixels=gray.width*gray.height;dark=sum(hist[:16])/pixels;bright=sum(hist[240:])/pixels;edges=gray.filter(ImageFilter.FIND_EDGES);edge_variance=float(ImageStat.Stat(edges).var[0]);width,height=image.size
  warnings=[]
  if dark>=.8:warnings.append('extreme_dark_fraction')
  if bright>=.8:warnings.append('extreme_bright_fraction')
  if std<12:warnings.append('very_low_global_contrast')
  if edge_variance<20:warnings.append('very_low_edge_variance_possible_blur_or_uniformity')
  if min(width,height)<480:warnings.append('small_reference_dimensions')
  rows.append({'observation_id':assignment['observation_id'],'reference_asset_sha256':assignment['reference_asset_sha256'],'width_px':width,'height_px':height,'grayscale_mean':mean,'grayscale_stddev':std,'dark_fraction_0_15':dark,'bright_fraction_240_255':bright,'edge_variance':edge_variance,'automatic_warnings':warnings,'human_quality_review_required':True,'replacement_performed':False})
 document={'schema_version':'1.0','contract_version':'i20-reference-technical-quality-audit-v1','protocol':{'cpu_only':True,'pixels_used':True,'vlm_used':False,'rankings_used':False,'ground_truth_used':False,'osm_used':False,'automatic_metrics_are_not_human_quality_decisions':True,'selection_frozen_no_replacement':True},'inputs':{'assignment_manifest_sha256':digest(a.assignment_manifest)},'summary':{'references':len(rows),'decode_valid':len(rows),'warning_references':sum(bool(row['automatic_warnings']) for row in rows),'mean_grayscale_stddev':statistics.fmean(row['grayscale_stddev'] for row in rows),'mean_edge_variance':statistics.fmean(row['edge_variance'] for row in rows)},'records':rows};a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(document,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf-8');print(json.dumps(document['summary'],sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
