import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_ROOT = ROOT / "results/generated/mapillary/h16-h23-selector-comparison-v1"


class SelectorExecutionPreflightTests(unittest.TestCase):
    def command(self, report, execute=False):
        command = [str(ROOT / ".venv-geo/bin/python"), str(ROOT / "scripts/run_h16_h23_selector_comparison.py"), "--coverage-manifest", str(MANIFEST_ROOT / "coverage_adaptive-manifest.json"), "--geometric-manifest", str(MANIFEST_ROOT / "geometric_adaptive-manifest.json"), "--paired-plan", str(MANIFEST_ROOT / "paired-reuse-plan.json"), "--authorization", str(ROOT / "config/h16_h23_selector_comparison_authorization.request.json"), "--dry-run-report", str(report)]
        if execute: command.append("--execute")
        return command

    def test_dry_run_succeeds_without_token_or_network(self):
        if not MANIFEST_ROOT.exists(): self.skipTest("artefactos locales ausentes")
        with tempfile.TemporaryDirectory() as temporary:
            report = Path(temporary) / "report.json"
            env = dict(os.environ);env.pop("MAPILLARY_ACCESS_TOKEN", None);env["https_proxy"]="http://127.0.0.1:9";env["http_proxy"]="http://127.0.0.1:9"
            result = subprocess.run(self.command(report), cwd=ROOT, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr);document=json.loads(report.read_text());self.assertFalse(document["network_opened"]);self.assertFalse(document["model_loaded"]);self.assertTrue(document["ready_for_download"]);self.assertFalse(document["credential_checked"])

    def test_execute_validates_authorization_without_opening_network(self):
        if not MANIFEST_ROOT.exists(): self.skipTest("artefactos locales ausentes")
        with tempfile.TemporaryDirectory() as temporary:
            result=subprocess.run(self.command(Path(temporary)/"report.json",execute=True),cwd=ROOT,capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0);self.assertIn("autorización válida",result.stderr)

    def test_manifest_tampering_is_rejected(self):
        if not MANIFEST_ROOT.exists(): self.skipTest("artefactos locales ausentes")
        with tempfile.TemporaryDirectory() as temporary:
            tampered=Path(temporary)/"coverage.json";document=json.loads((MANIFEST_ROOT/"coverage_adaptive-manifest.json").read_text());document["arm"]="tampered";tampered.write_text(json.dumps(document))
            command=self.command(Path(temporary)/"report.json");command[command.index("--coverage-manifest")+1]=str(tampered);result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True);self.assertNotEqual(result.returncode,0);self.assertIn("hashes de manifests incompatibles",result.stderr)


if __name__ == "__main__": unittest.main()
