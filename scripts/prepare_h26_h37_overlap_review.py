#!/usr/bin/env python3
"""Hash perceptual y visor ciego de solapamiento referencia-candidato H26-H37."""
from __future__ import annotations
import argparse,hashlib,json,os
from html import escape
from pathlib import Path
from PIL import Image

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def dhash(path):
 with Image.open(path) as image:pixels=list(image.convert("L").resize((9,8)).getdata())
 value=0
 for row in range(8):
  for column in range(8):value=(value<<1)|(pixels[row*9+column]>pixels[row*9+column+1])
 return f"{value:016x}"
def main():
 p=argparse.ArgumentParser();p.add_argument("--campaign",type=Path,required=True);p.add_argument("--plan",type=Path,required=True);p.add_argument("--reference-assets",type=Path,required=True);p.add_argument("--candidate-assets",type=Path,required=True);p.add_argument("--output-dir",type=Path,required=True);a=p.parse_args();campaign=json.loads(a.campaign.read_text());plan=json.loads(a.plan.read_text());references=json.loads(a.reference_assets.read_text());candidates=json.loads(a.candidate_assets.read_text());ref_by={r["query_id"]:r["reference_asset"]["image_id"] for r in campaign["observations"]};asset_docs={r["image_id"]:(a.reference_assets,r) for r in references["assets"]}|{r["image_id"]:(a.candidate_assets,r) for r in candidates["assets"]};hashes={}
 for image_id,(manifest,row) in asset_docs.items():
  path=(manifest.parent/row["logical_path"]).resolve()
  if digest(path)!=row["sha256"]:raise ValueError(f"hash inválido {image_id}")
  hashes[image_id]={"sha256":row["sha256"],"dhash":dhash(path),"path":path}
 pairs=[];seen=set()
 for association in plan["associations"]:
  key=(association["query_id"],association["image_id"])
  if key in seen:continue
  seen.add(key);reference_id=ref_by[association["query_id"]];left=hashes[reference_id];right=hashes[association["image_id"]];distance=(int(left["dhash"],16)^int(right["dhash"],16)).bit_count();pairs.append({"query_id":association["query_id"],"reference_image_id":reference_id,"candidate_image_id":association["image_id"],"candidate_sequence_id":association.get("sequence_id"),"exact_duplicate":left["sha256"]==right["sha256"],"dhash_distance":distance,"review_status":"pending","invalidating_overlap":None,"reviewer":None,"reviewed_at_utc":None})
 pairs.sort(key=lambda r:(r["query_id"],r["dhash_distance"],r["candidate_image_id"]));report={"schema_version":"1.0","contract_version":"h26-h37-overlap-review-v1","inputs":{"campaign_sha256":digest(a.campaign),"plan_sha256":digest(a.plan),"reference_assets_sha256":digest(a.reference_assets),"candidate_assets_sha256":digest(a.candidate_assets)},"protocol":{"rankings_shown":False,"vlm_outputs_shown":False,"ground_truth_coordinates_shown":False,"human_review_required":True},"summary":{"pairs":len(pairs),"exact_duplicates":sum(r["exact_duplicate"] for r in pairs),"dhash_distance_le_6":sum(r["dhash_distance"]<=6 for r in pairs),"dhash_distance_le_12":sum(r["dhash_distance"]<=12 for r in pairs)},"pairs":pairs};a.output_dir.mkdir(parents=True,exist_ok=True);(a.output_dir/"review.json").write_text(json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8")
 cards=[]
 for index,row in enumerate(pairs):
  rp=os.path.relpath(hashes[row["reference_image_id"]]["path"],a.output_dir.resolve());cp=os.path.relpath(hashes[row["candidate_image_id"]]["path"],a.output_dir.resolve());cards.append(f'<article data-index="{index}"><h2>{escape(row["query_id"])} · dHash {row["dhash_distance"]}</h2><div><figure><img src="{escape(rp)}"><figcaption>Referencia</figcaption></figure><figure><img src="{escape(cp)}"><figcaption>Candidata {escape(row["candidate_image_id"])}</figcaption></figure></div><label><input type="checkbox" class="invalid"> Solapamiento visual invalidante</label></article>')
 payload=json.dumps(report,ensure_ascii=False).replace("</","<\\/");html=f'''<!doctype html><meta charset="utf-8"><title>Revisión H26-H37</title><style>body{{font:15px sans-serif;max-width:1400px;margin:auto}}article{{border:1px solid #aaa;margin:1rem;padding:1rem}}article div{{display:flex;gap:1rem}}figure{{width:50%}}img{{width:100%;height:320px;object-fit:contain;background:#111}}.done{{opacity:.55}}</style><label>Revisor <input id="reviewer" value="marcos"></label><button id="export">Exportar revisión</button>{''.join(cards)}<script id="data" type="application/json">{payload}</script><script>const d=JSON.parse(data.textContent);export.onclick=()=>{{const reviewer=document.querySelector('#reviewer').value.trim();if(!reviewer)throw Error('revisor');d.pairs.forEach((r,i)=>{{r.invalidating_overlap=document.querySelector(`[data-index="${{i}}"] .invalid`).checked;r.review_status='reviewed';r.reviewer=reviewer;r.reviewed_at_utc=null}});const b=new Blob([JSON.stringify(d,null,2)+'\\n'],{{type:'application/json'}}),u=URL.createObjectURL(b),a=document.createElement('a');a.href=u;a.download='overlap-review.completed.json';a.click()}};</script>''';(a.output_dir/"review.html").write_text(html,encoding="utf-8");print(json.dumps(report["summary"],sort_keys=True));return 0
if __name__=="__main__":raise SystemExit(main())
