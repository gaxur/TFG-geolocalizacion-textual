#!/usr/bin/env python3
"""Registra revisión visual parcial y crea una cola complementaria Panoramax."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.f5_evidence_acquisition import attach_download, build_complementary_review_queue, download_review_asset, render_review_html, review_queue_id, sha256_bytes, canonical_bytes, upgrade_existing_visual_review_queue, upgrade_visual_review_queue, validate_review_queue


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-dir", required=True, type=Path)
    parser.add_argument("--decisions", type=Path, default=ROOT / "config/madrid_f55b_visual_review_decisions.json")
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--asset-role", choices=("thumb", "sd", "none"), default="thumb")
    parser.add_argument("--review-existing-queue", type=Path, help="Materializa revisión visual sobre una cola v2 existente sin crear complemento.")
    parser.add_argument("--user-agent", default="TFG-Geolocalizacion-Textual-F5.5b/1.0 (academic research; contact repository owner)")
    args = parser.parse_args()
    inventory_raw = (args.snapshot_dir / "inventory.json").read_bytes(); inventory = json.loads(inventory_raw)
    if args.review_existing_queue:
        queue = json.loads(args.review_existing_queue.read_text(encoding="utf-8")); decisions=json.loads(args.decisions.read_text(encoding="utf-8")); reviewed=upgrade_existing_visual_review_queue(queue,decisions); output_id="f55c-complementary-review-"+sha256_bytes(canonical_bytes(reviewed)); final=args.output_root/output_id
        if not final.exists():
            args.output_root.mkdir(parents=True,exist_ok=True)
            with tempfile.TemporaryDirectory(prefix=".f55c-complementary-",dir=args.output_root) as temporary:
                path=Path(temporary); (path/"assets").mkdir()
                source_root=args.review_existing_queue.parent
                for record in reviewed["records"]:
                    for role in ("thumb","sd"):
                        value=record["assets"].get(role)
                        if value and value.get("download"):
                            source=source_root/value["download"]["logical_path"]; destination=path/"assets"/source.name
                            if not source.is_file() or sha256_bytes(source.read_bytes())!=value["download"]["sha256"]: raise RuntimeError("asset complementario ausente o modificado")
                            shutil.copyfile(source,destination); value["download"]["logical_path"]=f"assets/{source.name}"
                reviewed["review_queue_id"]=review_queue_id(reviewed); validate_review_queue(reviewed); (path/"complementary-visual-review.json").write_text(json.dumps(reviewed,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n",encoding="utf-8"); render_review_html(reviewed,path/"complementary-visual-review.html"); os.replace(path,final)
        print(json.dumps({"output":str(final),"review_counts":validate_review_queue(reviewed),"visual_suitability":{s:sum(r["visual_review"]["suitability"]==s for r in reviewed["records"]) for s in ("suitable","limited","unsuitable")}},sort_keys=True)); return 0
    primary_raw = (args.snapshot_dir / "review-queue.json").read_bytes(); primary = json.loads(primary_raw)
    decisions = json.loads(args.decisions.read_text(encoding="utf-8"))
    reviewed = upgrade_visual_review_queue(primary, decisions)
    complementary = build_complementary_review_queue(inventory, primary)
    output_id = "f55b-visual-review-" + sha256_bytes(canonical_bytes({"inventory": inventory["inventory_id"], "primary": primary["review_queue_id"], "reviewed": reviewed["review_queue_id"], "complementary": complementary["review_queue_id"]}))
    final = args.output_root / output_id
    if final.exists():
        print_summary(final)
        return 0
    args.output_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".f55b-review-", dir=args.output_root) as temporary:
        path = Path(temporary)
        (path / "primary-assets").mkdir()
        for record in reviewed["records"]:
            for role in ("thumb", "sd"):
                value = record["assets"].get(role)
                if value and value.get("download"):
                    source = args.snapshot_dir / value["download"]["logical_path"]
                    destination = path / "primary-assets" / source.name
                    if not source.is_file() or sha256_bytes(source.read_bytes()) != value["download"]["sha256"]:
                        raise RuntimeError(f"asset primario ausente o modificado: {source}")
                    shutil.copyfile(source, destination)
                    value["download"]["logical_path"] = f"primary-assets/{source.name}"
        reviewed["review_queue_id"] = review_queue_id(reviewed)
        if args.asset_role != "none":
            hashes = set()
            for record in complementary["records"]:
                role = args.asset_role if record["assets"].get(args.asset_role) else "thumb"
                url = record["assets"][role]["url"]; relative = f"complementary-assets/{record['item_id']}-{role}.jpg"
                asset = download_review_asset(url, path / relative, logical_path=relative, user_agent=args.user_agent)
                if asset.sha256 in hashes: raise RuntimeError("assets complementarios duplicados")
                hashes.add(asset.sha256); attach_download(complementary, record["item_id"], role, asset)
        validate_review_queue(reviewed); validate_review_queue(complementary)
        (path / "inventory-reference.json").write_text(json.dumps({"inventory_id": inventory["inventory_id"], "inventory_sha256": sha256_bytes(inventory_raw), "primary_review_queue_id": primary["review_queue_id"], "primary_review_queue_sha256": sha256_bytes(primary_raw)}, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
        (path / "primary-visual-review.json").write_text(json.dumps(reviewed, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
        (path / "complementary-review-queue.json").write_text(json.dumps(complementary, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
        render_review_html(reviewed, path / "primary-review.html"); render_review_html(complementary, path / "complementary-review.html")
        os.replace(path, final)
    print_summary(final); return 0


def print_summary(path: Path) -> None:
    primary=json.loads((path/"primary-visual-review.json").read_text()); complementary=json.loads((path/"complementary-review-queue.json").read_text())
    suitability={value:sum(row["visual_review"]["suitability"]==value for row in primary["records"]) for value in ("suitable","limited","unsuitable")}
    print(json.dumps({"output":str(path),"primary_review_queue_id":primary["review_queue_id"],"visual_suitability":suitability,"gt_review":validate_review_queue(primary),"complementary_items":len(complementary["records"]),"complementary_review":validate_review_queue(complementary)},sort_keys=True))


if __name__ == "__main__": raise SystemExit(main())
