#!/usr/bin/env python3
"""Diagnóstico de evidencia exclusiva/compartida sin inferir corrección."""

from __future__ import annotations
import argparse,collections,hashlib,json
from pathlib import Path

def main():
 p=argparse.ArgumentParser();p.add_argument("--spatial",type=Path,required=True);p.add_argument("--run-2b",type=Path,required=True);p.add_argument("--run-8b",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args();spatial=json.loads(a.spatial.read_text());runs={"2b":json.loads(a.run_2b.read_text()),"8b":json.loads(a.run_8b.read_text())};rows=spatial["rows"];by_image=collections.defaultdict(set)
 for row in rows:by_image[row["image_id"]].add((row["query_id"],row["candidate_id"]));shared={image for image,targets in by_image.items() if len(targets)>1};association={(r["query_id"],r["candidate_id"],r["image_id"]):r for r in rows};models={}
 for model,run in runs.items():
  supported=[r for r in run["records"] if r["verdict"]=="supported"];exclusive=[r for r in supported if r["image_id"] not in shared];shared_rows=[r for r in supported if r["image_id"] in shared];models[model]={"supported_jobs":len(supported),"supported_on_exclusive_images":len(exclusive),"supported_on_shared_images":len(shared_rows),"supported_on_ambiguous_associations":sum(association[(r["query_id"],r["candidate_id"],r["image_id"])]["ambiguity_status"]=="spatially_ambiguous" for r in supported),"unique_supported_image_claim_pairs":len({(r["image_id"],r["claim_id"]) for r in supported}),"projected_supported_jobs_minus_unique_pairs":len(supported)-len({(r["image_id"],r["claim_id"]) for r in supported})}
 sensitivity={fov:collections.Counter() for fov in ("60","90","120")}
 for row in rows:
  for fov,relation in row.get("fov_sensitivity",{}).items():sensitivity[fov][relation]+=1
 doc={"schema_version":"1.0","contract_version":"h16-h23-shared-visual-evidence-audit-v1","inputs":{path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in (a.spatial,a.run_2b,a.run_8b)},"counts":{"physical_images":len(by_image),"shared_physical_images":len(shared),"exclusive_physical_images":len(by_image)-len(shared),"associations":len(rows)},"fov_sensitivity":{fov:dict(value) for fov,value in sensitivity.items()},"models":models,"diagnostic":{"exclusive_support_fraction":"supported_on_exclusive_images / supported_jobs","shared_support_is_not_independent":True,"ambiguity_is_geometric_not_visual":True},"limitations":["supported_is_not_correctness","same_image_claim_may_project_to_multiple_candidates","hypothetical_fov"]};a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(doc,ensure_ascii=False,sort_keys=True,indent=2)+"\n");print(json.dumps({"counts":doc["counts"],"models":models,"fov":doc["fov_sensitivity"]},sort_keys=True));return 0
if __name__=="__main__":raise SystemExit(main())
