import json
import tempfile
import unittest
from pathlib import Path

from src.tfg_phase0.remote_mapillary_campaign import EXPECTED_DEVELOPMENT_IDS


class RemoteDevelopmentIsolationTests(unittest.TestCase):
    def test_expected_development_ids_are_exact_and_disjoint_from_test(self):
        self.assertEqual(EXPECTED_DEVELOPMENT_IDS,tuple(f"H{i:02d}" for i in range(26,38)))
        self.assertFalse(set(EXPECTED_DEVELOPMENT_IDS)&{f"H{i:02d}" for i in range(38,62)})

    def test_validator_rejects_fixture_with_other_partition_record(self):
        import subprocess,sys
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/"fixture.json";observations=[{"query_id":value} for value in EXPECTED_DEVELOPMENT_IDS]+[{"query_id":"H38"}]
            path.write_text(json.dumps({"partition":"development","query_ids":list(EXPECTED_DEVELOPMENT_IDS),"forbidden_content":["other_partition_records"],"observations":observations}))
            result=subprocess.run([sys.executable,"scripts/validate_h26_h37_package.py","--fixture",str(path)],capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)


if __name__=="__main__":unittest.main()
