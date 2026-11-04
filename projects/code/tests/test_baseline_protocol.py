"""Disposable baseline protocol tests; no real sites, models or historic files."""
import io
import json,unittest
import urllib.error
from copy import deepcopy
from unittest.mock import patch,AsyncMock,Mock
import test_banded_plan as banded
import test_model_provider_protocols as provider
import test_candidate_entry_engineering as entry
from webcollect.banded_plan import tools,validate_plan,proves,bind_target
from webcollect.model_gateway import strict_plan_content
from webcollect.batch_core import OutcomeUnknown,load_json,save_json
from webcollect.agent_feedback import reference

class PlanProtocol(unittest.TestCase):
    def test_scroll_predicate_has_no_fake_text_but_endpoint_and_visible_content_still_require_text(self):
        p=banded.plan_for({'attempt_id':'a','observation':{'observation_id':'o'}})
        for step in p['steps']:step['expected']={'kind':'scroll_changed'}
        validate_plan(p,'a','o',['scroll'])
        p['finish_when']={'kind':'scroll_changed'}
        with self.assertRaises(Exception):validate_plan(p,'a','o',['scroll'])
        p['finish_when']={'kind':'visible_text'}
        with self.assertRaises(Exception):validate_plan(p,'a','o',['scroll'])
    def test_timeout_cannot_reach_the_original_lease_and_rejects_before_http(self):
        f=provider.ProviderProtocolTests('test_text_provider_payloads_include_schema_and_use_max_tokens');f.setUp();self.addCleanup(f.doCleanups)
        ledger,job,g=f.gateway(f.config('glm'))
        with self.assertRaisesRegex(ValueError,'job lease'):
            g.call_tool(job,'plan','x',tools(),system='s',attempt_id='a',max_requests=25,timeout_seconds=ledger.config['budget']['lease_seconds'])
        self.assertEqual(len(f.opener.calls),0)
        with ledger.connect() as con:self.assertEqual(con.execute('SELECT COUNT(*) FROM model_requests').fetchone()[0],0)

    def test_content_plan_exact_json_has_no_native_call_and_rejects_truncation_or_multiple(self):
        f=provider.ProviderProtocolTests('test_text_provider_payloads_include_schema_and_use_max_tokens');f.setUp();self.addCleanup(f.doCleanups)
        ledger,job,g=f.gateway(f.config('glm'))
        p=banded.plan_for({'attempt_id':'a','observation':{'observation_id':'o'}})
        f.opener.raw['choices']=[{'finish_reason':'stop','message':{'content':json.dumps(p)}}]
        result=g.call_tool(job,'plan','x',tools(),system='s',attempt_id='a',max_requests=25,content_plan_protocol='strict-plan-content-1',timeout_seconds=min(300,ledger.config['budget']['lease_seconds']-10))
        self.assertEqual(result['response_kind'],'strict_plan_content');self.assertNotIn('tool_call_id',result);self.assertNotIn('name',result)
        self.assertEqual(len(f.opener.calls),1)
        with ledger.connect() as con:
            row=con.execute('SELECT id,request_json,response FROM model_requests').fetchone()
        wire=json.loads(row['request_json'])
        self.assertEqual(wire['request_timeout_seconds'],min(300,ledger.config['budget']['lease_seconds']-10))
        timing=json.loads(row['response'])['http_timing']
        self.assertEqual(timing['client_request_id'],row['id'])
        self.assertEqual(json.loads(f.opener.calls[0].data)['request_id'],row['id'])
        self.assertEqual(timing['request_bytes'],len(f.opener.calls[0].data))
        self.assertTrue(timing['body_read_returned'])
        self.assertLessEqual(timing['headers_ms'],timing['elapsed_ms'])
        for content in ('{} {}','```json\n{}\n```','{"steps":'):
            with self.assertRaises(Exception):strict_plan_content({'content':content},{'submit_plan':tools()[0]['function']['parameters']})

    def test_incomplete_first_plan_records_transport_phase_and_original_id(self):
        class BrokenBody(io.BytesIO):
            def read(self, size):
                raise TimeoutError('fixture body timeout')

        fixture = provider.ProviderProtocolTests('test_text_provider_payloads_include_schema_and_use_max_tokens')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        rejected = urllib.error.HTTPError('https://provider.invalid/', 429, 'fixture', {}, io.BytesIO(b'{}'))
        for name, outcome, headers_seen in (
            ('before_headers', TimeoutError('fixture open timeout'), False),
            ('during_body', BrokenBody(), True),
            ('http_status', rejected, True),
        ):
            with self.subTest(name=name):
                ledger, job, gateway = fixture.gateway(fixture.config('glm'))
                with patch.object(fixture.opener, 'open', side_effect=[outcome]) as opener:
                    with self.assertRaises(OutcomeUnknown):
                        gateway.call_tool(job, 'plan', 'fixture', tools(), system='fixture', attempt_id=name,
                                          max_requests=1, content_plan_protocol='strict-plan-content-1')
                self.assertEqual(opener.call_count, 1)
                with ledger.connect() as con:
                    row = con.execute('SELECT id,state,usage,response FROM model_requests WHERE job_id=?',
                                      (job['id'],)).fetchone()
                self.assertEqual(row['state'], 'unknown')
                self.assertIsNone(row['usage'])
                timing = json.loads(row['response'])['http_timing']
                self.assertEqual(json.loads(opener.call_args.args[0].data)['request_id'], row['id'])
                self.assertEqual(timing['client_request_id'], row['id'])
                self.assertEqual(timing['headers_ms'] is not None, headers_seen)
                self.assertFalse(timing['body_read_returned'])
                self.assertGreaterEqual(timing['elapsed_ms'], timing['headers_ms'] or 0)

class Session(banded.BandedSessionTests):
    async def test_scoped_preflight_allows_planning_but_blocks_a_different_first_action(self):
        from webcollect.goal_evidence import VERSION as evidence_version
        session, _ = self.recorded()
        session.task['fragment']['session_objective'] = {'objective':{'kind':'reading',
            'description':'搜索条目并阅读','evidence_contract':{'kind':'reading','version':evidence_version,
            'subject':'月食','aspects':['月球','地球']}}}
        session.page.wait_for_timeout = AsyncMock()
        session.preflight = AsyncMock(return_value={'completed_probe_count':2,'summary':{
            'routing':'REVIEW_REQUIRED','routing_before_stability_override':'NORMAL_M1',
            'related_stability_failures':[{}]}})
        scope = {'node':'search-field','label':'站内搜索'}
        with patch('webcollect.browser.stability_pair',return_value={'accepted':False}), \
                patch('webcollect.goal_evidence.search_focus_from_pair',return_value=scope):
            await session.run()
        self.assertEqual(self.prompts[0]['first_action_constraint']['node'], 'search-field')
        self.assertEqual(session.actual_dispatches, 0)
        self.assertIn('PREFLIGHT_FIRST_ACTION_OUTSIDE_STABLE_SEARCH', load_json(session.root/'terminal.json')['stop_summary'])
        event = load_json(next(session.root.glob('*-preflight-scoped-search-focus.json')))
        self.assertFalse(event['full_page_accepted'])

    async def test_content_plan_executes_normally_without_forging_tool_call(self):
        s,_=self.recorded();choose=s.choose
        async def content(prompt):
            result=await choose(prompt)
            for step in result['arguments']['steps']:step['expected']={'kind':'scroll_changed'}
            return {'response_kind':'strict_plan_content','content_plan_protocol':'strict-plan-content-1','arguments':result['arguments'],'request_id':'mock-settled'}
        s.choose=content;r=await s.run();self.assertEqual(r['effective_steps'],5,r);self.assertEqual(s.tool_call_ids,set())
    async def test_preflight_finite_same_page_strict_pair_refresh(self):
        s,_=self.recorded();s.page.wait_for_timeout=AsyncMock();calls=[]
        async def preflight(page,directory):
            calls.append(str(directory))
            return {'completed_probe_count':2,'summary':{'routing':'REVIEW_REQUIRED','related_stability_failures':[{}]}} if len(calls)==1 else {'completed_probe_count':2,'summary':{'routing':'NORMAL_M1'}}
        s.preflight=preflight;r=await s.run();self.assertEqual(r['effective_steps'],5);self.assertEqual(len(calls),2)
        self.assertTrue(calls[1].endswith('preflight-recheck-1'))
    async def test_old_diagnostic_instability_needs_a_new_full_strict_pair_not_a_route_bypass(self):
        s,_=self.recorded()
        async def preflight(page,directory):
            return {'completed_probe_count':2,'summary':{'routing':'REVIEW_REQUIRED','routing_before_stability_override':'NORMAL_M1','related_stability_failures':[{}]}}
        s.preflight=preflight
        def exact_fixture_pair(before,after,png_before,png_after):return {'accepted':before==after and png_before==png_after,'scope':'synthetic exact pair'}
        with patch('webcollect.browser.stability_pair',side_effect=exact_fixture_pair):r=await s.run()
        self.assertEqual(r['effective_steps'],5,r)
        proof=load_json(next(s.root.glob('*-preflight-current-strict-pair.json')))
        self.assertTrue(proof['proof']['accepted']);self.assertTrue(proof['rule_unchanged'])

    async def test_label_node_maps_only_to_proven_visible_ancestor_and_left_constraint_retained(self):
        s,_=self.recorded();await s._observe();o=s.current
        c=deepcopy(o['controls']['control-0']);c['element'].update(element_id='label',native_role='strong',text='标题',parent_id='control-0')
        o['controls']['control-0']['element']['native_role']='a';o['controls']['label']=c
        state=load_json(o['evidence']['state']['path']);state['elements'].append(c['element']);state['elements'][0]['native_role']='a';alternate=self.root/'carrier-state.json';save_json(alternate,state);o['evidence']['state']={'path':str(alternate)}
        self.assertEqual(bind_target(o,{'text':'标题','node':'label','observation_id':o['observation_id']}),['control-0'])
        self.assertEqual(bind_target(o,{'text':'标题','region':'左栏菜单'}),[])

class NormalEntry(entry.EntryEngineering):
    async def test_explicit_objective_preserves_null_goal_and_reaches_first_model_via_normal_entry(self):
        from webcollect.model_gateway import ModelGateway
        from webcollect.candidate_consumer import consume
        objective=self.root/'objective.json';save_json(objective,{'schema_version':'webcollect-session-objective-1',
            'candidate_id':self.cid,'version':self.claim['version'],'entry_url':self.uri,'requested_goal':None,
            'objective':{'description':'逐段核对本次页面五项信息并滚动阅读。','minimum_effective_steps':5,'preferred_band':'five'}})
        execute=self.surface.execute_action
        def effect(kind,args):
            execute(kind,args)
            if len(self.surface.executed)==5:self.surface.state['visible_text']+='\n当前终点内容'
        self.surface.execute_action=effect
        def call(gateway,job,purpose,prompt,tools,**kw):
            p=json.loads(prompt);self.assertIsNone(p['requested_goal']);self.assertEqual(p['session_objective']['description'],'逐段核对本次页面五项信息并滚动阅读。')
            return {'name':'submit_plan','arguments':banded.plan_for(p),'tool_call_id':'mock-first'}
        with self.io_boundaries(mock_gateway=False,legacy_protocol=False),patch.object(ModelGateway,'call_tool',call):
            r=await consume(self.pool,self.claim,self.ledger,output=self.output,registry=self.registry,policy=self.policy_path,history_set=self.chain,session_objective=reference(objective))
        self.assertEqual(r['state'],'succeeded',r)
        task=load_json(next(self.output.rglob('plan.json')))['tasks'][0]
        self.assertIsNone(task['workflow_proposal']['spec']['goal']['structured'])
        self.assertIn('session_objective',task['workflow_proposal']['spec'])
        local=task['fragment']['session_objective']['reference']
        self.assertTrue(__import__('pathlib').Path(local['path']).is_relative_to(self.output))
        self.assertEqual(load_json(local['path']),load_json(objective))

class FirstPlanGateway(unittest.IsolatedAsyncioTestCase):
    async def test_only_latest_glm_first_plan_uses_configured_effort(self):
        from webcollect.react_session import ReactSession, build_url_task, react_chooser

        fixture = provider.ProviderProtocolTests('test_text_provider_payloads_include_schema_and_use_max_tokens')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        for version, setting, expected in ((7, 'low', 'low'), (7, None, 'max'), (6, 'low', 'max')):
            with self.subTest(version=version, setting=setting):
                config = fixture.config('glm', vision=True)
                if setting:
                    config['model']['reasoning_effort'] = setting
                ledger, parent, _ = fixture.gateway(config)
                ledger.finish(parent)
                protocol = 'webcollect-banded-conditional-plan-' + str(version)
                attempt = f'effort-{version}-{setting}'
                task = build_url_task(url='https://example.org/', task_version='diagnostic', plan_protocol=protocol)
                chooser = react_chooser(ledger, task, attempt)
                directory = fixture.root / attempt
                ReactSession(task, directory, chooser, Mock(), attempt_id=attempt)
                binding = load_json(directory / 'boundary.json')
                self.assertEqual(binding.get('first_plan_reasoning_effort', binding['reasoning_effort']), expected)
                prompt = {'protocol': protocol, 'phase': 'first', 'system': 'fixture', 'attempt_id': attempt,
                          'progress': {'decisions_used': 1}, 'tools': tools(),
                          'observation': {'observation_id': 'o', 'image_ref': str(fixture.image)}}
                plan = banded.plan_for(prompt)
                fixture.opener.raw['choices'] = [{'finish_reason': 'stop', 'message': {'content': json.dumps(plan)}}]
                await chooser(prompt)
                self.assertEqual(json.loads(fixture.opener.calls[-1].data)['reasoning_effort'], expected)
                prompt.update(phase='branch', progress={'decisions_used': 2})
                choice = {'attempt_id': attempt, 'observation_id': 'o', 'choice': 'stop'}
                fixture.opener.raw['choices'] = [{'finish_reason': 'stop', 'message': {'content': json.dumps(choice)}}]
                await chooser(prompt)
                self.assertEqual(json.loads(fixture.opener.calls[-1].data)['reasoning_effort'], 'max')

    async def test_lease_failure_after_unknown_dispatch_remains_unknown_and_is_not_resent(self):
        import time
        from webcollect.model_gateway import ModelGateway
        from webcollect.react_session import build_url_task,react_chooser
        from webcollect.banded_plan import VERSION
        from webcollect.batch_core import OutcomeUnknown
        f=provider.ProviderProtocolTests('test_text_provider_payloads_include_schema_and_use_max_tokens');f.setUp();self.addCleanup(f.doCleanups)
        ledger,parent,g=f.gateway(f.config('glm'))
        task=build_url_task(url='https://example.org',task_version='lease',plan_protocol=VERSION)
        chooser=react_chooser(ledger,task,'lease-attempt');calls=[]
        def lost(gateway,job,purpose,text,declared,**kw):
            calls.append(job['id'])
            request=ledger.reserve_request(job,'mock-dispatch',0,request_json={'dispatch_attempt_id':'lease-attempt','http_dispatch':True})
            ledger.settle_request(request['id'],state='unknown',error='TimeoutError')
            with ledger.transaction() as con:con.execute('UPDATE jobs SET lease=? WHERE id=?',(time.time()-1,job['id']))
            raise ValueError('Lost/expired job lease')
        prompt={'protocol':VERSION,'phase':'first','system':'s','attempt_id':'lease-attempt','observation':{'observation_id':'o','image_ref':str(f.image)},'progress':{'decisions_used':1},'tools':tools()}
        with patch.object(ModelGateway,'call_tool',lost):
            with self.assertRaises(OutcomeUnknown):await chooser(prompt)
            with self.assertRaises(OutcomeUnknown):await chooser(prompt)
        self.assertEqual(len(calls),1)
        with ledger.connect() as con:self.assertEqual(con.execute('SELECT state FROM model_requests').fetchone()[0],'unknown')

def load_tests(loader,tests,pattern):
    return unittest.TestSuite(cls(name) for cls in (PlanProtocol,Session,NormalEntry,FirstPlanGateway) for name in cls.__dict__ if name.startswith('test_'))
