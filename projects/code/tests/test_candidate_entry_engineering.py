"""V2 CLI wiring with disposable ledgers, synthetic pages and a fake gateway."""
import asyncio
from contextlib import ExitStack, redirect_stdout
from copy import deepcopy
import io
import json
import multiprocessing
from pathlib import Path
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import test_candidate_consumption as legacy
from test_react_session import ReactSurface, FakePage, decide, act_step
from webcollect.batch_core import BatchLedger, save_json, load_json, OutcomeUnknown
from webcollect.candidate_consumer import consume, finish_or_reconcile, statistics, main, retry
from webcollect.agent_controller import exclusive
from site_planner.candidate_pool import CandidatePool
from site_planner.discovery_tools import reference


class EntryEngineering(legacy.Consumption):
    def setUp(self):
        super().setUp()
        self.surface = ReactSurface(self.surface.state)
        for value in self.surface.state['values']:
            value.update(value='10',focused=False,selection_start=0,selection_end=0)
        self.pages = []
        self.contexts = []
        self.gotos = []
        self.prompts = []
        self.v2 = {'schema_version':'webcollect-data-candidate-2','candidate_kind':'entry',
                   'entry_url':self.uri,'requested_goal':None}
        self.source = {'origin':'codex_session','run_id':'entry-offline',
                       'references':[reference(self.root/'source.json')],
                       'category_hint':'在线工具','application_hint':'受控应用'}
        self.pool = CandidatePool(self.pool.path, install=True)
        self.cid = self.pool.put(self.v2, self.source)
        self.claim = self.pool.claim_next('entry-worker','entry/0',protocols=('webcollect-data-candidate-2',))
        self.output = self.root/'results/entry'
        self.cfg_path = self.root/'config.json'
        save_json(self.cfg_path,self.ledger.config)
        self.decisions = []
        for n,cid in enumerate(('control-0','control-1')):
            self.decisions.append(decide(tool='observe',arguments={'focus_control_id':cid}))
            self.decisions.append(decide(goal='依次修改数量与单价' if n==0 else None,
                tool='act',arguments=lambda p,cid=cid,n=n: {'observation_id':p['observation']['observation_id'],
                    'step':act_step('set_value',control_id=cid,value='20' if n==0 else '30')}))
        self.decisions.append(decide(tool='finish',arguments=lambda p: {
            'observation_id':p['observation']['observation_id'],'stop_reason':'ready',
            'summary':'已修改字段并查看实际状态','short_flow':False,'short_flow_reason':None}))

    def cli_args(self, prefix='entry', worker='entry-worker'):
        # --pool intentionally follows the subcommand; paths are relative where accepted.
        import os
        return ['run','--pool',str(self.pool.path),'--config',str(self.cfg_path),
            '--ledger',str(self.ledger.path),'--output',str(self.output),
            '--registry',os.path.relpath(self.registry),'--policy',str(self.policy_path),
            '--history-set',os.path.relpath(self.chain),'--worker-id',worker,
            '--request-prefix',prefix,'--protocol','entry','--limit','1']

    def io_boundaries(self, *, mock_gateway=True):
        stack = ExitStack()
        def gateway_init(gateway,ledger):
            gateway.ledger=ledger;gateway.config=ledger.config
        def reserve(gateway,job,purpose):
            from webcollect.batch_core import ModelRateWait
            while True:
                try:
                    return gateway.ledger.reserve_request(job,purpose,len(self.prompts),{})
                except ModelRateWait as wait:
                    time.sleep(wait.seconds)
        def call(gateway,job,purpose,prompt,schema,**kwargs):
            value=json.loads(prompt); self.prompts.append(value)
            if not self.decisions: raise AssertionError('unexpected extra model call')
            request=reserve(gateway,job,purpose)
            response=self.decisions.pop(0)(value)
            gateway.ledger.settle_request(request['id'],state='succeeded',response=response,
                usage={'input_tokens':1,'output_tokens':1,'cached_input_tokens':0})
            return response
        def call_tool(gateway,job,purpose,prompt,tools,**kwargs):
            value=json.loads(prompt); self.prompts.append(value)
            if not self.decisions: raise AssertionError('unexpected extra model call')
            decision=self.decisions.pop(0)(value)
            name=decision['tool_call']['name']
            args={**decision['tool_call']['arguments'], 'goal_update':decision['goal_update'],
                  'decision_summary':decision['decision_summary']}
            if name=='finish':
                args.pop('short_flow',None);args.pop('short_flow_reason',None)
                args['evidence_refs']=[value['observation']['observation_id']]
            cid='CONTROLLED-call-'+str(len(self.prompts))
            assistant={'role':'assistant','content':None,'tool_calls':[{'id':cid,'type':'function',
                'function':{'name':name,'arguments':json.dumps(args,ensure_ascii=False)}}]}
            response={'name':name,'arguments':args,'tool_call_id':cid,'assistant_message':assistant,
                      'user_message':{'role':'user','content':prompt}}
            request=reserve(gateway,job,purpose)
            gateway.ledger.settle_request(request['id'],state='succeeded',response=response,
                usage={'input_tokens':1,'output_tokens':1,'cached_input_tokens':0})
            return response
        class Page(FakePage):
            async def goto(page,url,**kwargs):
                self.gotos.append((id(page),url))
                await super().goto(url,**kwargs)
            def remove_listener(page,*args): pass
        def context_factory(**kwargs):
            page=Page(self.surface);self.pages.append(page)
            context=MagicMock();context.new_page=AsyncMock(return_value=page)
            context.close=AsyncMock();context.pages=[page]
            page.context=context; self.contexts.append(context)
            return context
        browser=MagicMock(version='CONTROLLED-offline');browser.new_context=AsyncMock(side_effect=context_factory)
        browser.close=AsyncMock()
        pw=MagicMock();pw.chromium.launch=AsyncMock(return_value=browser)
        manager=MagicMock();manager.__aenter__=AsyncMock(return_value=pw);manager.__aexit__=AsyncMock(return_value=False)
        async def before(page,evidence,selector=None,index=0,**kwargs):
            return await self.capture(page,selector,index)
        async def action(page,kind,args,execution):self.surface.execute_action(kind,args)
        async def verify(page,state,*args,**kwargs):return {'matched':True,'state_fingerprint':'CONTROLLED'}
        stack.enter_context(patch('playwright.async_api.async_playwright',return_value=manager))
        stack.enter_context(patch('webcollect.browser.capture',side_effect=self.capture))
        stack.enter_context(patch('webcollect.browser.verify_execution_state',side_effect=verify))
        stack.enter_context(patch('webcollect.browser.execute',side_effect=action))
        stack.enter_context(patch('webcollect.collect.capture_before_action',side_effect=before))
        stack.enter_context(patch('webcollect.preflight._wait_visible_readiness',AsyncMock(return_value={'ready':True})))
        stack.enter_context(patch('webcollect.preflight.inspect_page',AsyncMock(return_value={'summary':{'routing':'READY'}})))
        if mock_gateway:
            stack.enter_context(patch('webcollect.model_gateway.ModelGateway.__init__',gateway_init))
            stack.enter_context(patch('webcollect.model_gateway.ModelGateway.call',call))
            stack.enter_context(patch('webcollect.model_gateway.ModelGateway.call_tool',call_tool))
        return stack

    async def invoke_cli(self,args=None):
        def invoke():
            with redirect_stdout(io.StringIO()) as stream:
                main(args or self.cli_args())
                return json.loads(stream.getvalue())
        with self.io_boundaries():
            return await asyncio.to_thread(invoke)

    async def test_entry_cli_to_original_save_and_same_page(self):
        result=(await self.invoke_cli())[0]
        self.assertEqual(result['state'],'succeeded',(result,[load_json(p) for name in ('failure.json','terminal.json') for p in self.output.rglob(name)]))
        self.assertEqual(len(self.contexts),1)
        self.assertEqual(len(self.gotos),1)
        self.assertTrue(all(p['requested_goal'] is None for p in self.prompts))
        self.assertEqual(len(self.surface.executed),6)
        self.assertEqual(self.ledger.summary()['model_requests'],5)
        self.assertEqual(len(self.pool.get_claim(self.claim['claim_id'])['binding']['entry_visit_ids']),1)
        self.assertEqual(self.contexts[0].new_page.await_count,1)
        self.assertEqual(self.contexts[0].close.await_count,1)
        self.assertEqual(len(self.ledger.visits()),1)
        before=(len(self.gotos),len(self.prompts),statistics(self.pool)['formal_attempts'])
        again=finish_or_reconcile(self.pool,self.claim,reconciliation=True)
        self.assertEqual(again['result'],result['result'])
        self.assertEqual(before,(len(self.gotos),len(self.prompts),statistics(self.pool)['formal_attempts']))
        self.assertEqual((await self.invoke_cli())[0]['state'],'succeeded')
        self.assertEqual(before,(len(self.gotos),len(self.prompts),statistics(self.pool)['formal_attempts']))

    async def test_entry_cli_legacy_decision_adapter_compatibility(self):
        from webcollect.react_session import build_url_task,REACT_VERSION
        def old_task(**kwargs):
            return build_url_task(**{**kwargs,'decision_protocol':REACT_VERSION})
        with patch('webcollect.react_session.build_url_task',side_effect=old_task):
            result=(await self.invoke_cli())[0]
        self.assertEqual(result['state'],'succeeded',(result,[load_json(p) for name in ('failure.json','terminal.json')
            for p in self.output.rglob(name)]))
        self.assertEqual(len(self.gotos),1)
        self.assertEqual(len(self.contexts),1)
        self.assertEqual(len(self.prompts),5)
        self.assertEqual(statistics(self.pool)['formal_attempts'],1)
        self.assertEqual(result['QC'],'pending_review')

    async def test_entry_explicit_target_and_frozen_sources(self):
        target=deepcopy(self.v2);target.update(candidate_kind='target',requested_goal={
            'kind':'edit','entity':'fields','parameters':{'quantity':20,'price':30}})
        cid=self.pool.put(target,self.source)
        self.claim=self.pool.claim_next('entry-worker','target/0',candidate_id=cid,protocols=('webcollect-data-candidate-2',))
        result=(await self.invoke_cli(self.cli_args('target')))[0]
        self.assertEqual(result['state'],'succeeded',(result,[load_json(p) for name in ('failure.json','terminal.json') for p in self.output.rglob(name)]))
        self.assertTrue(all(p['requested_goal']==target['requested_goal'] for p in self.prompts))
        bound=self.pool.get_claim(self.claim['claim_id'])
        plan=load_json(bound['binding']['plan'])
        task=plan['tasks'][0]
        self.assertEqual(task['candidate_binding']['sources'],bound['sources'])
        self.assertEqual(task['candidate_binding']['version'],bound['version'])
        self.assertTrue(task['pilot_identity'])
        from webcollect.candidate_contract import validate_task_binding
        tampered=deepcopy(task);tampered['candidate_binding']['sources']=[]
        with self.assertRaisesRegex(ValueError,'sources changed'):validate_task_binding(tampered)
        tampered=deepcopy(task);tampered['workflow_proposal']['spec']['goal']['structured']={'kind':'different'}
        with self.assertRaisesRegex(ValueError,'requested goal differs'):validate_task_binding(tampered)

    async def test_entry_identity_failure_allocates_no_formal_number(self):
        self.surface.state['document_identity']={}
        with self.assertRaises(ValueError): await self.invoke_cli()
        self.assertEqual(statistics(self.pool)['formal_attempts'],0)
        self.assertEqual(self.prompts,[])
        self.assertEqual(len(self.gotos),1)
        self.assertEqual(self.contexts[0].close.await_count,1)

    async def test_entry_local_capture_error_keeps_site_failure_margin(self):
        from webcollect.site_failure_stop import SiteFailureStore
        self.capture = AsyncMock(side_effect=OSError('controlled local capture failure'))
        with self.assertRaisesRegex(OSError, 'local capture failure'):
            await self.invoke_cli()
        store = SiteFailureStore(self.ledger.config['site_failure_guard'])
        self.assertEqual(store.status(self.uri)['failure_count'], 0)
        self.assertEqual(statistics(self.pool)['formal_attempts'], 0)
        self.assertTrue(list(self.output.rglob('first-observation-failure.json')))

    async def test_entry_public_access_rejection_counts_once(self):
        from webcollect.site_failure_stop import SiteFailureStore
        self.capture = AsyncMock(return_value={'state': {'url': 'https://example.org/login'}})
        with self.assertRaisesRegex(ValueError, '登录门槛'):
            await self.invoke_cli()
        store = SiteFailureStore(self.ledger.config['site_failure_guard'])
        self.assertEqual(store.status(self.uri)['failure_count'], 1)
        self.assertEqual(statistics(self.pool)['formal_attempts'], 0)

    async def test_entry_exact_frame_rejects_sample_without_pausing_for_a_program_bug(self):
        with patch('webcollect.production_quality.ConcurrentExactImageIndex.conflicts',
                   return_value=[{'other_sample_id': 'controlled-first-owner'}]):
            result = (await self.invoke_cli())[0]
        self.assertEqual(result['state'], 'failed')
        failure = load_json(next(self.output.rglob('failure.json')))
        self.assertEqual((failure['failure_class'], failure['error']), ('collector', 'react_exact_image_conflict'))
        self.assertTrue(list(self.output.rglob('producer_dedup.json')))
        self.assertFalse(list(self.output.rglob('saved_sample.json')))

    async def test_entry_image_collision_at_commit_keeps_raw_and_rejects_late_owner(self):
        from webcollect.runtime import RuntimeStore, ImageCommitConflict
        original = RuntimeStore.finish_attempt
        def collide(store, *args, **kwargs):
            if kwargs.get('exact_images') is not None:
                raise ImageCommitConflict([{'other_sample_id': 'controlled-first-owner'}])
            return original(store, *args, **kwargs)
        with patch.object(RuntimeStore, 'finish_attempt', collide):
            result = (await self.invoke_cli())[0]
        self.assertEqual(result['state'], 'failed')
        failure = load_json(next(self.output.rglob('failure.json')))
        self.assertEqual((failure['failure_class'], failure['error']), ('collector', 'react_exact_image_commit_conflict'))
        self.assertTrue(list(self.output.rglob('concurrent_image_conflict.json')))
        self.assertEqual(statistics(self.pool)['collected'], 0)

    async def test_entry_preclaim_invalid_scope_and_policy(self):
        before=self.pool.stats()['consumption_attempts']
        bad=self.root/'bad-policy.json';save_json(bad,{**self.policy,'attempt_cap':99})
        args=self.cli_args('invalid');args[args.index('--policy')+1]=str(bad)
        with self.assertRaisesRegex(ValueError,'original authorized campaign'): await self.invoke_cli(args)
        self.assertEqual(self.pool.stats()['consumption_attempts'],before)
        self.assertEqual(self.gotos,[])

    async def test_entry_unknown_does_not_resend(self):
        jid=self.ledger.enqueue('react-decision',{'site_uri':self.uri})
        job=self.ledger.claim('react-decision',job_id=jid)
        request=self.ledger.reserve_request(job,'CONTROLLED',1,{})
        self.ledger.settle_request(request['id'],state='unknown',error='CONTROLLED timeout')
        self.ledger.finish(job,'review_required',error='unknown')
        with self.assertRaises(OutcomeUnknown): await self.invoke_cli()
        self.assertEqual(self.gotos,[])
        self.assertEqual(statistics(self.pool)['formal_attempts'],0)

    async def test_entry_saved_projection_crash_reconciles_without_dispatch(self):
        with patch('webcollect.candidate_consumer.finish_or_reconcile',side_effect=OSError('CONTROLLED crash after save')):
            with self.assertRaises(OSError):await self.invoke_cli()
        before=(len(self.gotos),len(self.prompts),statistics(self.pool)['formal_attempts'])
        result=finish_or_reconcile(self.pool,self.claim,reconciliation=True)
        self.assertEqual(result['state'],'succeeded')
        self.assertEqual(before,(len(self.gotos),len(self.prompts),statistics(self.pool)['formal_attempts']))

    async def test_entry_whole_application_three_failure_hold_blocks_dispatch(self):
        from webcollect.site_failure_stop import SiteFailureStore,SiteStopped
        store=SiteFailureStore(self.ledger.config['site_failure_guard'])
        for n in range(3):
            store.record(self.uri+'other-page/'+str(n),'CONTROLLED-network-'+str(n),
                stage='observation',state='failed',reason='CONTROLLED simulated network failure',real_execution=True,
                evidence=[reference(self.root/'source.json')],usage_refs=[])
        with self.assertRaises(SiteStopped):await self.invoke_cli()
        self.assertEqual(self.gotos,[])
        self.assertEqual(self.prompts,[])
        self.assertEqual(statistics(self.pool)['formal_attempts'],0)

    async def test_entry_retry_includes_native_decision_jobs(self):
        jid=self.ledger.enqueue('react-native-decision',{'site_uri':self.uri})
        self.ledger.claim('react-native-decision',job_id=jid)
        self.pool.stage(self.claim,'planning',{'ledger':str(self.ledger.path)})
        self.pool.finish(self.claim,state='failed',stage='planning',reason='CONTROLLED unresolved original job')
        with self.assertRaisesRegex(ValueError,'planning/decision unresolved'):
            retry(self.pool,self.cid,reason='Must inspect original native job')
        self.assertEqual(self.ledger.summary()['model_requests'],0)

    async def test_entry_lost_lease_before_formal_attempt(self):
        async def lose(page):
            with self.pool.transaction() as con:
                con.execute('UPDATE candidate_claims SET expires=0 WHERE claim_id=?',(self.claim['claim_id'],))
            return {'ready':True}
        with patch('webcollect.preflight._wait_visible_readiness',side_effect=lose):
            # invoke_cli owns the IO boundary, so replace readiness inside it.
            def invoke():
                with self.io_boundaries(), patch('webcollect.preflight._wait_visible_readiness',side_effect=lose):
                    main(self.cli_args())
            with self.assertRaisesRegex(ValueError,'Expired or invalid'):
                await asyncio.to_thread(invoke)
        self.assertEqual(statistics(self.pool)['formal_attempts'],0)
        self.assertEqual(self.prompts,[])
        self.assertEqual(self.contexts[0].close.await_count,1)

    async def test_entry_unknown_category_stays_out_of_formal_quota(self):
        self.v2['entry_url']=self.uri+'unknown-category'
        self.surface.state['url']=self.v2['entry_url']
        source={**self.source,'category_hint':'UNKNOWN'}
        cid=self.pool.put(self.v2,source)
        self.claim=self.pool.claim_next('entry-worker','unknown-category/0',candidate_id=cid,
            protocols=('webcollect-data-candidate-2',))
        result=(await self.invoke_cli(self.cli_args('unknown-category')))[0]
        self.assertEqual(result['state'],'failed')
        self.assertIn('category UNKNOWN',result['reason'])
        self.assertEqual(statistics(self.pool)['formal_attempts'],0)
        self.assertEqual(self.prompts,[])

    async def test_entry_distinct_candidates_get_distinct_contexts(self):
        first=(await self.invoke_cli())[0]
        self.assertEqual(first['state'],'succeeded',first)
        self.v2['entry_url']=self.uri+'second'
        self.surface=ReactSurface(self.surface.state)
        self.surface.state['url']=self.v2['entry_url']
        self.surface.state['document_identity']['url_without_fragment']=self.v2['entry_url']
        for value in self.surface.state['values']:
            value.update(value='10',focused=False,selection_start=0,selection_end=0)
        self.pool.put(self.v2,self.source)
        self.decisions=[]
        for n,cid in enumerate(('control-0','control-1')):
            self.decisions.append(decide(tool='observe',arguments={'focus_control_id':cid}))
            self.decisions.append(decide(goal='依次修改数量与单价' if n==0 else None,
                tool='act',arguments=lambda p,cid=cid,n=n: {'observation_id':p['observation']['observation_id'],
                    'step':act_step('set_value',control_id=cid,value='20' if n==0 else '30')}))
        self.decisions.append(decide(tool='finish',arguments=lambda p: {
            'observation_id':p['observation']['observation_id'],'stop_reason':'ready',
            'summary':'完成输入修改并查看状态','short_flow':False,'short_flow_reason':None}))
        second=(await self.invoke_cli(self.cli_args('second')))[0]
        self.assertEqual(second['state'],'succeeded',second)
        self.assertEqual(len(self.gotos),2)
        self.assertEqual(len(self.contexts),2)
        self.assertIsNot(self.contexts[0],self.contexts[1])
        self.assertNotEqual(first['result']['attempt_id'],second['result']['attempt_id'])

    async def test_entry_two_os_processes_replay_only_one_dispatch(self):
        ctx=multiprocessing.get_context('fork')
        ready=ctx.Event();start=ctx.Event()
        reports=self.root/'process-reports';reports.mkdir()
        def worker(n):
            ready.set();start.wait(10)
            try:
                with self.io_boundaries(), redirect_stdout(io.StringIO()) as stream:
                    main(self.cli_args())
                    result=json.loads(stream.getvalue())
                save_json(reports/str(n),{'result':result,'gotos':len(self.gotos),'models':len(self.prompts),
                    'contexts':len(self.contexts)})
            except BaseException as error:
                save_json(reports/str(n),{'error':type(error).__name__+':'+str(error),
                    'gotos':len(self.gotos),'models':len(self.prompts),'contexts':len(self.contexts)})
        processes=[ctx.Process(target=worker,args=(n,)) for n in range(2)]
        for process in processes:process.start()
        ready.wait(5);start.set()
        for process in processes:
            await asyncio.to_thread(process.join,30)
            if process.is_alive():process.kill();process.join();self.fail('bounded process did not finish')
            self.assertEqual(process.exitcode,0)
        rows=[load_json(reports/str(n)) for n in range(2)]
        self.assertFalse(any('error' in r for r in rows),rows)
        self.assertEqual(sum(r['gotos'] for r in rows),1,rows)
        self.assertEqual(sum(r['contexts'] for r in rows),1,rows)
        self.assertEqual(sum(r['models'] for r in rows),5,rows)
        self.assertEqual(statistics(self.pool)['formal_attempts'],1)
        self.assertEqual(statistics(self.pool)['collected'],1)

    async def test_entry_two_processes_claim_one_candidate_once(self):
        self.pool.finish(self.claim,state='failed',stage='claimed',reason='CONTROLLED zero dispatch setup')
        retry(self.pool,self.cid,reason='CONTROLLED release setup without IO')
        ctx=multiprocessing.get_context('fork')
        start=ctx.Event()
        reports=self.root/'claim-race';reports.mkdir()
        def worker(n):
            start.wait(10)
            try:
                with self.io_boundaries(), redirect_stdout(io.StringIO()) as stream:
                    main(self.cli_args('race-'+str(n),'worker-'+str(n)))
                    result=json.loads(stream.getvalue())
                save_json(reports/str(n),{'result':result,'gotos':len(self.gotos),'models':len(self.prompts)})
            except BaseException as error:
                save_json(reports/str(n),{'error':type(error).__name__+':'+str(error),
                    'gotos':len(self.gotos),'models':len(self.prompts)})
        processes=[ctx.Process(target=worker,args=(n,)) for n in range(2)]
        for process in processes:process.start()
        start.set()
        for process in processes:
            await asyncio.to_thread(process.join,30)
            if process.is_alive():process.kill();process.join();self.fail('claim race timeout')
            self.assertEqual(process.exitcode,0)
        rows=[load_json(reports/str(n)) for n in range(2)]
        self.assertFalse(any('error' in r for r in rows),rows)
        self.assertEqual(sum(r['gotos'] for r in rows),1,rows)
        self.assertEqual(sum(r['models'] for r in rows),5,rows)
        self.assertEqual(sum(r['result'][0]['state']=='EMPTY' for r in rows),1,rows)
        with self.pool.pool.connect() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM candidate_claims WHERE request_id LIKE 'race-%'").fetchone()[0],1)
        self.assertEqual(statistics(self.pool)['collected'],1)


def load_tests(loader, tests, pattern):
    return unittest.TestSuite(EntryEngineering(name) for name in loader.getTestCaseNames(EntryEngineering)
                              if name.startswith('test_entry_'))
