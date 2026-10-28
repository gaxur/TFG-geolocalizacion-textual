import hashlib,json,tempfile,unittest
from pathlib import Path
from src.tfg_phase0.independent_campaign import IndependentCampaignError,validate_campaign
ROOT=Path(__file__).resolve().parents[1]
class IndependentCampaignTests(unittest.TestCase):
 def row(self,root,q='H26',partition='development',block='b1'):
  raw=b'photo';(root/'p.jpg').write_bytes(raw);return {'query_id':q,'partition':partition,'location_id':'loc-'+q,'spatial_block_id':block,'collection_session_id':'s','collected_at_utc':'2026-11-01T10:00:00Z','collector_pseudonym':'c','description_es':'Estoy en una calle con edificios y una plaza visible delante.','observer_position':{'latitude':40.4,'longitude':-3.7,'crs':'EPSG:4326','method':'device_gnss_multi_sample','reported_accuracy_m':5,'raw_frozen_before_rankings':True},'orientation':{'status':'unknown','heading_degrees':None,'uncertainty_degrees':None,'meaning':'unknown'},'evidence':[{'logical_path':'p.jpg','sha256':hashlib.sha256(raw).hexdigest(),'captured_at_utc':'2026-11-01T10:00:00Z','source':'human_collector_owned','original_query_evidence_not_candidate_view':True}],'claims':[],'consent':{'academic_processing':True,'public_redistribution':False},'freeze':{'observation_frozen_at_utc':'2026-11-01T10:01:00Z','rankings_executed_at_utc':None,'edited_after_ranking':False},'review':{'status':'pending','factual_reviewer':None,'geographic_reviewer':None,'rankings_seen_by_reviewers':False}}
 def test_valid_partial_campaign(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);doc={'observations':[self.row(root)]};schema=json.loads((ROOT/'schemas/independent_human_observation.schema.json').read_text());self.assertFalse(validate_campaign(doc,schema=schema,evidence_root=root)['target_complete'])
 def test_spatial_block_cannot_cross_split(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);a=self.row(root);b=self.row(root,'H27','test_sealed','b1');doc={'observations':[a,b]};schema=json.loads((ROOT/'schemas/independent_human_observation.schema.json').read_text())
   with self.assertRaises(IndependentCampaignError):validate_campaign(doc,schema=schema,evidence_root=root)
if __name__=='__main__':unittest.main()
