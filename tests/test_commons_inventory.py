import io,json,unittest
from src.tfg_phase0.commons_inventory import build_query,fetch_metadata,freeze_inventory

class Response:
 def __init__(self,value):self.value=value
 def __enter__(self):return self
 def __exit__(self,*args):return False
 def read(self):return json.dumps(self.value).encode()
class CommonsInventoryTests(unittest.TestCase):
 def test_query_is_metadata_only_and_bounded(self):
  url=build_query(wikidata_id="Q123",label=None,limit=10);self.assertIn("gsrnamespace=6",url);self.assertIn("gsrlimit=10",url);self.assertNotIn("download",url)
 def test_fetch_uses_injected_opener(self):
  value={"query":{"pages":[]}};self.assertEqual(fetch_metadata(build_query(wikidata_id=None,label="Monument"),opener=lambda request,timeout:Response(value)),value)
 def test_empty_fixture_freezes_without_inventing_coverage(self):
  plan={"plan_id":"p","queries":[{"query_id":"H26","target":{"label":"X","wikidata_id":"Q123","osm_ref":"way/123"}}]};doc=freeze_inventory(plan,{},consulted_at_utc="2026-11-03T00:00:00Z");self.assertEqual(doc["summary"]["records"],0);self.assertEqual(doc["coverage"][0]["records"],0)
if __name__=="__main__":unittest.main()
