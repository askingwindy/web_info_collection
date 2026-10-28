"""Current-only cohort history fences, with no historical package/LATEST reads."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from webcollect import admission_cohort as cohort
from webcollect.current_chain import initialize_chain, history_context
from webcollect.task_admission import reference


class CurrentChainCohortTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.scope = initialize_chain(self.root / 'manifest.json', self.root / 'registry.sqlite3',
            chain_id='CONTROLLED-current-cohort', current_result_roots=[self.root / 'results'])
        self.context = history_context(self.scope, [], self.root / 'registry.sqlite3')
        packet = self.root / 'packet.json'; packet.write_text(json.dumps({'history_context': self.context}))
        self.plan = {'tasks': [{'observed_workflow': {}, 'workflow_admission': {'packet': reference(packet)}}]}

    def test_empty_current_chain_validates_and_stamps_without_legacy_reader(self):
        with patch('webcollect.task_generation.read_customer_history', side_effect=AssertionError('No old packages')), \
                patch('webcollect.task_generation.bind_formal_history', side_effect=AssertionError('No LATEST')):
            proofs = cohort.validate_customer_history(self.plan)
            cohort._check_customer_references(self.context, proofs)
        self.assertEqual(len(proofs), 1)
        self.assertEqual(set(next(iter(proofs.values()))['file_stamps']), {self.scope['manifest']['path']})

    def test_manifest_tampering_or_different_registry_fails(self):
        wrong = deepcopy(self.context)
        wrong['registry_snapshot']['registry'] = str(self.root / 'unmarked-legacy.sqlite3')
        with self.assertRaises(ValueError): cohort._check_customer_references(wrong)
        Path(self.scope['manifest']['path']).write_text('{}')
        with self.assertRaises(ValueError): cohort.validate_customer_history(self.plan)

    def test_outside_current_roots_ref_is_rejected_before_reading_it(self):
        wrong = deepcopy(self.scope)
        wrong['current_results_refs'] = [{'path': str(self.root / 'OLD-history/annotation.json'), 'sha256': '0' * 64}]
        with self.assertRaisesRegex(ValueError, 'out-of-chain'):
            cohort._file_stamps(wrong)


if __name__ == '__main__': unittest.main()
