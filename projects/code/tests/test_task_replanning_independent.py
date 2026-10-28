"""Independent repair-gate regression using only temporary synthetic ledgers."""
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from m4_runtime_fixtures import NOW, evidence, make_plan, make_registry
from webcollect.batch_core import BatchLedger, BudgetStop, file_sha
from webcollect.collect_runtime import runtime_scope, sync_manifest
from webcollect.planning import object_sha256
from webcollect.runtime import RuntimeStore
from webcollect.storage import write_json
from webcollect.task_generation import check_live_m4_history, execute, generate, generation_source_identity
from webcollect.task_replanning import closure_references, validated_replans
from test_s0_task_generation import capability, catalog, config


class RepairGateTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve();self.output=self.root/'original';self.output.mkdir()
        self.registry=make_registry(self.root/'registry.sqlite3')
        self.store=RuntimeStore(self.registry,runtime_scope(self.output))
        self.store.initialize({'attempt_cap':4,'target_total':1000},now=NOW)
        self.plan,self.publication=make_plan(self.root/'planning',1)
        self.store.enqueue_plan(self.plan,self.publication,now=NOW)
        self.attempt=self.store.claim_next('test',request_id='first',now=NOW)
        self.store.start_attempt(self.attempt['attempt_id'],'test',self.attempt['lease_token'],now=NOW)
        self.failure=evidence(self.output/'evidence'/self.attempt['sample_id']/'failure.json',json.dumps({'error':'controlled rejected original'}))
        self.store.finish_attempt(self.attempt['attempt_id'],'test',self.attempt['lease_token'],'rejected',
            failure_class='program',root_cause='program',evidence=self.failure,now=NOW+1)
        self.manifest={'runtime_scope_id':self.store.scope_id,'registry_path':str(self.registry)}
        write_json(self.output/'plan.json',self.plan)
        sync_manifest(self.store,self.output,self.manifest)
        self.reason=evidence(self.root/'repair-reason.txt')

    def close(self, *, pause=False):
        if pause:
            self.store.set_scope_paused(True,'controlled pause',now=NOW+2)
            sync_manifest(self.store,self.output,self.manifest)
        result=self.store.close_failed_scope(self.output,'controlled program repair',self.reason,now=NOW+3)
        self.refs=closure_references([result['path']]);return result

    def candidate(self):
        plan=deepcopy(self.plan);plan.pop('media_preflight',None)
        plan['generation']={'replan_closures':self.refs}
        return plan

    def test_committed_rejected_only_closure_allows_replanning_and_preserves_original(self):
        result=self.close();before=self.registry.read_bytes()
        allowed,campaigns=validated_replans(self.registry,self.refs)
        self.assertEqual(campaigns,{'m4-1000'})
        self.assertEqual(allowed,{self.store.scope_id:{object_sha256(self.plan['tasks'][0])}})
        check_live_m4_history(self.candidate(),self.registry,self.root/'replacement')
        self.assertEqual(before,self.registry.read_bytes())
        self.assertEqual(result['closure']['counts']['rejected_attempts'],1)
        self.assertTrue(Path(self.failure[0]['path']).exists())

    def test_same_task_without_closure_still_rejected(self):
        self.close();plan=self.candidate();plan['generation']['replan_closures']=[]
        with self.assertRaisesRegex(ValueError,'same business/structure'):
            check_live_m4_history(plan,self.registry,self.root/'replacement')

    def test_forged_rehashed_receipt_not_committed_in_event_rejected(self):
        result=self.close();forged=self.root/'forged.json';body=deepcopy(result['closure'])
        body['reason']='forged reason';forged.write_text(json.dumps(body))
        with self.assertRaisesRegex(ValueError,'committed ledger event'):
            validated_replans(self.registry,closure_references([forged]))

    def test_unclosed_scope_cannot_be_replaced_by_a_receipt(self):
        self.close()
        with sqlite3.connect(self.registry) as con:
            con.execute("UPDATE m4_scopes SET state='paused' WHERE scope_id=?",(self.store.scope_id,))
        with self.assertRaisesRegex(ValueError,'actually closed'):
            validated_replans(self.registry,self.refs)

    def test_saved_running_or_reserved_task_never_exempted(self):
        self.close()
        for state in ('collected_pending_review','reviewed_pass','published','running','reserved','queued'):
            with sqlite3.connect(self.registry) as con:con.execute('UPDATE m4_tasks SET status=?',(state,))
            with self.subTest(state=state),self.assertRaisesRegex(ValueError,'saved, or reserved tasks'):
                validated_replans(self.registry,self.refs)

    def test_attempt_saved_or_unstarted_cannot_use_old_closure(self):
        self.close()
        with sqlite3.connect(self.registry) as con:con.execute("UPDATE m4_attempts SET status='collected_pending_review'")
        with self.assertRaises(ValueError):validated_replans(self.registry,self.refs)
        with sqlite3.connect(self.registry) as con:con.execute("UPDATE m4_attempts SET status='rejected',started_at=NULL")
        with self.assertRaises(ValueError):validated_replans(self.registry,self.refs)

    def test_original_failure_evidence_drift_rejected(self):
        self.close();Path(self.failure[0]['path']).write_text('changed original')
        with self.assertRaises(ValueError):validated_replans(self.registry,self.refs)

    def test_repair_reason_evidence_drift_rejected(self):
        self.close();Path(self.reason[0]['path']).write_text('changed reason evidence')
        with self.assertRaises(ValueError):validated_replans(self.registry,self.refs)

    def test_duplicate_closure_reference_rejected(self):
        self.close()
        with self.assertRaises(ValueError):validated_replans(self.registry,self.refs+self.refs)

    def test_registry_attempt_identity_drift_is_not_hidden_by_same_attempt_id(self):
        self.close()
        with sqlite3.connect(self.registry) as con:con.execute("UPDATE m4_attempts SET root_cause='changed-after-closure'")
        with self.assertRaises(ValueError):validated_replans(self.registry,self.refs)

    async def execute_boundary(self,campaign='m4-1000',attempt_cap=None):
        self.close();plan=self.candidate()
        if attempt_cap is not None:self.store.update_policy({'attempt_cap':attempt_cap},'controlled remaining budget test',now=NOW+4)
        for task in plan['tasks']:task['deterministic_strategy']={'id':'controlled-repair-test'}
        manifest=self.root/'history.json';manifest.write_text('{}')
        scope={'schema_version':'webcollect-task-history-scope-1','manifest':{'path':str(manifest),'sha256':file_sha(manifest)}}
        plan['generation'].update(mode='real',source_identity=generation_source_identity(),history_scope=scope)
        plan_path=self.root/'candidate.json';plan_path.write_text(json.dumps(plan))
        catalog_path=self.root/'catalog-real.json';catalog_path.write_text(json.dumps({'mode':'real'}))
        policy=self.store.snapshot()['policy'];policy['campaign_id']=campaign
        policy_path=self.root/'policy.json';policy_path.write_text(json.dumps(policy))
        ledger=BatchLedger(self.root/'execution-ledger.sqlite3',config('real'),initialize=True)
        preflight=AsyncMock(side_effect=RuntimeError('controlled preflight sentinel'))
        with patch('webcollect.task_generation.read_customer_history',return_value=([],scope)), \
             patch('webcollect.task_generation.bind_formal_history',side_effect=lambda value:value), \
             patch('webcollect.preflight.preflight_plan',preflight):
            try:
                await execute(ledger,plan_path,catalog_path,self.root/'replacement',self.registry,policy_path)
            finally:
                self.boundary_preflight_calls=preflight.await_count
                self.boundary_visits=ledger.visits()

    async def test_cross_campaign_repair_stops_before_preflight_or_allocation(self):
        with self.assertRaisesRegex(ValueError,'original campaign'):
            await self.execute_boundary(campaign='different-campaign')
        self.assertEqual(self.boundary_preflight_calls,0);self.assertEqual(self.boundary_visits,[])
        self.assertEqual(self.store.snapshot()['campaign_actual_attempt_count'],1)

    async def test_same_campaign_valid_repair_can_reach_preflight_without_allocating(self):
        with self.assertRaisesRegex(RuntimeError,'controlled preflight sentinel'):
            await self.execute_boundary()
        self.assertEqual(self.boundary_preflight_calls,1);self.assertEqual(self.boundary_visits,[])
        self.assertEqual(self.store.snapshot()['campaign_actual_attempt_count'],1)

    async def test_valid_repair_does_not_reset_consumed_campaign_attempt_budget(self):
        with self.assertRaises(BudgetStop):await self.execute_boundary(attempt_cap=1)
        self.assertEqual(self.boundary_preflight_calls,0);self.assertEqual(self.boundary_visits,[])
        self.assertEqual(self.store.snapshot()['campaign_actual_attempt_count'],1)

    def generate_at_repair_boundary(self):
        record=capability(self.root/'capability')
        catalog_path=catalog(self.root/'catalog-synthetic.json',[record])
        ledger=BatchLedger(self.root/'generation-ledger.sqlite3',config(),initialize=True)
        # Isolate generation's history/closure gate from the independent business
        # compiler: the returned task is the real temporary ledger's frozen task.
        with patch('webcollect.task_generation.deterministic_specs',return_value={'tasks':[{}]}), \
             patch('webcollect.task_generation.compile_form',return_value=deepcopy(self.plan['tasks'][0])):
            return generate(ledger,catalog_path,self.root/'generated',history_registry=self.registry,
                            replan_closures=[self.refs[0]['path']])

    def test_generate_exempts_only_closed_failed_scope_and_binds_receipt(self):
        self.close();result=self.generate_at_repair_boundary()
        self.assertEqual(result['generated_tasks'],1)
        self.assertEqual(result['historical_tasks_consulted'],1)
        self.assertEqual(result['explicit_closed_failed_tasks_for_repair'],1)
        plan=json.loads(Path(result['plan_file']).read_text())
        self.assertEqual(plan['generation']['replan_closures'],self.refs)

    def test_generate_does_not_exempt_identical_saved_task_in_other_campaign_scope(self):
        self.close()
        other=RuntimeStore(self.registry,'different-saved-scope')
        other.initialize({'campaign_id':'different-campaign','attempt_cap':4,'target_total':1000},now=NOW+10)
        other.enqueue_plan(self.plan,self.publication,now=NOW+10)
        attempt=other.claim_next('other',request_id='other-saved',now=NOW+10)
        other.start_attempt(attempt['attempt_id'],'other',attempt['lease_token'],now=NOW+10)
        other.finish_attempt(attempt['attempt_id'],'other',attempt['lease_token'],'collected_pending_review',
                             evidence=evidence(self.root/'other-saved.txt'),now=NOW+11)
        result=self.generate_at_repair_boundary()
        self.assertEqual(result['generated_tasks'],0)
        self.assertEqual(result['historical_tasks_consulted'],2)
        self.assertEqual(result['explicit_closed_failed_tasks_for_repair'],1)

    def test_active_finished_all_rejected_closes_without_rewriting_original_files(self):
        self.assertEqual(self.store.snapshot()['scope']['state'],'active')
        self.assertEqual(self.manifest['collection_status'],'finished_pending_review')
        original={str(p):file_sha(p) for p in self.output.rglob('*') if p.is_file()}
        result=self.close(pause=False)
        self.assertEqual(result['closure']['counts']['unstarted_tasks'],0)
        self.assertEqual({path:file_sha(path) for path in original},original)
        self.assertEqual(self.store.snapshot()['scope']['state'],'closed_replanned')

    def test_active_finished_claim_with_unattempted_task_is_rejected(self):
        with sqlite3.connect(self.registry) as con:
            columns=[r[1] for r in con.execute('PRAGMA table_info(m4_tasks)')]
            row=list(con.execute('SELECT * FROM m4_tasks').fetchone())
            for name,value in [('task_key','unattempted-key'),('task_id','unattempted'),('status','queued')]:row[columns.index(name)]=value
            con.execute('INSERT INTO m4_tasks VALUES('+','.join('?' for _ in row)+')',row)
        with self.assertRaises(ValueError):self.close(pause=False)
        self.assertFalse((self.output/'replanning/closure.json').exists())

    def test_active_finished_with_saved_attempt_rejected_without_receipt(self):
        with sqlite3.connect(self.registry) as con:con.execute("UPDATE m4_attempts SET status='collected_pending_review'")
        with self.assertRaises(ValueError):self.close(pause=False)
        self.assertFalse((self.output/'replanning/closure.json').exists())


if __name__=='__main__':unittest.main()
