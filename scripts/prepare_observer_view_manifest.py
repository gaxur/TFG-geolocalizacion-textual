#!/usr/bin/env python3
"""Materializa un manifest observer_view desde una foto local y metadatos explícitos."""
import argparse,hashlib,json,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from jsonschema import Draft202012Validator
from scripts.run_qwen3_vl_8b_memory_smoke import atomic_write_json
from src.tfg_phase0.dialogue_visual_evidence import RESERVED_SET_EXCLUSION

def main():
    p=argparse.ArgumentParser();p.add_argument('--image',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--image-id',required=True);p.add_argument('--source',required=True);p.add_argument('--author',required=True);p.add_argument('--license-or-authorization',required=True);p.add_argument('--acquired-at-utc');p.add_argument('--provenance-url');p.add_argument('--observer-relation-evidence',required=True);p.add_argument('--usage-restriction',action='append',required=True);p.add_argument('--session-id',required=True);p.add_argument('--intent-family',choices=('square','church','monument','intersection','park','commercial'),required=True);p.add_argument('--authorization-id',required=True);a=p.parse_args()
    image=a.image.resolve();output=a.output.resolve()
    if not image.is_file() or image.parent!=output.parent:raise ValueError('la imagen debe existir directamente junto al manifest')
    from PIL import Image
    with Image.open(image) as value:value.verify();media=value.format
    if media not in {'JPEG','PNG','WEBP'}:raise ValueError('formato no permitido: use JPEG, PNG o WEBP')
    sha=hashlib.sha256(image.read_bytes()).hexdigest();document={'schema_version':'1.0','contract_version':'dialogue-observer-image-manifest-v1','status':'authorized','image_id':a.image_id,'logical_path':image.name,'sha256':sha,'source':a.source,'author':a.author,'license_or_authorization':a.license_or_authorization,'acquired_at_utc':a.acquired_at_utc,'provenance_url':a.provenance_url,'observer_relation':'observer_view','observer_relation_evidence':a.observer_relation_evidence,'usage_restrictions':a.usage_restriction,'reserved_set_exclusion':RESERVED_SET_EXCLUSION,'session_id':a.session_id,'intent_family':a.intent_family,'authorized':True,'authorization_id':a.authorization_id}
    schema=json.loads((ROOT/'schemas/dialogue_observer_image_manifest.schema.json').read_text());Draft202012Validator(schema).validate(document)
    if output.exists():raise ValueError('output ya existe')
    atomic_write_json(output,document);print(json.dumps({'status':'AUTHORIZED_MANIFEST_CREATED','sha256':sha,'format':media,'output':str(output)}));return 0
if __name__=='__main__':raise SystemExit(main())
