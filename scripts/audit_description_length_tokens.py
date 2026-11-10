#!/usr/bin/env python3
"""Añade conteos del tokenizer CLIP sin cargar modelos ni pesos."""
from __future__ import annotations
import argparse,hashlib,json,os
from pathlib import Path
import clip
def main()->int:
 p=argparse.ArgumentParser();p.add_argument('--manifest',type=Path,required=True);a=p.parse_args();document=json.loads(a.manifest.read_text())
 for row in document['variants']:
  tokens=clip.tokenize([row['text_es']],context_length=300,truncate=False);row['token_count']=int((tokens[0]!=0).sum().item());row['token_count_method']='openai_clip_tokenize_context_300_including_sot_eot'
 payload=json.dumps(document,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()+b'\n';temporary=a.manifest.with_name('.manifest.tokens.tmp');temporary.write_bytes(payload);os.replace(temporary,a.manifest);a.manifest.with_name('manifest.sha256').write_text(hashlib.sha256(payload).hexdigest()+'  manifest.json\n');return 0
if __name__=='__main__':raise SystemExit(main())
