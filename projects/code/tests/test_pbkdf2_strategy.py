"""Offline PBKDF2 arithmetic only; these tests do not register a live page."""
import hashlib
import hmac
import unittest

from webcollect.pbkdf2_strategy import (BUSINESS_ID, EXECUTION_ID, URI,
                                       matches_uri, pbkdf2_hex)


def independently_expand(password, salt, iterations, words, hash_name):
    """PBKDF2 block expansion via repeated HMAC, separate from hashlib KDF."""
    password = password.encode('utf-8')
    salt = salt.encode('utf-8')
    digest_size = hashlib.new(hash_name).digest_size
    blocks = []
    for index in range(1, (words * 4 + digest_size - 1) // digest_size + 1):
        value = hmac.new(password, salt + index.to_bytes(4, 'big'), hash_name).digest()
        aggregate = int.from_bytes(value, 'big')
        for _ in range(1, iterations):
            value = hmac.new(password, value, hash_name).digest()
            aggregate ^= int.from_bytes(value, 'big')
        blocks.append(aggregate.to_bytes(digest_size, 'big'))
    return b''.join(blocks)[:words * 4].hex()


class Pbkdf2OracleTests(unittest.TestCase):
    def test_exact_route_and_separate_business_share_execution_capability(self):
        self.assertTrue(matches_uri(URI))
        for uri in (URI.rstrip('/'), URI + '?iterations=2', URI + '#result',
                    URI.replace('https:', 'http:'), URI.replace('pbkdf2', 'evpkdf')):
            self.assertFalse(matches_uri(uri), uri)
        self.assertEqual(EXECUTION_ID, 'observed-form-result-v1')
        self.assertEqual(BUSINESS_ID, 'password-key-derivation-v1')

    def test_known_sha1_vector_prefix_and_sha256_vector(self):
        self.assertEqual(pbkdf2_hex('password', 'salt', 1, 4, hash_name='sha1'),
                         '0c60c80f961f0e71f3a9b524af601206')
        self.assertEqual(pbkdf2_hex('password', 'salt', 2, 4, hash_name='sha1'),
                         'ea6c014dc72d6f8ccd1ed92ace1d41f0')
        self.assertEqual(pbkdf2_hex('password', 'salt', 1, 8, hash_name='sha256'),
                         '120fb6cffcf8b32c43e7225256c4f837a86548c92ccc35480805987cb70be17b')

    def test_utf8_and_multi_block_word_units_match_separate_hmac_expansion(self):
        for name in ('sha1', 'sha256'):
            for words in (4, 8, 16):
                with self.subTest(hash_name=name, words=words):
                    actual = pbkdf2_hex('公开示例口令', '公开测试盐', 3, words, hash_name=name)
                    self.assertEqual(actual, independently_expand('公开示例口令', '公开测试盐',
                                                                  3, words, name))
                    self.assertEqual(len(actual), words * 8)

    def test_explicit_hasher_is_required_and_defaults_are_not_guessed(self):
        with self.assertRaises(TypeError):
            pbkdf2_hex('password', 'salt', 1000, 4)
        for name in (None, '', 'SHA256', 'md5', 'unknown'):
            with self.subTest(hash_name=name), self.assertRaisesRegex(ValueError, 'observed'):
                pbkdf2_hex('password', 'salt', 1000, 4, hash_name=name)
        self.assertNotEqual(pbkdf2_hex('password', 'salt', 1000, 4, hash_name='sha1'),
                            pbkdf2_hex('password', 'salt', 1000, 4, hash_name='sha256'))

    def test_invalid_iteration_and_length_options_are_rejected(self):
        for iterations in (True, 0, -1, 1.5, '1000', 1_000_001):
            with self.subTest(iterations=iterations), self.assertRaises(ValueError):
                pbkdf2_hex('password', 'salt', iterations, 4, hash_name='sha256')
        for words in (True, 0, 1, 5, 32, '4', 4.0):
            with self.subTest(words=words), self.assertRaises(ValueError):
                pbkdf2_hex('password', 'salt', 1000, words, hash_name='sha256')

    def test_unrepresentable_or_unbounded_gui_fixture_inputs_are_rejected(self):
        for password, salt in (('', 'salt'), (' ', 'salt'), ('password', ''),
                               ('password', ' '), ('A' * 4097, 'salt'),
                               ('password', 'S' * 129), ('pass\x00word', 'salt'),
                               (None, 'salt'), ('password', 1)):
            with self.subTest(password_type=type(password).__name__, salt_type=type(salt).__name__), \
                    self.assertRaises(ValueError):
                pbkdf2_hex(password, salt, 1000, 4, hash_name='sha256')


def observed_fixture():
    from webcollect.pbkdf2_strategy import ADAPTER_ID, TITLE
    widget = {'kind': 'non-form-widget', 'adapter_id': ADAPTER_ID, 'page_uri': URI,
              'label': 'PBKDF2 在线加密工具', 'algorithm': 'pbkdf2-hmac-sha256',
              'loaded_implementation': {'prf': 'sha256', 'default_iterations': 250000, 'default_key_size_words': 4},
              'fields': [{'selector': '#salt', 'tag': 'input', 'type': 'text', 'label': '请输入盐值',
                          'adjacent_label': '盐（salt）', 'value': '', 'visible': True, 'enabled': True,
                          'value_visible': True, 'label_source': 'visible-placeholder-and-adjacent-salt-label'},
                         {'selector': '#message_source', 'tag': 'textarea', 'type': 'textarea',
                          'label': '请输入需要加密的字符串', 'value': '', 'visible': True, 'enabled': True,
                          'value_visible': True, 'label_source': 'visible-placeholder'}],
              'settings': [{'selector': '#iterations', 'tag': 'input', 'type': 'number', 'label': '迭代次数',
                            'value': '1000', 'min': '1', 'visible': True, 'enabled': True,
                            'label_source': 'visible-adjacent-iteration-label'},
                           {'selector': '#key_size', 'tag': 'select', 'type': 'select-one', 'label': '密钥长度',
                            'value': '4', 'visible': True, 'enabled': True,
                            'label_source': 'visible-sibling-key-length-label',
                            'options': [{'value': '4', 'label': '128 位'}, {'value': '8', 'label': '256 位'},
                                        {'value': '16', 'label': '512 位'}]}],
              'submit': {'selector': '#btn-encrypt', 'tag': 'button', 'type': 'button', 'label': '加密',
                         'visible': True, 'enabled': True, 'handler': "CryptoTool.hash('pbkdf2')"},
              'output_case': 'lowercase', 'viewport': [1280, 720], 'observed_scroll_y': 0}
    page = {'page_uri': URI, 'title': TITLE, 'widgets': [widget], 'forms': [], 'elements': [],
            'result_targets': [{'selector': '#hash_result', 'tag': 'div', 'kind': 'pbkdf2-result',
                                'label': '加密结果', 'text': '等待输入…', 'visible': True}]}
    capability = {'site_uri': URI, 'site_category': '工具', 'capability_id': 'CONTROLLED-pbkdf2-fixture',
                  'version': 'controlled-observation-1', 'status': 'review_required', 'capabilities': [page]}
    return capability, page, widget


def compile_fixture():
    from webcollect.pbkdf2_strategy import pbkdf2_spec, compile_pbkdf2
    capability, page, widget = observed_fixture()
    return compile_pbkdf2(capability, pbkdf2_spec(capability, page, widget, 'controlled-strategy-1'))


class Pbkdf2ObservedCompilerTests(unittest.TestCase):
    def test_pipeline_and_generator_use_registered_distinct_business_with_shared_executor(self):
        from site_planner.pipeline import inventory_support
        from webcollect.task_generation import deterministic_specs, compile_form, semantic_signature
        from test_hmac_strategy import compiled as compile_hmac_fixture
        capability, page, widget = observed_fixture()
        _, forms, actions = inventory_support(URI, [page])
        self.assertEqual(forms, [widget])
        self.assertTrue({'click', 'type'} <= set(actions))
        proposals = deterministic_specs(capability)
        self.assertEqual(proposals['strategy_rejections'], [])
        self.assertEqual(len(proposals['tasks']), 1)
        task = compile_form(capability, proposals['tasks'][0])
        self.assertEqual(task['business_identity']['business_id'], BUSINESS_ID)
        self.assertIsNotNone(semantic_signature(task))
        hmac_task = compile_hmac_fixture()
        self.assertEqual(task['execution_capability']['id'], hmac_task['execution_capability']['id'])
        self.assertNotEqual(semantic_signature(task), semantic_signature(hmac_task))

    def test_five_necessary_actions_use_visible_salt_and_plain_textarea_without_parameter_padding(self):
        from webcollect.pbkdf2_strategy import PASSWORD, SALT
        task = compile_fixture()
        self.assertEqual([op['action_type'] for op in task['operations']], ['click', 'type', 'click', 'type', 'click'])
        self.assertEqual([op['selector'] for op in task['operations']],
                         ['#salt', '#salt', '#message_source', '#message_source', '#btn-encrypt'])
        self.assertEqual(task['operations'][1]['arguments']['text'], SALT)
        self.assertEqual(task['operations'][3]['arguments']['text'], PASSWORD)
        self.assertEqual(task['final_assertions'][0]['contains'], 'd8306fd4f7dd1af99d2dc62682c1a515')
        self.assertEqual(task['deterministic_strategy']['iterations'], 1000)
        self.assertEqual(task['deterministic_strategy']['key_size_words'], 4)
        self.assertEqual(len(task['required_actions']), 5)
        self.assertTrue(all(a['selector'] != '#pwd' for a in task['final_assertions']))
        self.assertTrue(task['capability_review_required'])
        self.assertNotEqual(task['business_identity']['business_id'], 'keyed-message-authentication-v1')
        self.assertEqual(task['execution_capability']['id'], EXECUTION_ID)

    def test_unknown_or_changed_prf_and_library_defaults_cannot_admit(self):
        from copy import deepcopy
        from webcollect.pbkdf2_strategy import validate_observation
        for change in ('missing', 'sha1', 'unknown', 'iterations', 'key-size'):
            capability, page, widget = observed_fixture()
            if change == 'missing': widget.pop('loaded_implementation')
            elif change == 'sha1': widget['loaded_implementation']['prf'] = 'sha1'
            elif change == 'unknown': widget['loaded_implementation']['prf'] = 'UNKNOWN'
            elif change == 'iterations': widget['loaded_implementation']['default_iterations'] = 1
            else: widget['loaded_implementation']['default_key_size_words'] = 8
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, 'loaded SHA256'):
                validate_observation(capability, page, widget)

    def test_controls_settings_handler_and_initial_result_must_match_actual_observation(self):
        from webcollect.pbkdf2_strategy import validate_observation
        for change in ('uri', 'title', 'salt-type', 'salt-label', 'salt-value', 'password-type', 'password-visible',
                       'iterations', 'length', 'length-options', 'handler', 'result', 'viewport', 'scroll', 'extra'):
            capability, page, widget = observed_fixture()
            if change == 'uri': capability['site_uri'] = URI + '?algorithm=sha1'
            elif change == 'title': page['title'] = 'EvpKDF 在线加密工具'
            elif change == 'salt-type': widget['fields'][0]['type'] = 'password'
            elif change == 'salt-label': widget['fields'][0]['adjacent_label'] = '密钥'
            elif change == 'salt-value': widget['fields'][0]['value'] = 'prefilled'
            elif change == 'password-type': widget['fields'][1]['tag'] = 'input'
            elif change == 'password-visible': widget['fields'][1]['value_visible'] = False
            elif change == 'iterations': widget['settings'][0]['value'] = '250000'
            elif change == 'length': widget['settings'][1]['value'] = '8'
            elif change == 'length-options': widget['settings'][1]['options'][0]['label'] = '64 位'
            elif change == 'handler': widget['submit']['handler'] = "CryptoTool.hash('evpkdf')"
            elif change == 'result': page['result_targets'][0]['text'] = 'already-derived'
            elif change == 'viewport': widget['viewport'] = [1000, 800]
            elif change == 'scroll': widget['observed_scroll_y'] = 50
            else: widget['fields'].append(dict(widget['fields'][0]))
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_observation(capability, page, widget)

    def test_spec_mutations_cannot_bypass_compiler(self):
        from webcollect.pbkdf2_strategy import pbkdf2_spec, compile_pbkdf2
        for change in ('input', 'oracle', 'algorithm', 'iterations', 'length'):
            capability, page, widget = observed_fixture()
            spec = pbkdf2_spec(capability, page, widget, 'controlled')
            if change == 'input': spec['inputs'][0]['value'] = 'different salt'
            elif change == 'oracle': spec['completion']['contains'] = '0' * 32
            elif change == 'algorithm': spec['deterministic_strategy']['algorithm'] = 'pbkdf2-hmac-sha1'
            elif change == 'iterations': spec['deterministic_strategy']['iterations'] = 2
            else: spec['deterministic_strategy']['key_size_words'] = 8
            with self.subTest(change=change), self.assertRaises(ValueError):
                compile_pbkdf2(capability, spec)

    def test_business_definition_bound_actions_and_visible_terminal_cannot_be_forged(self):
        from webcollect.pbkdf2_strategy import validated_business_identity
        for change in ('business', 'execution', 'hash', 'salt', 'password', 'padding', 'scope', 'hidden-proof',
                       'required', 'subgoal', 'instruction', 'iterations', 'length', 'final-result'):
            task = compile_fixture()
            if change == 'business': task['business_identity']['business_id'] = 'made-up-business'
            elif change == 'execution': task['execution_capability']['id'] = 'different-executor'
            elif change == 'hash': task['final_assertions'][0]['contains'] = '0' * 32
            elif change == 'salt': task['operations'][1]['arguments']['text'] = 'different salt'
            elif change == 'password': task['operations'][3]['arguments']['text'] = 'different public password'
            elif change == 'padding': task['operations'].insert(-1, {'action_type': 'scroll'})
            elif change == 'scope': task['initial_url'] = URI.rstrip('/')
            elif change == 'hidden-proof': task['final_assertions'].append({'selector': '#pwd', 'value': 'not used'})
            elif change == 'required': task['required_actions'].pop()
            elif change == 'subgoal': task['subgoals'][0]['evidence'] = [{'final_assertion_index': 0}]
            elif change == 'instruction': task['instruction'] = 'Use another task'
            elif change == 'iterations': task['deterministic_strategy']['iterations'] = 2000
            elif change == 'length': task['deterministic_strategy']['key_size_words'] = 8
            else: task['final_result'] = '生成64位密钥'
            with self.subTest(change=change), self.assertRaises(ValueError):
                validated_business_identity(task)

    def test_parameters_retain_same_business_identity_when_all_visible_oracles_are_rebound(self):
        from webcollect.pbkdf2_strategy import (PASSWORD, SALT, production_operations,
                                               validated_business_identity, _instruction)
        task = compile_fixture()
        original = validated_business_identity(task)
        password, salt = PASSWORD + '这也是公开示例。', SALT + '二'
        task['operations'] = production_operations(password, salt)
        task['final_assertions'] = task['operations'][-1]['postconditions']
        task['instruction'] = _instruction(password, salt)
        task['final_result'] = '加密结果区域显示128位派生密钥「' + task['final_assertions'][0]['contains'] + '」'
        self.assertEqual(validated_business_identity(task), original)


CONTROLLED_HTML = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>PBKDF2 在线加密工具 | 菜鸟工具</title>
<style>body{margin:30px;font:17px sans-serif}.card-header{display:flex;align-items:center;gap:20px}.form-row{display:flex;gap:30px}
.input-group{display:flex;align-items:center;margin:12px 0}.input-group-text{display:block;width:100px}input,button,textarea,select{font:16px sans-serif;padding:7px}
textarea{display:block;width:520px;height:130px;margin:15px 0}#hash_result{width:450px;min-height:50px;word-break:break-all}#upperText{width:15px;height:15px}
#pbkdf_fields{width:550px}#salt,#iterations{width:390px}#key_size{width:500px}h6{margin:10px 0}.form-group label{display:block}</style>
<div class="card"><div class="card-header"><h4>PBKDF2 在线加密工具</h4><span class="algorithm-badge">密钥派生</span></div>
<div class="form-row"><div><input id="pwd" type="password" placeholder="请输入密钥" style="display:none">
<div id="pbkdf_fields"><h6>密钥派生参数</h6>
<div class="form-group"><div class="input-group"><div class="input-group-prepend"><span class="input-group-text">盐（salt）</span></div><input id="salt" type="text" placeholder="请输入盐值"></div></div>
<div class="form-group"><div class="input-group"><div class="input-group-prepend"><span class="input-group-text">迭代次数</span></div><input id="iterations" type="number" value="1000" min="1" placeholder="迭代次数"></div></div>
<div class="form-group"><label>密钥长度</label><select id="key_size"><option value="4">128 位</option><option value="8">256 位</option><option value="16">512 位</option></select></div></div>
<textarea id="message_source" rows="6" placeholder="请输入需要加密的字符串"></textarea>
<button id="btn-encrypt" type="button" onclick="CryptoTool.hash('pbkdf2')">加密</button></div>
<div><div><span>加密结果</span><input id="upperText" type="checkbox"><label for="upperText">转为大写</label></div>
<div class="card result-card"><div class="card-body"><div id="hash_result" class="placeholder-text">等待输入…</div></div>
<div class="card-footer"><span id="result-info">—</span><span id="result-time"></span></div></div></div></div></div>
<script>
window.CryptoJS={algo:{SHA256:{},SHA1:{}}};CryptoJS.algo.PBKDF2={cfg:{hasher:CryptoJS.algo.SHA256,iterations:250000,keySize:4}};CryptoJS.PBKDF2=function(){};
window.CryptoTool={hash:async function(){
 const encoder=new TextEncoder(),password=document.querySelector('#message_source').value,salt=document.querySelector('#salt').value;
 const key=await crypto.subtle.importKey('raw',encoder.encode(password),'PBKDF2',false,['deriveBits']);
 const bytes=new Uint8Array(await crypto.subtle.deriveBits({name:'PBKDF2',hash:'SHA-256',salt:encoder.encode(salt),iterations:Number(document.querySelector('#iterations').value)},key,Number(document.querySelector('#key_size').value)*32));
 const text=[...bytes].map(value=>value.toString(16).padStart(2,'0')).join('');
 document.querySelector('#hash_result').textContent=text;document.querySelector('#hash_result').className='has-result';
 document.querySelector('#result-info').textContent=text.length+' 字符 / '+text.length+' 字节';
 document.querySelector('#result-time').textContent='受控计算完成';
}};</script></html>'''


class Pbkdf2ControlledBrowserTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from playwright.async_api import async_playwright
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(channel='chrome', headless=True)
        self.context = await self.browser.new_context(viewport={'width': 1280, 'height': 720}, service_workers='block')
        self.fulfilled = []
        async def controlled_only(route):
            self.fulfilled.append(route.request.url)
            if route.request.is_navigation_request():
                await route.fulfill(status=200, content_type='text/html; charset=utf-8', body=CONTROLLED_HTML)
            else:
                await route.abort()
        await self.context.route('**/*', controlled_only)
        self.page = await self.context.new_page()
        await self.page.goto(URI)

    async def asyncTearDown(self):
        await self.browser.close()
        await self.playwright.stop()

    async def test_inventory_five_native_actions_and_complete_visible_webcrypto_result(self):
        from webcollect.pbkdf2_strategy import PBKDF2_INVENTORY_JS, validate_observation
        from webcollect.browser import observe, prepare_action, execute
        from webcollect.collect import assert_state, chinese_ratio
        result = await self.page.evaluate(PBKDF2_INVENTORY_JS)
        self.assertEqual(result['widget_rejections'], [])
        self.assertEqual(len(result['widgets']), 1)
        capability, page, _ = observed_fixture()
        page['widgets'] = result['widgets']; page['result_targets'] = result['result_targets']
        validate_observation(capability, page, result['widgets'][0])
        task = compile_fixture(); ratios = []
        with self.assertRaises(ValueError):
            await assert_state(self.page, task['final_assertions'])
        for operation in task['operations']:
            state = await observe(self.page, operation['selector'])
            ratios.append(chinese_ratio(state['visible_text']))
            arguments, _ = prepare_action(state, operation)
            await execute(self.page, operation['action_type'], arguments, operation.get('execution'))
            if operation.get('postconditions'):
                await assert_state(self.page, operation['postconditions'])
        final = await observe(self.page, assertions=task['final_assertions'])
        ratios.append(chinese_ratio(final['visible_text']))
        await assert_state(self.page, task['final_assertions'], captured_state=final)
        self.assertEqual(await self.page.locator('#hash_result').text_content(), 'd8306fd4f7dd1af99d2dc62682c1a515')
        self.assertTrue(all(ratio >= 0.7 for ratio in ratios), ratios)
        self.assertEqual(await self.page.locator('#iterations').input_value(), '1000')
        self.assertEqual(await self.page.locator('#key_size').input_value(), '4')
        self.assertTrue(all(url == URI for url in self.fulfilled))
        length_proof = (await assert_state(self.page, task['final_assertions']))[-1]
        self.assertEqual(length_proof['display_actual'], '128 位')
        await self.page.locator('#key_size').select_option('8')
        with self.assertRaisesRegex(ValueError, '断言未通过'):
            await assert_state(self.page, task['final_assertions'])
        await self.page.locator('#key_size').select_option('4')
        await self.page.locator('#key_size').evaluate("e=>e.style.width='2px'")
        with self.assertRaisesRegex(ValueError, '完整值未|未完整显示'):
            await assert_state(self.page, task['final_assertions'])
        await self.page.locator('#key_size').evaluate("e=>e.style.width='500px'")
        await self.page.locator('#hash_result').evaluate("e=>e.style.transform='translateX(1300px)'")
        with self.assertRaisesRegex(ValueError, '未完整显示|视口'):
            await assert_state(self.page, task['final_assertions'])

    async def test_changed_live_prf_controls_labels_and_layout_are_rejected(self):
        from webcollect.pbkdf2_strategy import PBKDF2_INVENTORY_JS
        mutations = ["CryptoJS.algo.PBKDF2.cfg.hasher=CryptoJS.algo.SHA1",
                     "delete CryptoJS.algo.PBKDF2.cfg.hasher",
                     "CryptoJS.algo.PBKDF2.cfg.iterations=1",
                     "document.querySelector('#pwd').style.display='block'",
                     "document.querySelector('#salt').type='password'",
                     "document.querySelector('#salt').readOnly=true",
                     "document.querySelector('#salt').value='prefilled'",
                     "document.querySelector('#iterations').value='2'",
                     "document.querySelector('#key_size').value='8'",
                     "document.querySelector('#key_size').options[0].text='64 位'",
                     "document.querySelector('#btn-encrypt').setAttribute('onclick',\"CryptoTool.hash('evpkdf')\")",
                     "document.querySelector('#hash_result').textContent='already-derived'",
                     "document.querySelector('.result-card').previousElementSibling.querySelector('span').textContent='后台占位'",
                     "document.querySelector('.result-card').previousElementSibling.querySelector('span').style.display='none'",
                     "document.querySelector('#upperText').checked=true",
                     "document.querySelector('#message_source').style.opacity='0'",
                     "document.querySelector('.input-group-text').textContent='其他标签'",
                     "document.querySelector('#salt').style.transform='translateX(1300px)'",
                     "document.querySelector('.form-row').insertAdjacentHTML('beforeend','<input value=unknown>')"]
        for mutation in mutations:
            await self.page.goto(URI)
            await self.page.evaluate(mutation)
            result = await self.page.evaluate(PBKDF2_INVENTORY_JS)
            with self.subTest(mutation=mutation):
                self.assertEqual(result['widgets'], [])
                self.assertEqual(len(result['widget_rejections']), 1)
        await self.page.goto('https://www.jyshare.com/crypto/evpkdf/')
        self.assertEqual(await self.page.evaluate(PBKDF2_INVENTORY_JS),
                         {'widgets': [], 'result_targets': [], 'widget_rejections': []})

    async def test_unreadable_placeholder_and_clipped_value_cannot_bypass_runtime(self):
        from webcollect.browser import observe, prepare_action
        from webcollect.collect import assert_state
        from webcollect.pbkdf2_strategy import PASSWORD
        operation = compile_fixture()['operations'][0]
        await self.page.locator('#salt').evaluate("e=>e.style.width='2px'")
        state = await observe(self.page, '#salt')
        with self.assertRaisesRegex(ValueError, 'M4_TARGET_LABEL_UNREADABLE'):
            prepare_action(state, operation)
        await self.page.goto(URI)
        await self.page.locator('#message_source').click()
        await self.page.keyboard.insert_text(PASSWORD)
        await self.page.locator('#message_source').evaluate("e=>e.style.height='15px'")
        with self.assertRaisesRegex(ValueError, '完整值未|未完整显示'):
            await assert_state(self.page, [{'selector': '#message_source', 'value': PASSWORD}])


if __name__ == '__main__':
    unittest.main()
