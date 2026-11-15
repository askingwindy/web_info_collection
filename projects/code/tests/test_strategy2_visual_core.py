"""Three offline core contracts for strategy 2; no model or real browser."""
import asyncio
from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from webcollect.batch_core import file_sha
from webcollect.screenshot_effect import atomic_effect, step_expectation, input_changes
from webcollect.screenshot_execution import (bind_plan_targets, bind_target, compile_step,
                                             resolve_control, react_step)
from webcollect.screenshot_native_observation import action_availability
from webcollect.screenshot_observation import (body_element_ids, controls_projection, crop_visual,
                                               interaction_affordances, prepare_visuals,
                                               verify_visuals)


def control(cid='input1', selector='#amount'):
    return {'element': {'element_id': cid, 'native_role': 'input', 'text': '',
                        'visible': True, 'enabled': True, 'inputable': True,
                        'clickable': True, 'bbox': [20, 30, 120, 55]},
            'binding': {'element_id': cid, 'selector': selector, 'index': 0, 'tag': 'input'},
            'readable_labels': [{'kind': 'rendered_associated_label', 'text': '金额'}],
            'value': {'element_id': cid, 'value': '', 'value_visible': True, 'readonly': False, 'input_type': 'text'},
            'actions': {}}


def observation():
    return {'observation_id': 'observation-current', 'document_identity': 'doc-current',
            'viewport': [200, 100], 'controls': {'input1': control(),
                                               'hidden': control('hidden', '#hidden')}}


def node(element_id, role, text, parent, *, clickable=True, top=0):
    return {'element_id': element_id, 'native_role': role, 'element_type': 'link', 'text': text,
            'parent_id': parent, 'visible': True, 'enabled': True, 'clickable': clickable,
            'inputable': False, 'scrollable': False, 'state': 'default',
            'bbox': [10, top, 120, top + 20]}


def reading_observation(root):
    """One long-reading frame: article links, navigation links, passive wrappers.

    The navigation sits inside `main`, so only the nearest role can decide it.
    """
    tree = [node('root', 'body', '', None, clickable=False),
            node('main-1', 'main', '', 'root', clickable=False),
            node('nav-1', 'nav', '', 'main-1', clickable=False, top=20),
            node('link-body', 'a', '月球', 'main-1', top=40),
            node('wrapper-1', 'div', '容器', 'main-1', clickable=False, top=60),
            node('link-chrome', 'a', '登录', 'nav-1', top=80)]
    state = {'url': 'https://example.test/article', 'elements': tree,
             'visible_text': '月球 容器 登录', 'screen_resolution': [200, 100]}
    path = root / 'state.json'
    path.write_text(json.dumps(state), encoding='utf-8')
    controls = {row['element_id']: {'element': row, 'readable_labels': [], 'value': {}, 'actions': {},
                                    'binding': {'element_id': row['element_id'], 'tag': row['native_role'],
                                                'selector': f'#{row["element_id"]}'}}
                for row in tree if row['native_role'] in ('a', 'div')}
    return state, {'observation_id': 'observation-reading', 'document_identity': 'doc-reading',
                   'viewport': [200, 100], 'controls': controls,
                   'evidence': {'state': {'path': str(path), 'sha256': file_sha(path)}}}


def png(width, height):
    stream = BytesIO()
    Image.new('RGB', (width, height), 'white').save(stream, format='PNG')
    return stream.getvalue()


class VisualPage:
    """Only native read APIs used by overview capture; actions are absent."""
    def __init__(self, state):
        self.state = deepcopy(state)
        self.full_page_requests = 0

    async def evaluate(self, script, options=None):
        if script.startswith('() => [Math.max'):
            return [200, 4000]
        return deepcopy(self.state)

    async def screenshot(self, **kwargs):
        if kwargs.get('full_page') is not True:
            raise AssertionError('Overview must request real full-page pixels')
        self.full_page_requests += 1
        return png(200, 4000)


class Strategy2VisualCore(unittest.TestCase):
    def test_plan_target_provenance_rebind_and_wrong_object_refusal(self):
        from types import SimpleNamespace
        from webcollect.screenshot_plan import screenshot_chooser
        profile_ledger = SimpleNamespace(real_glm=False, config={'model': {'max_images': 2, 'reasoning_effort': 'low'}})
        profile_task = {'fragment': {'decision_protocol': 'conditional-plan',
            'reasoning_effort_profile': {'first_plan': 'high', 'branch': 'max'}}}
        chooser = screenshot_chooser(profile_ledger, profile_task, 'profile-offline')
        self.assertEqual((chooser.first_plan_reasoning_effort, chooser.branch_reasoning_effort), ('high', 'max'))
        # A native form popup is earned by its frozen form, trusted default
        # submit event, exact opener and actual first navigation request.
        from webcollect.plan_evidence import validate_native_form_popup
        from webcollect.plan_evidence import finish_native_form, close_native_form
        from unittest.mock import AsyncMock
        # A submit's inner evidence finalizer and outer action cleanup own the
        # same listener. Real Playwright rejects a second handler removal.
        other_listener = lambda request: None
        class ListenerContext:
            def __init__(self, listener):self.listeners = {listener, other_listener}
            def remove_listener(self, event, listener):
                self.assert_event = event
                self.listeners.remove(listener)
        listener = lambda request: None
        context = ListenerContext(listener)
        watcher = {'context':context,'listener':listener,'listener_active':True,
                   'intent':{'method':'post'},'request_log':[{'method':'POST'}]}
        origin_form = SimpleNamespace(evaluate=AsyncMock(return_value=[]))
        submit = asyncio.run(finish_native_form(origin_form, watcher))
        close_native_form(watcher)
        self.assertEqual(submit['document_requests'], [{'method':'POST'}])
        self.assertEqual(context.listeners, {other_listener})
        self.assertEqual(context.assert_event, 'request')
        form = {'form_selector':'form','submitter_selector':'input[type=submit]',
                'action':'https://example.org/search','method':'get',
                'target':'_blank','enctype':'application/x-www-form-urlencoded','fields':[['q','正文']]}
        state = {'url':'https://example.org/form','document_identity':'form-doc',
                 'capture_controls':[{'element_id':'submit','selector':'input[type=submit]',
                    'tag':'input','input_type':'submit','form_submission':form}]}
        operation = {'action_type':'click','evidence':{'anchor_element_id':'submit'}}
        landed = 'https://example.org/search?q=%E6%AD%A3%E6%96%87'
        proof = {'form_intent':form,'source_url':state['url'],'source_document':'form-doc','source_node':'submit',
                 'submit_events':[{'trusted':True,'default_prevented':False,'form_selector':'form',
                    'submitter_selector':'input[type=submit]','source_url':state['url'],'source_document':'form-doc'}],
                 'opener':{'url':state['url'],'document_identity':'form-doc'},'landed_url':landed,
                 'initial_request_count':1,'initial_request':{'url':landed,'method':'GET','redirected':False,'post_data':None}}
        self.assertTrue(validate_native_form_popup(proof,operation,state,landed))
        wrong = deepcopy(proof);wrong['initial_request']['url']='https://example.org/other'
        with self.assertRaisesRegex(ValueError,'REQUEST_UNPROVEN'):
            validate_native_form_popup(wrong,operation,state,landed)
        wrong = deepcopy(proof);wrong['opener']['document_identity']='other-document'
        with self.assertRaisesRegex(ValueError,'SOURCE_UNPROVEN'):
            validate_native_form_popup(wrong,operation,state,landed)
        wrong = deepcopy(proof);wrong['submit_events'][0]['default_prevented']=True
        with self.assertRaisesRegex(ValueError,'NATIVE_SUBMIT_UNPROVEN'):
            validate_native_form_popup(wrong,operation,state,landed)
        # Explicit child IDs and semantic target binding share the same native
        # carrier, while the actual click target stays the observed child.
        from webcollect.screenshot_execution import navigation_carrier
        from webcollect.plan_evidence import verify_popup
        linked={'url':'https://example.org/list','document_identity':'list-doc',
            'elements':[{'element_id':'link','native_role':'a','visible':True,'clickable':True},
                {'element_id':'heading','native_role':'h3','visible':True,'clickable':True,'parent_id':'link'}],
            'capture_controls':[{'element_id':'link','tag':'a','selector':'a','href':'https://example.org/article','target':'_blank'},
                {'element_id':'heading','tag':'h3','selector':'a > h3','href':None}]}
        self.assertEqual(navigation_carrier(linked,'heading')['link_node'],'link')
        origin=object()
        class Opened:
            url='https://example.org/article'
            async def opener(self):return origin
            async def wait_for_load_state(self,*args,**kwargs):pass
        click={'action_type':'click','evidence':{'anchor_element_id':'heading'}}
        earned=asyncio.run(verify_popup(origin,Opened(),click,linked))
        self.assertEqual(earned['source_node'],'heading')
        self.assertEqual(earned['link_carrier']['link_node'],'link')
        self.assertEqual(click['evidence']['anchor_element_id'],'heading')
        aria_link=deepcopy(linked);aria_link['elements'][0]['native_role']='button'
        self.assertEqual(navigation_carrier(aria_link,'heading')['link_node'],'link')
        direct={'action_type':'click','evidence':{'anchor_element_id':'link'}}
        self.assertEqual(asyncio.run(verify_popup(origin,Opened(),direct,aria_link))['clicked_href'],Opened.url)
        wrong_opened=Opened();wrong_opened.url='https://example.org/other'
        with self.assertRaisesRegex(ValueError,'POPUP_LANDING_UNPROVEN'):
            asyncio.run(verify_popup(origin,wrong_opened,click,linked))
        from webcollect.screenshot_plan import first_plan_admission, normalize_submit_plan
        admit = first_plan_admission
        def first_plan_admission(plan):
            fixture = deepcopy(plan)
            fixture.pop('final_presentation_step', None)
            for row in fixture.get('requirements', []):
                if 'acceptance' in row:
                    row['acceptance']['source_quote'] = fixture['goal']
            return admit(fixture)
        from webcollect.screenshot_plan import register_evidence_schema
        from jsonschema import Draft202012Validator
        local = Draft202012Validator(register_evidence_schema({'frame'}))
        self.assertTrue(local.is_valid({'status': 'insufficient', 'reason': '对象不符', 'answers': []}))
        for forbidden in ('decision', 'remaining_plan', 'complete', 'give_up'):
            self.assertFalse(local.is_valid({'status': 'registered', 'reason': '引用登记', 'answers': [], forbidden: True}))
        route_plan = {'goal': '读取结果并根据页面依据核对',
            'requirements': [
                {'id': 'result', 'kind': 'result', 'description': '读取业务结果', 'evidence_scope': 'current',
                 'evidence_route': {'source_type': 'page_result', 'observation_steps': [3]}, 'acceptance': {'mode': 'presence', 'subject': '读取业务结果', 'source_quote': '读取业务结果'}},
                {'id': 'check', 'kind': 'content', 'description': '核对结果', 'evidence_scope': 'current',
                 'evidence_route': {'source_type': 'derived_check', 'observation_steps': [4], 'depends_on': ['result']}, 'acceptance': {'mode': 'presence', 'subject': '核对结果', 'source_quote': '核对结果'}}],
            'final_presentation_step': 5,
            'steps': [{'action': 'scroll', 'direction': 'down', 'purpose': '读取必要依据',
                       'rationale': '计划前提：需要读取目标依据', 'expected_result': '必要依据进入视口'} for _ in range(5)]}
        normalized, _ = normalize_submit_plan(route_plan)
        self.assertNotIn('source_type', normalized['requirements'][0]['evidence_route'])
        from webcollect.collection_contract import compile_contract
        unsuitable, _ = compile_contract({'unsuitable': {'reason': '自然业务路径不足五步'}})
        self.assertEqual(first_plan_admission(unsuitable)[1]['kind'], 'unsuitable')
        compiled, _ = compile_contract(normalized)
        self.assertEqual(compiled['requirements'][1]['evidence_route']['source_type'], 'page_content')
        self.assertTrue(first_plan_admission(compiled)[0])
        for goal, source, allowed in [('阅读全文并查看作者', '阅读', False),
                                      ('使用全文检索查陈树人', '全文检索', True),
                                      ('取得全部指定的标题和日期', '标题和日期', True)]:
            case = deepcopy(compiled)
            case['goal'] = goal
            case['requirements'] = [{'id': 'scope', 'kind': 'content', 'description': source,
                'acceptance': {'mode': 'presence', 'subject': source, 'source_quote': source},
                'evidence_route': {'source_type': 'page_content'}}]
            self.assertEqual(first_plan_admission(case)[0], allowed)
        process_plan = deepcopy(compiled)
        process_plan['goal'] = '通过搜索陈树人阅读文章'
        process_plan['requirements'][0].update(business_role='process', description='搜索陈树人结果',
            acceptance={'mode': 'presence', 'subject': '陈树人', 'source_quote': '搜索陈树人'})
        process_plan['requirements'][1]['acceptance']['source_quote'] = '阅读文章'
        self.assertTrue(admit(process_plan)[0])
        process_plan['requirements'][0]['description'] = '比较陈树人与其他人物结果'
        self.assertEqual(admit(process_plan)[1]['kind'], 'BUSINESS_ROLE_CONFLICT')
        process_plan['requirements'][0]['description'] = '搜索另一人物结果'
        process_plan['requirements'][0]['acceptance']['subject'] = '另一人物'
        self.assertEqual(admit(process_plan)[1]['kind'], 'BUSINESS_ROLE_CONFLICT')
        process_plan['requirements'] = [process_plan['requirements'][0]]
        process_plan['requirements'][0]['description'] = '搜索陈树人结果'
        process_plan['requirements'][0]['acceptance']['subject'] = '陈树人'
        self.assertEqual(admit(process_plan)[1]['kind'], 'OUTCOME_REQUIREMENT_MISSING')
        explicit_derivation = deepcopy(route_plan)
        explicit_derivation['goal'] = '读取结果并根据页面依据独立验算'
        self.assertTrue(first_plan_admission(explicit_derivation)[0])
        from webcollect.screenshot_plan import result_requirements_feedback
        self.assertIsNone(result_requirements_feedback([], '页面输出的 Band F 年度与月度市政税账单'))
        self.assertIsNone(result_requirements_feedback([], '读取页面计算输出的租房与买房总成本对比及更省的结论'))
        reading = deepcopy(route_plan)
        reading['goal'] = '阅读煎蛋卷条目，查看第1条引用来源及后续章节内容'
        reading['requirements'] = [{'id': 'reading', 'kind': 'content',
            'description': '阅读引用来源及后续章节', 'evidence_scope': 'current',
            'evidence_route': {'source_type': 'page_content', 'observation_steps': [3]}, 'acceptance': {'mode': 'presence', 'subject': '阅读引用来源及后续章节', 'source_quote': '阅读引用来源及后续章节'}}]
        self.assertTrue(first_plan_admission(reading)[0])
        compound = deepcopy(route_plan)
        compound['goal'] = '随后查看页面计算输出的月供、总利息与总成本结果'
        compound['requirements'] = [
            {'id': 'r1', 'kind': 'result', 'description': '页面输出的月供结果', 'evidence_scope': 'current',
             'evidence_route': {'source_type': 'page_result', 'observation_steps': [3]}, 'acceptance': {'mode': 'presence', 'subject': '页面输出的月供结果', 'source_quote': '页面输出的月供结果'}},
            {'id': 'r2', 'kind': 'result', 'description': '页面输出的总利息与总成本结果', 'evidence_scope': 'current',
             'evidence_route': {'source_type': 'page_result', 'observation_steps': [3]}, 'acceptance': {'mode': 'presence', 'subject': '页面输出的总利息与总成本结果', 'source_quote': '页面输出的总利息与总成本结果'}}]
        rejected = first_plan_admission(compound)[1]
        self.assertEqual(rejected['kind'], 'RESULT_REQUIREMENT_ATOMICITY')
        self.assertEqual(rejected['requirement_ids'], ['r2'])
        compound['requirements'][1:] = [
            {'id': 'r2', 'kind': 'result', 'description': '页面输出的总利息结果', 'evidence_scope': 'current',
             'evidence_route': {'source_type': 'page_result', 'observation_steps': [3]}, 'acceptance': {'mode': 'presence', 'subject': '页面输出的总利息结果', 'source_quote': '页面输出的总利息结果'}},
            {'id': 'r3', 'kind': 'result', 'description': '页面输出的总成本结果', 'evidence_scope': 'current',
             'evidence_route': {'source_type': 'page_result', 'observation_steps': [3]}, 'acceptance': {'mode': 'presence', 'subject': '页面输出的总成本结果', 'source_quote': '页面输出的总成本结果'}}]
        self.assertTrue(first_plan_admission(compound)[0])
        missing = deepcopy(compound)
        missing['requirements'].pop()
        self.assertEqual(first_plan_admission(missing)[1]['missing_result_terms'], ['总成本'])
        single_metric = deepcopy(route_plan)
        single_metric['goal'] = '查看收入与支出比结果'
        single_metric['requirements'] = single_metric['requirements'][:1]
        single_metric['requirements'][0]['description'] = '查看收入与支出比结果'
        self.assertTrue(first_plan_admission(single_metric)[0])
        dual = deepcopy(single_metric)
        dual['goal'] = '随后查看页面计算输出的单利利息与到期总额结果'
        dual['requirements'][0]['description'] = '页面输出的单利利息与到期总额结果'
        self.assertEqual(first_plan_admission(dual)[1]['kind'], 'RESULT_REQUIREMENT_ATOMICITY')
        dual['requirements'] = [
            {'id': 'r1', 'kind': 'result', 'description': '页面输出的单利利息结果', 'evidence_scope': 'current',
             'evidence_route': {'source_type': 'page_result', 'observation_steps': [3]}, 'acceptance': {'mode': 'presence', 'subject': '页面输出的单利利息结果', 'source_quote': '页面输出的单利利息结果'}},
            {'id': 'r2', 'kind': 'result', 'description': '页面输出的到期总额结果', 'evidence_scope': 'current',
             'evidence_route': {'source_type': 'page_result', 'observation_steps': [3]}, 'acceptance': {'mode': 'presence', 'subject': '页面输出的到期总额结果', 'source_quote': '页面输出的到期总额结果'}}]
        self.assertTrue(first_plan_admission(dual)[0])
        misplaced = deepcopy(dual)
        for requirement in misplaced['requirements']:
            requirement['source_type'] = requirement['evidence_route'].pop('source_type')
        normalized, transforms = normalize_submit_plan(misplaced)
        self.assertTrue(all('source_type' not in row for row in normalized['requirements']))
        compiled, _ = compile_contract(normalized)
        self.assertEqual([row['evidence_route']['source_type'] for row in compiled['requirements']],
                         ['page_result', 'page_result'])
        misplaced_input = {'requirements': [{'kind': 'input', 'target': {
            'control': 'input1', 'expected_value': '42'}, 'expected_value': '42'}]}
        normalized_input, _ = normalize_submit_plan(misplaced_input)
        self.assertEqual(normalized_input['requirements'][0]['target'], {'control': 'input1'})
        misplaced_input['requirements'][0]['target']['expected_value'] = '43'
        conflicting, _ = normalize_submit_plan(misplaced_input)
        self.assertEqual(conflicting['requirements'][0]['target']['expected_value'], '43')
        invalid_route = deepcopy(explicit_derivation)
        invalid_route['requirements'][1]['evidence_route']['observation_steps'] = [6]
        self.assertTrue(first_plan_admission(invalid_route)[0])  # Future observation indexes no longer freeze business.
        invalid_route['requirements'][1]['evidence_route']['observation_steps'] = [4]
        invalid_route['requirements'][1]['evidence_route']['depends_on'] = ['unknown']
        self.assertFalse(first_plan_admission(invalid_route)[0])
        invalid_route = deepcopy(route_plan)
        # evidence_route已可整体省略（宿主编译生成）；必填字段evidence_scope
        # 缺失仍是wire schema错误。
        invalid_route['requirements'][0].pop('acceptance')
        self.assertEqual(first_plan_admission(invalid_route)[1]['kind'], 'PLAN_FIELDS_INVALID')
        original = observation()
        original['provided_control_ids'] = ['input1']
        rows = controls_projection(original, ['click', 'type'])
        numeric = {'steps': [{'action': 'click', 'target': {'control': str(rows[0]['number'])}}]}
        bind_plan_targets(numeric, original)
        self.assertEqual(numeric['steps'][0]['target']['control'], rows[0]['control'])
        self.assertEqual(numeric['steps'][0]['target']['_source']['mark_number'], 1)
        node_alias = {'requirements': [{'kind': 'input', 'target': {'node': '当前计算器的金额输入框', 'role': 'textbox'}}]}
        alias_notes = []
        unique_frame = deepcopy(original)
        unique_frame['provided_control_ids'] = ['input1']
        bind_plan_targets(node_alias, unique_frame, normalization=alias_notes)
        self.assertEqual(node_alias['requirements'][0]['target']['control'], 'input1')
        self.assertEqual(alias_notes[0]['transform'], 'unique_current_control_alias')
        ambiguous = deepcopy(original)
        ambiguous['provided_control_ids'].append('hidden')
        with self.assertRaisesRegex(ValueError, 'TARGET_NODE_NOT_UNIQUELY_BOUND'):
            bind_plan_targets({'steps': [{'target': {'node': '金额输入框'}}]}, ambiguous)
        conflict = deepcopy(original)
        conflict['controls']['1'] = control('1')
        conflict['provided_control_ids'].append('1')
        with self.assertRaisesRegex(ValueError, 'CONTROL_NUMBER_CONFLICT'):
            bind_plan_targets({'steps': [{'target': {'control': '1'}}]}, conflict)
        with self.assertRaisesRegex(ValueError, 'CONTROL_TARGET_CONFLICT'):
            bind_plan_targets({'steps': [{'target': {'control': '1', 'text': '错误金额'}}]}, original)
        original['provided_control_ids'] = ['input1']
        plan = {'steps': [{'action': 'click', 'target': {'control': 'input1'}}]}
        bind_plan_targets(plan, original)
        target = plan['steps'][0]['target']
        self.assertEqual(resolve_control(original, target), ['input1'])
        with self.assertRaisesRegex(ValueError, 'CONTROL_NOT_PROVIDED'):
            bind_plan_targets({'steps': [{'target': {'control': 'hidden'}}]}, original)
        drifted = deepcopy(original)
        drifted['controls']['input1']['binding']['selector'] = '#other'
        self.assertEqual(resolve_control(drifted, target), [])
        rerendered = deepcopy(original)
        rerendered['controls'] = {'new-input': control('new-input')}
        self.assertEqual(resolve_control(rerendered, target), ['new-input'])
        rerendered['controls']['duplicate'] = control('duplicate')
        self.assertEqual(resolve_control(rerendered, target), [])
        rerendered['document_identity'] = 'new-document'
        self.assertEqual(resolve_control(rerendered, target), [])
        future_route = {'steps': [{'action': 'open_url', 'page_id': 'p0'},
                                  {'action': 'click', 'target': {'text': '详情页章节', 'role': 'link'}}]}
        bind_plan_targets(future_route, original)
        self.assertEqual(future_route['steps'][1]['target'], {'text': '详情页章节', 'role': 'link'})
        with self.assertRaisesRegex(ValueError, 'FUTURE_TARGET_REQUIRES_SEMANTICS'):
            bind_plan_targets({'steps': [{'action': 'back'},
                {'action': 'click', 'target': {'control': 'input1'}}]}, original)

        with tempfile.TemporaryDirectory() as temporary:
            state, reading = reading_observation(Path(temporary))
            body_ids = body_element_ids(state)
            self.assertEqual({'link-body', 'wrapper-1'}, body_ids & {'link-body', 'wrapper-1', 'link-chrome'})
            rows = controls_projection(reading, ['click', 'scroll'], body_ids=body_ids)
            # The passive wrapper is never dispatchable and the article link must
            # outrank the navigation link, or a long page projects only chrome.
            self.assertEqual([row['control'] for row in rows], ['link-body', 'link-chrome'])
            self.assertEqual([row['number'] for row in rows], [1, 2])
            affordances = interaction_affordances(rows, body_ids)
            self.assertEqual(affordances['kinds'], ['body_link', 'chrome_link'])
            self.assertEqual(affordances['groups'][0]['examples'], ['月球'])
            self.assertIn('input', affordances['not_observed_kinds'])
            self.assertNotIn('body_link', affordances['not_observed_kinds'])
            self.assertIn('未观察到', affordances['scope'])
            self.assertEqual(affordances['dispatch_status_source'].split('；')[0], 'controls.action_states')
            from webcollect.screenshot_session import ScreenshotPlanSession
            from types import SimpleNamespace
            session = ScreenshotPlanSession.__new__(ScreenshotPlanSession)
            session.choose = SimpleNamespace(max_images=1)
            session._allowed_actions = lambda: ['click', 'scroll']
            capabilities = session._tool_capabilities()
            self.assertFalse(capabilities['inspect'])
            self.assertFalse(capabilities['historical_image_with_current'])
            self.assertEqual(capabilities['supported_actions'], ['click', 'scroll'])
            self.assertIn('file_upload', capabilities['unsupported'])
            self.assertEqual(controls_projection(reading, ['click', 'scroll'], limit=1)[0]['control'],
                             'link-body')
            # A region-only scroll target legally declares no text; absence is no
            # constraint, and used to raise KeyError instead of binding.
            self.assertEqual(bind_target(reading, {'role': 'a'}), ['link-body', 'link-chrome'])

    def test_visual_overview_crop_preserves_original_and_bound_sources(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            obs = observation()
            # Both controls occupy the same edge position: number badges must
            # find separate visible anchors while preserving target numbering.
            obs['controls']['hidden']['element']['bbox'] = [20, 30, 120, 55]
            state = {'url': 'https://example.test/form', 'document_identity': obs['document_identity'],
                     'scroll': [0, 0], 'elements': [row['element'] for row in obs['controls'].values()],
                     'values': [], 'visible_text': '金额'}
            original = root / 'original.png'
            original.write_bytes(png(200, 100))
            state_path = root / 'original.json'
            state_path.write_text(json.dumps(state), encoding='utf-8')
            obs['evidence'] = {'image': {'path': str(original), 'sha256': file_sha(original)},
                               'state': {'path': str(state_path), 'sha256': file_sha(state_path)}}
            original_bytes = original.read_bytes()
            controls_projection(obs, ['click', 'type'])
            page = VisualPage(state)
            visuals = asyncio.run(prepare_visuals(obs, root, page, first=True))
            overview, viewport = visuals
            self.assertEqual(page.full_page_requests, 1)
            self.assertEqual(viewport['control_mapping'][0]['control'], 'input1')
            badges = [row['badge'] for row in viewport['control_mapping']]
            self.assertEqual(len(badges), 2)
            from webcollect.dynamic_regions import overlap
            self.assertFalse(overlap(*badges))
            self.assertTrue(all(0 <= x1 < x2 <= 200 and 0 <= y1 < y2 <= 100
                                for x1, y1, x2, y2 in badges))
            self.assertNotEqual(Path(viewport['path']).read_bytes(), original_bytes)
            self.assertLess(overview['scale'], 1)
            crop = crop_visual(obs, root, [0, 100, 180, 300], image_ref=overview['ref'])
            self.assertEqual(crop_visual(obs, root, [0, 100, 180, 300], image_ref=overview['ref']), crop)
            # The same sealed source metadata is sufficient when the overview
            # itself is omitted to keep the actual model request within its cap.
            self.assertEqual(verify_visuals(obs, [viewport, crop]), [viewport['path'], crop['path']])
            self.assertEqual(original.read_bytes(), original_bytes)
            # A timed-out optional overview retains the unchanged synchronized
            # viewport; it supplies no fabricated whole-page evidence.
            failed_obs = deepcopy(obs)
            failed_obs.pop('visual_evidence', None)
            failure_root = root / 'overview-timeout'
            failure_root.mkdir()
            from playwright.async_api import TimeoutError as ScreenshotTimeoutError
            from unittest.mock import AsyncMock, patch
            with patch.object(page, 'screenshot', new=AsyncMock(side_effect=ScreenshotTimeoutError('waiting for fonts to load'))):
                fallback = asyncio.run(prepare_visuals(failed_obs, failure_root, page, first=True))
            self.assertEqual(len(fallback), 1)
            self.assertEqual(fallback[0]['scope'], 'viewport')
            self.assertEqual(fallback[0]['overview_unavailable']['reason'], 'screenshot_timeout')
            self.assertEqual(fallback[0]['source'], obs['evidence']['image'])
            # All four optional read stages share timeout-only fallback.
            for stage in ('before_observe', 'dimensions', 'after_observe'):
                stage_obs = deepcopy(obs)
                stage_obs.pop('visual_evidence', None)
                stage_root = root / stage
                stage_root.mkdir()
                if stage == 'dimensions':
                    async def dimensions_timeout(script, options=None):
                        if script.startswith('() => [Math.max'):
                            raise TimeoutError('dimension deadline')
                        return deepcopy(state)
                    boundary = patch.object(page, 'evaluate', side_effect=dimensions_timeout)
                else:
                    boundary = patch('webcollect.browser.observe', new=AsyncMock(
                        side_effect=[TimeoutError('before deadline')] if stage == 'before_observe'
                        else [deepcopy(state), ScreenshotTimeoutError('after deadline')]))
                with boundary:
                    stage_visuals = asyncio.run(prepare_visuals(stage_obs, stage_root, page, first=True))
                self.assertEqual(len(stage_visuals), 1)
                self.assertEqual(stage_visuals[0]['overview_unavailable']['reason'], stage + '_timeout')
                self.assertEqual(stage_visuals[0]['source'], obs['evidence']['image'])
                self.assertEqual(verify_visuals(stage_obs, stage_visuals), [stage_visuals[0]['path']])
            # Known geometry limitations in this optional overview do not
            # invalidate the original viewport or create whole-page evidence.
            from playwright.async_api import Error as BrowserError
            for stage in ('before_observe', 'after_observe'):
                limited = deepcopy(obs)
                limited.pop('visual_evidence', None)
                limited_root = root / (stage + '-unsupported')
                limited_root.mkdir()
                error = BrowserError('Page.evaluate: Error: UNSUPPORTED_GEOMETRY: rotation cannot supply target truth')
                failures = [error] if stage == 'before_observe' else [deepcopy(state), error]
                with patch('webcollect.browser.observe', new=AsyncMock(side_effect=failures)):
                    retained = asyncio.run(prepare_visuals(limited, limited_root, page, first=True))
                self.assertEqual(len(retained), 1)
                self.assertEqual(retained[0]['scope'], 'viewport')
                self.assertEqual(retained[0]['source'], obs['evidence']['image'])
                self.assertEqual(retained[0]['overview_unavailable']['reason'], stage + '_unsupported_geometry')
                self.assertEqual(verify_visuals(limited, retained), [retained[0]['path']])
                self.assertFalse(any(limited_root.glob('*full-*.json')))
            other = deepcopy(obs)
            other.pop('visual_evidence', None)
            other_root = root / 'other-browser-error'
            other_root.mkdir()
            with patch('webcollect.browser.observe', new=AsyncMock(side_effect=BrowserError('other snapshot defect'))):
                with self.assertRaisesRegex(BrowserError, 'other snapshot defect'):
                    asyncio.run(prepare_visuals(other, other_root, page, first=True))
            broken = deepcopy(obs)
            broken.pop('visual_evidence', None)
            broken_root = root / 'program-error'
            broken_root.mkdir()
            with patch('webcollect.browser.observe', new=AsyncMock(side_effect=ValueError('real snapshot defect'))):
                with self.assertRaisesRegex(ValueError, 'real snapshot defect'):
                    asyncio.run(prepare_visuals(broken, broken_root, page, first=True))
            self.assertEqual(original.read_bytes(), original_bytes)
            forged = deepcopy(crop)
            forged['parent_visual']['before_state']['sha256'] = '0' * 64
            with self.assertRaises(ValueError):
                verify_visuals(obs, [viewport, forged])
            with self.assertRaisesRegex(ValueError, 'NOT_PROVIDED'):
                crop_visual(obs, root, [0, 0, 20, 20], image_ref='unseen-image')

    def test_atomic_input_focus_select_value_and_observed_effect_chain(self):
        from webcollect.action_stability import action_scoped_projection, ActionScopeError
        empty_scope = {
            'screen_resolution': [200, 100],
            'capture_readiness': {'document_ready': 'complete', 'fonts_ready': True, 'images_ready': True},
            'elements': [{'element_id': 'empty', 'native_role': 'input', 'bbox': [10, 10, 190, 50],
                          'visible': True, 'enabled': True, 'inputable': True}],
            'capture_controls': [{'element_id': 'empty', 'tag': 'input', 'input_type': 'search'}],
            'values': [{'element_id': 'empty', 'value': '', 'focused': True,
                        'readonly': False, 'value_visible': False}],
            'geometry_witnesses': [{'element_id': 'empty', 'samples': [{'ancestor': True}] * 9}],
            'target': {'element_id': 'empty', 'hit_valid': True, 'focused': True}}
        self.assertEqual(action_scoped_projection(empty_scope, 'empty', 'type')['value']['value'], '')
        hidden_value = deepcopy(empty_scope); hidden_value['values'][0]['value'] = 'secret'
        with self.assertRaises(ActionScopeError) as failure:
            action_scoped_projection(hidden_value, 'empty', 'type')
        self.assertEqual(failure.exception.feedback()['dispatch_status'], 'NOT_DISPATCHED')
        self.assertEqual(failure.exception.missing, ['visible_existing_value_or_proven_empty_editor'])
        self.assertNotIn('unique_focus', failure.exception.missing)
        self.assertEqual(failure.exception.feedback()['recovery'], 'observe_or_revise_without_repeating_focus')
        protected = deepcopy(empty_scope); protected['capture_controls'][0]['input_type'] = 'password'
        with self.assertRaisesRegex(ActionScopeError, 'unprotected_input'):
            action_scoped_projection(protected, 'empty', 'type')
        edges = deepcopy(empty_scope); edges['geometry_witnesses'][0]['samples'] = [{'ancestor': False}] * 9
        edges['geometry_witnesses'][0]['samples'][4] = {'ancestor': True}
        edges['capture_controls'][0].update(selector='#empty',element_id='empty')
        edges['target'].update(bbox=[10,10,190,50],coordinate=[100,30])
        self.assertEqual(action_scoped_projection(edges,'empty','type')['value']['value'],'')
        self.assertEqual(action_availability(edges,edges['elements'][0],edges['capture_controls'][0],
            edges['values'][0],edges['target'],'type')['status'],'PROVEN')
        unreadable=deepcopy(edges);unreadable['values'][0]['value']='existing hidden value'
        self.assertEqual(action_availability(unreadable,unreadable['elements'][0],unreadable['capture_controls'][0],
            unreadable['values'][0],unreadable['target'],'type')['status'],'INSUFFICIENT')
        with self.assertRaises(ActionScopeError):action_scoped_projection(unreadable,'empty','type')
        occluded=deepcopy(edges);occluded['target']['hit_valid']=False
        with self.assertRaises(ActionScopeError):action_scoped_projection(occluded,'empty','type')
        self.assertEqual(action_availability(occluded,occluded['elements'][0],occluded['capture_controls'][0],
            occluded['values'][0],occluded['target'],'type')['status'],'UNAVAILABLE')
        center=deepcopy(edges);center['geometry_witnesses'][0]['samples'][4]['ancestor']=False
        with self.assertRaisesRegex(ValueError,'hit samples'):action_scoped_projection(center,'empty','type')
        disabled=deepcopy(edges);disabled['elements'][0]['enabled']=False
        with self.assertRaisesRegex(ValueError,'not visible/enabled'):action_scoped_projection(disabled,'empty','type')
        unfocused = deepcopy(empty_scope); unfocused['values'][0]['focused'] = False
        with self.assertRaisesRegex(ActionScopeError, 'unique_focus'):
            action_scoped_projection(unfocused, 'empty', 'type')
        readonly = deepcopy(empty_scope); readonly['values'][0]['readonly'] = True
        with self.assertRaisesRegex(ActionScopeError, 'editable'):
            action_scoped_projection(readonly, 'empty', 'type')
        hidden = deepcopy(empty_scope); hidden['elements'][0]['visible'] = False
        with self.assertRaisesRegex(ValueError, 'not visible/enabled'):
            action_scoped_projection(hidden, 'empty', 'type')
        missing_probe = deepcopy(empty_scope); missing_probe.pop('target')
        with self.assertRaisesRegex(ActionScopeError, 'visible_existing_value_or_proven_empty_editor'):
            action_scoped_projection(missing_probe, 'empty', 'type')
        # Explicit wait time belongs inside the atomic deadline. Scale only
        # the event-loop timer, retaining the production 20/65s decisions.
        import asyncio
        from unittest.mock import patch
        from webcollect import browser
        async def wait_deadlines():
            original_wait_for = asyncio.wait_for
            budgets = []
            async def scaled_wait_for(pending, timeout):
                budgets.append(timeout)
                return await original_wait_for(pending, timeout=timeout / 1000)
            async def normal_wait(*args):
                await asyncio.sleep(.03)
            with patch.object(browser, '_execute_and_settle', side_effect=normal_wait) as dispatch, \
                 patch.object(browser.asyncio, 'wait_for', side_effect=scaled_wait_for):
                await browser.execute(None, 'wait', {}, {'duration_ms': 60000})
                self.assertEqual(dispatch.call_count, 1)
            async def stalled(*args):
                await asyncio.sleep(1)
            with patch.object(browser, '_execute_and_settle', side_effect=stalled) as dispatch, \
                 patch.object(browser.asyncio, 'wait_for', side_effect=scaled_wait_for):
                with self.assertRaisesRegex(TimeoutError, '未知，不自动重发'):
                    await browser.execute(None, 'wait', {}, {'duration_ms': 60000})
                self.assertEqual(dispatch.call_count, 1)
                with self.assertRaises(TimeoutError):
                    await browser.execute(None, 'click', {})
            self.assertEqual(budgets, [65, 65, 20])
        asyncio.run(wait_deadlines())
        c = control()
        state = {'screen_resolution': [200, 100], 'document_identity': 'doc-current',
                 'url': 'https://example.test/form', 'scroll': [0, 0],
                 'elements': [c['element']], 'values': [c['value']], 'visible_text': '',
                 'geometry_witnesses':[{'element_id':'input1','samples':[{'ancestor':True}]*9}]}
        probe = {'element_id': 'input1', 'focused': False, 'hit_valid': True,
                 'bbox': c['element']['bbox'], 'coordinate': [50, 40],
                 'visible_label_evidence': c['readable_labels']}
        c['probe'] = probe
        c['actions']['type'] = action_availability(state, c['element'], c['binding'], c['value'], probe, 'type')
        obs = {'controls': {'input1': c}}
        task = {'fragment': {'allowed_actions': ['type', 'select', 'hotkey']}}
        step = {'action': 'type', 'control_id': 'input1', 'value': '42', 'expected_value': '42', 'goal': '输入金额', 'expected': '金额为42'}
        with self.assertRaisesRegex(ValueError, 'TYPE_REQUIRES_CURRENT_FOCUS'):
            compile_step(task, [], step, obs)
        probe['focused'] = True
        c['value']['focused'] = True
        c['actions']['type'] = action_availability(state, c['element'], c['binding'], c['value'], probe, 'type')
        rows = compile_step(task, [], step, obs)
        self.assertEqual([row['action'] for row in rows], ['type'])
        # A real click's ordinary observation proves focus without retaining
        # a targeted probe; keys still get a fresh probe before dispatch.
        focused = deepcopy(c)
        focused['probe'] = None
        focused['value'].update(focused=True, input_type='number', value='17')
        focused['element']['state'] = 'focused'
        focused_obs = {'controls': {'input1': focused}}
        select_all = {'action': 'hotkey', 'control_id': 'input1', 'keys': ['ctrl', 'a'],
                      'goal': '全选原数值', 'expected': '原数值已全选'}
        self.assertEqual(compile_step(task, [], select_all, focused_obs)[0]['keys'], ['ctrl', 'a'])
        with self.assertRaisesRegex(ValueError, 'HOTKEY_REQUIRES_CURRENT_TARGET_FOCUS'):
            compile_step(task, [], {**select_all, 'control_id': None}, focused_obs)
        focused['value']['focused'] = False
        focused['element']['state'] = ''
        with self.assertRaisesRegex(ValueError, 'HOTKEY_REQUIRES_CURRENT_TARGET_FOCUS'):
            compile_step(task, [], select_all, focused_obs)
        # Replacement uses the observed selection, not a preceding double click.
        c['value'].update(value='17', focused=True, selection_start=2, selection_end=2)
        with self.assertRaisesRegex(ValueError, 'TYPE_INSERTION_EXPECTATION_MISMATCH'):
            compile_step(task, [], step, obs)
        self.assertEqual(compile_step(task, [], {**step, 'expected_value': '1742'}, obs)[0]['value'], '42')
        c['value'].update(input_type='number', selection_start=None, selection_end=None,
                          all_text_selected=False)
        with self.assertRaisesRegex(ValueError, 'TYPE_REPLACEMENT_REQUIRES_OBSERVED_SELECTION_OR_EMPTY_VALUE'):
            compile_step(task, [], step, obs)
        # A browser lacking numeric selection evidence stays unknown; after-value
        # verification remains mandatory instead of an impossible selection gate.
        c['value'].pop('all_text_selected')
        self.assertEqual(compile_step(task, [], step, obs)[0]['value'], '42')
        # The later real targeted observation confirms numeric full selection.
        c['value'].update(input_type='number', value='17', focused=True, all_text_selected=True)
        numeric_rows = compile_step(task, [], step, obs)
        self.assertEqual([row['action'] for row in numeric_rows], ['type'])
        self.assertEqual(numeric_rows[0]['replace_selected_number'], '17')
        after = deepcopy(state)
        after['values'][0]['value'] = rows[0]['value']
        self.assertTrue(atomic_effect(state, after, 'type', {'text': rows[0]['value']}, 'input1')['verified'])
        self.assertFalse(atomic_effect(after, after, 'type', {'text': '42'}, 'input1')['verified'])
        compiled = react_step({**step, 'purpose': '输入金额', 'expected_result': '金额为42',
                               'rationale': '输入框可见'}, ['input1'], lambda _: [])
        self.assertEqual(compiled['expected_value'], '42')
        # A requested container survives normalization and compilation; only
        # that container's displacement can establish its scroll effect.
        planned_scroll = {'action': 'scroll', 'target': {'control': 'panel'}, 'direction': 'down',
                          'purpose': '读取弹层后续正文', 'rationale': '弹层存在未读正文',
                          'expected_result': '弹层内后续正文进入视口'}
        from webcollect.screenshot_plan import normalize_submit_plan
        normalized_scroll, _ = normalize_submit_plan({'steps': [planned_scroll]})
        self.assertEqual(normalized_scroll['steps'][0]['target'], {'control': 'panel'})
        planned_scroll['expected_result'] = '文' * 128
        planned_scroll['purpose'] = '读' * 200
        actual_scroll = react_step(planned_scroll, ['panel'], lambda _: [])
        self.assertEqual(actual_scroll['control_id'], 'panel')
        from webcollect.session_core import RawSessionCore, NATIVE_VERSION
        validator = RawSessionCore.__new__(RawSessionCore)
        validator.task = {'fragment': {'allowed_actions': ['scroll'],
            'decision_protocol': NATIVE_VERSION, 'collection_strategy': {'id': 'screenshot_plan'}}}
        validator._validate_step(actual_scroll)
        self.assertEqual(actual_scroll['expected'], '文' * 128)
        self.assertEqual(actual_scroll['goal'], '读' * 200)
        with self.assertRaisesRegex(ValueError, 'ACTION_SCHEMA'):
            validator._validate_step({**actual_scroll, 'expected': '文' * 401})
        validator._validate_step({key: value for key, value in actual_scroll.items() if key != 'control_id'})
        with self.assertRaisesRegex(ValueError, '动作参数不合法'):
            validator._validate_step({**actual_scroll, 'control_id': None})
        panel = {'element': {'visible': True}, 'binding': {'scroll_container': {'visible': True, 'axes': ['y']}}}
        scroll_task = {'fragment': {'allowed_actions': ['scroll']}}
        self.assertEqual(compile_step(scroll_task, [], actual_scroll, {'controls': {'panel': panel}})[0]['control_id'], 'panel')
        with self.assertRaisesRegex(ValueError, 'SCROLL_CONTAINER_NOT_UNIQUELY_BOUND'):
            react_step(planned_scroll, [], lambda _: [])
        before_panel = {'document_identity': 'dialog-doc', 'url': 'https://example.test/dialog',
                        'scroll': [0, 0], 'elements': [], 'values': [],
                        'scroll_containers': [{'element_id': 'panel', 'selector': '#panel', 'index': 0,
                                               'visible': True, 'scroll': [0, 0]}]}
        after_panel = deepcopy(before_panel)
        after_panel['scroll_containers'][0]['scroll'] = [0, 100]
        self.assertTrue(atomic_effect(before_panel, after_panel, 'scroll', {'direction': 'down'}, 'panel')['verified'])
        page_only = deepcopy(before_panel)
        page_only['scroll'] = [0, 100]
        self.assertFalse(atomic_effect(before_panel, page_only, 'scroll', {'direction': 'down'}, 'panel')['verified'])
        wrong = deepcopy(after); wrong['values'][0]['value'] = '1742'
        self.assertTrue(atomic_effect(state, wrong, 'type', {'text': '42'}, 'input1')['verified'])
        self.assertFalse(step_expectation(compiled, wrong, 'input1')['matched'])
        cleared = deepcopy(state); cleared['values'][0].update(value='', selection_start=0, selection_end=0)
        self.assertTrue(atomic_effect(state, cleared, 'hotkey', {'keys': ['backspace']}, 'input1')['verified'])
        self.assertEqual(input_changes(state, cleared, 'input1')[0]['after'], '')
        self.assertFalse(atomic_effect(cleared, cleared, 'hotkey', {'keys': ['backspace']}, 'input1')['verified'])
        projection_control = deepcopy(c); projection_control['value'] = cleared['values'][0]
        projection_control['value'].update(focused=True, value_visible=True)
        projected = controls_projection({'controls': {'input1': projection_control}, 'viewport': [200, 100]}, ['type'])[0]
        self.assertEqual(projected['value'], '')
        self.assertTrue(projected['focused'])
        projection_control['value'].update(value='hidden', value_visible=False)
        projected = controls_projection({'controls': {'input1': projection_control}, 'viewport': [200, 100]}, ['type'])[0]
        self.assertNotIn('value', projected)

        choice = control('choice', '#unit')
        choice['binding'].update(tag='select', options=[{'value': 'cm', 'label': '厘米'},
                                                     {'value': 'm', 'label': '米'}])
        choice['value']['value'] = 'cm'
        choice['actions']['select'] = {'status': 'PROVEN'}
        obs['controls']['choice'] = choice
        select = {'action': 'select', 'control_id': 'choice', 'value': 'm', 'expected_value': 'm', 'goal': '切换单位', 'expected': '米'}
        self.assertEqual(compile_step(task, [], select, obs)[0]['option'], '米')
        with self.assertRaisesRegex(ValueError, 'SELECT_OPTION_NOT_PROVEN'):
            compile_step(task, [], {**select, 'value': '米'}, obs)
        choice['binding']['options'][1]['disabled'] = True
        with self.assertRaisesRegex(ValueError, 'SELECT_OPTION_NOT_PROVEN'):
            compile_step(task, [], select, obs)
