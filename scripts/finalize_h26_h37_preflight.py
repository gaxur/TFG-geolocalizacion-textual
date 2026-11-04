#!/usr/bin/env python3
"""Publica estado reproducible de Fase C sin abrir test ni ejecutar VLM bloqueado."""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument("--root",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args();paths={name:a.root/name for name in ("selection.json","h38-h61-container-seal.json","assets-hashed.json","remote-campaign-annotations.frozen.json","ct2l-top100.json","recoverability.json","visual-plan-top50.json","visual-budget-top50.json","candidate-assets-top50.json","overlap-review-top50/overlap-review.completed.json")}
 for path in paths.values():
  if not path.is_file():raise ValueError(f"artefacto ausente: {path}")
 annotations=json.loads(paths["remote-campaign-annotations.frozen.json"].read_text());recoverability=json.loads(paths["recoverability.json"].read_text());budget=json.loads(paths["visual-budget-top50.json"].read_text());overlap=json.loads(paths["overlap-review-top50/overlap-review.completed.json"].read_text());pending=sum(row["human_approval_required"] and row["invalidating_overlap"] is None for row in overlap["pairs"])
 document={"schema_version":"1.0","contract_version":"h26-h37-phase-c-preflight-v1","status":"blocked_pending_human_overlap_review","inputs":{name:{"logical_path":str(path),"sha256":digest(path)} for name,path in paths.items()},"completed":{"development_annotations_frozen":len(annotations["observations"])==12,"ct2l_top100_frozen":True,"recoverability_evaluated_post_freeze":recoverability["protocol"]["references_loaded_only_after_top100_freeze"],"candidate_neutral_top50_plan_frozen":True,"candidate_assets_acquired":105,"ai_overlap_pairs_processed":len(overlap["pairs"]),"new_vlm_inferences":0,"h38_h61_opened":False},"recoverability":recoverability["aggregate"],"pilot_budget":budget,"blockers":[{"code":"human_overlap_review_pending","pending_pairs":pending,"reason":"AI audit does not replace the protocol-required human overlap review"}],"forbidden_until_unblocked":["qwen3_vl_2b_inference","reranking_calibration","policy_selection","mvp_bundle_publication","h38_h61_opening"]};a.output.write_text(json.dumps(document,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8");print(json.dumps({"status":document["status"],"pending_pairs":pending,"sha256":digest(a.output)},sort_keys=True));return 0
if __name__=="__main__":raise SystemExit(main())
