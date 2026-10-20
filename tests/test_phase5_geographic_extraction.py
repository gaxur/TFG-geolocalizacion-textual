import copy
import hashlib
import json
from pathlib import Path
import unittest

import jsonschema

from src.tfg_phase0.f5_geographic_extraction import (
    ExtractionConfig,
    FakeGeographicExtractor,
    GeographicExtractionError,
    QwenGeographicExtractor,
    build_extraction_prompt,
    literal_evidence_schema,
    compare_extraction_set,
    extraction_comparison_id,
    extraction_set_id,
    materialize_extractions,
    parse_and_validate_extraction,
    parse_resolve_and_validate_extraction,
    validate_extraction_set_against_sidecar,
)
from src.tfg_phase0.f5_text_transform import TransformResult, TransformerMetadata
from src.tfg_phase0.f5_textual_variants import textual_variant_dataset_id
from src.tfg_phase0.validation import SchemaValidationError, validate_document


ROOT = Path(__file__).resolve().parents[1]


def evidence(text, mention, support="explicit"):
    start = text.index(mention)
    return {"text": mention, "span": {"start": start, "end": start + len(mention)}, "support": support}


def empty_orientation():
    return {"status": "unknown", "cardinal": None, "bearing_degrees": None, "reference_frame": "unknown", "evidence": None}


def extraction(entities=(), relations=(), negations=(), ambiguities=(), orientation=None):
    return {"schema_version": "1.0", "entities": list(entities), "relations": list(relations), "negations": list(negations), "observer_orientation": orientation or empty_orientation(), "ambiguities": list(ambiguities)}


def entity(text, entity_id, kind, mention, *, name=None, negated=False, attributes=()):
    return {"entity_id": entity_id, "type": kind, "name": name, "negated": negated, "attributes": list(attributes), "evidence": evidence(text, mention)}


def relation(text, relation_id, subject, predicate, objects, mention, frame="none", negated=False):
    return {"relation_id": relation_id, "subject": subject, "predicate": predicate, "object_ids": list(objects), "negated": negated, "reference_frame": frame, "evidence": evidence(text, mention)}


def reviewed_variant(variant_id, kind, text, language):
    return {"variant_id": variant_id, "kind": kind, "status": "reviewed", "text": text, "language": language, "generation": {"method": "original" if kind == "es_original" else ("model_assisted_cartographic_rewrite" if kind == "es_cartographic" else "model_assisted_translation"), "tool_or_model": "fixture", "version": "v1", "configuration_or_prompt": "fixture", "transformation_time_ms": None}, "review_status": "reviewed", "transformations": ["preserve_original"] if kind == "es_original" else (["cartographic_filter"] if kind == "es_cartographic" else ["translation"]), "preserved_elements": [], "removed_elements": [], "modified_elements": [], "protected_toponyms": []}


def sidecar(texts):
    document = json.loads((ROOT / "config/madrid_f51_textual_variants_template.json").read_text())
    original = texts["es_original"]
    start = original.find("Plaza Mayor")
    toponyms = [] if start < 0 else [{"mention": "Plaza Mayor", "span": {"start": start, "end": start + 12}, "entity_type": "square", "name_kind": "proper_name", "aliases": [], "annotation_provenance": "manual", "review_status": "reviewed"}]
    document["dataset_version"] = "f53-fixture-v1"
    document["observations"] = [{"source_query_id": "f53-source", "source_input_sha256": "1" * 64, "partition": "development", "location_id": None, "derivation_group_id": "f53-group", "toponyms": toponyms, "orientation": {"status": "absent", "cardinal": None, "bearing_degrees": None, "bearing_convention": None, "method": None, "uncertainty_degrees": None, "provenance": None, "verification_status": "not_applicable", "relative_relations_present": False, "notes": None}, "variants": [reviewed_variant(f"v-{kind}", kind, texts[kind], "es" if kind.startswith("es_") else "en") for kind in ("es_original", "es_cartographic", "en_conventional", "en_toponym_preserved")], "notes": "fixture"}]
    if toponyms:
        document["observations"][0]["variants"][3]["transformations"] = ["translation", "toponym_protection"]
        document["observations"][0]["variants"][3]["protected_toponyms"] = ["Plaza Mayor"]
    document["dataset_id"] = textual_variant_dataset_id(document)
    return document


class Phase5GeographicExtractionTests(unittest.TestCase):
    class AdapterStub:
        def __init__(self, outputs):
            self.outputs = iter(outputs); self.calls = 0; self.closed = False
            self.metadata = TransformerMetadata("stub", "stub", "v1", "stub", "v1", "0" * 64, False)
        def generate_prompt(self, prompt, config):
            self.calls += 1; value = next(self.outputs); return TransformResult(value, value, 1.0)
        def close(self): self.closed = True

    def test_schema_accepts_realistic_set(self):
        text = "Estoy cerca de Plaza Mayor"
        ext = extraction([entity(text, "e1", "square", "Plaza Mayor", name="Plaza Mayor")], [relation(text, "r1", "observer", "near", ["e1"], "cerca de")])
        sc = sidecar({kind: text if kind.startswith("es_") else "I am near Plaza Mayor" for kind in ("es_original", "es_cartographic", "en_conventional", "en_toponym_preserved")})
        fake = FakeGeographicExtractor({text: json.dumps(ext), "I am near Plaza Mayor": json.dumps(extraction([entity("I am near Plaza Mayor", "e1", "square", "Plaza Mayor", name="Plaza Mayor")], [relation("I am near Plaza Mayor", "r1", "observer", "near", ["e1"], "near")]))})
        document = materialize_extractions(sc, fake, ExtractionConfig(max_attempts=1), sidecar_logical_path="sidecar.json", sidecar_sha256="2" * 64)
        schema = json.loads((ROOT / "schemas/f5_geographic_extraction_set.schema.json").read_text())
        jsonschema.Draft202012Validator.check_schema(schema); jsonschema.validate(document, schema); validate_document(document, "f5_geographic_extraction_set")
        self.assertEqual(document["extraction_set_id"], extraction_set_id(document)); self.assertEqual(len(document["records"]), 4)

    def test_literal_evidence_generation_schema_is_valid(self):
        jsonschema.Draft202012Validator.check_schema(literal_evidence_schema())

    def test_fake_extractor_uses_literal_resolution_strategy(self):
        text = "Estoy en una plaza"
        value = extraction([entity(text, "e1", "square", "una plaza")])
        del value["entities"][0]["evidence"]["span"]
        result = FakeGeographicExtractor({text: json.dumps(value)}).extract(text, "es", [], ExtractionConfig(max_attempts=1, strategy="literal_evidence"))
        self.assertTrue(result.validation["semantically_valid"])
        self.assertEqual(result.extraction["entities"][0]["evidence"]["span"], {"start": 9, "end": 18})

    def test_invalid_json_can_retry_and_raw_hashes_are_preserved(self):
        text = "Estoy en una plaza"
        valid = json.dumps(extraction([entity(text, "e1", "square", "una plaza")]))
        result = FakeGeographicExtractor({text: ("not-json", valid)}).extract(text, "es", [], ExtractionConfig(max_attempts=2))
        self.assertEqual(len(result.raw_outputs), 2); self.assertTrue(result.validation["semantically_valid"])

    def test_qwen_extractor_retries_once_and_preserves_raw_attempts(self):
        text = "Estoy en una plaza"
        valid = json.dumps(extraction([entity(text, "e1", "square", "una plaza")]))
        adapter = self.AdapterStub(("invalid", valid)); extractor = QwenGeographicExtractor(adapter)
        result = extractor.extract(text, "es", [], ExtractionConfig(max_attempts=2))
        self.assertEqual(adapter.calls, 2); self.assertEqual(result.raw_outputs, ("invalid", valid)); self.assertTrue(result.validation["semantically_valid"])
        extractor.close(); self.assertTrue(adapter.closed)

    def test_duplicate_ids_unknown_references_and_between_arity_are_rejected(self):
        text = "Estoy entre una plaza y un parque"
        entities = [entity(text, "e1", "square", "una plaza"), entity(text, "e1", "park", "un parque")]
        ext = extraction(entities, [relation(text, "r1", "observer", "between", ["e1"], "entre")])
        _, validation = parse_and_validate_extraction(text, "es", [], json.dumps(ext))
        codes = {row["code"] for row in validation["issues"]}
        self.assertIn("duplicate_entity_id", codes); self.assertIn("between_requires_two_objects", codes)
        ext = extraction([entity(text, "e1", "square", "una plaza")], [relation(text, "r1", "observer", "near", ["missing"], "entre")])
        _, validation = parse_and_validate_extraction(text, "es", [], json.dumps(ext)); self.assertIn("unknown_relation_reference", {row["code"] for row in validation["issues"]})

    def test_evidence_spans_and_protected_toponyms_are_enforced(self):
        text = "Estoy cerca de Plaza Mayor"
        ext = extraction([entity(text, "e1", "square", "Plaza Mayor", name="Plaza Mayor")])
        ext["entities"][0]["evidence"]["span"]["start"] += 1
        _, validation = parse_and_validate_extraction(text, "es", ["Plaza Mayor"], json.dumps(ext)); self.assertIn("evidence_span_mismatch", {row["code"] for row in validation["issues"]})
        ext = extraction([entity(text, "e1", "square", "Plaza Mayor")])
        _, validation = parse_and_validate_extraction(text, "es", ["Plaza Mayor"], json.dumps(ext)); self.assertIn("protected_toponym_missing", {row["code"] for row in validation["issues"]})

    def test_literal_evidence_offsets_are_resolved_only_when_unique(self):
        text = "Estoy cerca de Plaza Mayor"
        ext = extraction([entity(text, "e1", "square", "Plaza Mayor", name="Plaza Mayor")])
        del ext["entities"][0]["evidence"]["span"]
        parsed, validation = parse_resolve_and_validate_extraction(text, "es", ["Plaza Mayor"], json.dumps(ext))
        self.assertTrue(validation["semantically_valid"])
        self.assertEqual(parsed["entities"][0]["evidence"]["span"], {"start": 15, "end": 26})
        repeated = "plaza y plaza"
        ext = extraction([entity(repeated, "e1", "square", "plaza")])
        del ext["entities"][0]["evidence"]["span"]
        _, validation = parse_resolve_and_validate_extraction(repeated, "es", [], json.dumps(ext))
        self.assertIn("evidence_not_unique", {row["code"] for row in validation["issues"]})

    def test_negation_requires_explicit_index_and_target_kind(self):
        text = "No hay ningún parque cerca"
        park = entity(text, "e1", "park", "ningún parque", negated=True)
        ext = extraction([park])
        _, validation = parse_and_validate_extraction(text, "es", [], json.dumps(ext)); self.assertIn("negation_index_mismatch", {row["code"] for row in validation["issues"]})
        negation = {"negation_id": "n1", "target_kind": "entity", "target_id": "e1", "evidence": evidence(text, "No")}
        ext = extraction([park], negations=[negation]); _, validation = parse_and_validate_extraction(text, "es", [], json.dumps(ext)); self.assertTrue(validation["semantically_valid"])
        ext["negations"][0]["target_kind"] = "relation"; _, validation = parse_and_validate_extraction(text, "es", [], json.dumps(ext)); self.assertIn("negation_target_kind_mismatch", {row["code"] for row in validation["issues"]})

    def test_orientation_and_egocentric_relations_do_not_infer_cardinal(self):
        text = "Veo una iglesia a mi izquierda"
        church = entity(text, "e1", "church", "una iglesia")
        rel = relation(text, "r1", "e1", "left_of_observer", ["observer"], "a mi izquierda", frame="egocentric")
        ext = extraction([church], [rel]); _, validation = parse_and_validate_extraction(text, "es", [], json.dumps(ext)); self.assertTrue(validation["semantically_valid"]); self.assertEqual(ext["observer_orientation"]["status"], "unknown")
        ext["observer_orientation"] = {"status": "verified", "cardinal": "north", "bearing_degrees": None, "reference_frame": "cardinal", "evidence": evidence(text, "izquierda")}
        _, validation = parse_and_validate_extraction(text, "es", [], json.dumps(ext)); self.assertIn("orientation_cannot_be_verified_from_text", {row["code"] for row in validation["issues"]})

    def test_reported_cardinal_orientation_needs_literal_evidence(self):
        text = "Estoy mirando al norte junto a una plaza"
        square = entity(text, "e1", "square", "una plaza")
        orientation = {"status": "reported", "cardinal": "north", "bearing_degrees": None, "reference_frame": "cardinal", "evidence": evidence(text, "mirando al norte")}
        ext = extraction([square], orientation=orientation); _, validation = parse_and_validate_extraction(text, "es", [], json.dumps(ext)); self.assertTrue(validation["semantically_valid"])

    def test_ambiguity_and_no_geographic_content(self):
        text = "Estoy en algún lugar"
        ambiguity = {"ambiguity_id": "a1", "kind": "insufficient_information", "description": "No hay elementos geográficos suficientes", "entity_ids": [], "relation_ids": [], "evidence": None}
        ext = extraction(ambiguities=[ambiguity]); _, validation = parse_and_validate_extraction(text, "es", [], json.dumps(ext)); self.assertTrue(validation["semantically_valid"])
        ext = extraction(); _, validation = parse_and_validate_extraction(text, "es", [], json.dumps(ext)); self.assertIn("no_geographic_content", {row["code"] for row in validation["issues"]})

    def test_sidecar_provenance_is_exact_and_identity_detects_tampering(self):
        texts = {kind: "Estoy en una plaza" if kind.startswith("es_") else "I am in a square" for kind in ("es_original", "es_cartographic", "en_conventional", "en_toponym_preserved")}
        sc = sidecar(texts); ext_es = json.dumps(extraction([entity(texts["es_original"], "e1", "square", "una plaza")])) ; ext_en = json.dumps(extraction([entity(texts["en_conventional"], "e1", "square", "a square")]))
        document = materialize_extractions(sc, FakeGeographicExtractor({texts["es_original"]: ext_es, texts["en_conventional"]: ext_en}), ExtractionConfig(512, 0, 1), sidecar_logical_path="sidecar.json", sidecar_sha256="2" * 64)
        validate_extraction_set_against_sidecar(document, sc, sidecar_sha256="2" * 64)
        document["records"][0]["input_text"] += " alterado"; document["extraction_set_id"] = extraction_set_id(document)
        with self.assertRaises(GeographicExtractionError): validate_extraction_set_against_sidecar(document, sc, sidecar_sha256="2" * 64)

    def test_extraction_set_identity_changes_on_tampering(self):
        text = "Estoy en una plaza"; sc = sidecar({kind: text if kind.startswith("es_") else "I am in a square" for kind in ("es_original", "es_cartographic", "en_conventional", "en_toponym_preserved")})
        es = json.dumps(extraction([entity(text, "e1", "square", "una plaza")])); en_text = "I am in a square"; en = json.dumps(extraction([entity(en_text, "e1", "square", "a square")]))
        document = materialize_extractions(sc, FakeGeographicExtractor({text: es, en_text: en}), ExtractionConfig(max_attempts=1), sidecar_logical_path="s.json", sidecar_sha256="2" * 64)
        original_id = document["extraction_set_id"]; document["records"][0]["duration_ms"] += 1
        self.assertNotEqual(original_id, extraction_set_id(document))

    def test_comparison_uses_semantic_signatures_not_local_ids(self):
        es = "Estoy cerca de una plaza"
        en = "I am near a square"
        sc = sidecar({"es_original": es, "es_cartographic": es, "en_conventional": en, "en_toponym_preserved": en})
        ext_es = extraction([entity(es, "e1", "square", "una plaza")], [relation(es, "r1", "observer", "near", ["e1"], "cerca")])
        ext_en = extraction([entity(en, "e9", "square", "a square")], [relation(en, "r7", "observer", "near", ["e9"], "near")])
        document = materialize_extractions(sc, FakeGeographicExtractor({es: json.dumps(ext_es), en: json.dumps(ext_en)}), ExtractionConfig(512, 0, 1), sidecar_logical_path="sidecar.json", sidecar_sha256="2" * 64)
        raw = json.dumps(document, sort_keys=True).encode(); report = compare_extraction_set(document, extraction_set_sha256=hashlib.sha256(raw).hexdigest())
        self.assertEqual(len(report["comparisons"]), 3); self.assertTrue(all(row["entity_jaccard"] == 1 for row in report["comparisons"])); self.assertTrue(all(row["relation_jaccard"] == 1 for row in report["comparisons"])); self.assertEqual(report["comparison_id"], extraction_comparison_id(report)); validate_document(report, "f5_geographic_extraction_comparison")

    def test_opposite_relations_and_negation_changes_are_flagged(self):
        left_text, right_text = "La iglesia está a mi izquierda", "The church is on my right"
        left = extraction([entity(left_text, "e1", "church", "La iglesia")], [relation(left_text, "r1", "e1", "left_of_observer", ["observer"], "a mi izquierda", frame="egocentric")])
        right = extraction([entity(right_text, "e2", "church", "The church")], [relation(right_text, "r2", "e2", "right_of_observer", ["observer"], "on my right", frame="egocentric")])
        sc = sidecar({"es_original": left_text, "es_cartographic": left_text, "en_conventional": right_text, "en_toponym_preserved": right_text})
        document = materialize_extractions(sc, FakeGeographicExtractor({left_text: json.dumps(left), right_text: json.dumps(right)}), ExtractionConfig(512, 0, 1), sidecar_logical_path="sidecar.json", sidecar_sha256="2" * 64)
        report = compare_extraction_set(document, extraction_set_sha256="3" * 64); rows = [row for row in report["comparisons"] if row["variant_kind"] == "en_conventional"]
        self.assertIn("left_of_observer_vs_right_of_observer", rows[0]["potential_contradictions"])

    def test_fake_extractor_closes_and_qwen_prompt_contains_no_ground_truth(self):
        prompt = build_extraction_prompt("Estoy en una plaza", "es", [])
        self.assertNotIn("ground truth", prompt.casefold()); self.assertNotIn("candidate", prompt.casefold()); self.assertNotIn("osm", prompt.casefold())
        fake = FakeGeographicExtractor({"x": json.dumps(extraction(ambiguities=[{"ambiguity_id": "a1", "kind": "insufficient_information", "description": "sin información", "entity_ids": [], "relation_ids": [], "evidence": None}]))}); fake.close()
        with self.assertRaises(GeographicExtractionError): fake.extract("x", "es", [], ExtractionConfig())


if __name__ == "__main__": unittest.main()
