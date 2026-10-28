import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class H16H23MulticandidateTests(unittest.TestCase):
    def test_top20_plan_is_symmetric_and_not_authorized(self):
        required = ROOT / "results/generated/f5/h11-h25-independent/top100/rankings.json"
        if not required.exists():
            self.skipTest("artefactos locales H11-H25 ausentes")
        with tempfile.TemporaryDirectory() as temporary:
            subprocess.run([str(ROOT / ".venv-geo/bin/python"), str(ROOT / "scripts/prepare_h16_h23_multicandidate.py"), "--output-root", temporary], cwd=ROOT, check=True, capture_output=True, text=True)
            fixture = json.loads((Path(temporary) / "fixture.json").read_text())
            plan = json.loads((Path(temporary) / "acquisition-plan.json").read_text())
            self.assertEqual(fixture["policy"]["complete_symmetric_rank_block"], [1, 20])
            self.assertEqual({row["query_id"] for row in fixture["queries"]}, {"H16", "H23"})
            self.assertTrue(all(row["kind"] == "en_cartographic" for row in fixture["queries"]))
            self.assertTrue(all(row["claims"]["source_text_sha256"] == row["text_sha256"] for row in fixture["queries"]))
            self.assertFalse(plan["authorization"]["downloads_permitted"])
            self.assertEqual(plan["counts"]["candidate_slots"], 40)


if __name__ == "__main__":
    unittest.main()
