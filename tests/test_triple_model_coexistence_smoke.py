import json
import tempfile
import unittest
from pathlib import Path

from scripts.run_triple_model_coexistence_smoke import (
    MAXIMUM_SWAP_GROWTH_BEFORE_VLM_BYTES,
    MINIMUM_RAM_BEFORE_VLM_BYTES,
    own_processes_only,
    phase,
    refresh_manifest,
)
from scripts.run_qwen3_vl_8b_memory_smoke import atomic_write_json


class TripleCoexistenceRunnerTests(unittest.TestCase):
    def test_intermediate_gate_constants_are_fixed(self):
        self.assertEqual(MINIMUM_RAM_BEFORE_VLM_BYTES, 40 * 1024**3)
        self.assertEqual(MAXIMUM_SWAP_GROWTH_BEFORE_VLM_BYTES, 1024**3)

    def test_compute_process_gate_accepts_only_current_python_family(self):
        self.assertTrue(own_processes_only([{"process_name": "python", "pid": 1}], own_pid=1))
        self.assertFalse(own_processes_only([{"process_name": "/usr/lib/ollama/llama-server", "pid": 2}]))
        self.assertFalse(own_processes_only([{"process_name": "python", "pid": 2}], own_pid=1))
        self.assertFalse(own_processes_only([{"status": "NOT_VERIFIED"}]))

    def test_phase_checkpoint_roundtrips_atomically(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "c0.json"
            document = phase("C0", {"status": "PASS", "measurement": {"cuda": {"allocated_bytes": 0}}})
            self.assertEqual(atomic_write_json(path, document), json.loads(path.read_text()))

    def test_manifest_includes_intermediate_gate(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            atomic_write_json(root / "c3-gate.json", phase("C3_GATE", {"status": "PASS"}))
            atomic_write_json(root / "protocol.json", {"models": {}})
            (root / "report.md").write_text("report")
            manifest = refresh_manifest(root, {})
            self.assertIn("c3-gate.json", manifest["artifacts"])


if __name__ == "__main__":
    unittest.main()
