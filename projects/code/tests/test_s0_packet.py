"""The no-model session packet binds all selected originals and starts no review."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_s0_sampling import multi_fixture
from webcollect.batch_core import BatchLedger, load_json, save_json
from quality_inspector.cumulative import build_set_manifest
from quality_inspector.sampling import prepare
from quality_inspector.sampling_packet import export

REPO = Path(__file__).resolve().parents[3]


class SessionPacketTests(unittest.TestCase):
    def test_complete_originals_blank_decisions_and_idempotent_no_model_export(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            dataset = multi_fixture(root / 'controlled', count=2)
            manifest = root / 'effective.json'; save_json(manifest, build_set_manifest([dataset]))
            config = load_json(REPO / 'projects/code/config/batch-no-model.json')
            ledger = BatchLedger(root / 'ops.sqlite3', config, initialize=True)
            plan = prepare(ledger, dataset, root / 'qc', effective_set=manifest)
            with patch('urllib.request.OpenerDirector.open', side_effect=AssertionError('No network')):
                result = export(ledger, plan['plan_file'], root / 'packet')
                self.assertEqual(result, export(ledger, plan['plan_file'], root / 'packet'))
            packet = load_json(result['packet_file']); template = load_json(result['review_template'])
            self.assertEqual(result['selected_samples'], 2)
            for item in packet['packets']:
                self.assertEqual(len(item['focal']['original_frames']), 6)
                self.assertEqual([f['step_id'] for f in item['focal']['original_frames']], list(range(1, 7)))
                self.assertEqual(len(item['neighbors']), 1)
                self.assertEqual(len(item['neighbors'][0]['original_frames']), 6)
            self.assertTrue(all(not row['provenance']['frames_viewed'] and not row['step_observations']
                                and all(c['status'] == 'REVIEW_REQUIRED' for c in row['checks'].values())
                                for row in template['records']))
            self.assertEqual(ledger.summary()['model_requests'], 0)
            self.assertEqual(result['actual_reviews_created'], 0)
            with self.assertRaisesRegex(ValueError, 'outside candidates'):
                export(ledger, plan['plan_file'], dataset / 'packet')
            Path(result['packet_file']).write_text('{}')
            with self.assertRaisesRegex(ValueError, 'artifact changed'):
                export(ledger, plan['plan_file'], root / 'packet')


if __name__ == '__main__': unittest.main()
