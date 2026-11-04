"""Disposable native ReAct fixtures: no network, real gateway, or production data."""
import asyncio
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from test_react_session import ReactHarness, Script, decide, act_step
from webcollect.batch_core import load_json, file_sha, OutcomeUnknown
from webcollect.react_session import (ReactSession, build_url_task, validate_task, struct_goal,
                                     GOAL_BUDGETS, LEGACY_BUDGETS, REACT_VERSION, react_chooser)
from webcollect.react_protocol import VERSION, SYSTEM, native_tools, native_decision, atomic_effect
from webcollect.postprocess import session_record, effective_trajectory, process, terminal_outcome


def native(build, cid):
    def result(prompt):
        decision = build(prompt)
        args = {**decision['tool_call']['arguments'], 'goal_update': decision['goal_update'],
                'decision_summary': decision['decision_summary']}
        name = decision['tool_call']['name']
        schema=next((t['function']['parameters'] for t in prompt.get('tools',[]) if t['function']['name']==name),{})
        if 'task_intent' in schema.get('required',[]) or 'planning_basis' in prompt:
            args['task_intent']={'status':'UNKNOWN','task_types':[], 'basis_observation_id':prompt['observation']['observation_id'],
                'visible_end_condition':'受控页面最终状态','basis':'离线协议夹具；不猜测业务类型'}
        return {'name': name, 'arguments': args, 'tool_call_id': cid,
                'assistant_message': {'role': 'assistant', 'content': None,
                    'reasoning_content': 'opaque-protocol-private',
                    'tool_calls': [{'id': cid, 'type': 'function',
                        'function': {'name': name, 'arguments': json.dumps(args, ensure_ascii=False)}}]},
                'user_message': {'role': 'user', 'content': [
                    {'type': 'text', 'text': 'actual sent current observation'},
                    {'type': 'image_url', 'image_url': {'url': prompt['observation']['image_ref']}}]}}
    return result


def finish(reason='ready', summary='当前连续片段结束'):
    return decide(tool='finish', arguments=lambda p: {
        'observation_id': p['observation']['observation_id'], 'stop_reason': reason,
        'summary': summary, 'evidence_refs': [p['observation']['observation_id']]})


def scroll(goal=None):
    return decide(goal=goal, tool='act', arguments=lambda p: {
        'observation_id': p['observation']['observation_id'],
        'step': act_step('scroll', direction='down', goal='查看下方内容', expected='视口下移')})


class NativeSessionTests(ReactHarness, unittest.IsolatedAsyncioTestCase):
    async def test_unrelated_uninspected_iframe_defers_review_but_overlap_and_errors_block(self):
        from unittest.mock import AsyncMock
        from webcollect.react_session import ReactStop
        record={'completed_probe_count':2,'error':None,'summary':{'routing':'REVIEW_REQUIRED',
            'reasons':['Visible iframe internals are uninspected; never infer editorial/ad content or stability: iframe'],
            'critical_regions':[{'kind':'body','bbox':[0,100,1000,700],'readable':True}],
            'media_evidence':[{'kind':'iframe','bbox':[0,0,1000,72],
                'task_or_body_geometry_related':False,'critical_geometry_overlaps':[]}],
            'other_dynamic_reasons':[],'page_capture_risks':[]}}
        session,_,_=self.recorded([]);session.preflight=AsyncMock(return_value=record)
        await session._run_preflight()
        self.assertEqual(self.surface.executed,[])
        self.assertTrue(list(session.root.glob('*preflight-unrelated-opaque-deferred.json')))
        for kind in ('overlap','error','dynamic'):
            altered=deepcopy(record)
            if kind=='overlap':altered['summary']['media_evidence'][0]['bbox']=[0,90,1000,200]
            if kind=='error':altered['error']='missing evidence'
            if kind=='dynamic':altered['summary']['other_dynamic_reasons']=['target movement']
            session.preflight=AsyncMock(return_value=altered)
            with self.assertRaises(ReactStop):await session._run_preflight()

    async def test_predispatch_drift_publishes_fresh_evidence_without_dispatch_or_overwriting(self):
        session, evidence, _ = self.recorded([])
        await session._observe()
        await session._observe('control-0')
        old_id=session.current['observation_id'];old_ref=deepcopy(session.current['evidence']['state'])
        session.working_goal='在当前控件上操作'
        self.surface.state['visible_text']+='\n页面通知已更新'
        result=await session._tool_act({'observation_id':old_id,'step':act_step('click',control_id='control-0')})
        self.assertEqual(result['status'],'need_observation')
        self.assertEqual(self.surface.executed,[])
        self.assertNotEqual(session.current['observation_id'],old_id)
        self.assertEqual(result['data']['refreshed_observation_id'],session.current['observation_id'])
        self.assertEqual(file_sha(old_ref['path']),old_ref['sha256'])
        self.assertIn('页面通知已更新',load_json(session.current['evidence']['state']['path'])['visible_text'])
        result=await session._tool_act({'observation_id':session.current['observation_id'],
                                       'step':act_step('click',control_id='control-0')})
        self.assertEqual(result['status'],'ok')
        self.assertEqual(len(self.surface.executed),1)

    async def test_observe_literal_null_returns_exact_json_null_correction(self):
        session, _, _ = self.recorded([])
        await session._observe()
        result=await session._observe('null')
        expected={'name':'observe','arguments':{'focus_control_id':None}}
        self.assertEqual(result['status'],'rejected')
        self.assertEqual(result['data']['next_tool'],expected)
        self.assertEqual(result['error']['next_tool'],expected)
        self.assertEqual(self.surface.executed,[])

    async def test_html_inspection_does_not_upgrade_missing_readable_label(self):
        self.surface.readable = False
        session, _, _ = self.recorded([])
        await session._observe()
        before = deepcopy(session.current['controls'])
        result = await session._tool_inspect({'kind':'html', 'observation_id':session.current['observation_id']})
        self.assertEqual(result['status'],'ok')
        self.assertTrue(result['data']['does_not_upgrade_actions'])
        self.assertIn('INSUFFICIENT 仍不能 act',result['summary'])
        self.assertEqual(session.current['controls'],before)

    async def test_bad_finish_references_return_one_bound_correction_without_finishing(self):
        session, _, _ = self.recorded([])
        session.current = {'observation_id':'current'}
        session.observations = ['current']
        for refs in (['observation:current'], ['current','control:e_82']):
            args={'observation_id':'current','evidence_refs':refs,'stop_reason':'ready','summary':'结果已显示'}
            rejected = await session._native_finish(args)
            self.assertEqual(rejected['status'],'rejected')
            expected = {'name':'finish','arguments':{**args,'evidence_refs':['current']}}
            self.assertEqual(rejected['data']['next_tool'],expected)
            self.assertEqual(rejected['error']['next_tool'],expected)
            self.assertFalse(session.stop_reason)

    def setUp(self):
        super().setUp()
        self.task = build_url_task(url=self.page.url, task_version='native-fixture')
        self.ids = {'sample_id': 'S000001_sample_000001', 'site_id': 'S000001',
                    'batch_id': 'B20261031_001', 'attempt_id': 'synthetic-attempt'}
        self.manifest = {'batch_id': 'B20261031_001', 'sample_kind': 'real', 'program_version': 't',
                         'rule_version': '1.0.0', 'sites': [{'site_id': 'S000001',
                          'uri': self.task['site_uri'], 'site_category': self.task['site_category']}],
                         'samples': [self.ids['sample_id']]}

    def recorded(self, builds, name='native'):
        evidence = self.root / name / 'evidence' / self.ids['sample_id']
        script = Script([native(build, f'tc{i}') for i, build in enumerate(builds)])
        return ReactSession(self.task, evidence / 'raw', script, self.page,
                            steps_directory=evidence), evidence, script

    async def test_native_tool_round_trip_filters_permissions_keeps_private_history(self):
        self.task = build_url_task(url=self.page.url, task_version='n', allowed_actions=['scroll'])
        session, evidence, script = self.recorded([scroll('查看页面下方内容'), finish()])
        result = await session.run()
        self.assertEqual(result['effective_steps'], 1)
        self.assertEqual(result['stop_reason'], 'ready')
        self.assertEqual(len(self.surface.executed), 1)
        prompt = script.prompts[1]
        self.assertEqual(prompt['system'], SYSTEM)
        self.assertEqual(prompt['observation']['page_actions'], ['scroll'])
        self.assertEqual([m['role'] for m in prompt['_history']], ['assistant', 'tool'])
        self.assertEqual(prompt['_history'][0]['reasoning_content'], 'opaque-protocol-private')
        self.assertEqual(prompt['_history'][1]['tool_call_id'], 'tc0')
        feedback = json.loads(prompt['_history'][1]['content'])
        self.assertEqual(feedback['data']['effective_steps_delta'], 1)
        self.assertIn('actual_change', prompt['trajectory'][-1])
        # Opaque protocol fields are confined to transport history, not ordinary journals.
        for path in (evidence / 'raw').glob('*.json'):
            self.assertNotIn('opaque-protocol-private', path.read_text())
        self.assertTrue(result['short_flow'])
        self.assertIn('实际完成1个', result['short_flow_reason'])

    async def test_entry_observation_reused_without_navigation_and_invalid_refreshed(self):
        captured = await self.surface.capture(self.page)
        entry = {'captured': captured, 'html': await self.page.content()}
        for invalid in (False, True):
            supplied = deepcopy(entry)
            if invalid:
                supplied['captured']['capture']['screenshot_sha256'] = 'bad'
            session, _, _ = self.recorded([finish('no_path')], name='entry-' + str(invalid))
            session.entry_observation = supplied
            session.preflight = preflight = unittest.mock.AsyncMock(return_value={})
            with patch.object(self.page, 'goto', side_effect=AssertionError('must reuse claimed Page')):
                await session.run()
            preflight.assert_awaited_once()
            first = session.observation_records[session.observations[0]]
            self.assertTrue(first['capture_verified'])
            self.assertIs(session.page, self.page)

    async def test_native_protocol_failures_never_dispatch(self):
        valid = native(scroll('查看页面下方内容'), 'tc0')
        def change(kind):
            def build(prompt):
                response = valid(prompt)
                if kind == 'content':
                    response['assistant_message'].pop('tool_calls')
                elif kind == 'many':
                    response['assistant_message']['tool_calls'] *= 2
                elif kind == 'wrong':
                    response['name'] = 'rogue'
                elif kind == 'flat':
                    response['arguments']['action'] = 'scroll'
                elif kind == 'empty-id':
                    response['tool_call_id'] = ''
                return response
            return build
        for kind in ('content', 'many', 'wrong', 'flat', 'empty-id'):
            session = self.session(Script([change(kind), native(finish('no_path'), 'tc1')]), name=kind)
            result = await session.run()
            self.assertEqual(result['effective_steps'], 0, kind)
            self.assertEqual(self.surface.executed, [], kind)
            self.assertFalse(result['unknown'], kind)

    async def test_post_dispatch_capture_rejection_is_unknown_and_diagnostics_are_sealed(self):
        from webcollect.browser import EvidenceStale
        session,evidence,_=self.recorded([scroll('查看下方内容')],name='capture-rejected')
        original=self.surface.capture
        async def capturing(*args,**kwargs):
            if self.surface.executed:
                error=EvidenceStale('controlled loading/structure mismatch')
                error.capture={'attempts':[{'mismatch_fields':['capture_readiness'],'pixel_change':{'changed_pixels':0}}]}
                raise error
            return await original(*args,**kwargs)
        with patch('webcollect.browser.capture',side_effect=capturing):
            result=await session.run()
        self.assertTrue(result['unknown'],result)
        self.assertEqual(result['failure_class'],'interrupted')
        self.assertEqual((result['actual_actions'],result['effective_steps']),(1,0))
        diagnostic=load_json(next((evidence/'raw').glob('capture-rejection-*.json')))
        self.assertTrue(diagnostic['after_dispatch'])
        self.assertEqual(diagnostic['diagnostic']['attempts'][0]['mismatch_fields'],['capture_readiness'])
        receipt=load_json(result['raw_receipt']['path'])
        self.assertTrue(any(name.startswith('capture-rejection-') for name in receipt['files_sha256']))
        from webcollect.candidate_consumer import unverified_original_actions
        self.assertEqual(len(list(unverified_original_actions({'evidence_json':json.dumps([result['raw_receipt']])}))),1)

    async def test_cancellation_seals_dispatched_unknown_and_propagates(self):
        session, evidence, _ = self.recorded([scroll('查看页面下方内容')])
        async def cancel(*args, **kwargs):
            raise asyncio.CancelledError()
        with patch('webcollect.browser.execute', side_effect=cancel):
            with self.assertRaises(asyncio.CancelledError):
                await session.run()
        self.assertTrue((evidence / 'raw/raw-receipt.json').is_file())
        terminal = load_json(evidence / 'raw/terminal.json')
        self.assertTrue(terminal['unknown'])
        raw = load_json(evidence / 'step_001.json')
        self.assertTrue(raw['dispatched'])
        self.assertIsNone(raw['action_executed'])
        self.assertEqual(terminal['effective_steps'], 0)

    async def test_compound_atomic_count_and_automatic_short_flow_derivation(self):
        session, evidence, _ = self.recorded([
            decide(tool='observe', arguments={'focus_control_id': 'control-0'}),
            decide(goal='修改数量字段并查看结果', tool='act', arguments=lambda p: {
                'observation_id': p['observation']['observation_id'],
                'step': act_step('set_value', control_id='control-0', value='20')}), finish()])
        result = await session.run()
        self.assertEqual(result['effective_steps'], 3, result)
        record = session_record(evidence / 'raw')
        self.assertEqual(len(effective_trajectory(record)), 3)
        # Program derives short_flow even if an untrusted label says otherwise.
        record['terminal'].update(short_flow=False, short_flow_reason=None)
        from webcollect.postprocess import derive
        delivery = self.root / 'sample' / self.ids['sample_id']
        derived = derive(self.task, record, delivery, self.ids, self.manifest)
        self.assertEqual(derived['status'], 'derived', derived)
        annotation = load_json(delivery / 'annotation.json')
        self.assertTrue(annotation['short_flow'])
        self.assertIn('实际完成3个', annotation['short_flow_reason'])
        self.assertEqual(annotation['completion_status'], 'success')
        self.assertNotIn('opaque-protocol-private', json.dumps(annotation))
        self.assertEqual(len(annotation['steps']), 4)
        self.assertIn('ctrl+a', [step['action']['input_text'] for step in annotation['steps']])
        with self.assertRaises(FileExistsError):
            derive(self.task, record, delivery, self.ids, self.manifest)

    async def test_technical_terms_below_old_ratio_derive_without_language_approval(self):
        self.surface.state['visible_text']='中文技术说明 搜索 文档 关于\n'+('Vue TypeScript JavaScript API '*20)
        session,evidence,_=self.recorded([scroll('查看当前技术文档下方内容')]+[scroll() for _ in range(4)]+[finish()],
                                         name='technical-language')
        result=await session.run()
        self.assertEqual(result['effective_steps'],5,result)
        derived=process(evidence,self.root/'technical-derived'/self.ids['sample_id'],self.ids,self.manifest)
        self.assertEqual(derived['status'],'derived_saved',derived)
        self.assertLess(derived['minimum_chinese_character_ratio'],.7)
        self.assertTrue(derived['chinese_ratio_diagnostic_only'])
        self.assertEqual(derived['language_review'],'REVIEW_REQUIRED')

    async def test_five_actions_regular_and_zero_actions_raw_only(self):
        for count in (0, 4, 5, 11):
            session, evidence, _ = self.recorded(
                [scroll('查看页面下方内容' if i == 0 else None) for i in range(count)] + [finish()],
                name='length-' + str(count))
            result = await session.run()
            self.assertEqual(result['effective_steps'], count, result)
            record = session_record(evidence / 'raw')
            self.assertEqual(len(effective_trajectory(record)), count)
            derived = process(evidence, self.root / ('derived-' + str(count)) / self.ids['sample_id'],
                              self.ids, self.manifest)
            if count == 0:
                self.assertEqual(derived['status'], 'no_actions')
                self.assertFalse((self.root / 'derived-0').exists())
            else:
                self.assertEqual(derived['status'], 'derived_saved', derived)
                annotation = load_json(self.root / ('derived-' + str(count)) / self.ids['sample_id'] / 'annotation.json')
                self.assertEqual(annotation.get('short_flow', False), count < 5)

    async def test_native_recounts_unique_dispatch_rejects_gap_unknown_and_raw_mutation(self):
        session, evidence, _ = self.recorded([scroll('查看页面下方内容'), scroll(), finish()])
        await session.run()
        record = session_record(evidence / 'raw')
        duplicate = deepcopy(record)
        duplicate['trajectory'].append(deepcopy(duplicate['trajectory'][-1]))
        self.assertEqual(len(effective_trajectory(duplicate)), 2)
        gap = deepcopy(record)
        gap['trajectory'][1]['before_observation_id'] = gap['trajectory'][0]['before_observation_id']
        with self.assertRaises(ValueError):
            effective_trajectory(gap)
        raw_path = evidence / 'step_001.json'
        raw = load_json(raw_path)
        raw['action_executed'] = None
        raw_path.write_text(json.dumps(raw))
        with self.assertRaises(ValueError):
            effective_trajectory(record)
        image = evidence / 'raw/observation-001.png'
        image.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, '封存原件'):
            session_record(evidence / 'raw')

    async def test_unknown_never_retried(self):
        calls = []
        async def unknown(prompt):
            calls.append(prompt)
            raise OutcomeUnknown('sent request unresolved')
        session = self.session(unknown)
        result = await session.run()
        self.assertEqual(len(calls), 1)
        self.assertTrue(result['unknown'])
        self.assertEqual(self.surface.executed, [])

    async def test_no_effect_is_dispatched_fact_and_waf_remains_failure(self):
        session, evidence, _ = self.recorded([scroll('查看页面下方内容')], name='no-effect')
        with patch('webcollect.browser.execute', new=unittest.mock.AsyncMock()):
            result = await session.run()
        self.assertEqual(result['effective_steps'], 0)
        self.assertEqual(result['actual_actions'], 1)
        self.assertIn('NO_EFFECTIVE_ACTION', result['stop_summary'])
        self.assertTrue(load_json(evidence / 'step_001.json')['dispatched'])
        self.assertEqual(process(evidence, self.root / 'no-effect-delivery', self.ids, self.manifest)['status'], 'no_actions')

        session, evidence, _ = self.recorded([scroll('查看页面下方内容'), finish()], name='waf')
        original = self._fake_execute
        async def blocked(*args, **kwargs):
            await original(*args, **kwargs)
            self.surface.state.update(title='访问被阻止', visible_text='您的访问被阻止，请联系站点管理员。')
        with patch('webcollect.browser.execute', side_effect=blocked):
            await session.run()
        result = process(evidence, self.root / 'waf-delivery', self.ids, self.manifest)
        self.assertEqual(result['status'], 'terminal_failed')
        self.assertFalse((self.root / 'waf-delivery').exists())

    async def test_roundtrip_cannot_be_removed_to_join_other_actions(self):
        up = decide(tool='act', arguments=lambda p: {
            'observation_id': p['observation']['observation_id'],
            'step': act_step('scroll', direction='up', goal='查看上方内容', expected='视口上移')})
        session, evidence, _ = self.recorded([scroll('查看页面内容'), up, scroll(), finish()], name='roundtrip')
        original = self._fake_execute
        async def scroll_both(page, action_type, arguments, execution):
            if action_type == 'scroll' and arguments['direction'] == 'up':
                self.surface.executed.append((action_type, deepcopy(arguments)))
                self.surface.state['scroll'][1] -= 480
            else:
                await original(page, action_type, arguments, execution)
        with patch('webcollect.browser.execute', side_effect=scroll_both):
            result = await session.run()
        self.assertEqual(result['actual_actions'], 3)
        record = session_record(evidence / 'raw')
        with self.assertRaisesRegex(ValueError, '无效往返'):
            effective_trajectory(record)

    async def test_completed_call_id_cannot_be_reused_to_dispatch_again(self):
        first = native(scroll('查看页面下方内容'), 'same-id')
        second = native(scroll(), 'same-id')
        script = Script([first, second, native(finish(), 'finish-id')])
        session = self.session(script)
        result = await session.run()
        self.assertEqual(result['effective_steps'], 1)
        self.assertEqual(len(self.surface.executed), 1)
        self.assertEqual([message['tool_call_id'] for message in session.history if message['role'] == 'tool'],
                         ['same-id', 'finish-id'])

    async def test_new_tab_capability_failure_preserves_known_dispatch(self):
        from test_react_session import FakePage
        opening=decide(goal='查看可见入口',tool='act',arguments=lambda p:{
            'observation_id':p['observation']['observation_id'],
            'step':act_step('open_url',page_id='p1',goal='查看详情',expected='显示详情')})
        session,evidence,_=self.recorded([opening],name='new-tab')
        session.page_urls.append(self.page.url.rstrip('/')+'/detail')
        original=self._fake_execute
        async def popup(page,action_type,arguments,execution):
            await original(page,action_type,arguments,execution)
            page.context.pages.append(FakePage(self.surface))
        with patch('webcollect.browser.execute',side_effect=popup):
            result=await session.run()
        self.assertFalse(result['unknown'],result)
        self.assertEqual((result['actual_actions'],result['effective_steps']),(1,0))
        self.assertIn('TOOL_CAPABILITY_UNAVAILABLE',result['stop_summary'])
        raw=load_json(evidence/'step_001.json')
        self.assertTrue(raw['dispatched'])
        self.assertTrue(raw['action_executed'])
        self.assertEqual(len(raw['opened_pages']),1)

    async def test_navigation_back_then_another_branch_keeps_whole_trajectory(self):
        def action(name, **arguments):
            return decide(goal='查看两个分支并返回目录' if name=='open_url' else None,tool='act',
                arguments=lambda p:{'observation_id':p['observation']['observation_id'],
                    'step':act_step(name,**arguments)})
        session,evidence,_=self.recorded([action('open_url',page_id='p1'),action('back'),
            action('open_url',page_id='p2'),action('back'),finish()],name='branches')
        home=self.page.url
        for suffix in ('A','B'):
            cid='link-'+suffix
            self.surface.state['elements'].append({**self.surface.state['elements'][-1],
                'element_id':cid,'element_type':'link','native_role':'a','text':'目录分支'+suffix,'clickable':True})
            self.surface.state['capture_controls'].append({'element_id':cid,'selector':'#'+cid,'index':0,
                'tag':'a','href':home.rstrip('/')+'/'+suffix})
        result=await session.run()
        self.assertEqual(result['effective_steps'],4,result)
        record=session_record(evidence/'raw')
        self.assertEqual([row['action'] for row in effective_trajectory(record)],['open_url','back','open_url','back'])
        processed=process(evidence,self.root/'branch-delivery'/self.ids['sample_id'],self.ids,self.manifest)
        self.assertEqual(processed['status'],'derived_saved',processed)
        self.assertEqual(self.page.url,home)

    async def test_observed_navigation_enables_back_without_padding_policy(self):
        session, _, _ = self.recorded([finish()], name='navigate')
        await session._open_entry()
        session.working_goal = '查看词条内容后返回入口'
        destination = self.page.url.rstrip('/') + '/article'
        session.page_urls.append(destination)
        open_result = await session._tool_act({'observation_id': session.current['observation_id'],
            'step': act_step('open_url', page_id='p1', goal='查看词条', expected='显示词条页')})
        self.assertEqual(open_result['status'], 'ok', open_result)
        self.assertIn('back', session._compact(session.current)['page_actions'])
        back_result = await session._tool_act({'observation_id': session.current['observation_id'],
            'step': act_step('back', goal='返回入口', expected='显示入口页')})
        self.assertEqual(back_result['status'], 'ok', back_result)
        self.assertEqual(self.page.url, self.task['initial_url'])
        session.stop_reason, session.stop_summary = 'ready', '返回后结束'
        session._close()

    def test_observed_same_application_links_beyond_64_keep_their_identity(self):
        from webcollect.candidate_navigation import extend
        from webcollect.react_protocol import LEGACY_VERSION
        task = build_url_task(url=self.task['initial_url'], task_version='old-native', decision_protocol=LEGACY_VERSION)
        uri = task['initial_url']
        task['candidate_binding'] = {'candidate':{'entry_url':uri}}
        links=[uri+'?page='+str(n) for n in range(90)]
        state={'url':uri,'capture_controls':[{'href':u} for u in links+['https://outside.example/']]}
        self.assertEqual(extend(task,[uri],state),[uri,*links])
        with self.assertRaisesRegex(ValueError,'left evidence-backed application'):
            extend(task,[uri],{'url':'https://outside.example/'},{'action_type':'click'})
        old = build_url_task(url=uri, task_version='archived', decision_protocol=REACT_VERSION)
        old['candidate_binding']=task['candidate_binding']
        self.assertEqual(len(extend(old,[uri],state)),64)

    async def test_new_native_task_continues_past_former_12_and_24_rounds(self):
        def inspect(offset):
            return decide(tool='inspect',arguments=lambda p:{
                'kind':'html','observation_id':p['observation']['observation_id'],
                'offset':offset,'limit_chars':1})
        session, _, script = self.recorded([inspect(i) for i in range(25)]+[finish('no_path')])
        result = await session.run()
        self.assertEqual(result['stop_reason'],'no_path',result)
        self.assertEqual((len(script.prompts),session.used['max_queries']),(26,25))
        self.assertIsNone(script.prompts[-1]['boundary']['remaining_budgets']['max_decisions'])
        self.assertEqual(session.used['max_model_calls'],0)
        repeated, _, history = self.recorded([inspect(0) for _ in range(8)]+[finish('no_path')],'repeat')
        result = await repeated.run()
        self.assertEqual(result['stop_reason'],'no_path',result)
        self.assertEqual(len(history.prompts),9)
        self.task = build_url_task(url=self.page.url, task_version='frozen', budgets={'max_no_progress':5})
        frozen, _, _ = self.recorded([inspect(0) for _ in range(7)],'frozen-repeat')
        self.assertIn('无进展',(await frozen.run())['stop_summary'])

    async def test_lower_frozen_decision_budget_and_legacy_budget(self):
        self.assertEqual(self.task['fragment']['glm_http_call_limit'],25)
        self.assertEqual(self.task['workflow_proposal']['spec']['glm_http_call_limit'],25)
        self.assertTrue(all(limit is None for limit in GOAL_BUDGETS.values()))
        self.task = build_url_task(url=self.page.url, task_version='low', budgets={'max_decisions': 1})
        session, evidence, script = self.recorded([scroll('查看页面下方内容'), finish()])
        result = await session.run()
        self.assertEqual(result['stop_reason'], 'budget')
        self.assertEqual(len(script.prompts), 1)
        self.assertEqual(load_json(evidence / 'raw/terminal.json')['used']['max_decisions'], 1)
        old = build_url_task(url=self.page.url, task_version='old', decision_protocol=REACT_VERSION)
        self.assertEqual(old['fragment']['budgets'], LEGACY_BUDGETS)
        self.assertNotIn('decision_protocol', old['fragment'])
        validate_task(old)

    async def test_real_chooser_interface_synthetic_wire_history_and_settled_original_cache(self):
        from webcollect.batch_core import BatchLedger
        from webcollect.model_gateway import ModelGateway
        config = load_json(__import__('pathlib').Path(__file__).resolve().parents[1] / 'config/batch-synthetic.json')
        ledger = BatchLedger(self.root / 'wire.sqlite3', config, initialize=True)
        choose = react_chooser(ledger, self.task, 'attempt-wire')
        builds = [scroll('查看页面下方内容'), finish()]
        calls = []
        original = ModelGateway.call_tool

        def controlled(gateway, job, purpose, text, tools, **kwargs):
            self.assertEqual(kwargs['system'], SYSTEM)
            self.assertEqual(kwargs['reasoning_effort'], 'max')
            self.assertIsNone(kwargs['max_requests'])
            self.assertEqual({tool['function']['name'] for tool in tools}, {'observe', 'inspect', 'act', 'finish'})
            payload = json.loads(text)
            self.assertNotIn('system', payload)
            self.assertNotIn('_history', payload)
            self.assertNotIn('tools', payload)
            index = len(calls)
            calls.append(deepcopy(kwargs))
            assistant = native(builds[index], 'wire-' + str(index))(payload)['assistant_message']
            return original(gateway, job, purpose, text, tools, synthetic_response=assistant, **kwargs)

        evidence = self.root / 'wire/evidence' / self.ids['sample_id']
        session = ReactSession(self.task, evidence / 'raw', choose, self.page, steps_directory=evidence)
        with patch.object(ModelGateway, 'call_tool', new=controlled):
            result = await session.run()
        self.assertEqual(result['effective_steps'], 1, result)
        self.assertEqual(len(calls), 2)
        self.assertEqual([m['role'] for m in calls[1]['history']], ['assistant', 'tool'])
        self.assertEqual(calls[1]['history'][0]['reasoning_content'], 'opaque-protocol-private')
        self.assertEqual(len(calls[1]['images']), 1)
        self.assertEqual(choose.requests_used(), 0)  # synthetic responses are not HTTP
        with ledger.connect() as con:
            self.assertEqual(con.execute('SELECT count(*) FROM model_requests').fetchone()[0], 2)
        # Exact original prompt/cache replay does not claim or issue a new request.
        replay = session._prompt()
        replay['progress']['decisions_used'] = 0
        replay['_history'] = []
        # Build a separate explicit settled original identity and replay it.
        replay_chooser = react_chooser(ledger, self.task, 'attempt-replay')
        calls.clear()
        with patch.object(ModelGateway, 'call_tool', new=controlled):
            first = await replay_chooser(replay)
            second = await replay_chooser(replay)
        self.assertEqual(first, second)
        self.assertEqual(len(calls), 1)

    async def test_one_short_sample_can_queue_independent_review_without_formal_release(self):
        from pathlib import Path
        from webcollect.batch_core import BatchLedger
        from quality_inspector.ai_worker import prepare
        from quality_inspector.delivery_scope import verify_delivery_scope
        session, evidence, _ = self.recorded([scroll('查看页面下方内容'), finish()], name='single-qc')
        await session.run()
        dataset = self.root / 'single-candidate'
        result = process(evidence, dataset / 'samples' / self.ids['sample_id'], self.ids, self.manifest)
        self.assertEqual(result['status'], 'derived_saved')
        config = load_json(Path(__file__).resolve().parents[1] / 'config/batch-synthetic.json')
        ledger = BatchLedger(self.root / 'qc-only.sqlite3', config, initialize=True)
        queue = prepare(ledger, dataset, self.root / 'qc-output', sample_ids=[self.ids['sample_id']])
        self.assertEqual(queue['queued_samples'], 1, queue)
        self.assertEqual(queue['model_requests'], 0)
        prepared = load_json(queue['queue_file'])
        self.assertEqual(len(prepared['jobs']), 1)
        self.assertTrue(prepared['batch_errors'])  # missing formal package files stay explicit
        with self.assertRaisesRegex(ValueError, 'Explicit effective-set'):
            verify_delivery_scope(None, None, dataset=dataset)


class NativePureContractTests(unittest.TestCase):
    def test_v2_goals_only_frozen_goal_and_v1_identity_preserved(self):
        for kind, goal in [('entry', None), ('target', {'kind': '查询', 'entity': '图书', 'parameters': {'书名': '三国'}})]:
            candidate = {'schema_version': 'webcollect-data-candidate-2', 'candidate_kind': kind,
                         'requested_goal': goal, 'entry_url': 'https://example.org'}
            task = {'candidate_binding': {'candidate': candidate}}
            self.assertEqual(struct_goal(task), goal)
            if goal:
                struct_goal(task)['entity'] = 'changed'
                self.assertEqual(candidate['requested_goal']['entity'], '图书')
        v1 = {'schema_version': 'webcollect-data-candidate-1', 'description': '旧目标'}
        self.assertEqual(struct_goal({'candidate_binding': {'candidate': v1}}), v1)

    def test_atomic_effect_excludes_pixels_wait_complete_and_unrelated_values(self):
        state = {'url': 'u', 'scroll': [0, 0], 'visible_text': '中文', 'elements': [],
                 'values': [{'element_id': 'a', 'value': '1', 'focused': True},
                            {'element_id': 'b', 'value': '1'}]}
        after = deepcopy(state)
        after['values'][1]['value'] = '2'
        for action in ('type', 'wait', 'complete', 'observe', 'inspect'):
            self.assertFalse(atomic_effect(state, after, action, {}, 'a')['verified'])
        after = deepcopy(state)
        after['values'][0].update(selection_start=0, selection_end=1)
        self.assertTrue(atomic_effect(state, after, 'hotkey', {'keys': ['meta', 'a']}, 'a')['verified'])
        after = deepcopy(state)
        after['scroll'] = [0, -5]
        self.assertFalse(atomic_effect(state, after, 'scroll', {'direction': 'down'})['verified'])

    def test_waf_and_stopped_terminal_not_success_and_exception_requires_policy(self):
        task = build_url_task(url='https://example.org', task_version='v')
        record = {'terminal': {'stop_reason': 'ready', 'stop_summary': '模型声称完成'}}
        state = {'visible_text': '您的访问被阻止', 'elements': [], 'title': '访问被阻止'}
        status, description = terminal_outcome(task, record, state)
        self.assertEqual(status, 'failed')
        self.assertIn('访问被阻止', description)
        article = {'title':'帮助中心', 'visible_text':'常见问题\n这篇文章解释验证码和安全验证的使用。', 'elements':[]}
        self.assertEqual(terminal_outcome(task, record, article)[0], 'success')
        task['fragment']['allow_controlled_exception'] = True
        self.assertEqual(terminal_outcome(task, record, state)[0], 'controlled_exception')
        with self.assertRaises(ValueError):
            validate_task(task)  # flag cannot bypass frozen caller policy
        task = build_url_task(url='https://example.org', task_version='v', allow_controlled_exception=True)
        self.assertEqual(terminal_outcome(task, record, state)[0], 'controlled_exception')
        record['terminal']['unknown'] = True
        self.assertEqual(terminal_outcome(task, record, state)[0], 'failed')


if __name__ == '__main__':
    unittest.main()
