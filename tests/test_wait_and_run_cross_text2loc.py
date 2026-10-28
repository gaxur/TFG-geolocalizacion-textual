import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "wait_and_run_cross_text2loc.py"
SPEC = importlib.util.spec_from_file_location("wait_and_run_cross_text2loc", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class WaitAndRunCrossText2LocTests(unittest.TestCase):
    def test_parse_meminfo_uses_named_fields(self):
        parsed = MODULE.parse_meminfo(
            """MemTotal: 100 kB
MemFree: 10 kB
MemAvailable: 60 kB
Buffers: 2 kB
Cached: 30 kB
SReclaimable: 3 kB
SwapTotal: 20 kB
SwapFree: 15 kB
"""
        )
        self.assertEqual(parsed["MemTotal"], 100 * 1024)
        self.assertEqual(parsed["MemAvailable"], 60 * 1024)
        self.assertEqual(parsed["SwapFree"], 15 * 1024)

    def test_gib_to_bytes(self):
        self.assertEqual(MODULE.gib_to_bytes(1.5), 1_610_612_736)
        with self.assertRaises(ValueError):
            MODULE.gib_to_bytes(-1)

    def test_conditions_and_consecutive_window(self):
        sample = {
            "cuda_free_bytes": 20 * MODULE.GIB,
            "MemAvailable": 30 * MODULE.GIB,
            "SwapFree": 10 * MODULE.GIB,
            "gpu_utilization_percent": 0,
            "services_ok": True,
        }
        ready, reasons = MODULE.evaluate_conditions(
            sample, 16 * MODULE.GIB, 16 * MODULE.GIB, 8 * MODULE.GIB, 10
        )
        self.assertTrue(ready)
        self.assertEqual(reasons, [])
        count = 0
        for value in (True, True, False, True, True, True):
            count = MODULE.update_stable_count(count, value)
        self.assertEqual(count, 3)

    def test_condition_failure_is_explicit(self):
        sample = {
            "cuda_free_bytes": 15 * MODULE.GIB,
            "MemAvailable": 30 * MODULE.GIB,
            "SwapFree": 10 * MODULE.GIB,
            "gpu_utilization_percent": 0,
            "services_ok": True,
        }
        ready, reasons = MODULE.evaluate_conditions(
            sample, 16 * MODULE.GIB, 16 * MODULE.GIB, 8 * MODULE.GIB, 10
        )
        self.assertFalse(ready)
        self.assertEqual(reasons, ["cuda_free_below_threshold"])

    def test_official_command(self):
        command = MODULE.build_evaluation_command(Path("/project/external/CVG-Text"), Path("/project/.venv-cvgtext/bin/python"))
        self.assertEqual(
            command,
            [
                "env", "CUDA_VISIBLE_DEVICES=0", "../../.venv-cvgtext/bin/python",
                "zeroshot.py", "--version", "NewYork-mixed", "--img_type", "osm",
                "--model", "CLIP-L/14@336", "--expand", "--checkpoint",
                MODULE.CHECKPOINT_NAME,
            ],
        )

    def test_sha256(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "value"
            path.write_bytes(b"CrossText2Loc")
            self.assertEqual(MODULE.sha256(path), hashlib.sha256(b"CrossText2Loc").hexdigest())

    def test_states_are_declared(self):
        self.assertEqual(
            set(MODULE.STATES),
            {
                "READY", "WAITING", "TIMEOUT_NO_WINDOW", "PRECHECK_FAILED",
                "REPO_VALIDATION_FAILED", "CHECKPOINT_VALIDATION_FAILED",
                "DATASET_VALIDATION_FAILED", "EVALUATION_STARTED",
                "EVALUATION_SUCCESS", "EVALUATION_FAILED", "SAFETY_ABORT",
                "MONITORING_ERROR",
            },
        )

    def test_timeout(self):
        self.assertFalse(MODULE.wait_timed_out(9.9, 10.0))
        self.assertTrue(MODULE.wait_timed_out(10.0, 10.0))


if __name__ == "__main__":
    unittest.main()
