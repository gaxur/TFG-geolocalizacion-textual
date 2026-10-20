import unittest

from src.tfg_phase0.f5_extraction_diagnostics import diagnose_extraction_sets, diagnostic_report_id


class F53ExtractionDiagnosticsTests(unittest.TestCase):
    def test_structural_and_semantic_failures_are_counted_separately(self):
        records = [
            {"source_query_id": "a", "variant_id": "v-a", "status": "rejected", "attempt_count": 1, "duration_ms": 1.0, "validation": {"structurally_valid": False, "semantically_valid": False, "issues": [{"code": "invalid_json", "severity": "error", "message": "x"}]}},
            {"source_query_id": "b", "variant_id": "v-b", "status": "rejected", "attempt_count": 1, "duration_ms": 3.0, "validation": {"structurally_valid": True, "semantically_valid": False, "issues": [{"code": "evidence_span_mismatch", "severity": "error", "message": "x"}]}},
        ]
        document = {"extraction_set_id": "set", "generation": {"prompt_version": "v", "max_attempts": 1}, "records": records}
        report = diagnose_extraction_sets([document], ["1" * 64])
        campaign = report["campaigns"][0]
        self.assertEqual(campaign["json_syntax_valid_count"], 1)
        self.assertEqual(campaign["structurally_valid_count"], 1)
        self.assertEqual(campaign["semantically_valid_count"], 0)
        self.assertEqual(campaign["error_category_counts"], {"semantic": 1, "structural": 1})
        self.assertEqual(report["diagnostic_id"], diagnostic_report_id(report))


if __name__ == "__main__":
    unittest.main()
