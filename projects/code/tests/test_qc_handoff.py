"""Temporary current-chain handoff fixtures; network/model/dispatch are forbidden."""
from contextlib import ExitStack, closing
import importlib.util
import json
from pathlib import Path
import socket
import shutil
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(REPO / 'projects/quality-inspector'),
                str(REPO / 'projects/quality-inspector/tests')]
from test_customer_layout import fixture
from quality_inspector.profiles import package_files
from webcollect.batch_core import file_sha
from webcollect.current_chain import initialize_chain, read_chain_history
from webcollect.qc_handoff import prepare_qc_inputs
from webcollect.collect_runtime import sample_hashes


class QCHandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.results = self.root / 'current-results'
        self.history = self.root / 'run/scope/manifest.json'
        self.registry = self.root / 'state/current.sqlite3'
        initialize_chain(self.history, self.registry, chain_id='CONTROLLED-handoff',
                         current_result_roots=[self.results])
        self.source, self.candidate, _ = fixture(self.results / 'fixture')
        sid = next((self.candidate / 'samples').iterdir()).name
        self.sample_id = sid
        saved = self.source / 'evidence' / sid / 'saved_sample.json'
        saved.write_text(json.dumps({'attempt_id': 'CONTROLLED-attempt', 'sample_id': sid,
            'sample_files_sha256': sample_hashes(self.source / 'samples' / sid),
            'capture_files_sha256': sample_hashes(saved.parent)}))
        evidence = [{'path': str(saved), 'sha256': file_sha(saved)}]
        # Explicit synthetic ledger row, never an actual production allocation.
        with closing(sqlite3.connect(self.registry)) as con, con:
            con.execute('INSERT INTO m4_attempts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                ('CONTROLLED-attempt', 'CONTROLLED-scope', 'CONTROLLED-campaign',
                 'CONTROLLED-task', 'CONTROLLED-task', 'v1', 'CONTROLLED-worker',
                 'CONTROLLED-lease', 9999999999, sid, 'SITE1', 'CONTROLLED-batch',
                 'collected_pending_review', 1, 1, 2, None, None, None, json.dumps(evidence)))
        self.args = SimpleNamespace(dataset=self.candidate, history=self.history,
            output=self.root / 'handoff', seed='CONTROLLED-seed', ai_percent=50,
            human_percent=25)
        self.guards = ExitStack(); self.addCleanup(self.guards.close)
        self.forbidden = []
        for target in ('socket.socket', 'socket.create_connection',
                       'urllib.request.urlopen', 'subprocess.Popen',
                       'webcollect.model_gateway.ModelGateway.call',
                       'webcollect.runtime.RuntimeStore.claim_next',
                       'webcollect.runtime.RuntimeStore.start_attempt',
                       'webcollect.collect.collect_plan',
                       'webcollect.collect_runtime.collect_m4'):
            guard = self.guards.enter_context(patch(target,
                side_effect=AssertionError('offline handoff forbids ' + target)))
            self.forbidden.append(guard)
        self.addCleanup(self.assert_forbidden_unused)

    def assert_forbidden_unused(self):
        for guard in self.forbidden:
            guard.assert_not_called()

    def prepare(self, **updates):
        arguments = dict(dataset=self.candidate, history_set=self.history,
            output=self.args.output, seed=self.args.seed,
            ai_percent=self.args.ai_percent, human_percent=self.args.human_percent)
        arguments.update(updates)
        return prepare_qc_inputs(**arguments)

    def test_raw_comparison_resolves_only_through_original_export_receipt(self):
        from webcollect.qc_handoff import _customer_root
        from webcollect.current_chain import read_chain_scope
        root=self.results/'export-case';raw=root/'capture';client=root/'candidate'
        shutil.copytree(self.source,raw);shutil.copytree(self.candidate,client)
        annotation=raw/'samples'/self.sample_id/'annotation.json'
        receipt=root/'candidate-receipt.json'
        receipt.write_text(json.dumps({'files_sha256':package_files(client)}))
        provenance=root/'candidate.evidence.json'
        provenance.write_text(json.dumps({'source_root':str(raw),'client_root':str(client),
            'source_samples':[{'sample_id':self.sample_id,'annotation_sha256':file_sha(annotation)}]}))
        scope=read_chain_scope(self.history)
        self.assertEqual(_customer_root(scope,annotation),client)
        (client/'README.md').write_text('changed package')
        with self.assertRaisesRegex(ValueError,'binding changed'):
            _customer_root(scope,annotation)

    def test_first_current_candidate_with_explicit_ratios(self):
        original = package_files(self.candidate)
        registry_sha = file_sha(self.registry); history_sha = file_sha(self.history)
        result = self.prepare()
        sampling = json.loads(Path(result['sampling_plan']).read_text())
        effective = json.loads(Path(result['effective_set']).read_text())
        self.assertEqual(sampling['policy']['ai_percent'], 50)
        self.assertEqual(sampling['policy']['human_percent'], 25)
        self.assertEqual(len(effective['packages']), 1)
        self.assertEqual(effective['packages'][0]['path'], str(self.candidate))
        self.assertFalse(result['QC_approval'])
        self.assertEqual(package_files(self.candidate), original)
        self.assertEqual(file_sha(self.registry), registry_sha)
        self.assertEqual(file_sha(self.history), history_sha)
        self.assertEqual(read_chain_history(self.history)[0], [])

    @unittest.skipUnless((REPO / 'verify_results/pilot1000-20261028-r01/pilot_execution_adapter_r01.py').is_file(),
                         'Optional local compatibility adapter is absent in a clean checkout')
    def test_local_adapter_delegates_to_product_module(self):
        path = REPO / 'verify_results/pilot1000-20261028-r01/pilot_execution_adapter_r01.py'
        spec = importlib.util.spec_from_file_location('controlled_pilot_adapter', path)
        adapter = importlib.util.module_from_spec(spec); spec.loader.exec_module(adapter)
        with patch('webcollect.qc_handoff.prepare_qc_inputs', return_value={'fixture': True}) as prepare:
            self.assertEqual(adapter.qc_inputs(self.args), {'fixture': True})
            prepare.assert_called_once_with(self.args.dataset, self.args.history, self.args.output,
                ai_percent=50, human_percent=25, seed=self.args.seed)

    def test_unknown_rejected_or_missing_attempt_cannot_be_frozen(self):
        for state in ('running', 'rejected', 'interrupted', 'unknown'):
            with self.subTest(state=state), closing(sqlite3.connect(self.registry)) as con, con:
                con.execute('UPDATE m4_attempts SET status=?', (state,))
            with self.assertRaisesRegex(ValueError, 'original saved current-chain attempt'):
                self.prepare()
            self.assertFalse(self.args.output.exists())
        with closing(sqlite3.connect(self.registry)) as con, con:
            con.execute('DELETE FROM m4_attempts')
        with self.assertRaisesRegex(ValueError, 'original saved current-chain attempt'):
            self.prepare()

    def test_out_of_chain_is_rejected_before_reading_candidate_files(self):
        with patch('quality_inspector.profiles.package_files',
                   side_effect=AssertionError('out-of-chain files must not be read')) as read_files:
            with self.assertRaisesRegex(ValueError, 'out-of-chain'):
                self.prepare(dataset=self.root / 'unrelated-population')
            read_files.assert_not_called()

    def test_empty_or_missing_frame_does_not_publish_handoff(self):
        empty = self.results / 'empty'; empty.mkdir()
        with self.assertRaisesRegex(ValueError, 'nonempty current candidate'):
            self.prepare(dataset=empty)
        sample = next((self.candidate / 'samples').iterdir())
        (sample / 'images/step_002.png').unlink()  # Only a disposable fixture.
        with self.assertRaisesRegex(ValueError, 'Candidate bytes differ'):
            self.prepare()
        self.assertFalse(self.args.output.exists())

    def test_pending_row_without_committed_receipt_is_insufficient(self):
        with closing(sqlite3.connect(self.registry)) as con, con:
            con.execute("UPDATE m4_attempts SET evidence_json='[]'")
        with self.assertRaisesRegex(ValueError, 'committed saved-sample receipt'):
            self.prepare()
        self.assertFalse(self.args.output.exists())

    def test_same_id_changed_annotation_or_raw_evidence_cannot_be_adopted(self):
        sample = self.candidate / 'samples' / self.sample_id
        original = (sample / 'annotation.json').read_bytes()
        annotation = json.loads(original)
        annotation['final_result'] = 'CONTROLLED changed candidate, same ID'
        (sample / 'annotation.json').write_text(json.dumps(annotation, ensure_ascii=False))
        with self.assertRaisesRegex(ValueError, 'Candidate bytes differ'):
            self.prepare()
        (sample / 'annotation.json').write_bytes(original)
        (self.source / 'evidence' / self.sample_id / 'ground_truth.json').write_text('[]')
        with self.assertRaisesRegex(ValueError, '原始采集证据改变'):
            self.prepare()
        self.assertFalse(self.args.output.exists())

    def test_outputs_are_external_immutable_and_symlink_free(self):
        with self.assertRaisesRegex(ValueError, 'fresh QC directory'):
            self.prepare(output=self.candidate / 'handoff')
        link = self.root / 'linked'; link.symlink_to(self.root / 'other')
        with self.assertRaisesRegex(ValueError, 'symlink'):
            self.prepare(output=link / 'handoff')
        result = self.prepare()
        frozen = package_files(self.args.output)
        self.assertEqual(self.prepare(), result)
        with self.assertRaisesRegex(ValueError, 'immutable request'):
            self.prepare(ai_percent=75)
        self.assertEqual(package_files(self.args.output), frozen)
        self.assertFalse(json.loads(Path(result['receipt']).read_text())['QC_approval'])

    def test_collection_checks_are_frozen_and_reused_without_dispatch(self):
        path = self.results / 'pending-quality-checks.json'
        path.write_text(json.dumps({'schema_version': 'webcollect-pending-quality-checks-1',
            'QC_approval': False, 'requires_independent_QC': True, 'checks': []}))
        ref = {'path': str(path), 'sha256': file_sha(path)}
        first = self.prepare(collection_checks=ref)
        before = package_files(self.args.output)
        self.assertEqual(self.prepare(collection_checks=ref), first)
        self.assertEqual(package_files(self.args.output), before)
        self.assertEqual(json.loads(Path(first['receipt']).read_text())['collection_checks'], ref)
        path.write_text('{}')
        with self.assertRaises(ValueError): self.prepare(collection_checks=ref)

    def test_modified_handoff_artifact_is_never_silently_regenerated(self):
        result = self.prepare()
        Path(result['effective_set']).write_text('{}')
        with self.assertRaisesRegex(ValueError, 'immutable request'):
            self.prepare()

    def test_same_original_current_result_is_not_a_second_comparison_sample(self):
        from webcollect.current_chain import append_current_result
        append_current_result(self.history, self.candidate / 'samples' / self.sample_id / 'annotation.json',
            site_uri='https://example.org/', task_key='CONTROLLED-task')
        copy = self.results / 'candidate-copy'
        shutil.copytree(self.candidate, copy)
        registry_sha = file_sha(self.registry)
        result = self.prepare(dataset=copy)
        effective = json.loads(Path(result['effective_set']).read_text())
        self.assertEqual({row['path'] for row in effective['packages']}, {str(copy)})
        self.assertEqual(file_sha(self.registry), registry_sha)

    def test_changes_during_freeze_reject_before_publication(self):
        from quality_inspector.delivery_sampling import freeze
        def mutate_fixture(*args, **kwargs):
            plan = freeze(*args, **kwargs)
            (self.candidate / 'README.md').write_text('CONTROLLED concurrent change')
            return plan
        with patch('quality_inspector.delivery_sampling.freeze', side_effect=mutate_fixture):
            with self.assertRaisesRegex(ValueError, 'changed during QC handoff'):
                self.prepare()
        self.assertFalse(self.args.output.exists())

    def test_handoff_cannot_reset_three_failure_stop(self):
        from webcollect.site_failure_stop import SiteFailureStore, SiteStopped
        binding = {'ledger': str(self.root / 'stop.sqlite3'),
                   'campaign_id': 'CONTROLLED-stop', 'formal_since': 1}
        store = SiteFailureStore.initialize(binding)
        for number in range(3):
            store.record('https://example.org/', 'CONTROLLED-' + str(number),
                stage='observation', state='failed', reason='synthetic failure',
                real_execution=True, evidence=[{'fixture': number}], usage_refs=[{'fixture': number}])
        before = file_sha(binding['ledger'])
        self.prepare()
        self.assertEqual(file_sha(binding['ledger']), before)
        self.assertEqual(store.status('https://example.org/')['failure_count'], 3)
        with self.assertRaises(SiteStopped):
            store.guard('https://example.org/another-page')


if __name__ == '__main__':
    unittest.main()
