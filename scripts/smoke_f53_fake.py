#!/usr/bin/env python3
"""Smoke técnico F5.3 con 10 casos y extractor fake; no valida Qwen."""

from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.f5_geographic_extraction import ExtractionConfig, FakeGeographicExtractor, compare_extraction_set, materialize_extractions
from src.tfg_phase0.f5_textual_variants import textual_variant_dataset_id
from src.tfg_phase0.validation import validate_document


CASES = (
    "Estoy cerca de Plaza Mayor, junto a una calle estrecha.",
    "Hay un parque grande al lado de una avenida.",
    "Estoy en la intersección de dos calles.",
    "No hay ningún parque cerca de esta intersección.",
    "La estación está al norte de la plaza.",
    "Veo una iglesia a mi izquierda.",
    "Estoy junto a una plaza; mi orientación es desconocida.",
    "Estoy cerca de Sol.",
    "Estoy entre una plaza, una iglesia y una estación.",
    "El ambiente es agradable.",
)


def ev(text: str, mention: str):
    start = text.index(mention); return {"text": mention, "span": {"start": start, "end": start + len(mention)}, "support": "explicit"}


def entity(text, eid, kind, mention, *, name=None, negated=False):
    return {"entity_id": eid, "type": kind, "name": name, "negated": negated, "attributes": [], "evidence": ev(text, mention)}


def base(entities=(), relations=(), negations=(), ambiguities=()):
    return {"schema_version": "1.0", "entities": list(entities), "relations": list(relations), "negations": list(negations), "observer_orientation": {"status": "unknown", "cardinal": None, "bearing_degrees": None, "reference_frame": "unknown", "evidence": None}, "ambiguities": list(ambiguities)}


def outputs():
    rows = {}
    t = CASES[0]; rows[t] = base([entity(t,"e1","square","Plaza Mayor",name="Plaza Mayor"),entity(t,"e2","street","una calle")],[{"relation_id":"r1","subject":"observer","predicate":"near","object_ids":["e1"],"negated":False,"reference_frame":"none","evidence":ev(t,"cerca de")},{"relation_id":"r2","subject":"observer","predicate":"next_to","object_ids":["e2"],"negated":False,"reference_frame":"none","evidence":ev(t,"junto a")}])
    t = CASES[1]; rows[t] = base([entity(t,"e1","park","un parque grande"),entity(t,"e2","road","una avenida")],[{"relation_id":"r1","subject":"e1","predicate":"next_to","object_ids":["e2"],"negated":False,"reference_frame":"none","evidence":ev(t,"al lado de")}])
    t = CASES[2]; rows[t] = base([entity(t,"e1","intersection","la intersección"),entity(t,"e2","street","dos calles")])
    t = CASES[3]; park=entity(t,"e1","park","ningún parque",negated=True); rows[t]=base([park],negations=[{"negation_id":"n1","target_kind":"entity","target_id":"e1","evidence":ev(t,"No")}])
    t = CASES[4]; rows[t]=base([entity(t,"e1","station","La estación"),entity(t,"e2","square","la plaza")],[{"relation_id":"r1","subject":"e1","predicate":"north_of","object_ids":["e2"],"negated":False,"reference_frame":"cardinal","evidence":ev(t,"al norte de")}])
    t = CASES[5]; rows[t]=base([entity(t,"e1","church","una iglesia")],[{"relation_id":"r1","subject":"e1","predicate":"left_of_observer","object_ids":["observer"],"negated":False,"reference_frame":"egocentric","evidence":ev(t,"a mi izquierda")}])
    t = CASES[6]; rows[t]=base([entity(t,"e1","square","una plaza")],ambiguities=[{"ambiguity_id":"a1","kind":"insufficient_information","description":"Orientación no indicada","entity_ids":["e1"],"relation_ids":[],"evidence":ev(t,"orientación es desconocida")}])
    t = CASES[7]; rows[t]=base([entity(t,"e1","unknown","Sol",name="Sol")],ambiguities=[{"ambiguity_id":"a1","kind":"ambiguous_reference","description":"Sol puede referir a distintos lugares","entity_ids":["e1"],"relation_ids":[],"evidence":ev(t,"Sol")}])
    t = CASES[8]; rows[t]=base([entity(t,"e1","square","una plaza"),entity(t,"e2","church","una iglesia"),entity(t,"e3","station","una estación")],[{"relation_id":"r1","subject":"observer","predicate":"between","object_ids":["e1","e2"],"negated":False,"reference_frame":"none","evidence":ev(t,"entre") }],ambiguities=[{"ambiguity_id":"a1","kind":"incomplete_relation","description":"La tercera entidad no queda integrada en la relación between binaria","entity_ids":["e3"],"relation_ids":["r1"],"evidence":ev(t,"y una estación")}])
    t = CASES[9]; rows[t]=base(ambiguities=[{"ambiguity_id":"a1","kind":"insufficient_information","description":"Sin elementos geográficos identificables","entity_ids":[],"relation_ids":[],"evidence":None}])
    return {text: json.dumps(value,ensure_ascii=False) for text,value in rows.items()}


def sidecar():
    template=json.loads((ROOT/'config/madrid_f51_textual_variants_template.json').read_text()); observations=[]
    for index,text in enumerate(CASES,1):
        variant={"variant_id":f"f53-technical-{index:02d}-es-original","kind":"es_original","status":"reviewed","text":text,"language":"es","generation":{"method":"original","tool_or_model":"manual","version":"v1","configuration_or_prompt":"technical","transformation_time_ms":None},"review_status":"reviewed","transformations":["preserve_original"],"preserved_elements":[],"removed_elements":[],"modified_elements":[],"protected_toponyms":[]}
        observations.append({"source_query_id":f"f53-technical-{index:02d}","source_input_sha256":"1"*64,"partition":"development","location_id":None,"derivation_group_id":f"f53-technical-{index:02d}","toponyms":[],"orientation":{"status":"absent","cardinal":None,"bearing_degrees":None,"bearing_convention":None,"method":None,"uncertainty_degrees":None,"provenance":None,"verification_status":"not_applicable","relative_relations_present":False,"notes":None},"variants":[variant],"notes":"technical smoke"})
    template["dataset_version"]="f53-technical-smoke-v1"; template["observations"]=observations; template["dataset_id"]=textual_variant_dataset_id(template); return template


def main():
    source=sidecar(); extractor=FakeGeographicExtractor(outputs()); document=materialize_extractions(source,extractor,ExtractionConfig(max_attempts=1),sidecar_logical_path="technical-sidecar.json",sidecar_sha256="2"*64); extractor.close(); validate_document(document,"f5_geographic_extraction_set"); report=compare_extraction_set(document,extraction_set_sha256="3"*64); validate_document(report,"f5_geographic_extraction_comparison"); print(json.dumps({"status":"pass","technical_fake_only":True,"records":len(document["records"]),"valid":sum(r["status"]=="valid" for r in document["records"]),"comparisons":len(report["comparisons"]),"accuracy_available":False},sort_keys=True)); return 0


if __name__=="__main__": raise SystemExit(main())
