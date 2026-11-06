#!/usr/bin/env python3
"""Audita E0-E3 con el tokenizer CLIP real sin cargar pesos ni modelo."""

from __future__ import annotations
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.tfg_phase0.append_jsonl_checkpoint import finalize_json_atomic
from src.tfg_phase0.dialogue_en_cartographic import audit_clip_tokenization,sha256_file

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--queries",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args();bundle=json.loads(a.queries.read_text())
    import clip  # Import tardío; clip.load no se llama.
    report=audit_clip_tokenization(bundle,clip.tokenize);report["openai_clip_commit"]="dcba3cb2e2827b402d2701e7e1c7d9fed8a20ef1";report["queries_sha256"]=sha256_file(a.queries);finalize_json_atomic(output_path=a.output,document=report);print(json.dumps({"status":report["status"],"output":str(a.output)}));return 0
if __name__=="__main__":raise SystemExit(main())
