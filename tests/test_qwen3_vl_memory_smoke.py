import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.run_qwen3_vl_8b_memory_smoke import atomic_write_json, json_value


class PersistenceTests(unittest.TestCase):
    def test_normalizes_supported_scientific_types_without_string_fallback(self):
        import numpy as np
        class SizeLike:
            def __iter__(self):
                return iter((("shortest_edge", 65536), ("longest_edge", 16777216)))
        value = json_value({"size": SizeLike(), "numpy": np.int64(7), "array": np.array([1, 2]), "tuple": (1, None)})
        self.assertEqual(value["size"], {"shortest_edge": 65536, "longest_edge": 16777216})
        self.assertEqual(value["numpy"], 7)
        self.assertEqual(value["array"], [1, 2])
        self.assertEqual(value["tuple"], [1, None])

    def test_torch_scalars_and_vectors_are_normalized_in_isolated_process(self):
        code = "import json,torch;from scripts.run_qwen3_vl_8b_memory_smoke import json_value;print(json.dumps(json_value({'scalar':torch.tensor(9),'vector':torch.tensor([1.,2.])})))"
        completed = subprocess.run([sys.executable, "-c", code], check=True, capture_output=True, text=True)
        self.assertEqual(json.loads(completed.stdout), {"scalar": 9, "vector": [1.0, 2.0]})

    def test_unknown_type_is_rejected_not_stringified(self):
        class Unknown: pass
        with self.assertRaisesRegex(TypeError, "tipo no serializable"):
            json_value(Unknown())

    def test_atomic_write_roundtrips_and_leaves_no_temporary_file(self):
        import numpy as np
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "checkpoint.json"
            loaded = atomic_write_json(path, {"value": np.float32(1.5), "optional": None})
            self.assertEqual(loaded, {"value": 1.5, "optional": None})
            self.assertEqual(json.loads(path.read_text()), loaded)
            self.assertEqual([item.name for item in path.parent.iterdir()], ["checkpoint.json"])

    def test_complete_prevalidation_is_readable(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "prevalidation.json"
            code = f"import json;from pathlib import Path;from scripts.run_qwen3_vl_8b_memory_smoke import prevalidate_persistence;print(json.dumps(prevalidate_persistence(Path({str(path)!r}))))"
            completed = subprocess.run([sys.executable, "-c", code], check=True, capture_output=True, text=True)
            result = json.loads(completed.stdout)
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(json.loads(path.read_text())["fixture"]["nested"]["tokenizer"]["class"], "Qwen2Tokenizer")


if __name__ == "__main__":
    unittest.main()
