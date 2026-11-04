import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT=Path(__file__).resolve().parents[1]
ART=ROOT/"results/generated/mapillary/h16-h23-selector-comparison-v1"


class SelectorUnionAcquisitionTests(unittest.TestCase):
 def command(self,dry=False):
  command=[str(ROOT/".venv-geo/bin/python"),str(ROOT/"scripts/acquire_h16_h23_selector_union.py"),"--coverage-manifest",str(ART/"coverage_adaptive-manifest.json"),"--geometric-manifest",str(ART/"geometric_adaptive-manifest.json"),"--paired-plan",str(ART/"paired-reuse-plan.json"),"--authorization",str(ROOT/"config/h16_h23_selector_comparison_authorization.request.json"),"--output",str(ROOT/"/tmp/never.json")]
  if dry:command.append("--dry-run")
  return command
 def test_dry_run_has_no_network_and_reports_474(self):
  if not ART.exists():self.skipTest("artefactos locales ausentes")
  env=dict(os.environ);env.pop("MAPILLARY_ACCESS_TOKEN",None);env["https_proxy"]="http://127.0.0.1:9";result=subprocess.run(self.command(True),cwd=ROOT,env=env,capture_output=True,text=True);self.assertEqual(result.returncode,0,result.stderr);document=json.loads(result.stdout);self.assertFalse(document["network_opened"]);self.assertEqual(document["pending_assets"],474);self.assertTrue(document["authorization_approved"])
 def test_online_mode_requires_token_after_valid_authorization(self):
  if not ART.exists():self.skipTest("artefactos locales ausentes")
  env=dict(os.environ);env.pop("MAPILLARY_ACCESS_TOKEN",None);result=subprocess.run(self.command(False),cwd=ROOT,env=env,capture_output=True,text=True);self.assertNotEqual(result.returncode,0);self.assertIn("MAPILLARY_ACCESS_TOKEN",result.stderr)
 def test_versioned_execution_budget_matches_dry_run(self):
  config=json.loads((ROOT/"config/h16_h23_selector_comparison_execution_v1.json").read_text());self.assertEqual(config["physical_budget"]["pending_unique_assets"],474);self.assertEqual(config["inference_budget_per_model"]["physical_tasks_union"],9613);self.assertFalse(config["gates"]["authorization"])
if __name__=="__main__":unittest.main()
