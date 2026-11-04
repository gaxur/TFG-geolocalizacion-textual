import json
import unittest
from pathlib import Path

import jsonschema

from src.tfg_phase0.i20_remote_acquisition import dhash,hamming,select_shortlist,validate_observation_states,validate_shortlist

ROOT=Path(__file__).resolve().parents[1]

class I20RemoteAcquisitionTests(unittest.TestCase):
    def test_dhash_is_version_compatible(self):
        path=ROOT/'data/cache/mapillary/images/1374483029591141.jpg'
        if not path.exists():self.skipTest('asset histórico no disponible')
        try: import PIL
        except ImportError: self.skipTest('Pillow no disponible en este entorno')
        self.assertEqual(dhash(path),'d9f0991a4a4a49cb')
        self.assertEqual(hamming('0'*16,'0'*15+'1'),1)

    def test_materialized_shortlist_has_fixed_budget_and_no_ranking_inputs(self):
        path=ROOT/'results/generated/i01-i20-remote-acquisition-v1/metadata-shortlist.frozen.json'
        if not path.exists():self.skipTest('shortlist no materializado')
        document=json.loads(path.read_text());validate_shortlist(document)
        serialized=json.dumps(document).casefold()
        self.assertNotIn('cosine_similarity',serialized)
        self.assertNotIn('candidate_id',serialized)
        self.assertFalse(document['protocol']['pixels_used'])

    def test_observations_cannot_be_eligible_while_ledger_and_review_are_pending(self):
        path=ROOT/'results/generated/i01-i20-remote-acquisition-v1/observation-status.json'
        if not path.exists():self.skipTest('estados no materializados')
        counts=validate_observation_states(json.loads(path.read_text()))
        self.assertEqual(counts['ELIGIBLE'],0)
        self.assertEqual(counts['PENDING_BLIND_EXCLUSION'],20)

    def test_asset_manifest_and_annotation_geography_separation(self):
        root=ROOT/'results/generated/i01-i20-remote-acquisition-v1'
        if not (root/'manifest.json').exists():self.skipTest('lineage remoto no materializado')
        assets=json.loads((root/'asset-manifest.json').read_text());schema=json.loads((ROOT/'schemas/i20_remote_asset_manifest.schema.json').read_text());jsonschema.Draft202012Validator.check_schema(schema);jsonschema.validate(assets,schema)
        assignments=json.loads((root/'annotation-package/assignment-manifest.json').read_text());files={path.name for path in (root/'annotation-package/references').iterdir() if path.is_file()};expected={Path(row['reference_asset_path']).name for row in assignments['assignments']}
        self.assertEqual(files,expected);self.assertEqual(len(files),20)
        annotation_text=(root/'annotation-package/assignment-manifest.json').read_text().casefold()+(root/'annotation-package/observations.json').read_text().casefold()
        for forbidden in ('latitude','longitude','coordinate_source','quality_score','provider_record_id','sequence_id'):
            self.assertNotIn(forbidden,annotation_text)
        ledger=(root/'blind-ledger-submission-draft.json').read_text().casefold()
        for forbidden in ('latitude','longitude','provider_record_id','image_id','coordinates'):
            self.assertNotIn(forbidden,ledger)

    def test_final_manifest_reports_no_models_or_eligibility(self):
        path=ROOT/'results/generated/i01-i20-remote-acquisition-v1/manifest.json'
        if not path.exists():self.skipTest('manifest remoto no materializado')
        document=json.loads(path.read_text())
        self.assertEqual(document['summary']['eligible'],0)
        self.assertEqual(document['summary']['selected_observations'],20)
        self.assertEqual(document['summary']['selected_duplicate_assets'],0)
        self.assertFalse(document['execution']['gpu_used'])
        self.assertFalse(document['execution']['models_run'])
        self.assertFalse(document['execution']['evaluation'])
        self.assertFalse(document['independence']['holdout_checked'])

if __name__=='__main__':unittest.main()
