#!/usr/bin/env python3
"""Presupuesta tareas físicas provisionales por image_id antes de adquisición."""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path

def main():
 p=argparse.ArgumentParser();p.add_argument("--plan",type=Path,required=True);p.add_argument("--cache",type=Path,default=Path("data/cache/mapillary"));p.add_argument("--output",type=Path,required=True);a=p.parse_args();plan=json.loads(a.plan.read_text());claims={q["query_id"]:q["claims"] for q in plan["queries"]};physical=set();generate=set()
 for association in plan["associations"]:
  for claim in claims[association["query_id"]]:
   policy=bool(claim["requires_orientation"] and not association["orientation_comparable"]);key=(association["image_id"],claim["claim_id"],policy);physical.add(key)
   if not policy:generate.add(key)
 cached=sum((a.cache/"metadata"/f"{image_id}.json").exists() for image_id in plan["asset_ids"]);pending=len(plan["asset_ids"])-cached
 document={"schema_version":"1.0","contract_version":"h26-h37-visual-budget-v1","plan_id":plan["plan_id"],"plan_sha256":hashlib.sha256(a.plan.read_bytes()).hexdigest(),"identity_status":"provisional_by_image_id_until_all_sha256_available","assets":{"unique":len(plan["asset_ids"]),"cached":cached,"pending":pending,"estimated_pending_bytes":round(pending*127767.625),"hard_maximum_pending_bytes":pending*8_000_000},"tasks_per_model":{"logical":plan["summary"]["logical_tasks_per_model"],"physical_provisional":len(physical),"generate_provisional":len(generate),"automatic_abstentions_provisional":len(physical-generate)},"estimated_2b_seconds":len(generate)*0.46137872336367003,"estimated_checkpoint_bytes_1_5x":round(len(physical)*1055)};a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(document,indent=2,sort_keys=True)+"\n");print(json.dumps(document,sort_keys=True));return 0
if __name__=="__main__":raise SystemExit(main())
