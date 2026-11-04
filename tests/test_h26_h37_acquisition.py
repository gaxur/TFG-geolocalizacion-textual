import json,os,subprocess,tempfile,unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SELECTION=ROOT/"results/generated/mapillary/h26-h37-calibration-v1/selection.json"

class H26H37AcquisitionTests(unittest.TestCase):
 def test_dry_run_is_offline_and_exact(self):
  if not SELECTION.exists():self.skipTest("selección aislada ausente")
  env=dict(os.environ);env.pop("MAPILLARY_ACCESS_TOKEN",None);env["https_proxy"]="http://127.0.0.1:9"
  result=subprocess.run([str(ROOT/".venv-geo/bin/python"),str(ROOT/"scripts/acquire_h26_h37_assets.py"),"--selection",str(SELECTION),"--authorization",str(ROOT/"config/h26_h37_mapillary_authorization.request.json"),"--output",str(Path(tempfile.gettempdir())/"never.json"),"--dry-run"],cwd=ROOT,env=env,capture_output=True,text=True)
  self.assertEqual(result.returncode,0,result.stderr);document=json.loads(result.stdout);self.assertFalse(document["network_opened"]);self.assertTrue(document["approved"]);self.assertEqual(document["assets"],24)

if __name__=="__main__":unittest.main()
