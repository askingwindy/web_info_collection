"""Temporary rejected-only scopes; no production DB or browser mutation."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from m4_runtime_fixtures import NOW, evidence, make_plan, make_registry
from webcollect.collect_runtime import close_scope_for_replan, runtime_scope, sync_manifest
from webcollect.production_quality import sha
from webcollect.runtime import RuntimeStore
from webcollect.storage import write_json


class RuntimeClosureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve(); self.output = self.root / 'batch'; self.output.mkdir()
        self.registry = make_registry(self.root / 'registry.sqlite3')
        self.store = RuntimeStore(self.registry, runtime_scope(self.output))
        self.store.initialize({'attempt_cap': 40, 'target_total': 1000}, now=NOW)
        self.plan, self.publication = make_plan(self.root / 'planning', 20)
        self.store.enqueue_plan(self.plan, self.publication, now=NOW)
        batch_id = None
        for i in range(5):
            row = self.store.claim_next('test-worker', request_id=str(i), now=NOW+i*3, batch_id=batch_id)
            batch_id = row['batch_id']
            self.store.start_attempt(row['attempt_id'], 'test-worker', row['lease_token'], now=NOW+i*3)
            proof = evidence(self.output / 'evidence' / row['sample_id'] / 'failure.json', json.dumps({'error': 'controlled program rejection'}))
            self.store.finish_attempt(row['attempt_id'], 'test-worker', row['lease_token'], 'rejected',
                failure_class='program', root_cause='program', evidence=proof, now=NOW+i*3+1)
        self.store.set_scope_paused(True, 'controlled fixture pause', now=NOW+20)
        self.manifest = {'runtime_scope_id': self.store.scope_id, 'registry_path': str(self.registry)}
        write_json(self.output / 'plan.json', self.plan)
        sync_manifest(self.store, self.output, self.manifest)
        self.proof = evidence(self.root / 'reason.txt')
        self.original = {p: sha(p) for p in self.output.rglob('*') if p.is_file()}

    def close(self, **kwargs):
        return self.store.close_failed_scope(self.output, 'repair actual program failure', self.proof, now=NOW+30, **kwargs)

    def test_close_preserves_five_attempts_and_fifteen_unstarted_tasks_and_files(self):
        before = self.store.snapshot(); result = self.close(); receipt = result['closure']; after = self.store.snapshot()
        self.assertEqual(receipt['counts'], {'planned_tasks':20,'actual_attempts':5,'rejected_attempts':5,
            'saved_attempts':0,'inflight_attempts':0,'reserved_unstarted':0,'unstarted_tasks':15})
        self.assertEqual(before['attempts'], after['attempts'])
        self.assertEqual(after['campaign_actual_attempt_count'], 5)
        self.assertEqual(after['policy']['attempt_cap'], 40)
        self.assertEqual(after['scope']['state'], 'closed_replanned')
        self.assertTrue(all(row['status']=='needs_replan' and not row['quota_reserved'] for row in after['tasks']))
        self.assertEqual({p:sha(p) for p in self.original}, self.original)
        self.assertTrue(all(set(row)=={'task_id','task_version','plan_entry'} for row in receipt['unstarted_tasks']))
        self.assertEqual(receipt['attempts'], self.manifest['attempts'])
        event=after['events'][-1]; self.assertEqual(event['event_type'],'scope_closed_replanned')
        self.assertEqual(event['payload']['sha256'],sha(result['path']))
        self.assertIsNone(self.store.claim_next('worker',request_id='after-close',now=NOW+40))
        with self.assertRaisesRegex(ValueError,'永久'):self.store.set_scope_paused(False,'forbidden resume')
        with self.assertRaisesRegex(ValueError,'永久'):sync_manifest(self.store,self.output,self.manifest)
        with self.assertRaisesRegex(ValueError,'永久'):self.store.resource_checkpoint(self.output)
        with self.assertRaisesRegex(ValueError,'永久'):self.store.enqueue_plan(self.plan,self.publication,now=NOW+40)

    def test_new_version_new_scope_shares_remaining_budget_without_reviving_old(self):
        self.close()
        newer = RuntimeStore(self.registry, 'new-scope'); newer.initialize({'attempt_cap':40,'target_total':1000},now=NOW+40)
        plan,pub=make_plan(self.root/'replanned',20,version='2'); newer.enqueue_plan(plan,pub,now=NOW+40)
        row=newer.claim_next('new-worker',request_id='new',now=NOW+40)
        newer.start_attempt(row['attempt_id'],'new-worker',row['lease_token'],now=NOW+40)
        self.assertEqual(newer.snapshot()['campaign_actual_attempt_count'],6)
        self.assertEqual(self.store.snapshot()['scope']['state'],'closed_replanned')
        self.assertNotIn(row['sample_id'],{a['sample_id'] for a in self.store.snapshot()['attempts']})

    def test_duplicate_close_is_idempotent_and_conflicting_reason_rejected(self):
        first=self.close(); before=self.registry.read_bytes(); again=self.close()
        self.assertTrue(again['already_closed']); self.assertEqual(first['sha256'],again['sha256'])
        self.assertEqual(before,self.registry.read_bytes())
        with self.assertRaisesRegex(ValueError,'原因或证据不同'):
            self.store.close_failed_scope(self.output,'different',self.proof)
        receipt=Path(first['path']);receipt.write_text('{}')
        with self.assertRaisesRegex(ValueError,'SHA'):self.close()

    def test_concurrent_closures_have_one_receipt_and_event(self):
        with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(lambda _:self.close(),range(2)))
        self.assertEqual(sorted(r['already_closed'] for r in results),[False,True])
        self.assertEqual(len([e for e in self.store.snapshot()['events'] if e['event_type']=='scope_closed_replanned']),1)

    def test_active_reserved_and_saved_scopes_cannot_close(self):
        self.store.set_scope_paused(False,'controlled restart',now=NOW+30)
        with self.assertRaisesRegex(ValueError,'已暂停'):self.close()
        row=self.store.claim_next('worker',request_id='reserved',now=NOW+31)
        self.store.set_scope_paused(True,'paused with reserved',now=NOW+32)
        with self.assertRaisesRegex(ValueError,'在途'):self.close()
        self.store.start_attempt(row['attempt_id'],'worker',row['lease_token'],now=NOW+33)
        self.store.finish_attempt(row['attempt_id'],'worker',row['lease_token'],'collected_pending_review',
                                 evidence=self.proof,now=NOW+34)
        with self.assertRaisesRegex(ValueError,'成功'):self.close()
        self.assertFalse((self.output/'replanning'/'closure.json').exists())

    def test_snapshot_drift_or_manifest_omission_is_not_rewritten(self):
        path=self.output/'runtime-snapshot.json';value=json.loads(path.read_text());value['attempts'].pop();path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError,'快照'):self.close()
        sync_manifest(self.store,self.output,self.manifest)
        path=self.output/'manifest.json';value=json.loads(path.read_text());value['attempts'].pop();path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError,'分母'):self.close()

    def fractional_started_fixture(self):
        # Controlled DB only: use the exact float that exposed ISO round-trip loss.
        started = 1792939275.2014441
        attempt_id = self.store.snapshot()['attempts'][-1]['attempt_id']
        with sqlite3.connect(self.registry) as con:
            con.execute('UPDATE m4_attempts SET started_at=? WHERE attempt_id=?', (started, attempt_id))
        sync_manifest(self.store, self.output, self.manifest)
        original = next(row for row in self.manifest['attempts'] if row['attempt_id'] == attempt_id)
        self.assertNotEqual(datetime.fromisoformat(original['started_at']).timestamp(), started)
        return original

    def test_fractional_sqlite_start_matches_its_original_iso_microsecond_serialization(self):
        original = self.fractional_started_fixture()
        self.assertEqual(original['started_at'], '2026-10-25T14:41:15.201444+00:00')
        before = self.store.snapshot()['attempts']
        self.assertEqual(self.close()['closure']['counts']['actual_attempts'], 5)
        self.assertEqual(self.store.snapshot()['attempts'], before)

    def test_real_microsecond_started_difference_is_rejected_without_receipt_or_db_change(self):
        original = self.fractional_started_fixture()
        original['started_at'] = (datetime.fromisoformat(original['started_at']) + timedelta(microseconds=1)).isoformat()
        (self.output / 'manifest.json').write_text(json.dumps(self.manifest))
        before = self.store.snapshot()
        with self.assertRaisesRegex(ValueError, '开始时间'):self.close()
        self.assertEqual(self.store.snapshot(), before)
        self.assertFalse((self.output / 'replanning' / 'closure.json').exists())

    def test_failed_before_receipt_does_not_release_quota(self):
        before=self.store.snapshot()
        def fail(point):
            if point=='before_receipt':raise RuntimeError('controlled pre-receipt failure')
        with self.assertRaisesRegex(RuntimeError,'controlled'):self.close(_fault=fail)
        self.assertEqual(before,self.store.snapshot());self.assertFalse((self.output/'replanning'/'closure.json').exists())

    def test_commit_interruption_retains_diagnosable_orphan_without_changing_attempts(self):
        before=self.store.snapshot()
        def fail(point):
            if point=='after_receipt_before_commit':raise RuntimeError('controlled commit interruption')
        with self.assertRaisesRegex(RuntimeError,'controlled'):self.close(_fault=fail)
        self.assertEqual(before,self.store.snapshot());self.assertFalse((self.output/'replanning'/'closure.json').exists())
        self.assertEqual(len(list((self.output/'replanning').glob('.closure-*.prepared.json'))),1)
        with self.assertRaisesRegex(ValueError,'提交中断'):self.close()

    def test_committed_closure_can_recover_interrupted_receipt_publication(self):
        def fail(point):
            if point=='after_commit_before_publish':raise RuntimeError('controlled publication interruption')
        with self.assertRaisesRegex(RuntimeError,'controlled'):self.close(_fault=fail)
        self.assertEqual(self.store.snapshot()['scope']['state'],'closed_replanned')
        self.assertFalse((self.output/'replanning'/'closure.json').exists())
        recovered=self.close();self.assertTrue(recovered['already_closed'])
        self.assertTrue((self.output/'replanning'/'closure.json').is_file())
        self.assertFalse(list((self.output/'replanning').glob('.closure-*.prepared.json')))

    def test_close_adapter_refuses_running_output_lock(self):
        import fcntl
        lock_path=self.output.parent/('.'+self.store.scope_id+'.lock')
        with lock_path.open('a+') as lock:
            fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaisesRegex(ValueError,'并发关闭'):
                close_scope_for_replan(self.output,self.registry,'reason',self.proof)

    def test_evidence_is_mandatory_and_original_evidence_drift_blocks_replay(self):
        with self.assertRaisesRegex(ValueError,'证据'):self.store.close_failed_scope(self.output,'reason',[])
        self.close();next(iter(self.original)).write_text('tamper')
        with self.assertRaisesRegex(ValueError,'SHA'):self.close()


if __name__=='__main__':unittest.main()
