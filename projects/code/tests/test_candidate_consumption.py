"""Whole candidate->generation->execute->collect/runtime->reconcile, IO simulated."""
import asyncio
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import socket
import time
import unittest
from unittest.mock import patch, AsyncMock, MagicMock
from test_planner_repair import SemanticFixture
from test_agent_loop import Surface
from webcollect.agent_controller import exclusive, FRAGMENT_VERSION, LIMITS, FragmentController, compile_goal
from webcollect.candidate_contract import capability, instruction, fragment_ending
from webcollect.candidate_consumer import consume, finish_or_reconcile, retry, statistics
from webcollect.batch_core import BatchLedger, load_json, save_json, file_sha, OutcomeUnknown
from webcollect.planning import object_sha256
from webcollect.runtime import RuntimeStore
from site_planner.site_pool import SitePool
from site_planner.candidate_pool import CandidatePool, VERSION
from site_planner.discovery_tools import reference


class Consumption(SemanticFixture, unittest.IsolatedAsyncioTestCase):
    chain_manifest = 'chain.json'
    def setUp(self):
        super().setUp()
        self.root=self.root.resolve(); self.fixture.root=self.root
        net=patch.object(socket.socket,'connect',side_effect=AssertionError('No network'))
        net.start();self.addCleanup(net.stop)
        SitePool(self.root/'pool.db',initialize=True);self.pool=CandidatePool(self.root/'pool.db',install=True)
        original,_=self.semantic();self.surface=Surface(load_json(original['capabilities'][0]['page_anchor']['state']['path']))
        self.surface.state.pop('fixture',None);self.surface.state.pop('mode',None)
        for element in self.surface.state['elements']:
            element.update(parent_id='root',native_role='input' if element['inputable'] else 'p',scrollable=False,state='default')
        self.uri=self.surface.url
        proof=self.root/'source.json';save_json(proof,{'CONTROLLED':'simulated search'})
        self.candidate={'schema_version':VERSION,'entry_url':self.uri,'name':'受控离线页面','parent_category':'在线工具',
            'business_kind':'输入操作','description':'修改数量和单价并查看输入状态','target':{'kind':'edit','entity':'fields','parameters':{'quantity':20,'price':30}}}
        self.cid=self.pool.put(self.candidate,{'origin':'codex_session','run_id':'offline','references':[reference(proof)]})
        self.claim=self.pool.claim_next('worker','first')
        cfg=load_json(Path(__file__).parents[1]/'config/batch-synthetic.json');cfg['mode']='real'
        cfg['model'].update(provider='chat-completions',endpoint='https://model.invalid',api_key_env='CONTROLLED_UNUSED_KEY')
        cfg['model']['reserve_cost_micros']=1
        cfg['budget'].update(max_model_cost_micros=10000,currency='CNY',min_model_interval_seconds=1)
        cfg['model']['rates'].update(input=1,output=1)
        cfg['budget']['min_domain_interval_seconds']=1
        cfg['budget']['max_concurrent_jobs']=1
        from webcollect.current_chain import initialize_chain
        self.registry=self.root/'results/registry.db';self.chain=self.root/self.chain_manifest
        initialize_chain(self.chain,self.registry,chain_id='CONTROLLED-candidate',current_result_roots=[self.root/'results'])
        from webcollect.site_failure_stop import SiteFailureStore
        guard=SiteFailureStore.initialize({'ledger':str(self.root/'stop.db'),'campaign_id':'CONTROLLED-candidate','formal_since':time.time()-1}).binding
        cfg['site_failure_guard']=guard
        self.policy={'campaign_id':'CONTROLLED-candidate','baseline_category_counts':{},'pilot_identity_required':True,'site_failure_guard':guard}
        RuntimeStore(self.registry,'authorized').initialize(self.policy)
        self.policy_path=self.root/'policy.json';save_json(self.policy_path,self.policy)
        self.ledger=BatchLedger(self.root/'jobs.db',cfg,initialize=True)
        self.calls=[]

    async def capture(self,*args,**kw):
        frame=await self.surface.capture(*args,**kw)
        import webcollect.collect as collect
        frame['capture']['observer_sha256']=hashlib.sha256(collect.SNAPSHOT_JS.encode()).hexdigest()
        return frame

    async def observe_first(self,ledger,claim,root):
        self.assertEqual(self.pool.get_claim(claim['claim_id'])['state'],'consuming')
        captured=await self.capture(self.surface);image=root/'first.png';image.write_bytes(captured['png'])
        return {'image':reference(image),'state':exclusive(root/'state.json',captured['state']),
                'capture':exclusive(root/'capture.json',captured['capture'])}

    def model(self,job,purpose,prompt,schema,**kw):
        value=json.loads(prompt);self.calls.append(purpose)
        if 'required_instruction' in value:
            self.assertEqual(value['claimed_candidate']['candidate_id'],self.cid)
            spec={'schema_version':FRAGMENT_VERSION,'task_family':'navigation-reading','instruction':value['required_instruction'],
                'task_type':['填写表单','数据查看'],'page_id':'p0','end_description':value['required_end_description'],
                'allowed_actions':['set_value','click','type','hotkey'],'budgets':dict(LIMITS)}
            return {'tasks':[spec],'empty_reasons':[]}
        n=value['used']['max_actions'];cid='control-0' if n<3 else 'control-1'
        base={'kind':'finish','observation_id':value['observation']['observation_id'],'reason':'受控目标','steps':[],'control_id':''}
        if n>=6:return base
        if value['observation']['controls'][cid]['actions']['set_value']['status']!='PROVEN':
            return {**base,'kind':'observe','control_id':cid}
        return {**base,'kind':'plan','steps':[{'action':'set_value','control_id':cid,'value':'20' if n<3 else '30','goal':'修改目标字段','expected':'显示输入值'}]}

    async def preflight(self,source,output,**kw):
        from webcollect.preflight import _files,digest,object_digest,schedule_plan,SOURCE_FILES
        import webcollect.preflight as module
        import m4_runtime_fixtures as fixtures
        # Reuse original binding format; this is an authored offline preflight fixture.
        template=self.root/'preflight-template'
        fixtures.make_plan(template)
        shutil.copytree(template/'preflight',output)
        original=load_json(source);(output/'input-plan.json').write_text(json.dumps(original,ensure_ascii=False))
        report=load_json(output/'report.json');report['input_plan_sha256']=digest(output/'input-plan.json')
        for row,task in zip(report['records'],original['tasks']):
            row['task_id']=task['task_id'];row['task_sha256']=object_digest(task)
            (output/row['evidence_directory']/'result.json').write_text(json.dumps({k:v for k,v in row.items() if k!='evidence_directory'}))
        report['evidence_files_sha256']={k:v for k,v in _files(output).items() if k not in {'report.json','scheduled-plan.json','manifest.json','SHA256SUMS'}}
        (output/'report.json').write_text(json.dumps(report))
        scheduled=schedule_plan(original,report['records'],output/'report.json',digest(output/'report.json'),True)
        save_json(output/'scheduled-plan.json',scheduled)
        return report

    async def execute_action(self,page,action,args,execution=None):
        if action=='complete':return
        cid=next((b['element_id'] for b in self.surface.state['capture_controls'] if b['selector']==(execution or {}).get('selector')),None)
        # browser.execute gets execution coordinates, so use current focused target for typing.
        if action=='click':
            cid='control-0' if len(self.surface.executed)<3 else 'control-1'
        if action=='type': cid=next(v['element_id'] for v in self.surface.state['values'] if v['focused'])
        self.surface.execute({'action_type':action,'arguments':args,'evidence':{'anchor_element_id':cid}})

    async def perform(self):
        from contextlib import ExitStack
        context=MagicMock();context.new_page=AsyncMock(return_value=self.surface);context.close=AsyncMock();context.pages=[]
        browser=MagicMock(version='CONTROLLED');browser.new_context=AsyncMock(return_value=context);browser.close=AsyncMock()
        pw=MagicMock();pw.chromium.launch=AsyncMock(return_value=browser)
        manager=MagicMock();manager.__aenter__=AsyncMock(return_value=pw);manager.__aexit__=AsyncMock(return_value=False)
        nav=MagicMock();nav.goto=AsyncMock()
        async def final(page,evidence,*args,**kw):
            frame=await self.capture(page,*args,**kw);frame['terminal_refresh']={'accepted':True};return frame
        async def observed(*args,**kw):return (await self.capture(*args,**kw))['state']
        def gateway_init(gateway,ledger): gateway.ledger=ledger;gateway.config=ledger.config
        with ExitStack() as stack:
            stack.enter_context(patch('webcollect.model_gateway.ModelGateway.__init__',gateway_init))
            mocks=[('webcollect.candidate_consumer.first_observation',AsyncMock(side_effect=self.observe_first)),
                ('webcollect.model_gateway.ModelGateway.call',MagicMock(side_effect=self.model)),
                ('webcollect.preflight.preflight_plan',AsyncMock(side_effect=self.preflight)),
                ('playwright.async_api.async_playwright',MagicMock(return_value=manager)),
                ('webcollect.navigation.BatchNavigation',MagicMock(return_value=nav)),
                ('webcollect.browser.capture',AsyncMock(side_effect=self.capture)),
                ('webcollect.collect.capture',AsyncMock(side_effect=self.capture)),
                ('webcollect.collect.observe',AsyncMock(side_effect=observed)),
                ('webcollect.collect.execute',AsyncMock(side_effect=self.execute_action)),
                ('webcollect.collect.assess_content',AsyncMock(return_value={'page_url':self.uri,'decision':{'action':'ready','reason':'CONTROLLED'}})),
                ('webcollect.collect.verify_execution_state',AsyncMock(side_effect=lambda page,state,*a,**kw:{'matched':True,'state_fingerprint':__import__('webcollect.browser',fromlist=['fingerprint']).fingerprint(state)})),
                ('webcollect.collect.capture_complete',AsyncMock(side_effect=final)),
                ('webcollect.browser_planner.observe_task',AsyncMock(side_effect=AssertionError('No rehearsal')))]
            for target,mock in mocks:stack.enter_context(patch(target,mock))
            return await consume(self.pool,self.claim,self.ledger,output=self.root/'results/consumer',registry=self.registry,
                policy=str(self.policy_path),history_set=self.chain)

    async def test_full_chain_save_recovery_trace_no_recollection_and_tamper_rejected(self):
        result=await self.perform()
        from webcollect.candidate_consumer import _original_attempts
        self.assertEqual(result['state'],'succeeded',(result,[load_json(ref['path']) for row,task in _original_attempts(self.pool.get_claim(self.claim['claim_id'])) for ref in json.loads(row['evidence_json']) if Path(ref['path']).name=='failure.json']))
        self.assertEqual(len(self.surface.executed),6)
        self.assertEqual(result['QC'],'pending_review')
        saved=result['result'];self.assertTrue(Path(saved['save_receipt']['path']).is_file())
        bound=self.pool.get_claim(self.claim['claim_id'])
        self.assertTrue(bound['binding']['planning_jobs']);self.assertTrue(bound['binding']['queue_job_id'])
        count=len(self.calls)
        again=finish_or_reconcile(self.pool,self.claim,reconciliation=True)
        self.assertEqual(again['result']['sample_id'],saved['sample_id']);self.assertEqual(len(self.calls),count)
        self.assertEqual(statistics(self.pool)['formal_attempts'],1)
        with self.assertRaises(ValueError):retry(self.pool,self.cid,reason='No duplicate pending')
        self.assertEqual(self.pool.claim_next('another','new')['state'],'EMPTY')
        Path(saved['save_receipt']['path']).write_text('tamper')
        with self.assertRaises(ValueError):finish_or_reconcile(self.pool,self.claim,reconciliation=True)

    async def test_planning_empty_no_formal_id_and_unknown_no_resend(self):
        self.model=lambda *a,**kw:{'tasks':[],'empty_reasons':[{'category':'MISSING_OBSERVATION','reason':'CONTROLLED missing target','control_ids':[]}]}
        result=await self.perform();self.assertEqual(result['state'],'failed')
        self.assertEqual(statistics(self.pool)['formal_attempts'],0)
        self.assertEqual(self.pool.get_claim(self.claim['claim_id'])['stage'],'planning')
        retry(self.pool,self.cid,reason='Explicit corrected planner')
        self.assertEqual(self.pool.stats()['pending'],1)

    async def test_six_actual_actions_save_as_fragment_without_all_business_fields(self):
        # A longer candidate remains the frozen intent. The first two observed
        # fields can form a six-action fragment; an unobserved third condition
        # is not claimed complete and is never fabricated in the UI.
        self.candidate=deepcopy(self.candidate)
        self.candidate['description']='修改数量、单价和运费并查看本段输入状态'
        self.candidate['target']['parameters']['shipping']=40
        self.cid=self.pool.put(self.candidate,{'origin':'codex_session','run_id':'offline-fragment',
            'references':[reference(self.root/'source.json')]})
        self.claim=self.pool.claim_next('worker','longer-business',candidate_id=self.cid)
        result=await self.perform()
        self.assertEqual(result['state'],'succeeded',result)
        self.assertEqual(len(self.surface.executed),6)
        from webcollect.candidate_consumer import _original_attempts
        attempt,task=_original_attempts(self.pool.get_claim(self.claim['claim_id']))[0]
        self.assertEqual(attempt['status'],'collected_pending_review')
        self.assertEqual(task['candidate_binding']['candidate']['target']['parameters']['shipping'],40)
        self.assertEqual(task['fragment']['business_completion'],'NOT_CLAIMED')
        self.assertEqual(task['fragment']['ending_policy'],'candidate-fragment-ending-1')
        self.assertEqual(task['final_result'],fragment_ending(self.candidate))
        self.assertEqual(result['QC'],'pending_review')

    async def test_dynamic_navigation_links_results_detail_and_unbound_scope_blocked(self):
        # Full controller observation protocol, no browser; current target remains checked.
        root=self.root/'nav';root.mkdir()
        claim={**self.claim,'pool':str(self.pool.path)};ref=exclusive(root/'claim.json',claim)
        anchor=await self.observe_first(self.ledger,claim,root)
        cap=capability(claim,anchor,ref,'real')
        spec={'schema_version':FRAGMENT_VERSION,'task_family':'navigation-reading','instruction':instruction(self.candidate),
            'task_type':['数据查看'],'page_id':'p0','end_description':fragment_ending(self.candidate),'allowed_actions':['click','open_url','scroll','hotkey'],'budgets':dict(LIMITS)}
        task=compile_goal(cap,spec,'fixture')
        c=FragmentController(task,root/'controller',None)
        async def observe():
            c.consume('max_observations');return c.accept_capture(await self.capture(self.surface))
        self.surface.state['capture_controls'][0]['href']=self.uri+'?page=2'
        first=await observe();self.assertIn(self.uri+'?page=2',c.page_urls)
        c.trajectory=[{'operation_id':'one','action':'click','arguments':{},'observed':{}}]
        c.pending_effect=(deepcopy(self.surface.state),{'action_type':'click','operation_id':'one'})
        c.effect_png='different'
        self.surface.state['url']=self.uri+'?search=books';self.surface.state['document_identity']['performance_time_origin']+=1
        await observe();self.assertIn(self.surface.url,c.page_urls)
        self.surface.state['capture_controls'][0]['href']=self.uri+'detail/1'
        await observe();self.assertIn(self.uri+'detail/1',c.page_urls)
        c.compile_step({'action':'open_url','page_id':f'p{c.page_urls.index(self.uri+"detail/1")}','goal':'详情','expected':'显示'},c.current)
        self.surface.state['url']='https://unrelated.example/'
        from webcollect.agent_controller import ControllerStop
        with self.assertRaises(ControllerStop):await observe()

    async def test_passive_same_host_navigation_and_unrelated_goal_cannot_expand_scope(self):
        root=self.root/'passive';root.mkdir()
        claim={**self.claim,'pool':str(self.pool.path)};ref=exclusive(root/'claim.json',claim)
        anchor=await self.observe_first(self.ledger,claim,root);cap=capability(claim,anchor,ref,'real')
        spec={'schema_version':FRAGMENT_VERSION,'task_family':'navigation-reading','instruction':instruction(self.candidate),
            'task_type':['数据查看'],'page_id':'p0','end_description':fragment_ending(self.candidate),'allowed_actions':['click','scroll'],'budgets':dict(LIMITS)}
        task=compile_goal(cap,spec,'fixture')
        changed=deepcopy(spec);changed['instruction']='查看「无关页面」的数据。'
        with self.assertRaises(ValueError):compile_goal(cap,changed,'fixture')
        changed=deepcopy(spec);changed['end_description']='额外点击提交并查看完整业务结果'
        with self.assertRaisesRegex(ValueError,'original claimed goal'):compile_goal(cap,changed,'fixture')
        c=FragmentController(task,root/'controller',None)
        c.consume('max_observations');c.accept_capture(await self.capture(self.surface))
        self.surface.state['url']=self.uri+'invented'
        c.consume('max_observations')
        from webcollect.agent_controller import ControllerStop
        with self.assertRaises(ControllerStop):c.accept_capture(await self.capture(self.surface))

    async def test_explicit_application_aliases_bind_observation_identity_and_navigation(self):
        from webcollect.candidate_contract import application_matches
        from webcollect.single_record import identity
        root=self.root/'aliases';root.mkdir()
        proof=root/'ownership.json';save_json(proof,{'CONTROLLED':'authored alias fixture'})
        registry=root/'registry.json'
        from urllib.parse import urlsplit,urlunsplit
        parsed=urlsplit(self.uri);whole=urlunsplit((parsed.scheme,parsed.netloc,'/','',''))
        save_json(registry,{'schema_version':'webcollect-application-aliases-1','applications':[{
            'canonical_uri':whole,'aliases':[whole,'https://movies.example.org/'], 'evidence':[reference(proof)]}]})
        ref=reference(registry)
        self.assertTrue(application_matches(self.uri,'https://movies.example.org/detail',ref))
        self.assertFalse(application_matches(self.uri,'https://other.example.org/',ref))
        self.assertFalse(application_matches(self.uri,'https://movies.example.org/detail'))
        claim={**self.claim,'pool':str(self.pool.path),'application_registry':ref}
        claim_ref=exclusive(root/'claim.json',claim)
        anchor=await self.observe_first(self.ledger,claim,root)
        cap=capability(claim,anchor,claim_ref,'real')
        catalog=root/'catalog.json';save_json(catalog,{'records':[cap]})
        bound=identity(catalog,root/'identity.json',candidate_observation=True)
        self.assertEqual(bound['pages'][self.uri]['application']['application_registry'],ref)

    async def test_nested_job_serial_slot_and_parent_fencing_without_request(self):
        from webcollect.batch_core import BudgetStop
        parent_id=self.ledger.enqueue('collection',{'validation':'serial-parent'})
        parent=self.ledger.claim('collection',job_id=parent_id)
        child_id=self.ledger.enqueue('fragment-decision',{'parent_job_id':parent_id,'decision':1})
        child=self.ledger.claim('fragment-decision',job_id=child_id,parent_job=parent)
        other_id=self.ledger.enqueue('task-generation',{'validation':'independent'})
        with self.assertRaises(BudgetStop):self.ledger.claim('task-generation',job_id=other_id)
        second_id=self.ledger.enqueue('fragment-decision',{'parent_job_id':parent_id,'decision':2})
        with self.assertRaises(BudgetStop):self.ledger.claim('fragment-decision',job_id=second_id,parent_job=parent)
        self.ledger.finish(child,result={'CONTROLLED':'no model request'})
        second=self.ledger.claim('fragment-decision',job_id=second_id,parent_job=parent)
        with self.ledger.transaction() as con:con.execute('UPDATE jobs SET lease=0 WHERE id=?',(parent_id,))
        with self.assertRaises(ValueError):self.ledger.heartbeat(second)
        self.assertEqual(self.ledger.summary()['model_requests'],0)

    async def test_unknown_scope_preserves_reservation_and_blocks_original_unscoped_and_inflight(self):
        from webcollect.candidate_consumer import guard_request_scope
        jid=self.ledger.enqueue('fragment-decision',{'site_uri':self.uri,'decision':1})
        job=self.ledger.claim('fragment-decision',job_id=jid)
        request=self.ledger.reserve_request(job,'decision',1,{})
        other='https://independent.example.org/tool/'
        with self.assertRaises(OutcomeUnknown):guard_request_scope(self.ledger,other)
        self.ledger.settle_request(request['id'],state='unknown',error='URLError')
        self.ledger.finish(job,'review_required',error='unknown:URLError')
        with self.assertRaises(OutcomeUnknown):guard_request_scope(self.ledger,self.uri)
        with self.ledger.connect() as con:
            before=[dict(row) for row in con.execute('SELECT * FROM model_requests')]
        isolated=guard_request_scope(self.ledger,other)
        self.assertEqual(isolated[0]['id'],request['id'])
        with self.ledger.connect() as con:
            self.assertEqual([dict(row) for row in con.execute('SELECT * FROM model_requests')],before)
        with self.ledger.transaction() as con:con.execute("UPDATE jobs SET payload='{}' WHERE id=?",(jid,))
        with self.assertRaises(OutcomeUnknown):guard_request_scope(self.ledger,other)
        with self.ledger.transaction() as con:con.execute('UPDATE jobs SET payload=? WHERE id=?',(json.dumps({'site_uri':other}),jid))
        self.pool.stage(self.claim,'planning',{'ledger':str(self.ledger.path)})
        self.pool.finish(self.claim,state='failed',stage='planning',reason='CONTROLLED definite failure')
        self.assertEqual(retry(self.pool,self.cid,reason='Explicit fixed independent target')['state'],'pending')
        with self.ledger.connect() as con:
            self.assertEqual(con.execute('SELECT state FROM model_requests WHERE id=?',(request['id'],)).fetchone()[0],'unknown')

    async def test_decision_claim_budget_failure_is_zero_send_local_failure(self):
        from webcollect.agent_controller import model_chooser,DecisionRequestError
        parent_id=self.ledger.enqueue('collection',{'validation':'occupied-slot'})
        self.ledger.claim('collection',job_id=parent_id)
        def init(gateway,ledger):gateway.ledger=ledger;gateway.config=ledger.config
        with patch('webcollect.model_gateway.ModelGateway.__init__',init),patch('webcollect.model_gateway.ModelGateway.call',side_effect=AssertionError('No request')):
            choose=model_chooser(self.ledger,{'task_id':'CONTROLLED','site_uri':self.uri},'attempt-local')
            with self.assertRaises(DecisionRequestError):await choose({'used':{'max_decisions':1}})
        with self.ledger.connect() as con:
            self.assertEqual(con.execute("SELECT state FROM jobs WHERE kind='fragment-decision'").fetchone()[0],'failed')
        self.assertEqual(self.ledger.summary()['model_requests'],0)

    async def test_saved_then_projection_failure_recovers_only_from_original_receipt(self):
        with patch('webcollect.candidate_consumer.finish_or_reconcile',side_effect=OSError('CONTROLLED pool write unavailable')):
            with self.assertRaises(OSError): await self.perform()
        before=statistics(self.pool);calls=len(self.calls);actions=len(self.surface.executed)
        self.assertEqual(before['formal_attempts'],1);self.assertEqual(before['collected'],1)
        with self.pool.transaction() as con:con.execute('UPDATE candidate_claims SET expires=0')
        self.assertEqual(self.pool.claim_next('other','after-crash')['state'],'EMPTY')
        with self.assertRaises(ValueError): finish_or_reconcile(self.pool,self.claim)
        recovered=finish_or_reconcile(self.pool,self.claim,reconciliation=True)
        self.assertEqual(recovered['state'],'succeeded')
        self.assertEqual(statistics(self.pool)['formal_attempts'],1)
        self.assertEqual(len(self.calls),calls);self.assertEqual(len(self.surface.executed),actions)

    async def test_unknown_planning_stays_bound_no_new_directory_or_retry(self):
        calls=[]
        def unknown(*a,**kw):calls.append(1);raise OutcomeUnknown('CONTROLLED remote UNKNOWN')
        self.model=unknown
        self.assertEqual((await self.perform())['state'],'reconcile')
        self.assertEqual(self.pool.get_claim(self.claim['claim_id'])['state'],'reconcile')
        again=await consume(self.pool,self.claim,self.ledger,output=self.root/'other',registry=self.registry,
            policy=self.policy_path,history_set=self.chain)
        self.assertEqual(again['state'],'reconcile');self.assertEqual(calls,[1])
        with self.assertRaises(ValueError):retry(self.pool,self.cid,reason='Cannot resend unknown')
        self.assertEqual(statistics(self.pool)['formal_attempts'],0)

    async def test_local_planning_failure_proves_zero_send_and_allows_explicit_retry(self):
        def local(*a,**kw):raise ValueError('CONTROLLED local preflight failure')
        self.model=local
        result=await self.perform()
        self.assertEqual(result['state'],'failed')
        self.assertEqual(result['requests'][0]['outcome'],'LOCAL_NOT_SENT')
        self.assertEqual(self.ledger.summary()['model_requests'],0)
        retry(self.pool,self.cid,reason='Explicit repair after zero-send failure')
        self.assertEqual(self.pool.stats()['pending'],1)

    def qc_report(self, execution, status):
        from quality_inspector import engine
        from quality_inspector.profiles import DEFAULT_DELIVERY_PROFILE
        from quality_inspector.reporting import review_template
        dataset=Path(execution['result_location']).parent.parent
        # Inspect the real exported customer bytes, generated from the simulated collector.
        bound=self.pool.get_claim(self.claim['claim_id'])
        dataset=Path(bound['binding']['output'])/'execution/candidate'
        out=self.root/('qc-'+status);out.mkdir()
        profile=load_json(DEFAULT_DELIVERY_PROFILE)
        profile.update(profile_id='CONTROLLED-CANDIDATE',authority='Offline authored fixture only')
        profile['targets'].update(expected_samples=1,category_share='report-only')
        profile_path=out/'profile.json';save_json(profile_path,profile)
        report=engine.inspect(None,dataset,profile=profile_path,inspection_stage='payload')
        if status!='REVIEW_REQUIRED':
            reviews=review_template(report);reviews.pop('package_review',None)
            for row in reviews['records']:
                steps=[s['step_id'] for s in load_json(dataset/'samples'/row['sample_id']/'annotation.json')['steps']]
                row['reviewer']={'kind':'ai','name':'CONTROLLED offline expectations'}
                row['provenance']={'description':'Authored synthetic protocol fixture; no actual review','frames_viewed':steps}
                row['step_observations']=[{'step_id':s,'note':'CONTROLLED fixture'} for s in steps]
                row['checks']={name:{'status':status,'note':'CONTROLLED fixture','evidence_steps':steps} for name in engine.SEMANTIC}
            document=reviews['delivery_document_review'];document['reviewer']={'kind':'ai','name':'CONTROLLED fixture'}
            document['provenance']={'description':'Authored fixture'}
            for check in document['checks'].values():
                check.update(status='PASS',note='CONTROLLED fixture',evidence=[{'path':'README.md',
                    'sha256':document['payload_files_sha256']['README.md'],'detail':'Fixture bytes'}])
            review_path=out/'reviews.json';save_json(review_path,reviews)
            report=engine.inspect(None,dataset,profile=profile_path,reviews=review_path,inspection_stage='payload')
        path=out/'report.json';save_json(path,report);return reference(path),report

    async def test_candidate_qc_pending_failed_and_forged_pass_never_requeues(self):
        result=await self.perform();saved=result['result']
        store=RuntimeStore(self.registry,saved['scope_id'])
        pending,report=self.qc_report(saved,'REVIEW_REQUIRED')
        store.record_qc_report(pending)
        self.assertEqual(self.pool.rows()[0]['result']['qc_state'],'pending_review')
        forged=self.root/'forged.json';save_json(forged,{'status':'PASS','samples':[{'sample_id':saved['sample_id']}], 'dataset':'fake'})
        with self.assertRaises((ValueError,KeyError)):store.record_qc_report(reference(forged))
        failed,report=self.qc_report(saved,'FAIL');self.assertEqual(report['status'],'FAIL',report.get('issues',report))
        store.record_qc_report(failed)
        self.assertEqual(self.pool.rows()[0]['state'],'succeeded')
        self.assertEqual(self.pool.rows()[0]['result']['qc_state'],'failed')
        self.assertEqual(self.pool.claim_next('another','qc-failed')['state'],'EMPTY')
        retry(self.pool,self.cid,reason='Explicit replacement after independent fixture QC')
        self.assertEqual(self.pool.stats()['pending'],1)
        with self.assertRaises(ValueError):finish_or_reconcile(self.pool,self.claim,reconciliation=True)
        self.assertEqual(self.pool.stats()['pending'],1)
        with self.pool.pool.connect() as con:self.assertEqual(con.execute('SELECT COUNT(*) FROM candidate_results').fetchone()[0],1)

    async def test_candidate_qc_accepted_keeps_capture_pending_and_rejects_retry(self):
        result=await self.perform();saved=result['result'];store=RuntimeStore(self.registry,saved['scope_id'])
        accepted,report=self.qc_report(saved,'PASS');self.assertEqual(report['status'],'PASS',report.get('issues',report))
        store.record_qc_report(accepted)
        self.assertEqual(self.pool.rows()[0]['result']['qc_state'],'accepted')
        self.assertEqual(statistics(self.pool)['QC_accepted'],1)
        self.assertEqual(store.snapshot()['attempts'][0]['status'],'collected_pending_review')
        with self.assertRaises(ValueError):retry(self.pool,self.cid,reason='Cannot double count accepted')
