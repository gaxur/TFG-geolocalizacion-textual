import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import jsonschema

from src.tfg_phase0.catalog import build_catalog, write_manifest
from src.tfg_phase0.config import load_region_config
from src.tfg_phase0.f4_evaluation import assign_reference, query_dataset_id
from src.tfg_phase0.f4_validation import load_verified_f1_50m
from src.tfg_phase0.f5_textual_variants import (
    F5ValidationError,
    paired_variant_plan,
    source_query_input_sha256,
    textual_variant_dataset_id,
    validate_textual_variant_dataset,
)
from src.tfg_phase0.validation import SchemaValidationError, validate_document


ROOT = Path(__file__).resolve().parents[1]
ZERO_HASH = "0" * 64


class Phase5TextualVariantTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = load_region_config(ROOT / "config/madrid.yaml")
        cls.temporary = tempfile.TemporaryDirectory()
        cls.manifest_path = Path(cls.temporary.name) / "manifest-50m.json"
        write_manifest(build_catalog(cls.config, spacing_m=50), cls.manifest_path)
        cls.catalog = load_verified_f1_50m(cls.manifest_path, cls.config)
        cls.schema = json.loads((ROOT / "schemas/f5_textual_variant_dataset.schema.json").read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def source_query(self, query_id="obs-001", partition="development", candidate_index=40, *, validated=True, text="Estoy cerca de Plaza Mayor y junto a una calle estrecha"):
        candidate = self.catalog.candidates[candidate_index]
        query = {
            "query_id": query_id,
            "location_id": f"loc-{candidate_index}" if validated or partition == "evaluation" else None,
            "derivation_group_id": f"derivation-{query_id}",
            "partition": partition,
            "description": {"text": text, "language": "es", "contains_coordinates": False},
            "provenance": {"source_type": "human_in_situ" if validated else "technical_probe", "description": "Fixture sintética de software; no es una observación del TFG.", "independent_environment_observation": validated, "instructions_version": "fixture-f51-v1", "collected_at_utc": "2026-10-19T12:00:00Z" if validated else None},
            "reference": {"status": "validated" if validated else "pending", "latitude": candidate.latitude if validated else None, "longitude": candidate.longitude if validated else None, "crs": "EPSG:4326" if validated else None, "capture_method": "synthetic_candidate_center" if validated else None, "reported_accuracy_m": 0.0 if validated else None, "validation_method": "fixture" if validated else None, "catalog_assignment": None},
            "ambiguity": {"status": "not_ambiguous" if validated else "unreviewed", "notes": None},
            "validation_status": "validated" if validated else "pending",
        }
        if validated:
            query["reference"]["catalog_assignment"] = assign_reference(candidate.latitude, candidate.longitude, self.catalog, reported_accuracy_m=0.0)
        return query

    def source_dataset(self, queries):
        document = {
            "schema_version": "1.0", "contract_version": "f4-query-dataset-v1", "dataset_id": "f4-madrid-queries-sha256-" + ZERO_HASH, "dataset_version": "fixture-f51-v1",
            "region": {"region_id": "madrid_pilot", "bbox_wgs84": dict(self.config["region"]["bbox"])},
            "catalog": {"manifest_id": self.catalog.manifest_id, "manifest_sha256": self.catalog.sha256, "candidate_count": 253, "assignment_policy": "projected_cell_interior_boundary_ambiguous_v1"},
            "partition_policy": {"version": "location-and-derivation-group-v1", "group_by": ["location_id", "derivation_group_id"], "evaluation_frozen": False, "evaluation_use_restriction": "no_parameter_prompt_checkpoint_or_pipeline_selection", "near_duplicate_token_jaccard_threshold": 0.8},
            "queries": queries,
        }
        document["dataset_id"] = query_dataset_id(document)
        return document

    def pending_variant(self, kind):
        return {
            "variant_id": None, "kind": kind, "status": "pending", "text": None,
            "language": "es" if kind.startswith("es_") else "en",
            "generation": {"method": "pending", "tool_or_model": None, "version": None, "configuration_or_prompt": None, "transformation_time_ms": None},
            "review_status": "pending", "transformations": [], "preserved_elements": [], "removed_elements": [], "modified_elements": [], "protected_toponyms": [],
        }

    def reviewed_variant(self, kind, text, method, transformations, *, protected=()):
        return {
            "variant_id": f"obs-001-{kind}-v1", "kind": kind, "status": "reviewed", "text": text,
            "language": "es" if kind.startswith("es_") else "en",
            "generation": {"method": method, "tool_or_model": "manual", "version": "v1", "configuration_or_prompt": "f51-fixture", "transformation_time_ms": 1.0},
            "review_status": "reviewed", "transformations": transformations, "preserved_elements": ["Plaza Mayor", "calle estrecha"], "removed_elements": [], "modified_elements": [], "protected_toponyms": list(protected),
        }

    def orientation_absent(self, *, relative=False):
        return {"status": "absent", "cardinal": None, "bearing_degrees": None, "bearing_convention": None, "method": None, "uncertainty_degrees": None, "provenance": None, "verification_status": "not_applicable", "relative_relations_present": relative, "notes": None}

    def observation(self, source, *, complete=False):
        start = source["description"]["text"].index("Plaza Mayor")
        toponyms = [{"mention": "Plaza Mayor", "span": {"start": start, "end": start + len("Plaza Mayor")}, "entity_type": "square", "name_kind": "proper_name", "aliases": ["Plaza Mayor de Madrid"], "annotation_provenance": "manual", "review_status": "reviewed"}]
        if complete:
            variants = [
                self.reviewed_variant("es_original", source["description"]["text"], "original", ["preserve_original"]),
                self.reviewed_variant("es_cartographic", "Estoy cerca de Plaza Mayor y junto a una calle estrecha", "manual_cartographic_rewrite", ["cartographic_filter"]),
                self.reviewed_variant("en_conventional", "I am near the Main Square and next to a narrow street", "manual_translation", ["translation"]),
                self.reviewed_variant("en_toponym_preserved", "I am near Plaza Mayor and next to a narrow street", "manual_translation", ["translation", "toponym_protection"], protected=["Plaza Mayor"]),
            ]
        else:
            variants = [
                self.reviewed_variant("es_original", source["description"]["text"], "original", ["preserve_original"]),
                self.pending_variant("es_cartographic"), self.pending_variant("en_conventional"), self.pending_variant("en_toponym_preserved"),
            ]
        return {"source_query_id": source["query_id"], "source_input_sha256": source_query_input_sha256(source), "partition": source["partition"], "location_id": source["location_id"], "derivation_group_id": source["derivation_group_id"], "toponyms": toponyms, "orientation": self.orientation_absent(), "variants": variants, "notes": None}

    def sidecar(self, source, observations):
        source_raw = json.dumps(source, sort_keys=True).encode()
        document = json.loads((ROOT / "config/madrid_f51_textual_variants_template.json").read_text(encoding="utf-8"))
        document["dataset_version"] = "fixture-f51-v1"
        document["source_query_dataset"] = {"dataset_id": source["dataset_id"], "sha256": hashlib.sha256(source_raw).hexdigest()}
        document["observations"] = observations
        document["dataset_id"] = textual_variant_dataset_id(document)
        return document, hashlib.sha256(source_raw).hexdigest()

    def validate(self, document, source, source_hash):
        return validate_textual_variant_dataset(document, source, source_sha256=source_hash, catalog=self.catalog)

    def test_schema_and_empty_template_are_valid_and_have_no_metrics(self):
        jsonschema.Draft202012Validator.check_schema(self.schema)
        template = json.loads((ROOT / "config/madrid_f51_textual_variants_template.json").read_text(encoding="utf-8"))
        jsonschema.validate(template, self.schema)
        source = json.loads((ROOT / "config/madrid_f43_query_dataset_draft.json").read_text(encoding="utf-8"))
        summary = self.validate(template, source, template["source_query_dataset"]["sha256"])
        self.assertEqual(summary["observation_count"], 0)
        self.assertEqual(summary["validated_ground_truth_count"], 0)
        self.assertFalse(summary["precision_metrics_available"])

    def test_v2_template_adds_en_cartographic_without_reinterpreting_v1(self):
        legacy = json.loads((ROOT / "config/madrid_f51_textual_variants_template.json").read_text(encoding="utf-8"))
        current = json.loads((ROOT / "config/madrid_f53b_textual_variants_template.json").read_text(encoding="utf-8"))
        self.assertEqual(legacy["contract_version"], "f5-textual-variant-dataset-v1")
        self.assertEqual(legacy["protocol"]["variant_kinds"], ["es_original", "es_cartographic", "en_conventional", "en_toponym_preserved"])
        self.assertEqual(current["contract_version"], "f5-textual-variant-dataset-v2")
        self.assertEqual(current["protocol"]["variant_kinds"][-1], "en_cartographic")
        validate_document(legacy, "f5_textual_variant_dataset")

    def test_valid_partial_observation_preserves_pending_variants(self):
        query = self.source_query()
        source = self.source_dataset([query])
        document, source_hash = self.sidecar(source, [self.observation(query)])
        jsonschema.validate(document, self.schema)
        validate_document(document, "f5_textual_variant_dataset")
        summary = self.validate(document, source, source_hash)
        self.assertEqual(summary["variant_status_counts"]["es_original"]["reviewed"], 1)
        self.assertEqual(summary["variant_status_counts"]["en_conventional"]["pending"], 1)
        self.assertEqual(summary["paired_comparison_ready_count"], 0)

    def test_complete_variants_generate_six_paired_comparisons(self):
        query = self.source_query()
        source = self.source_dataset([query])
        document, source_hash = self.sidecar(source, [self.observation(query, complete=True)])
        summary = self.validate(document, source, source_hash)
        self.assertEqual(summary["complete_observation_count"], 1)
        self.assertEqual(len(paired_variant_plan(document)), 6)

    def test_identity_and_source_reference_tampering_are_rejected(self):
        query = self.source_query()
        source = self.source_dataset([query])
        document, source_hash = self.sidecar(source, [self.observation(query)])
        document["observations"][0]["notes"] = "tampered"
        with self.assertRaises(F5ValidationError):
            self.validate(document, source, source_hash)
        document["dataset_id"] = textual_variant_dataset_id(document)
        document["source_query_dataset"]["sha256"] = "f" * 64
        document["dataset_id"] = textual_variant_dataset_id(document)
        with self.assertRaises(F5ValidationError):
            self.validate(document, source, source_hash)

    def test_missing_query_and_partition_mismatch_are_rejected(self):
        query = self.source_query()
        source = self.source_dataset([query])
        observation = self.observation(query)
        observation["source_query_id"] = "missing"
        document, source_hash = self.sidecar(source, [observation])
        with self.assertRaises(F5ValidationError):
            self.validate(document, source, source_hash)
        observation = self.observation(query)
        observation["partition"] = "evaluation"
        document, source_hash = self.sidecar(source, [observation])
        with self.assertRaises(F5ValidationError):
            self.validate(document, source, source_hash)

    def test_duplicate_observation_and_variant_id_are_rejected(self):
        query = self.source_query()
        source = self.source_dataset([query])
        observation = self.observation(query)
        document, source_hash = self.sidecar(source, [observation, copy.deepcopy(observation)])
        with self.assertRaises(F5ValidationError):
            self.validate(document, source, source_hash)
        complete = self.observation(query, complete=True)
        complete["variants"][1]["variant_id"] = complete["variants"][0]["variant_id"]
        document, source_hash = self.sidecar(source, [complete])
        with self.assertRaises(F5ValidationError):
            self.validate(document, source, source_hash)

    def test_pending_ground_truth_is_valid_but_metrics_remain_unavailable(self):
        query = self.source_query(validated=False)
        source = self.source_dataset([query])
        document, source_hash = self.sidecar(source, [self.observation(query)])
        summary = self.validate(document, source, source_hash)
        self.assertEqual(summary["reference_status_counts"], {"pending": 1})
        self.assertEqual(summary["catalog_assignment_status_counts"], {"unavailable": 1})
        self.assertFalse(summary["precision_metrics_available"])

    def test_invalid_source_coordinate_and_accuracy_are_rejected_by_f43(self):
        query = self.source_query()
        query["reference"]["latitude"] = 91
        source = self.source_dataset([query])
        document, source_hash = self.sidecar(source, [self.observation(query)])
        with self.assertRaises(F5ValidationError):
            self.validate(document, source, source_hash)
        query = self.source_query()
        query["reference"]["reported_accuracy_m"] = -1
        source = self.source_dataset([query])
        document, source_hash = self.sidecar(source, [self.observation(query)])
        with self.assertRaises(F5ValidationError):
            self.validate(document, source, source_hash)

    def test_toponym_span_name_kind_and_aliases_are_validated(self):
        query = self.source_query()
        source = self.source_dataset([query])
        observation = self.observation(query)
        observation["toponyms"].append({"mention": "una calle", "span": {"start": query["description"]["text"].index("una calle"), "end": query["description"]["text"].index("una calle") + len("una calle")}, "entity_type": "street", "name_kind": "generic_expression", "aliases": [], "annotation_provenance": "manual", "review_status": "reviewed"})
        document, source_hash = self.sidecar(source, [observation])
        self.assertEqual(self.validate(document, source, source_hash)["proper_toponym_count"], 1)
        observation["toponyms"][0]["span"]["start"] += 1
        document, source_hash = self.sidecar(source, [observation])
        with self.assertRaises(F5ValidationError):
            self.validate(document, source, source_hash)
        observation = self.observation(query)
        observation["toponyms"][0]["aliases"] = ["Mayor", "MAYOR"]
        document, source_hash = self.sidecar(source, [observation])
        with self.assertRaises(F5ValidationError):
            self.validate(document, source, source_hash)

    def test_optional_orientation_accepts_cardinal_or_bearing_not_both(self):
        query = self.source_query()
        source = self.source_dataset([query])
        observation = self.observation(query)
        observation["orientation"] = {"status": "verified", "cardinal": "north", "bearing_degrees": None, "bearing_convention": None, "method": "compass", "uncertainty_degrees": 5.0, "provenance": "observer_measurement", "verification_status": "verified", "relative_relations_present": True, "notes": "Derecha no se convierte automáticamente a este."}
        document, source_hash = self.sidecar(source, [observation])
        self.validate(document, source, source_hash)
        observation["orientation"]["bearing_degrees"] = 10.0
        observation["orientation"]["bearing_convention"] = "degrees_clockwise_from_true_north"
        document, source_hash = self.sidecar(source, [observation])
        with self.assertRaises(F5ValidationError):
            self.validate(document, source, source_hash)

    def test_variant_language_missing_slots_and_incompatible_original_are_rejected(self):
        query = self.source_query()
        source = self.source_dataset([query])
        observation = self.observation(query)
        observation["variants"].pop()
        document, source_hash = self.sidecar(source, [observation])
        with self.assertRaises((SchemaValidationError, F5ValidationError)):
            self.validate(document, source, source_hash)
        observation = self.observation(query)
        observation["variants"][1]["language"] = "en"
        document, source_hash = self.sidecar(source, [observation])
        with self.assertRaises(F5ValidationError):
            self.validate(document, source, source_hash)
        observation = self.observation(query)
        observation["variants"][0]["text"] += " cambiado"
        document, source_hash = self.sidecar(source, [observation])
        with self.assertRaises(F5ValidationError):
            self.validate(document, source, source_hash)

    def test_toponym_preserved_variant_requires_literal_reviewed_names(self):
        query = self.source_query()
        source = self.source_dataset([query])
        observation = self.observation(query, complete=True)
        observation["variants"][3]["text"] = "I am near the main square and next to a narrow street"
        document, source_hash = self.sidecar(source, [observation])
        with self.assertRaises(F5ValidationError):
            self.validate(document, source, source_hash)

    def test_generated_duplicate_variant_crossing_partitions_is_rejected(self):
        left = self.source_query("obs-dev", "development", 80, text="Estoy cerca de Plaza Mayor y junto a una calle estrecha")
        right = self.source_query("obs-eval", "evaluation", 90, text="Desde Plaza Mayor observo una avenida amplia, edificios altos y un parque distante")
        source = self.source_dataset([left, right])
        left_observation = self.observation(left, complete=True)
        right_observation = self.observation(right, complete=True)
        duplicate = "I am near a square"
        left_observation["variants"][2]["text"] = duplicate
        right_observation["variants"][2]["text"] = duplicate
        document, source_hash = self.sidecar(source, [left_observation, right_observation])
        with self.assertRaises(F5ValidationError):
            self.validate(document, source, source_hash)

    def test_osm_preselection_remains_standby_and_fusion_disabled(self):
        source = self.source_dataset([])
        document, source_hash = self.sidecar(source, [])
        document["protocol"]["osm_preselection_status"] = "implemented"
        document["dataset_id"] = textual_variant_dataset_id(document)
        with self.assertRaises((SchemaValidationError, F5ValidationError)):
            self.validate(document, source, source_hash)
        document, source_hash = self.sidecar(source, [])
        document["comparison_protocol"]["fusion_enabled"] = True
        document["dataset_id"] = textual_variant_dataset_id(document)
        with self.assertRaises((SchemaValidationError, F5ValidationError)):
            self.validate(document, source, source_hash)


if __name__ == "__main__":
    unittest.main()
