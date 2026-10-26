import unittest

from src.tfg_phase0.mapillary_vlm_smoke import (
    VLMSmokeError,
    compare_human,
    conservative_verification_prompt,
    parse_verification,
    reject_forbidden_input,
    verification_prompt,
)


class MapillaryVLMSmokeTests(unittest.TestCase):
    def test_prompt_contains_no_ground_truth_or_rank(self):
        prompt = verification_prompt("Una iglesia con arco", "OPAQUE_1")
        self.assertIn("OPAQUE_1", prompt)
        self.assertNotIn("ground_truth", prompt)
        self.assertNotIn("baseline_rank", prompt)

    def test_forbidden_input_is_rejected(self):
        with self.assertRaisesRegex(VLMSmokeError, "query_id"):
            reject_forbidden_input({"candidate_id": "x", "query_id": "H14"})

    def test_conservative_prompt_encodes_abstention_rules(self):
        prompt = conservative_verification_prompt("Una farmacia a la derecha", "OPAQUE_2")
        self.assertIn("rótulo exacto es legible", prompt)
        self.assertIn("Ante la duda, unverifiable e insufficient", prompt)
        self.assertIn("ausencia", prompt)
        self.assertNotIn("H14", prompt)

    def test_strict_output_parsing(self):
        value = parse_verification('{"matches":["iglesia"],"contradictions":[],"unverifiable":["derecha"],"verification_level":"partial_match"}')
        self.assertEqual(value["verification_level"], "partial_match")
        with self.assertRaises(VLMSmokeError):
            parse_verification('{"matches":[],"verification_level":"partial_match"}')

    def test_human_comparison_is_explicit_mapping(self):
        comparison = compare_human(
            {"matches": ["iglesia"], "contradictions": [], "unverifiable": [], "verification_level": "partial_match"},
            {"utility": "useful", "matches": ["iglesia"], "contradictions": []},
        )
        self.assertTrue(comparison["level_agreement"])


if __name__ == "__main__":
    unittest.main()
