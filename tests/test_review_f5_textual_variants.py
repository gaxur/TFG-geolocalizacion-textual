import json
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ReviewF5TextualVariantsTests(unittest.TestCase):
    def fixture(self, root: Path):
        sidecar = json.loads((ROOT / "config/madrid_f51_textual_variants_template.json").read_text())
        sidecar["dataset_id"] = "f5-source"
        sidecar["dataset_version"] = "fixture"
        sidecar["observations"] = [{"variants": [
                {"variant_id": "original", "status": "reviewed", "review_status": "reviewed"},
                {"variant_id": "generated-a", "status": "generated", "review_status": "pending"},
                {"variant_id": "generated-b", "status": "generated", "review_status": "pending"},
            ]}]
        source = root / "sidecar.json"
        source.write_text(json.dumps(sidecar))
        return source, sidecar

    def run_review(self, source: Path, decisions: dict, output: Path):
        decision_path = output.parent / "decisions.json"
        decision_path.write_text(json.dumps(decisions))
        return subprocess.run([str(ROOT / ".venv-geo/bin/python"), str(ROOT / "scripts/review_f5_textual_variants.py"), "--sidecar", str(source), "--decisions", str(decision_path), "--output", str(output)], cwd=ROOT, capture_output=True, text=True)

    def test_review_requires_exact_coverage_and_applies_explicit_decisions(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, sidecar = self.fixture(root)
            decisions = {"contract_version": "f52-human-review-decisions-v1", "source_dataset_id": "f5-source", "reviewer": "human", "decisions": [
                {"variant_id": "generated-a", "decision": "approve", "notes": "equivalente"},
                {"variant_id": "generated-b", "decision": "reject", "notes": "pierde negación"},
            ]}
            result = self.run_review(source, decisions, root / "reviewed.json")
            self.assertEqual(result.returncode, 0, result.stderr)
            reviewed = json.loads((root / "reviewed.json").read_text())
            variants = reviewed["observations"][0]["variants"]
            self.assertEqual((variants[1]["status"], variants[1]["review_status"]), ("reviewed", "reviewed"))
            self.assertEqual((variants[2]["status"], variants[2]["review_status"]), ("rejected", "rejected"))

    def test_review_rejects_partial_or_duplicate_decisions(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, _ = self.fixture(root)
            partial = {"contract_version": "f52-human-review-decisions-v1", "source_dataset_id": "f5-source", "reviewer": "human", "decisions": [{"variant_id": "generated-a", "decision": "approve", "notes": "ok"}]}
            self.assertNotEqual(self.run_review(source, partial, root / "partial.json").returncode, 0)
            duplicate = {"contract_version": "f52-human-review-decisions-v1", "source_dataset_id": "f5-source", "reviewer": "human", "decisions": [{"variant_id": "generated-a", "decision": "approve", "notes": "ok"}, {"variant_id": "generated-a", "decision": "approve", "notes": "ok"}]}
            self.assertNotEqual(self.run_review(source, duplicate, root / "duplicate.json").returncode, 0)


if __name__ == "__main__":
    unittest.main()
