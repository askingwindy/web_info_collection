"""HMAC adapter guards and independent oracle; browser pages are intercepted fixtures."""
import asyncio
from copy import deepcopy
import hashlib
import hmac
import unittest

from webcollect.hmac_strategy import (ADAPTER_ID, BUSINESS_ID, EXECUTION_ID, URI, TITLE, KEY, MESSAGE,
    HMAC_INVENTORY_JS, compile_hmac, hmac_sha256, hmac_spec, production_operations,
    validate_observation, validated_business_identity)
from webcollect.task_generation import compile_form, deterministic_specs, semantic_signature
from site_planner.pipeline import INVENTORY_JS, inventory_support


def inventory():
    widget = {'kind': 'non-form-widget', 'adapter_id': ADAPTER_ID, 'page_uri': URI,
              'label': 'HMACSHA256 在线加密工具', 'algorithm': 'hmac-sha256',
              'fields': [{'selector': '#pwd', 'tag': 'input', 'type': 'password', 'label': '请输入密钥',
                          'adjacent_label': '密钥', 'value': '', 'visible': True, 'enabled': True,
                          'value_visible': False, 'label_source': 'visible-placeholder-and-adjacent-key-label'},
                         {'selector': '#message_source', 'tag': 'textarea', 'type': 'textarea',
                          'label': '请输入需要加密的字符串', 'value': '', 'visible': True, 'enabled': True,
                          'value_visible': True, 'label_source': 'visible-placeholder'}],
              'submit': {'selector': '#btn-encrypt', 'tag': 'button', 'type': 'button', 'label': '加密',
                         'visible': True, 'enabled': True, 'handler': "CryptoTool.hash('hmacsha256')"},
              'output_case': 'lowercase', 'viewport': [1280, 720], 'observed_scroll_y': 0}
    page = {'page_uri': URI, 'title': TITLE, 'widgets': [widget], 'forms': [], 'elements': [],
            'result_targets': [{'selector': '#hash_result', 'tag': 'div', 'kind': 'hmac-result',
                                'label': '加密结果', 'text': '等待输入…', 'visible': True}]}
    capability = {'capability_id': 'CONTROLLED-hmac-fixture', 'version': 'observed-fixture-1',
                  'site_uri': URI, 'site_category': '工具', 'capabilities': [page], 'status': 'review_required'}
    return capability, page, widget


def compiled():
    capability, page, widget = inventory()
    return compile_hmac(capability, hmac_spec(capability, page, widget, 'controlled-strategy-1'))


class HmacStrategyTests(unittest.TestCase):
    def test_python_oracle_known_hmac_sha256_vector_and_utf8(self):
        self.assertEqual(hmac_sha256('The quick brown fox jumps over the lazy dog', 'key'),
                         'f7bc83f430538424b13298e6aa6fb143ef4d59a14946175997479dbc2d1a3cd8')
        self.assertEqual(hmac_sha256(MESSAGE, KEY), hmac.new(KEY.encode(), MESSAGE.encode(), hashlib.sha256).hexdigest())
        for message, key in [('', KEY), (MESSAGE, ''), (MESSAGE, 'x' * 129), ('x' * 4097, KEY), (None, KEY)]:
            with self.subTest(message=str(message)[:10], key=str(key)[:10]), self.assertRaises(ValueError):
                hmac_sha256(message, key)

    def test_registered_five_necessary_actions_have_visible_result_and_no_hidden_key_assertion(self):
        task = compiled()
        self.assertEqual([op['action_type'] for op in task['operations']], ['click', 'type', 'click', 'type', 'click'])
        self.assertEqual(len(task['required_actions']), 5)
        self.assertEqual(task['operations'][1]['postconditions'], [{'visible_text': '密钥'}])
        self.assertEqual(task['subgoals'][0]['evidence'], [{'final_assertion_index': 0}])
        self.assertTrue(all(assertion['selector'] != '#pwd' for assertion in task['final_assertions']))
        self.assertEqual(task['final_assertions'][0]['contains'], hmac_sha256(MESSAGE, KEY))
        self.assertIn('掩码', task['operations'][1]['expected'])
        self.assertFalse(task['capability_screen_status'] == 'ready')
        self.assertTrue(task['capability_review_required'])

    def test_pipeline_supports_actual_password_message_workflow_without_hidden_value_pass(self):
        capability, page, widget = inventory()
        controls, forms, actions = inventory_support(URI, [page])
        self.assertEqual(forms, [widget])
        self.assertTrue({'click', 'type'} <= set(actions))
        self.assertFalse(widget['fields'][0]['value_visible'])

    def test_task_generator_dispatches_observed_hmac_adapter(self):
        capability, _, _ = inventory()
        proposals = deterministic_specs(capability)
        self.assertEqual(proposals['strategy_rejections'], [])
        self.assertEqual(len(proposals['tasks']), 1)
        task = compile_form(capability, proposals['tasks'][0])
        self.assertEqual(task['execution_capability']['id'], EXECUTION_ID)
        self.assertEqual(task['business_identity']['business_id'], BUSINESS_ID)
        self.assertEqual(semantic_signature(task), semantic_signature({'deterministic_strategy': {'id': BUSINESS_ID}}))

    def test_parameters_do_not_create_new_business_when_all_bound_oracles_match(self):
        task = compiled()
        variant = deepcopy(task)
        variant['operations'] = production_operations(MESSAGE + '本公告仅作演示。', KEY + '演示')
        variant['final_assertions'] = variant['operations'][-1]['postconditions']
        self.assertEqual(semantic_signature(task), semantic_signature(variant))

    def test_business_statement_execution_identity_and_visible_oracle_cannot_be_forged(self):
        for change in ('business', 'execution', 'oracle', 'message', 'key', 'padding', 'scope', 'hidden-key-proof', 'required', 'subgoal'):
            task = compiled()
            if change == 'business': task['business_identity']['business_id'] = 'made-up-business'
            elif change == 'execution': task['execution_capability']['id'] = 'other-executor'
            elif change == 'oracle': task['final_assertions'][0]['contains'] = '0' * 64
            elif change == 'message': task['operations'][3]['arguments']['text'] = '改过的消息'
            elif change == 'key': task['operations'][1]['arguments']['text'] = '改过的密钥'
            elif change == 'padding': task['operations'].insert(-1, {'action_type': 'scroll'})
            elif change == 'scope': task['initial_url'] = 'https://www.jyshare.com/crypto/'
            elif change == 'hidden-key-proof': task['final_assertions'].append({'selector': '#pwd', 'value': KEY})
            elif change == 'required': task['required_actions'].pop()
            else: task['subgoals'][0]['evidence'] = [{'final_assertion_index': 1}]
            with self.subTest(change=change):
                self.assertIsNone(semantic_signature(task))
                with self.assertRaises(ValueError): validated_business_identity(task)

    def test_observed_initial_controls_algorithm_handler_and_empty_state_are_required(self):
        for change in ('uri', 'title', 'key-type', 'key-label', 'key-initial-value', 'key-value-visible', 'message',
                       'submit-handler', 'submit-label', 'initial-result', 'missing-result', 'case', 'viewport', 'scroll', 'extra-field'):
            capability, page, widget = inventory()
            if change == 'uri': capability['site_uri'] = URI + '?algorithm=md5'
            elif change == 'title': page['title'] = '任意加密页面'
            elif change == 'key-type': widget['fields'][0]['type'] = 'text'
            elif change == 'key-label': widget['fields'][0]['label'] = '密码'
            elif change == 'key-initial-value': widget['fields'][0]['value'] = 'already-filled'
            elif change == 'key-value-visible': widget['fields'][0]['value_visible'] = True
            elif change == 'message': widget['fields'][1]['label'] = '新字段'
            elif change == 'submit-handler': widget['submit']['handler'] = "CryptoTool.hash('sha256')"
            elif change == 'submit-label': widget['submit']['label'] = '下载'
            elif change == 'initial-result': page['result_targets'][0]['text'] = hmac_sha256(MESSAGE, KEY)
            elif change == 'missing-result': page['result_targets'] = []
            elif change == 'case': widget['output_case'] = 'uppercase'
            elif change == 'viewport': widget['viewport'] = [1000, 800]
            elif change == 'scroll': widget['observed_scroll_y'] = 100
            else: widget['fields'].append(deepcopy(widget['fields'][0]))
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_observation(capability, page, widget)

    def test_changed_specification_cannot_bypass_observed_compiler(self):
        for change in ('input', 'oracle', 'algorithm'):
            capability, page, widget = inventory()
            spec = hmac_spec(capability, page, widget, 'controlled')
            if change == 'input': spec['inputs'][0]['value'] = 'other-example-key'
            elif change == 'oracle': spec['completion']['contains'] = '0' * 64
            else: spec['deterministic_strategy']['algorithm'] = 'hmac-sha1'
            with self.subTest(change=change), self.assertRaises(ValueError):
                compile_hmac(capability, spec)


CONTROLLED_HTML = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>HMACSHA256 在线加密工具 | 菜鸟工具</title>
<style>body{margin:30px;font:18px sans-serif}.card-header{display:flex;align-items:center;gap:20px}.form-row{display:flex;gap:20px}
.input-group-text{display:inline-block}input,button,textarea{font:18px sans-serif;padding:8px}textarea{display:block;width:500px;height:130px}#hash_result{width:400px;min-height:32px}#upperText{width:15px;height:15px}</style>
<div class="card"><div class="card-header"><h4>HMACSHA256 在线加密工具</h4><span class="algorithm-badge">HMAC</span></div>
<div class="form-row"><div><div class="input-group"><div class="input-group-prepend"><span class="input-group-text">密钥</span></div>
<input id="pwd" type="password" placeholder="请输入密钥" autocomplete="new-password"></div>
<textarea id="message_source" rows="6" placeholder="请输入需要加密的字符串"></textarea>
<button id="btn-encrypt" type="button" onclick="CryptoTool.hash('hmacsha256')">加密</button></div>
<div><input id="upperText" type="checkbox"><label for="upperText">转为大写</label><div id="hash_result" class="placeholder-text">等待输入…</div>
<span id="result-info">—</span><span id="result-time"></span></div></div></div>
<script>window.CryptoTool={hash:function(){}};window.CryptoJS={HmacSHA256:function(){}};</script></html>'''


class HmacControlledInventoryBrowserTests(unittest.IsolatedAsyncioTestCase):
    async def test_password_step_never_describes_internal_key_value_as_visible(self):
        from playwright.async_api import async_playwright
        from webcollect.browser import observe
        from webcollect.collect import describe_change
        from webcollect.task_contract import narrative_evidence
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(channel='chrome', headless=True)
            self.addAsyncCleanup(browser.close)
            context = await browser.new_context(viewport={'width': 1280, 'height': 720})
            await context.route('**/*', lambda route: route.fulfill(status=200, content_type='text/html', body=CONTROLLED_HTML))
            page = await context.new_page()
            await page.goto(URI)
            await page.locator('#pwd').click()
            before = await observe(page, '#pwd')
            element = next(e for e in before['elements'] if e['element_id'] == before['target']['element_id'])
            await page.keyboard.insert_text(KEY)
            after = await observe(page, '#pwd')
            prose = describe_change(before, after, production_operations()[1], element)
            self.assertNotIn(KEY, after['visible_text'])
            self.assertNotIn(KEY, prose)
            self.assertEqual(prose, '操作后，可见文字「密钥」')
            safe, evidence = narrative_evidence(prose, before, after, production_operations()[1])
            self.assertEqual(safe, prose)
            self.assertEqual(evidence['machine_status'], 'PASS')
            self.assertEqual(evidence['semantic_status'], 'REVIEW_REQUIRED')
            self.assertEqual(evidence['quoted_evidence'], [{'quote': '密钥', 'source': 'after_visible_text'}])
            leaky, rejection = narrative_evidence('密钥框显示「' + KEY + '」', before, after, production_operations()[1])
            self.assertIsNone(leaky)
            self.assertEqual(rejection['machine_status'], 'REVIEW_REQUIRED')
            self.assertFalse(any(value.get('value_visible') for value in after['values']
                                 if value['element_id'] == after['target']['element_id']))

    async def test_intercepted_local_fixture_matches_and_guarded_mutations_reject(self):
        from playwright.async_api import async_playwright
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(channel='chrome', headless=True)
            self.addAsyncCleanup(browser.close)
            context = await browser.new_context(viewport={'width': 1280, 'height': 720})
            await context.route('**/*', lambda route: route.fulfill(status=200, content_type='text/html', body=CONTROLLED_HTML))
            page = await context.new_page()
            await page.goto(URI)
            result = await page.evaluate(HMAC_INVENTORY_JS)
            self.assertEqual(result['widget_rejections'], [])
            self.assertEqual(len(result['widgets']), 1)
            capability, _, _ = inventory()
            inventory_result = await page.evaluate(INVENTORY_JS)
            inventory_result['page_uri'] = URI
            validate_observation(capability, inventory_result, result['widgets'][0])
            for mutation in ["document.querySelector('#pwd').type='text'",
                             "document.querySelector('#pwd').value='prefilled'",
                             "document.querySelector('#btn-encrypt').setAttribute('onclick',\"CryptoTool.hash('sha256')\")",
                             "document.querySelector('#hash_result').textContent='already-completed'",
                             "document.querySelector('#upperText').checked=true",
                             "document.querySelector('#message_source').style.opacity='0'",
                             "document.querySelector('.input-group-text').textContent='其他标签'",
                             "document.querySelector('#btn-encrypt').disabled=true",
                             "document.querySelector('.form-row').insertAdjacentHTML('beforeend','<input value=unknown>')"]:
                await page.goto(URI)
                await page.evaluate(mutation)
                rejected = await page.evaluate(HMAC_INVENTORY_JS)
                with self.subTest(mutation=mutation):
                    self.assertEqual(rejected['widgets'], [])
                    self.assertEqual(len(rejected['widget_rejections']), 1)
            await page.goto('https://www.jyshare.com/crypto/hmacsha1/')
            outside = await page.evaluate(HMAC_INVENTORY_JS)
            self.assertEqual(outside, {'widgets': [], 'result_targets': [], 'widget_rejections': []})


if __name__ == '__main__':
    unittest.main()
