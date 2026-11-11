"""Two bounded disposable rounds through normal CLIs and simulated transports."""
import asyncio
from copy import deepcopy
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from test_pipeline_offline_e2e import PipelineAcceptance
from test_react_session import FakePage, decide, act_step
from site_planner.candidate_discovery import main as producer_cli
from site_planner.candidate_pool import CandidatePool, VERSION2
from site_planner.discovery_tools import reference
from webcollect.batch_core import load_json, save_json, file_sha, BudgetStop, BatchLedger, ModelRateWait
from webcollect.candidate_consumer import main as consumer_cli, finish_or_reconcile, retry
from webcollect.candidate_batch import report, recover, reprocess, first_frame_disposition, usage_report
from webcollect.runtime import RuntimeStore
from test_react_native import NativeSessionTests, finish


class ProbeFeedbackAcceptance(NativeSessionTests):
    async def test_known_missing_probe_feedback_and_no_false_hint(self):
        session, evidence, script = self.recorded([
            decide(goal='修改当前数量并核对输入',tool='act',arguments=lambda p: {
                'observation_id':p['observation']['observation_id'],
                'step':act_step('set_value',control_id='control-0',value='20')}),
            decide(tool='observe',arguments={'focus_control_id':'control-0'}),
            decide(tool='act',arguments=lambda p: {'observation_id':p['observation']['observation_id'],
                'step':act_step('set_value',control_id='control-0',value='20')}), finish()])
        summary = await session.run()
        feedback = script.prompts[1]['last_tool_result']
        self.assertEqual(feedback['data']['next_tool'],{'name':'observe','arguments':{'focus_control_id':'control-0'}})
        self.assertEqual(feedback['data']['original_rejection'],'INSUFFICIENT: MISSING_TARGET_PROBE')
        self.assertEqual(feedback['data']['actual_actions_delta'],0)
        self.assertEqual(script.prompts[1]['progress']['effective_steps'],0)
        history = json.loads(script.prompts[1]['_history'][-1]['content'])
        self.assertEqual({k:history[k] for k in feedback},feedback)
        self.assertEqual(summary['effective_steps'],3)
        rejected = await session._tool_act({'observation_id':session.current['observation_id'],
            'step':act_step('set_value',control_id='invented',value='30')})
        self.assertNotIn('next_tool',rejected['data'])
        # A known label gap is not a missing probe: do not repeat the hint.
        session.current['controls']['control-0']['actions']['set_value'] = {
            'status':'INSUFFICIENT','reason':'MISSING_READABLE_LABEL_EVIDENCE'}
        rejected = await session._tool_act({'observation_id':session.current['observation_id'],
            'step':act_step('set_value',control_id='control-0',value='30')})
        self.assertNotIn('next_tool',rejected['data'])


class BatchAcceptance(PipelineAcceptance):
    def export_batch(self, name, value):
        root = os.environ.get('WEBCOLLECT_BATCH_REPORT_DIR')
        if root:
            import shutil
            archive = Path(root) / (name + '-disposable-fixture')
            shutil.copytree(self.root, archive)
            value['detached_fixture'] = {'path':str(archive),'original_root':str(self.root),
                'note':'Read-only forensic copy; original absolute bindings are retained, not rebased for dispatch.'}
            save_json(Path(root) / (name + '.json'), {'scope':'DISPOSABLE SIMULATED BATCH; no real review or production', **value})

    async def test_two_round_targeted_recovery_and_isolated_revision(self):
        root, scope, producer, consumer = self.fresh_project()
        goals = root / 'goals.json'
        save_json(goals, {'schema_version':'webcollect-caller-goals-1', 'goals':[
            {'uri':self.uri, 'requested_goal':{'kind':'edit','entity':'fields','parameters':{'quantity':20+i,'price':30+i}},
             'category_hint':'在线工具'} for i in range(5)]})
        initial = deepcopy(self.surface.state)
        original_goto = FakePage.goto
        visits = []
        fixed = False
        async def goto(page, url, **kwargs):
            index = len(visits) if not fixed else 1
            visits.append(index)
            self.surface.state = deepcopy(initial)
            self.surface.executed = []
            self.surface.state['document_identity']['performance_time_origin'] += 1000 + len(visits)
            self.surface.state['title'] = '404' if index == 3 else '受控输入页面'
            self.surface.state['visible_text'] = '页面不存在' if index == 3 else '受控输入页面\n数量\n单价\n这里查看当前输入内容与页面状态。'
            self.decisions = []
            if index == 1 and not fixed:
                self.decisions.append(decide(tool='finish',arguments=lambda p: {
                    'observation_id':p['observation']['observation_id'], 'stop_reason':'no_path',
                    'summary':'CONTROLLED first round repairable tool blocker','short_flow':False,'short_flow_reason':None}))
            elif index != 3:
                for n, cid in enumerate(('control-0','control-1')):
                    self.decisions.append(decide(tool='observe',arguments={'focus_control_id':cid}))
                    self.decisions.append(decide(goal='修改当前一组数量和单价并核对输入' if n == 0 else None,
                        tool='act',arguments=lambda p,cid=cid,n=n,index=index: {
                            'observation_id':p['observation']['observation_id'],
                            'step':act_step('set_value',control_id=cid,value=str(20+index if n == 0 else 30+index))}))
                self.decisions.append(decide(tool='finish',arguments=lambda p: {
                    'observation_id':p['observation']['observation_id'],'stop_reason':'ready',
                    'summary':'已修改当前一组并查看输入','short_flow':False,'short_flow_reason':None}))
            await original_goto(page,url,**kwargs)
        with self.boundaries(), patch.object(FakePage, 'goto', goto):
            produced = await asyncio.to_thread(self.invoke,producer_cli,producer + ['--goals',str(goals),'--target','5'])
            self.assertEqual(produced['row_results'], {'NEW':5}, produced)
            batch = produced['batch_scope']
            self.pool = CandidatePool(scope['pool'])
            consumer += ['--producer-batch',batch,'--target','5','--limit','5','--request-prefix','round-one']
            first = await asyncio.to_thread(self.invoke,consumer_cli,consumer)
            self.assertEqual(first['processed'],5,first)
            self.assertEqual(first['summary']['saved_pending_or_reviewed'],3,first)
            self.assertEqual(first['summary']['qualified'],0,first)
            self.assertEqual(first['summary']['shortfall'],2)
            self.assertEqual(first['stop_reason'],'processing_limit')
            self.assertEqual(first['summary']['dispositions']['abandon'],1)
            self.assertEqual(first['summary']['dispositions']['optimize'],1)
            self.assertEqual(visits,[0,1,2,3,4])
            rows = first['results']
            repair_id = rows[1]['candidate_id']
            revision_claim = self.pool.get_claim(rows[2]['claim_id'])
            self.pool.record_disposition(revision_claim,disposition='reprocess',reason='description_only',stage='delivery',
                evidence=[rows[2]['result']['save_receipt']],policy_version='fixture-descriptions-1')
            original = Path(rows[2]['result']['save_receipt']['path']).parent.parent.parent
            before = {str(p):file_sha(p) for p in original.rglob('*') if p.is_file()}
            calls = (len(self.wire),len(visits))
            with self.assertRaisesRegex(ValueError,'outside the original dataset'):
                reprocess(self.pool,rows[2]['candidate_id'],original/'invalid-revision',reason='description_only',fix_version='narrative-1')
            revision = reprocess(self.pool,rows[2]['candidate_id'],root/'isolated-revision',reason='description_only',fix_version='narrative-1')
            repeated = reprocess(self.pool,rows[2]['candidate_id'],root/'unused-revision',reason='description_only',fix_version='narrative-1')
            self.assertTrue(repeated['repeated'])
            self.assertEqual(revision['status'],'revision_pending_review',revision)
            self.assertEqual(calls,(len(self.wire),len(visits)))
            self.assertEqual(before,{str(p):file_sha(p) for p in original.rglob('*') if p.is_file()})
            self.assertFalse((root/'unused-revision').exists())
            # Simulate a crash after writing the revision receipt but before pool projection.
            with self.pool.transaction() as con:
                con.execute("DELETE FROM candidate_events WHERE candidate_id=? AND kind='revision'", (rows[2]['candidate_id'],))
            recovered_revision = reprocess(self.pool,rows[2]['candidate_id'],root/'isolated-revision',reason='description_only',fix_version='narrative-1')
            self.assertEqual(recovered_revision['receipt'],revision['receipt'])
            self.assertEqual(calls,(len(self.wire),len(visits)))
            args = dict(reasons=['consumer_failure'],fix_version='tool-fix-1',candidate_ids=produced['candidate_ids'])
            selection = recover(self.pool,batch,**args)
            self.assertEqual(sum(r['state']=='pending' for r in selection['results']),1,selection)
            self.assertEqual(self.pool.claim_next('ordinary','ordinary-worker',protocols=(VERSION2,),producer_batch=batch)['state'],'EMPTY')
            from concurrent.futures import ThreadPoolExecutor
            def compete(index):
                return self.pool.claim_next('repair-worker-'+str(index),'repair-race-'+str(index)+'/0',
                    protocols=(VERSION2,),producer_batch=batch,recovery_version='tool-fix-1')
            with ThreadPoolExecutor(2) as workers:
                claimed = list(workers.map(compete,range(2)))
            winners = [c for c in claimed if c['state'] != 'EMPTY']
            self.assertEqual(len(winners),1,claimed)
            winner = winners[0]
            self.assertEqual(winner['candidate_id'],repair_id)
            fixed = True
            second = await asyncio.to_thread(self.invoke,consumer_cli,consumer + ['--limit','2',
                '--request-prefix',winner['request_id'].rsplit('/',1)[0],'--worker-id',winner['worker_id'],'--recovery-version','tool-fix-1'])
            self.assertEqual(second['processed'],1,second)
            self.assertEqual(second['results'][0]['candidate_id'],repair_id)
            self.assertEqual(second['summary']['saved_pending_or_reviewed'],4)
            self.assertEqual(second['summary']['formal_attempts'],5) # 4 first-round + 1 new; abandon is zero-attempt
            self.assertEqual(second['summary']['qualified'],0)
            self.assertEqual(second['summary']['dispositions']['recovery_ready'],0)
            self.assertEqual(second['stop_reason'],'candidates_exhausted')
            self.assertEqual(second['summary']['shortfall'],1)
            calls = (len(self.wire),len(visits))
            repeat = recover(self.pool,batch,**args)
            # A request prefix is frozen to its original phase. Recovery uses
            # its own prefix and cannot reinterpret the first-round requests.
            with self.assertRaisesRegex(ValueError,'recovery version conflict'):
                await asyncio.to_thread(self.invoke,consumer_cli,consumer + ['--recovery-version','tool-fix-1'])
            third = await asyncio.to_thread(self.invoke,consumer_cli,consumer + ['--request-prefix','repeat-recovery','--recovery-version','tool-fix-1'])
            self.assertEqual(third['processed'],0)
            self.assertEqual(calls,(len(self.wire),len(visits)))
            self.assertEqual(next(r for r in repeat['results'] if r['candidate_id']==repair_id)['state'],'already_recovered')
            # Recovery of the same completed claim and repeated receipt reads count once.
            finish_or_reconcile(self.pool,self.pool.get_claim(rows[0]['claim_id']),reconciliation=True)
            self.assertEqual(report(self.pool,batch,target=5)['target_count'],4)
            await_review = await asyncio.to_thread(self.invoke,consumer_cli,consumer + ['--target-basis','qualified',
                '--request-prefix','review-wait','--recovery-version','tool-fix-1'])
            self.assertEqual(await_review['stop_reason'],'awaiting_review')
            self.assertEqual(await_review['summary']['shortfall'],5)
            # Authored independent-QC fixture is separate from actual production QC.
            self.claim = self.pool.get_claim(rows[0]['claim_id'])
            self.registry = Path(scope['registry'])
            accepted, _ = self.qc_report(rows[0]['result'],'PASS')
            RuntimeStore(self.registry,rows[0]['result']['scope_id']).record_qc_report(accepted)
            reviewed = report(self.pool,batch,target=5,basis='qualified')
            self.assertEqual(reviewed['qualified'],1,reviewed)
            self.assertEqual(reviewed['independently_reviewed_pass'],1)
            self.assertEqual(reviewed['accepted_by_batch_policy'],0)
            self.assertEqual(reviewed['published'],0)
            self.assertEqual(reviewed['pending_review'],3)
            self.assertEqual(reviewed['shortfall'],4)
            usage = usage_report(scope,batch)
            self.assertEqual(usage['consumer_request_classes']['formal_consumption']['requests'],21)
            self.assertEqual(usage['consumer_request_classes']['diagnostic']['requests'],0)
            self.assertNotIn('known_cost_micros',usage['consumer_request_classes']['formal_consumption'])
            self.assertIn('known_cached_input_tokens',usage['consumer_request_classes']['formal_consumption'])
            self.assertEqual(usage['consumer_request_classes']['unattributed']['requests'],0)
            self.assertTrue(usage['disposition_usage'])
            # Mirror the evidence's response-only diagnostic job kind. This is
            # an authored local ledger fixture, with zero external requests.
            diagnostic_ledger = BatchLedger(scope['consumer_db'],load_json(scope['consumer_config']))
            jid = diagnostic_ledger.enqueue('react-feedback-comparison',{'response_only':True,'site_uri':self.uri})
            job = diagnostic_ledger.claim('react-feedback-comparison',job_id=jid)
            while True:
                try:
                    request = diagnostic_ledger.reserve_request(job,'CONTROLLED response-only fixture',1,{})
                    break
                except ModelRateWait as wait:
                    import time
                    time.sleep(wait.seconds)
            diagnostic_ledger.settle_request(request['id'],state='succeeded',response={'offline':True},usage={'input_tokens':2,'output_tokens':1,'cached_input_tokens':0})
            diagnostic_ledger.finish(job,result={'offline':True})
            usage = usage_report(scope,batch)
            self.assertEqual(usage['consumer_request_classes']['formal_consumption']['requests'],21)
            self.assertEqual(usage['consumer_request_classes']['diagnostic']['requests'],1)
            # Export detached evidence: temporary originals are deliberately cleaned up.
            self.export_batch('two-rounds',{'first':first,'selection':selection,'second':second,'repeat':repeat,
                'repeat_run':third,'qualified_target_wait':await_review,'simulated_qc_after':reviewed,
                'revision':load_json(revision['receipt']['path']), 'usage':usage, 'browser_calls':len(visits),
                'model_http_calls':len(self.wire), 'original_bytes_unchanged_by_revision':True,
                'real_independent_review':'NOT_RUN','published':0})

    async def test_frozen_cohort_passes_old_visit_cap_without_replacing_or_replaying_rows(self):
        import hashlib
        root, scope, producer, consumer = self.fresh_project(consumer_limits={'max_top_level_visits':1,'max_probe_pages':1})
        cfg=load_json(scope['consumer_config'])
        goals=root/'goals.json'
        save_json(goals,{'schema_version':'webcollect-caller-goals-1','goals':[
            {'uri':self.uri,'requested_goal':{'kind':'edit','entity':'fields','parameters':{'quantity':n,'price':30}},
             'category_hint':'在线工具'} for n in (20,21,22)]})
        with self.boundaries():
            report=await asyncio.to_thread(self.invoke,producer_cli,producer+['--target','3','--goals',str(goals)])
            batch=report['batch_scope']; pool=CandidatePool(scope['pool'])
            with pool.pool.connect() as con:
                matches=con.execute("""SELECT c.*,b.row_id,b.response_sha256 FROM candidate_batch_rows b
                    JOIN data_candidates c USING(candidate_id) WHERE b.run_id=? AND b.result='NEW' ORDER BY b.raw_index""",(batch,)).fetchall()
            self.assertEqual(len(matches),3)
            selected=[{'order':i,'candidate_id':r['candidate_id'],'version':r['version'],'application_id':r['application_id'],
                'body_sha256':hashlib.sha256(r['body'].encode()).hexdigest(),'producer_row_id':r['row_id'],
                'producer_row_response_sha256':r['response_sha256']} for i,r in enumerate(matches[:2],1)]
            original=root/'selected-scope.json'; save_json(original,{**scope,'batch':batch})
            frozen=root/'cohort.json'; data={'schema_version':'webcollect-validation-cohort-1','source_scope':reference(original),
                'pool':scope['pool'],'registry':scope['registry'],'producer_batch':batch,'denominator':2,'selected':selected}
            save_json(frozen,data)
            ledger=BatchLedger(scope['consumer_db'],cfg,initialize=True)
            job=ledger.claim('original',job_id=ledger.enqueue('original',{'fixture':True}))
            ledger.consume('probe_pages','earlier-visit'); visit=ledger.reserve_visit(job,'https://earlier.example/','original','earlier.example')
            ledger.settle_visit(visit,state='succeeded',response_status=200); ledger.finish(job)
            args=consumer+['--cohort',str(frozen),'--request-prefix','frozen-list']
            bad=root/'mismatch.json';save_json(bad,{**data,'selected':[{**selected[0],'body_sha256':'f'*64},selected[1]]})
            with self.assertRaisesRegex(ValueError,'Frozen candidate version'):
                await asyncio.to_thread(self.invoke,consumer_cli,args+['--cohort',str(bad)])
            one=await asyncio.to_thread(self.invoke,consumer_cli,args)
            self.assertEqual((one['processed'],one['unexamined'],one['denominator']),(1,1,2),one)
            # Omit the fixture's --limit 1; the normal cohort entry drains the remainder.
            args.remove('--limit'); args.remove('1')
            two=await asyncio.to_thread(self.invoke,consumer_cli,args)
            self.assertEqual([r['candidate_id'] for r in two['results']],[selected[1]['candidate_id']],two)
            self.assertEqual(two['skipped'],[{'candidate_id':selected[0]['candidate_id'],'reason':'ALREADY_CLAIMED'}])
            calls=(len(self.gotos),len(self.wire))
            done=await asyncio.to_thread(self.invoke,consumer_cli,args+['--request-prefix','another-worker'])
            self.assertEqual((done['processed'],len(done['skipped']),done['unexamined'],done['stop_reason']),(0,2,0,'cohort_exhausted'))
            self.assertEqual(calls,(len(self.gotos),len(self.wire)))
            self.assertEqual(ledger.summary()['top_level_visits_attempted'],3)
            self.assertEqual([r['candidate_id'] for r in pool.rows(state='pending',protocols=(VERSION2,))],[matches[2]['candidate_id']])

    async def test_glm_25_closes_each_session_with_reason_and_keeps_processing_batch(self):
        root, scope, producer, consumer=self.fresh_project()
        goals=root/'goals.json'
        save_json(goals,{'schema_version':'webcollect-caller-goals-1','goals':[
            {'uri':self.uri,'requested_goal':{'kind':'edit','entity':'fields','parameters':{'quantity':n,'price':30}},
             'category_hint':'在线工具'} for n in (20,21)]})
        inspect=decide(tool='inspect',arguments=lambda p:{
            'kind':'html','observation_id':p['observation']['observation_id'],
            'offset':0,'limit_chars':10})
        actions=self.decisions[:-1]
        self.decisions=[inspect]*25 + actions + [inspect]*(25-len(actions))
        with self.boundaries():
            produced=await asyncio.to_thread(self.invoke,producer_cli,producer+['--target','2','--goals',str(goals)])
            self.assertEqual(produced['row_results'],{'NEW':2},produced)
            first,second=await asyncio.to_thread(self.invoke,consumer_cli,consumer+[
                '--producer-batch',produced['batch_scope'],'--request-prefix','session25','--limit','2'])
        self.assertEqual((first['state'],second['state']),('failed','succeeded'),(first,second))
        self.assertEqual(len(self.prompts),50)
        self.assertEqual(second['QC'],'pending_review',second)
        pool=CandidatePool(scope['pool'])
        with pool.pool.connect() as con:
            disposition=pool.disposition(con,first['candidate_id'])
            self.assertEqual((disposition['disposition'],disposition['reason']),('optimize','glm_session_call_limit'))
        terminal,=[r for r in disposition['evidence'] if Path(r['path']).name=='terminal.json']
        failure=load_json(terminal['path'])['stop_details']
        saved=second['result']['stop_details']
        self.assertEqual((failure['used'],saved['used'],failure['limit'],saved['limit']),(25,25,25,25))
        self.assertNotEqual(failure['attempt_id'],saved['attempt_id'])
        self.assertEqual(saved,load_json(second['result']['save_receipt']['path'])['raw_execution']['stop_details'])
        self.assertEqual(saved['code'],'glm_session_call_limit')

    async def test_target_unknown_and_global_budget_never_redispatch(self):
        with self.boundaries():
            produced = await self.produce()
            self.return_unknown = True
            args = self.cli_args('unknown-target') + ['--producer-batch',produced['batch_scope'],'--target','1']
            first = await asyncio.to_thread(self.invoke,consumer_cli,args)
            self.assertEqual(first['results'][0]['state'],'reconcile',first)
            calls = (len(self.wire),len(self.gotos))
            again = await asyncio.to_thread(self.invoke,consumer_cli,args + ['--request-prefix','unknown-again'])
            self.assertEqual(again['stop_reason'],'account_reconciliation',again)
            selection = recover(self.pool,produced['batch_scope'],reasons=['original_account_unresolved'],
                fix_version='must-not-retry',candidate_ids=produced['candidate_ids'])
            self.assertEqual(selection['results'][0]['state'],'held')
            with patch('webcollect.candidate_consumer.startup_check',return_value={'resource_stop':{'reasons':['disk_full']}}):
                paused = await asyncio.to_thread(self.invoke,consumer_cli,args + ['--request-prefix','budget'])
            self.assertEqual(paused['stop_reason'],'resource_pause')
            self.assertEqual(paused['processed'],0)
            self.assertEqual(calls,(len(self.wire),len(self.gotos)))
            self.export_batch('unknown-budget',{'first':first,'again':again,'recovery':selection,'paused':paused,'additional_dispatches':0})

    async def test_unscoped_worker_keeps_original_explicit_retry(self):
        with self.boundaries():
            produced = await self.produce()
            self.decisions = [decide(tool='finish',arguments=lambda p:{
                'observation_id':p['observation']['observation_id'],'stop_reason':'no_path',
                'summary':'CONTROLLED settled no path','short_flow':False,'short_flow_reason':None})]
            first = await asyncio.to_thread(self.invoke,consumer_cli,self.cli_args('unscoped-compat'))
            self.assertEqual(first[0]['state'],'failed',first)
            cid = produced['candidate_ids'][0]
            with self.pool.pool.connect() as con:
                self.assertIsNone(self.pool.disposition(con,cid))
            result = retry(self.pool,cid,reason='Explicit original unscoped retry after settled failure')
            self.assertEqual(result['state'],'pending')

    async def test_receipt_target_stops_at_one_and_repeated_start_is_read_only(self):
        with self.boundaries():
            produced = await self.produce()
            args = self.cli_args('one-target') + ['--producer-batch',produced['batch_scope'],'--target','1','--limit','3']
            first = await asyncio.to_thread(self.invoke,consumer_cli,args)
            self.assertEqual(first['processed'],1,first)
            self.assertEqual(first['stop_reason'],'target_reached')
            self.assertEqual(first['summary']['shortfall'],0)
            self.assertEqual(first['summary']['qualified'],0)
            calls = (len(self.wire),len(self.gotos))
            again = await asyncio.to_thread(self.invoke,consumer_cli,args + ['--request-prefix','one-target-again'])
            self.assertEqual(again['processed'],0)
            self.assertEqual(again['stop_reason'],'target_reached')
            self.assertEqual(calls,(len(self.wire),len(self.gotos)))

    def test_first_frame_routing_requires_candidate_evidence(self):
        self.assertEqual(first_frame_disposition({'title':'404','visible_text':'页面不存在'}),('abandon','page_absent'))
        self.assertIsNone(first_frame_disposition({'title':'404','visible_text':'数字显示工具'}))
        self.assertIsNone(first_frame_disposition({'title':'工具页','visible_text':'登录 更多工具'}))
        self.assertIsNone(first_frame_disposition({'title':'复杂页面','elements':[{}]*500}))
        self.assertEqual(first_frame_disposition({'title':'安全验证'}),('optimize','access_blocked'))
        self.assertEqual(first_frame_disposition({'title':'登录','visible_text':'请登录后使用','elements':[{'element_type':'link','text':'公开工具'}]}),('abandon','login_page'))


def load_tests(loader, tests, pattern):
    # Only new acceptance scenarios, not inherited historical suites.
    suite = unittest.TestSuite(BatchAcceptance(name) for name in (
        'test_two_round_targeted_recovery_and_isolated_revision',
        'test_glm_25_closes_each_session_with_reason_and_keeps_processing_batch',
        'test_target_unknown_and_global_budget_never_redispatch',
        'test_frozen_cohort_passes_old_visit_cap_without_replacing_or_replaying_rows',
        'test_unscoped_worker_keeps_original_explicit_retry',
        'test_receipt_target_stops_at_one_and_repeated_start_is_read_only',
        'test_first_frame_routing_requires_candidate_evidence'))
    suite.addTest(ProbeFeedbackAcceptance('test_known_missing_probe_feedback_and_no_false_hint'))
    return suite
