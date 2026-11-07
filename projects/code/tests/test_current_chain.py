"""Temporary current-chain fixtures; no real data, models or browser activity."""
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from webcollect.batch_core import file_sha, save_json
from webcollect.current_chain import (initialize_chain, read_chain_history, history_context,
    assert_registry_scope, assert_current_result_path, assert_current_evidence,
    append_current_result, validate_history_context)
from webcollect.task_admission import context, reference
from webcollect.task_generation import read_customer_history, bind_formal_history, read_history


class CurrentChainTests(unittest.TestCase):
    def test_research_inputs_do_not_adopt_historical_observations(self):
        objective=self.root/'old-objective.json';authorization=self.root/'authorization.json'
        save_json(objective,{'schema_version':'webcollect-session-objective-1','candidate_id':'c','version':1})
        save_json(authorization,{'scope':'original-two-baselines-only','candidate_id':'c','version':1,
                               'objective':reference(objective),'production_counted':False})
        descriptor={'schema_version':'candidate-research-replay-1','original_claim_id':'original',
                    'objective':reference(objective),'authorization':reference(authorization),'production_counted':False}
        assert_current_evidence(self.scope,descriptor)
        for origin in ('original','model-proposed-research'):
            assert_current_evidence(self.scope,{**descriptor,'objective_origin':origin})
        with self.assertRaisesRegex(ValueError,'invalid research'):
            assert_current_evidence(self.scope,{**descriptor,'objective_origin':'invented'})
        with self.assertRaisesRegex(ValueError,'out-of-chain'):
            assert_current_evidence(self.scope,{'research_replay':descriptor,'observation':reference(objective)})
        bad=deepcopy(descriptor);bad['observation']=reference(objective)
        with self.assertRaisesRegex(ValueError,'invalid research'):assert_current_evidence(self.scope,bad)
        authorization.write_text(json.dumps({'candidate_id':'wrong'}))  # disposable tamper fixture
        with self.assertRaisesRegex(ValueError,'changed'):assert_current_evidence(self.scope,descriptor)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.manifest = self.root/'run'/'scope'/'manifest.json'
        self.registry = self.root/'new-results'/'state'/'registry.sqlite3'
        self.results = self.root/'new-results'
        self.scope = initialize_chain(self.manifest, self.registry, chain_id='CONTROLLED-current',
                                      current_result_roots=[self.results])

    def test_initial_empty_is_explicit_and_never_reads_formal_latest(self):
        with patch('webcollect.task_generation.FORMAL_LATEST_PATH', self.root/'MISSING-LATEST'):
            records, scope = read_customer_history(self.manifest)
            self.assertEqual(records, [])
            self.assertEqual(bind_formal_history(scope), scope)
            self.assertEqual(read_history(self.registry), [])
            self.assertEqual(context(scope, [], self.registry)['comparisons'], [])
            self.assertNotIn('formal_anchor', scope)

    def test_exact_initialization_is_idempotent(self):
        digest = file_sha(self.manifest)
        self.assertEqual(initialize_chain(self.manifest, self.registry, chain_id='CONTROLLED-current',
                         current_result_roots=[self.results]), self.scope)
        self.assertEqual(file_sha(self.manifest), digest)

    def test_cannot_rebind_chain_or_registry(self):
        with self.assertRaisesRegex(ValueError, 'cannot rebind'):
            initialize_chain(self.manifest, self.registry, chain_id='OTHER', current_result_roots=[self.results])
        with self.assertRaisesRegex(ValueError, 'changed'):
            assert_registry_scope(self.scope, self.root/'old-registry.sqlite3')

    def test_old_unmarked_registry_is_not_adopted_or_deleted(self):
        old = self.root/'old.sqlite3'
        with sqlite3.connect(old) as con:
            con.execute('CREATE TABLE m4_tasks(task_json TEXT)')
            con.execute('INSERT INTO m4_tasks VALUES(?)', ('{"old":true}',))
        digest = file_sha(old)
        with self.assertRaisesRegex(ValueError, 'existing registry'):
            initialize_chain(self.root/'another/manifest.json', old, chain_id='OTHER',
                             current_result_roots=[self.root/'empty'])
        self.assertEqual(file_sha(old), digest)

    def test_existing_historical_annotations_cannot_seed_empty_scope(self):
        old = self.root/'old200'; old.mkdir(); save_json(old/'annotation.json', {'sample_id':'old'})
        with self.assertRaisesRegex(ValueError, 'initial current result population must be empty'):
            initialize_chain(self.root/'another/manifest.json', self.root/'another.sqlite3',
                             chain_id='OTHER', current_result_roots=[old])

    def test_outside_result_path_and_symlink_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'out-of-chain'):
            assert_current_result_path(self.scope, self.root/'old200'/'annotation.json')
        link = self.results/'linked'; link.symlink_to(self.root)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            assert_current_result_path(self.scope, link/'old200'/'annotation.json')

    def test_forged_comparison_or_legacy_anchor_cannot_enter_context(self):
        ctx = history_context(self.scope, [], self.registry)
        self.assertTrue(validate_history_context(ctx))
        forged = deepcopy(ctx); forged['comparisons'] = [{'id':'customer:OLD200','record':{}}]
        with self.assertRaisesRegex(ValueError, 'historical|unbound'):
            validate_history_context(forged)
        forged = deepcopy(ctx); forged['history_scope']['formal_anchor'] = {'path':'/old/LATEST','sha256':'x'}
        with self.assertRaises(ValueError):
            validate_history_context(forged)

    def test_manifest_bytes_and_registry_marker_are_bound(self):
        text = self.manifest.read_text(); self.manifest.write_text(text+'\n')
        with self.assertRaisesRegex(ValueError, 'changed'):
            assert_registry_scope(self.scope, self.registry)

    def test_copying_old_task_into_new_registry_cannot_create_history(self):
        with sqlite3.connect(self.registry) as con:
            con.execute('INSERT INTO m4_tasks VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                        ('old-key','old-scope','old-campaign','old','v1','sha','{}','x','old.example',
                         'failed',0,9999999999,0,0))
        with self.assertRaisesRegex(ValueError, 'plan bound'):
            read_history(self.registry)

    def test_no_unbacked_result_can_be_added(self):
        folder = self.results/'S-current'; folder.mkdir()
        path = folder/'annotation.json'; save_json(path, {'sample_id':'S-current'})
        with self.assertRaisesRegex(ValueError, 'no original current-chain attempt'):
            append_current_result(self.manifest, path, site_uri='https://example.org/', task_key='unknown')
        self.assertEqual(read_chain_history(self.manifest)[0], [])

    def test_current_evidence_keeps_original_bytes_and_rejects_external_history(self):
        raw = self.root/'run'/'raw.json'; save_json(raw, {'original':True})
        digest = file_sha(raw)
        self.assertTrue(assert_current_evidence(self.scope, reference(raw)))
        self.assertEqual(file_sha(raw), digest)
        old = self.root/'old200.json'; save_json(old, {'old':True})
        with self.assertRaisesRegex(ValueError, 'out-of-chain'):
            assert_current_evidence(self.scope, reference(old))

    def test_nested_legacy_population_inside_current_run_is_rejected(self):
        raw = self.root/'run'/'old-context.json'
        save_json(raw, {'history_scope':{'schema_version':'webcollect-task-history-scope-1'}})
        with self.assertRaisesRegex(ValueError, 'historical population'):
            assert_current_evidence(self.scope, reference(raw))

    def test_explicit_rejected_frame_relocation_keeps_dispatch_and_checks_original_bytes(self):
        old=self.results/'capture/samples/S-current/images/step_001.png'
        old.parent.mkdir(parents=True);old.write_bytes(b'CONTROLLED ORIGINAL PNG BYTES')
        original=reference(old);dispatch=self.results/'capture/evidence/dispatch.json'
        save_json(dispatch,{'formal_frame':original});digest=file_sha(dispatch)
        moved=self.results/'capture/rejected/S-current/images/step_001.png'
        moved.parent.mkdir(parents=True);old.rename(moved)
        value={'dispatch':reference(dispatch),'frame_relocations':[{
            'schema_version':'webcollect-rejected-frame-relocation-1','original_path':str(old),
            'original_sha256':original['sha256'],'current':reference(moved),'dispatch':reference(dispatch)}]}
        self.assertTrue(assert_current_evidence(self.scope,value))
        self.assertEqual(file_sha(dispatch),digest);self.assertFalse(old.exists())
        forged=deepcopy(value);forged['frame_relocations'][0]['current']=reference(self.manifest)
        with self.assertRaisesRegex(ValueError,'original samples-to-rejected'):
            assert_current_evidence(self.scope,forged)
        moved.write_bytes(b'CHANGED')
        with self.assertRaisesRegex(ValueError,'bytes changed'):
            assert_current_evidence(self.scope,value)


if __name__ == '__main__':
    unittest.main()
