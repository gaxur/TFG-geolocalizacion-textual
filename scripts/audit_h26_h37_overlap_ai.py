#!/usr/bin/env python3
"""Auditoría IA de solapamiento; no sustituye el gate humano del protocolo."""
from __future__ import annotations
import argparse,hashlib,json,sys
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
from PIL import Image
import torch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def histogram(path):
 with Image.open(path) as image:
  data=np.asarray(image.convert("RGB").resize((128,128)),dtype=np.uint8)
 hist=[]
 for channel in range(3):
  values,_=np.histogram(data[:,:,channel],bins=32,range=(0,256),density=True);hist.extend(values)
 vector=np.asarray(hist,dtype=np.float64);return vector/np.linalg.norm(vector)
def main():
 p=argparse.ArgumentParser();p.add_argument("--review",type=Path,required=True);p.add_argument("--reference-assets",type=Path,required=True);p.add_argument("--candidate-assets",type=Path,required=True);p.add_argument("--clip-weights-dir",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args();review=json.loads(a.review.read_text());references=json.loads(a.reference_assets.read_text());candidates=json.loads(a.candidate_assets.read_text());docs={r["image_id"]:(a.reference_assets,r) for r in references["assets"]}|{r["image_id"]:(a.candidate_assets,r) for r in candidates["assets"]};paths={image_id:(manifest.parent/row["logical_path"]).resolve() for image_id,(manifest,row) in docs.items()};ids=sorted({row["reference_image_id"] for row in review["pairs"]}|{row["candidate_image_id"] for row in review["pairs"]})
 import clip
 model,preprocess=clip.load("ViT-L/14@336px",device="cuda",download_root=str(a.clip_weights_dir));model.eval();embeddings={}
 for start in range(0,len(ids),16):
  batch=ids[start:start+16];images=torch.stack([preprocess(Image.open(paths[value]).convert("RGB")) for value in batch]).to("cuda")
  with torch.inference_mode():values=model.encode_image(images).float();values/=values.norm(dim=-1,keepdim=True)
  for image_id,value in zip(batch,values.cpu().numpy(),strict=True):embeddings[image_id]=value
 histograms={image_id:histogram(path) for image_id,path in paths.items() if image_id in ids};counts={"same_scene":0,"different_scene":0,"pending_human":0};completed=[]
 for row in review["pairs"]:
  left,right=row["reference_image_id"],row["candidate_image_id"];clip_similarity=float(embeddings[left]@embeddings[right]);color_similarity=float(histograms[left]@histograms[right]);dhash=row["dhash_distance"]
  # Solo evidencia convergente extrema permite clasificar automáticamente.
  if row["exact_duplicate"] or (clip_similarity>=0.985 and color_similarity>=0.98 and dhash<=12):decision=True;status="ai_same_scene_requires_human_confirmation";counts["same_scene"]+=1
  elif clip_similarity<0.72 and color_similarity<0.92 and dhash>18:decision=False;status="ai_different_scene_requires_human_confirmation";counts["different_scene"]+=1
  else:decision=None;status="pending_human_ambiguous";counts["pending_human"]+=1
  completed.append({**row,"invalidating_overlap":decision,"review_status":status,"reviewer":"opencode_visual_overlap_audit_v1","reviewed_at_utc":datetime.now(timezone.utc).isoformat().replace("+00:00","Z"),"ai_metrics":{"clip_l14_336_cosine":clip_similarity,"rgb_histogram_cosine":color_similarity,"dhash_distance":dhash},"human_approval_required":True})
 document={**review,"contract_version":"h26-h37-overlap-ai-audit-v1","ai_audit":{"model":"CLIP-L/14@336px","weights_sha256":digest(a.clip_weights_dir/"ViT-L-14-336px.pt"),"thresholds":{"same_scene":{"clip_min":0.985,"color_min":0.98,"dhash_max":12},"different_scene":{"clip_max_exclusive":0.72,"color_max_exclusive":0.92,"dhash_min_exclusive":18}},"counts":counts,"not_human_review":True,"pilot_2b_unblocked":False},"pairs":completed};a.output.write_text(json.dumps(document,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8");print(json.dumps({"counts":counts,"sha256":digest(a.output)},sort_keys=True));return 0
if __name__=="__main__":raise SystemExit(main())
