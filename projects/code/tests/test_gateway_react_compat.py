"""Actual gateway + ReAct wiring on fake HTTP, page, PNGs and disposable SQLite."""
import io
import json
import itertools
import time
import unittest
from copy import deepcopy
from unittest.mock import patch

import test_model_provider_protocols as provider_fixtures
import test_react_native as native_fixtures
from test_react_session import ReactHarness
from webcollect.batch_core import BatchLedger, OutcomeUnknown, SessionGLMCallLimit, load_json
from webcollect.agent_controller import DecisionRequestError, DecisionModelFault
from webcollect.react_session import ReactSession, build_url_task, react_chooser


class GatewayReactCompatibility(ReactHarness, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.provider = provider_fixtures.ProviderProtocolTests('test_text_provider_payloads_include_schema_and_use_max_tokens')
        self.provider.setUp()
        self.addCleanup(self.provider.doCleanups)
        self.task = build_url_task(url=self.page.url, task_version='gateway-react-compat', allowed_actions=['scroll'])
        self.config = self.provider.config('glm', vision=True)
        self.config['model'].update(model='glm-5.3-flash', image_encoding='data_url')
        self.payloads = []
        self.builds = [native_fixtures.scroll('查看页面下方内容'), native_fixtures.finish()]
        self.raw_responses = []

        def fake_http(request, timeout):
            self.provider.opener.calls.append(request)
            payload = json.loads(request.data)
            self.payloads.append(payload)
            if self.provider.opener.error is not None:
                raise self.provider.opener.error
            prompt = json.loads(payload['messages'][-1]['content'][0]['text'])
            message = native_fixtures.native(self.builds.pop(0), 'http-call-' + str(len(self.payloads)))(prompt)['assistant_message']
            raw = deepcopy(self.provider.opener.raw)
            raw['choices'] = [{'finish_reason':'tool_calls','message':message}]
            self.raw_responses.append(deepcopy(raw))
            return io.BytesIO(json.dumps(raw).encode())
        self.provider.opener.open = fake_http

    def session_with_gateway(self, *, cap=24):
        self.task = build_url_task(url=self.page.url, task_version='gateway-react-compat', allowed_actions=['scroll'],
                                   budgets={'max_model_calls':cap})
        self.ledger = BatchLedger(self.root/'gateway.sqlite3', self.config, initialize=True)
        self.choose = react_chooser(self.ledger, self.task, 'original-attempt')
        return ReactSession(self.task, self.root/'session/raw', self.choose, self.page)

    async def test_default_25_glm_dispatches_stop_only_this_session_and_keep_original_images(self):
        self.config['model']['max_images'] = 24
        self.config['budget']['lease_seconds'] = 3600
        read = native_fixtures.decide(tool='inspect',arguments=lambda p:{
            'kind':'html','observation_id':p['observation']['observation_id'],
            'offset':0,'limit_chars':10})
        self.builds = [read]*25 + [native_fixtures.finish()]
        with patch('webcollect.batch_core.time', wraps=time) as clock:
            clock.time.side_effect = itertools.count(time.time(),2).__next__
            session = self.session_with_gateway(cap=None)
            result = await session.run()
            details={'code':'glm_session_call_limit','attempt_id':'original-attempt','used':25,'limit':25}
            self.assertEqual((result['stop_reason'],result['stop_details'],result['unknown']),('budget',details,False))
            terminal=load_json(result['terminal']['path'])
            self.assertEqual(terminal['stop_details'], details)
            self.assertEqual(terminal['used']['max_model_calls'],25)
            self.assertEqual(len(self.payloads),25)
            sent=self.payloads[-1]['messages']
            count_images=lambda messages: sum(p['type']=='image_url' for m in messages if isinstance(m['content'],list) for p in m['content'])
            self.assertEqual(count_images(sent),1)
            self.assertEqual(count_images(session.history),25)
            self.assertEqual(sent[-1]['content'][1]['type'],'image_url')
            self.assertEqual([m for m in sent if m['role'] in ('assistant','tool')],
                             [m for m in session.history[:-2] if m['role'] in ('assistant','tool')][-4:])
            resumed = BatchLedger(self.ledger.path,self.config)
            chooser = react_chooser(resumed,self.task,'original-attempt')
            self.assertEqual((await ReactSession(self.task,self.root/'resume/raw',chooser,self.page).run())['stop_details'],details)
            fresh = react_chooser(resumed,self.task,'next-attempt')
            next_result=await ReactSession(self.task,self.root/'next/raw',fresh,self.page).run()
            self.assertEqual((next_result['stop_reason'],fresh.requests_used(),chooser.requests_used()),('ready',1,25))

    async def test_twenty_fifth_glm_response_can_finish_or_exhaust_an_internal_retry(self):
        for last in ('ready','invalid','unknown','budget'):
            with self.subTest(last=last), patch('webcollect.batch_core.time',wraps=time) as clock:
                clock.time.side_effect=itertools.count(time.time(),2).__next__
                self.config['budget']['lease_seconds']=3600
                ledger=BatchLedger(self.root/(last+'.sqlite3'),self.config,initialize=True)
                aid='original-'+last
                task=deepcopy(self.task)
                kind='react-decision'
                original_request={'provider':'glm'}
                if last == 'invalid':
                    # Previous native tasks froze a null wire cap. Retain their original
                    # identity and receipts when applying today's dispatch ceiling.
                    from webcollect.planning import object_sha256
                    for part in (task['fragment'],task['workflow_proposal']['spec']):
                        part.pop('glm_http_call_limit')
                        part['budgets']['max_no_progress']=5
                    task['task_id']='react-'+object_sha256({'url':task['initial_url'],'spec':task['workflow_proposal']['spec']})[:24]
                    kind='react-native-decision'
                    original_request.update(protocol='native-tool-1',dispatch_attempt_id=aid,dispatch_max_requests=None,http_dispatch=True)
                job=ledger.claim(kind,job_id=ledger.enqueue(kind,{'attempt_id':aid,'historical':True}))
                for i in range(24):
                    request=ledger.reserve_request(job,'prior-decision-'+str(i),0,request_json=original_request)
                    ledger.settle_request(request['id'],state='succeeded',usage={'input_tokens':10,'output_tokens':1,'cached_input_tokens':0})
                ledger.finish(job)
                self.builds=[native_fixtures.finish('budget' if last=='budget' else 'ready')]
                before=len(self.payloads)
                original=self.provider.opener.open
                def transport(req,timeout):
                    response=original(req,timeout)
                    if last in ('ready','budget'): return response
                    if last=='unknown': raise TimeoutError('dispatched final request has no known outcome')
                    body=json.loads(response.read())
                    body['choices'][0]['message']['tool_calls'][0]['function']['name']='undeclared'
                    return io.BytesIO(json.dumps(body).encode())
                with patch.object(self.provider.opener,'open',side_effect=transport):
                    chooser=react_chooser(ledger,task,aid)
                    result=await ReactSession(task,self.root/last/'raw',chooser,self.page).run()
                self.assertEqual((len(self.payloads)-before,chooser.requests_used()),(1,25))
                self.assertEqual(load_json(result['terminal']['path'])['glm_http_requests'],25)
                self.assertEqual(result['stop_reason'],{'ready':'ready','unknown':'blocked','invalid':'budget','budget':'budget'}[last],result)
                if last=='unknown':
                    self.assertTrue(result['unknown'])
                    restarted=react_chooser(BatchLedger(ledger.path,self.config),task,aid)
                    again=await ReactSession(task,self.root/'unknown-resumed/raw',restarted,self.page).run()
                    self.assertTrue(again['unknown'])
                    self.assertEqual(len(self.payloads)-before,1)
                if last=='invalid':
                    self.assertEqual(result['stop_details'],{'code':SessionGLMCallLimit.code,'attempt_id':aid,'used':25,'limit':25})
                    with ledger.connect() as con:
                        rows=con.execute("SELECT r.state,j.error FROM model_requests r JOIN jobs j ON j.id=r.job_id WHERE j.kind='react-native-decision' AND json_extract(j.payload,'$.historical') IS NULL").fetchall()
                    self.assertEqual([tuple(row) for row in rows],[('invalid_response','budget:glm_session_call_limit')])
                elif last=='budget':
                    self.assertEqual(result['stop_details']['code'],SessionGLMCallLimit.code)
                else:
                    self.assertNotIn('stop_details',result)

    async def test_real_gateway_history_roundtrip_cache_and_http_budget(self):
        session = self.session_with_gateway()
        result = await session.run()
        self.assertEqual(result['effective_steps'],1,result)
        self.assertFalse(result['unknown'])
        self.assertEqual(self.choose.requests_used(),2)
        self.assertEqual(session.used['max_model_calls'],2)
        self.assertEqual(len(self.payloads),2)
        self.assertEqual([m['role'] for m in self.payloads[1]['messages']],
                         ['system','assistant','tool','user'])
        self.assertEqual(self.payloads[1]['messages'][1], self.raw_responses[0]['choices'][0]['message'])
        self.assertEqual(self.payloads[1]['messages'][2]['tool_call_id'],'http-call-1')
        tool_result = json.loads(self.payloads[1]['messages'][2]['content'])
        self.assertEqual(tool_result['data']['effective_steps_delta'],1)
        self.assertIn('reasoning_content', self.payloads[1]['messages'][1])
        self.assertNotEqual(self.payloads[0]['messages'][-1]['content'][1], self.payloads[1]['messages'][-1]['content'][1])
        for path in (self.root/'session/raw').glob('*.json'):
            self.assertNotIn('opaque-protocol-private',path.read_text())
        # A separate exact prompt identity caches its settled original envelope.
        session2 = ReactSession(self.task,self.root/'cache/raw',self.choose,self.page)
        await session2._open_entry()
        prompt = session2._prompt()
        self.builds = [native_fixtures.finish()]
        first = await self.choose(prompt)
        with patch('webcollect.model_gateway.socket.getaddrinfo',side_effect=AssertionError('cache performs no DNS')):
            second = await self.choose(prompt)
        self.assertEqual(first,second)
        self.assertEqual(self.choose.requests_used(),3)
        self.assertEqual(len(self.payloads),3)

    async def test_last_request_consumed_by_invalid_response_closes_as_budget_without_action(self):
        session = self.session_with_gateway(cap=1)
        original = self.provider.opener.open
        def wrong_name(request, timeout):
            stream = original(request,timeout)
            raw = json.loads(stream.read())
            raw['choices'][0]['message']['tool_calls'][0]['function']['name'] = 'undeclared'
            return io.BytesIO(json.dumps(raw).encode())
        self.provider.opener.open = wrong_name
        result = await session.run()
        self.assertEqual(result['stop_reason'],'budget',result)
        self.assertFalse(result['unknown'],result)
        self.assertEqual(self.choose.requests_used(),1)
        self.assertEqual(session.used['max_model_calls'],1)
        self.assertEqual(len(self.payloads),1)
        self.assertEqual(self.surface.executed,[])
        with self.ledger.connect() as con:
            self.assertEqual(con.execute('SELECT state FROM model_requests').fetchone()[0],'invalid_response')

    async def test_retry_is_two_actual_requests_for_one_decision(self):
        session = self.session_with_gateway(cap=2)
        self.builds = [native_fixtures.finish(),native_fixtures.finish()]
        original = self.provider.opener.open
        def first_wrong(request,timeout):
            stream = original(request,timeout)
            raw = json.loads(stream.read())
            if len(self.payloads)==1:
                raw['choices'][0]['message']['tool_calls'][0]['function']['name']='undeclared'
            return io.BytesIO(json.dumps(raw).encode())
        self.provider.opener.open = first_wrong
        result = await session.run()
        self.assertFalse(result['unknown'],result)
        self.assertEqual(result['stop_reason'],'ready',result)
        self.assertEqual(session.used['max_decisions'],1)
        self.assertEqual(session.used['max_model_calls'],2)
        self.assertEqual(self.choose.requests_used(),2)
        self.assertEqual(len(self.payloads),2)
        self.assertEqual(self.surface.executed,[])

    async def test_zero_dispatch_replay_does_not_invent_unknown_or_resend(self):
        session = self.session_with_gateway()
        await session._open_entry()
        prompt = session._prompt()
        prompt['observation']['image_ref']=str(self.root/'missing-original.png')
        for _ in range(2):
            with self.assertRaises(DecisionRequestError):
                await self.choose(prompt)
        self.assertEqual(self.payloads,[])
        self.assertEqual(self.choose.requests_used(),0)
        self.assertEqual(self.ledger.summary()['model_requests'],0)

    async def test_unknown_original_and_changed_prompt_are_not_resent_after_gateway_restart(self):
        session = self.session_with_gateway()
        self.provider.opener.error = TimeoutError('controlled post-dispatch timeout')
        await session._open_entry()
        prompt = session._prompt()
        with patch('webcollect.model_gateway.time.sleep'), patch('webcollect.batch_core.time', wraps=time) as clock:
            clock.time.side_effect=itertools.count(time.time(),2).__next__
            with self.assertRaises(OutcomeUnknown):
                await self.choose(prompt)
        with self.ledger.connect() as con:
            original = dict(con.execute('SELECT * FROM model_requests').fetchone())
        restarted = react_chooser(self.ledger,self.task,'original-attempt')
        changed = deepcopy(prompt)
        changed['progress']['decisions_used'] += 1
        changed['recent_feedback'] = [{'reason':'changed prompt must not bypass original UNKNOWN'}]
        for candidate in (prompt,changed):
            with self.assertRaises(OutcomeUnknown):
                await restarted(candidate)
        self.assertEqual(len(self.payloads),4)
        self.assertEqual(restarted.requests_used(),4)
        with self.ledger.connect() as con:
            self.assertEqual(dict(con.execute('SELECT * FROM model_requests').fetchone()),original)
        self.assertEqual(self.surface.executed,[])

    async def test_actual_request_counter_matches_gateway_attempt_scope(self):
        session = self.session_with_gateway()
        # Other callers of the shared gateway use the same reservation scope.
        jid=self.ledger.enqueue('shared-tool-diagnostic',{'fixture':'same original attempt'})
        job=self.ledger.claim('shared-tool-diagnostic',job_id=jid)
        from webcollect.model_gateway import ModelGateway
        gateway=ModelGateway(self.ledger)
        await session._open_entry()
        prompt=session._prompt()
        tools=prompt['tools']
        self.builds=[native_fixtures.finish()]
        gateway.call_tool(job,'shared',json.dumps({k:v for k,v in prompt.items() if k not in ('system','tools','_history')}),
            tools,system=prompt['system'],images=[prompt['observation']['image_ref']],attempt_id='original-attempt',max_requests=24)
        self.ledger.finish(job,result={'fixture':'done'})
        self.assertEqual(self.choose.requests_used(),1)

    async def test_unknown_last_request_remains_unknown_when_another_session_checks_exhausted_budget(self):
        session = self.session_with_gateway(cap=1)
        self.provider.opener.error = TimeoutError('controlled last request UNKNOWN')
        result = await session.run()
        self.assertTrue(result['unknown'],result)
        restarted=react_chooser(self.ledger,self.task,'original-attempt')
        other=ReactSession(self.task,self.root/'exhausted-unknown/raw',restarted,self.page)
        result=await other.run()
        self.assertTrue(result['unknown'],result)
        self.assertEqual(result['stop_reason'],'blocked',result)
        self.assertEqual(other.used['max_model_calls'],1)
        self.assertEqual(len(self.payloads),1)
        self.assertEqual(self.surface.executed,[])

    async def test_known_exhausted_request_scope_stops_before_new_model_job(self):
        session=self.session_with_gateway(cap=1)
        await session._open_entry()
        self.builds=[native_fixtures.finish()]
        await self.choose(session._prompt())
        with self.ledger.connect() as con:
            jobs_before=con.execute('SELECT COUNT(*) FROM jobs').fetchone()[0]
        other=ReactSession(self.task,self.root/'exhausted-known/raw',self.choose,self.page)
        result=await other.run()
        self.assertFalse(result['unknown'],result)
        self.assertEqual(result['stop_reason'],'budget',result)
        self.assertEqual(other.used['max_model_calls'],1)
        self.assertEqual(len(self.payloads),1)
        with self.ledger.connect() as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM jobs').fetchone()[0],jobs_before)

    async def test_host_rejected_action_has_matching_tool_result_in_next_http_history(self):
        from test_react_session import decide,act_step
        session=self.session_with_gateway()
        self.builds=[decide(goal='查看页面下方内容',tool='act',arguments=lambda p:{
            'observation_id':'stale-observation',
            'step':act_step('scroll',direction='down',goal='查看下方',expected='视口下移')}),
            native_fixtures.finish('no_path')]
        result=await session.run()
        self.assertFalse(result['unknown'],result)
        self.assertEqual(len(self.payloads),2)
        messages=self.payloads[1]['messages']
        self.assertEqual(messages[1]['tool_calls'][0]['id'],messages[2]['tool_call_id'])
        feedback=json.loads(messages[2]['content'])
        self.assertIn(feedback['status'],('rejected','need_observation'))
        self.assertEqual(self.surface.executed,[])
        self.assertEqual(self.choose.requests_used(),2)

    async def test_cache_and_unknown_replay_do_not_select_or_read_model_account(self):
        session=self.session_with_gateway()
        await session._open_entry()
        prompt=session._prompt()
        self.builds=[native_fixtures.finish()]
        result=await self.choose(prompt)
        with patch('webcollect.model_gateway.ModelGateway',side_effect=AssertionError('no account access on replay')):
            restarted=react_chooser(self.ledger,self.task,'original-attempt')
            self.assertEqual(await restarted(prompt),result)
        self.provider.opener.error=TimeoutError('controlled new request UNKNOWN')
        changed=deepcopy(prompt)
        changed['progress']['decisions_used']+=1
        with patch('webcollect.model_gateway.time.sleep'), patch('webcollect.batch_core.time', wraps=time) as clock:
            clock.time.side_effect=itertools.count(time.time(),2).__next__
            with self.assertRaises(OutcomeUnknown):
                await self.choose(changed)
        changed['progress']['decisions_used']+=1
        with patch('webcollect.model_gateway.ModelGateway',side_effect=AssertionError('UNKNOWN cannot select another account')):
            restarted=react_chooser(self.ledger,self.task,'original-attempt')
            with self.assertRaises(OutcomeUnknown):
                await restarted(changed)
        self.assertEqual(len(self.payloads),5)

    async def test_timeout_retry_answer_runs_action_once_and_continues_original_session(self):
        session=self.session_with_gateway()
        original=self.provider.opener.open
        attempts=[]
        def once(req,timeout):
            attempts.append(req)
            if len(attempts)==1:
                raise TimeoutError('controlled timeout before receiving the decision')
            return original(req,timeout)
        with patch.object(self.provider.opener,'open',side_effect=once), \
                patch('webcollect.model_gateway.time.sleep'), patch('webcollect.batch_core.time', wraps=time) as clock:
            clock.time.side_effect=itertools.count(time.time(),2).__next__
            result=await session.run()
        self.assertFalse(result['unknown'],result)
        self.assertEqual((result['stop_reason'],len(self.surface.executed)),('ready',1))
        self.assertEqual((len(attempts),self.choose.requests_used()),(3,3))
        self.assertEqual(load_json(result['terminal']['path'])['glm_http_requests'],3)
        with self.ledger.connect() as con:
            states=[r[0] for r in con.execute('SELECT state FROM model_requests ORDER BY started')]
        self.assertEqual(states,['unknown','succeeded','succeeded'])

    async def test_cancelled_http_with_late_success_keeps_original_attempt_on_hold(self):
        import asyncio
        import threading
        session=self.session_with_gateway()
        started=threading.Event()
        release=threading.Event()
        settled=asyncio.Event()
        loop=asyncio.get_running_loop()
        http=self.provider.opener.open
        original_settle=self.ledger.settle_request
        def blocked_http(request,timeout):
            started.set()
            if not release.wait(3):
                raise AssertionError('controlled HTTP release was not signalled')
            return http(request,timeout)
        def settle(*args,**kwargs):
            original_settle(*args,**kwargs)
            loop.call_soon_threadsafe(settled.set)
        self.provider.opener.open=blocked_http
        try:
            with patch.object(self.ledger,'settle_request',side_effect=settle):
                pending=asyncio.create_task(session.run())
                self.assertTrue(await asyncio.to_thread(started.wait,2))
                pending.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await pending
                release.set()
                await asyncio.wait_for(settled.wait(),2)
        finally:
            release.set()
        with self.ledger.connect() as con:
            request=dict(con.execute('SELECT * FROM model_requests').fetchone())
            self.assertEqual(request['state'],'succeeded')
            self.assertEqual(con.execute('SELECT state FROM jobs').fetchone()[0],'review_required')
        # A late known provider result does not authorize resuming an interrupted
        # browser trajectory under the original attempt or a changed prompt.
        restarted=react_chooser(self.ledger,self.task,'original-attempt')
        other=ReactSession(self.task,self.root/'late-http/raw',restarted,self.page)
        result=await other.run()
        self.assertTrue(result['unknown'],result)
        self.assertEqual(len(self.payloads),1)
        self.assertEqual(self.surface.executed,[])
        with self.ledger.connect() as con:
            self.assertEqual(dict(con.execute('SELECT * FROM model_requests').fetchone()),request)

        # The shared reservation transaction also enforces the hold if a caller
        # bypasses the ReAct preflight with a fresh job/purpose in this attempt.
        jid=self.ledger.enqueue('late-reply-replacement',{'fixture':'must not dispatch'})
        job=self.ledger.claim('late-reply-replacement',job_id=jid)
        from webcollect.model_gateway import ModelGateway
        gateway=ModelGateway(self.ledger)
        tools=[{'type':'function','function':{'name':'observe','parameters':{'type':'object'}}}]
        with self.assertRaises(OutcomeUnknown):
            gateway.call_tool(job,'changed-purpose','controlled text',tools,system='controlled policy',
                              attempt_id='original-attempt',max_requests=24)
        self.assertEqual(len(self.payloads),1)
        self.assertEqual(restarted.requests_used(),1)
        with self.ledger.connect() as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM model_requests').fetchone()[0],1)
