import copy
import json
import tempfile
import unittest
from pathlib import Path

from src.tfg_phase0.h16_h23_claim_review import ClaimReviewError, import_complete_review, pending_review, sha256_file, validate_review


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "results/generated/mapillary/h16-h23-multicandidate-top50-v1/fixture.json"
PROTOCOL_PATH = ROOT / "config/h16_h23_top50_experiment.json"


class H16H23ClaimReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not FIXTURE_PATH.exists() or not PROTOCOL_PATH.exists():
            raise unittest.SkipTest("artefactos locales Top-50 ausentes")
        cls.fixture = json.loads(FIXTURE_PATH.read_text())
        cls.protocol = json.loads(PROTOCOL_PATH.read_text())
        cls.fixture_sha = sha256_file(FIXTURE_PATH)
        cls.protocol_sha = sha256_file(PROTOCOL_PATH)

    def complete(self):
        document = pending_review(self.fixture, self.protocol, fixture_sha256=self.fixture_sha, protocol_sha256=self.protocol_sha)
        document["review_status"] = "complete"
        for row in document["records"]:
            row.update({"decision": "approved", "reason": "revisión de prueba", "reviewer": "human-test", "reviewed_at_utc": "2026-10-27T12:00:00Z"})
        return document

    def test_complete_review_imports_and_preserves_provenance(self):
        exported = self.complete()
        result = import_complete_review(exported, self.fixture, self.protocol, fixture_sha256=self.fixture_sha, protocol_sha256=self.protocol_sha, source_export_sha256="a" * 64, previous_canonical_sha256="b" * 64)
        summary = validate_review(result, self.fixture, self.protocol, require_complete=True, fixture_sha256=self.fixture_sha, protocol_sha256=self.protocol_sha)
        self.assertTrue(summary["gate_passed"])
        self.assertEqual(result["provenance"]["source_export_sha256"], "a" * 64)

    def test_incomplete_review_is_rejected_for_gate(self):
        document = self.complete()
        document["records"][0].update({"decision": "pending", "reviewer": None, "reviewed_at_utc": None})
        document["review_status"] = "pending"
        with self.assertRaisesRegex(ClaimReviewError, "incompleta"):
            validate_review(document, self.fixture, self.protocol, require_complete=True, fixture_sha256=self.fixture_sha, protocol_sha256=self.protocol_sha)

    def test_manipulated_claim_is_rejected(self):
        document = self.complete()
        document["records"][0]["claim"]["value"] = {"object_type": "invented"}
        with self.assertRaisesRegex(ClaimReviewError, "manipulado"):
            validate_review(document, self.fixture, self.protocol, require_complete=True, fixture_sha256=self.fixture_sha, protocol_sha256=self.protocol_sha)

    def test_other_protocol_is_rejected(self):
        document = self.complete()
        document["protocol_id"] = "another-protocol"
        with self.assertRaisesRegex(ClaimReviewError, "otro fixture o protocolo"):
            validate_review(document, self.fixture, self.protocol, require_complete=True, fixture_sha256=self.fixture_sha, protocol_sha256=self.protocol_sha)

    def test_pending_template_has_no_human_decisions(self):
        document = pending_review(self.fixture, self.protocol, fixture_sha256=self.fixture_sha, protocol_sha256=self.protocol_sha)
        summary = validate_review(document, self.fixture, self.protocol, require_complete=False, fixture_sha256=self.fixture_sha, protocol_sha256=self.protocol_sha)
        self.assertEqual(summary, {"valid": True, "claims": 27, "pending": 27, "approved": 0, "rejected": 0, "gate_passed": False})

    def test_v1_review_is_rejected_by_v2_fixture_and_protocol(self):
        fixture_path=ROOT/"results/generated/mapillary/h16-h23-multicandidate-top50-v2/fixture.json"
        protocol_path=ROOT/"config/h16_h23_top50_experiment_v2.json"
        if not fixture_path.exists() or not protocol_path.exists():self.skipTest("artefactos v2 ausentes")
        fixture=json.loads(fixture_path.read_text());protocol=json.loads(protocol_path.read_text());document=pending_review(self.fixture,self.protocol,fixture_sha256=self.fixture_sha,protocol_sha256=self.protocol_sha)
        with self.assertRaisesRegex(ClaimReviewError,"otro fixture o protocolo"):
            validate_review(document,fixture,protocol,require_complete=False,fixture_sha256=sha256_file(fixture_path),protocol_sha256=sha256_file(protocol_path))


if __name__ == "__main__":
    unittest.main()
