"""Actual gateway + ReAct wiring on fake HTTP, page, PNGs and disposable SQLite."""
import io
import json
import unittest
from copy import deepcopy
from unittest.mock import patch

import test_model_provider_protocols as provider_fixtures
import test_react_native as native_fixtures
from test_react_session import ReactHarness
from webcollect.batch_core import BatchLedger, OutcomeUnknown
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

    async def test_real_gateway_history_roundtrip_cache_and_http_budget(self):
        session = self.session_with_gateway()
        result = await session.run()
        self.assertEqual(result['effective_steps'],1,result)
        self.assertFalse(result['unknown'])
        self.assertEqual(self.choose.requests_used(),2)
        self.assertEqual(session.used['max_model_calls'],2)
        self.assertEqual(len(self.payloads),2)
        self.assertEqual([m['role'] for m in self.payloads[1]['messages']],
                         ['system','user','assistant','tool','user'])
        self.assertEqual(self.payloads[1]['messages'][2], self.raw_responses[0]['choices'][0]['message'])
        self.assertEqual(self.payloads[1]['messages'][3]['tool_call_id'],'http-call-1')
        tool_result = json.loads(self.payloads[1]['messages'][3]['content'])
        self.assertEqual(tool_result['data']['effective_steps_delta'],1)
        self.assertIn('reasoning_content', self.payloads[1]['messages'][2])
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
        self.config['model']['reserve_input_tokens']=200
        session = self.session_with_gateway()
        await session._open_entry()
        prompt = session._prompt()
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
        self.assertEqual(len(self.payloads),1)
        self.assertEqual(restarted.requests_used(),1)
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
        self.assertEqual(messages[2]['tool_calls'][0]['id'],messages[3]['tool_call_id'])
        feedback=json.loads(messages[3]['content'])
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
        with self.assertRaises(OutcomeUnknown):
            await self.choose(changed)
        changed['progress']['decisions_used']+=1
        with patch('webcollect.model_gateway.ModelGateway',side_effect=AssertionError('UNKNOWN cannot select another account')):
            restarted=react_chooser(self.ledger,self.task,'original-attempt')
            with self.assertRaises(OutcomeUnknown):
                await restarted(changed)
        self.assertEqual(len(self.payloads),2)

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
