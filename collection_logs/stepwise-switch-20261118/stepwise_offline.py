"""策略 3 stepwise 隔离离线集成：真实本地 HTTP + Chrome + 正常消费者入口。

覆盖：候选领取 → stepwise逐步执行（真实浏览器动作）→ 原始记录 → 回写 →
单独判定 → annotation 生成 → RuntimeStore 正式保存 → 候选回写 → 客户导出
读回；包含短流程、协议、真实本地断网失败，select拒绝后修正及旋转装饰。外部模型传输为离线替身
（经真实 ModelGateway 解析/校验/结算链）；全部库与输出为隔离工程，
不触达生产。真实 GLM 请求 0、真实站点请求 0。
"""
import asyncio
import importlib.util
import io
import json
import os
import re
import sys
import threading
import time
import traceback
from contextlib import ExitStack
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
CODE = REPO / 'projects/code'
sys.path[:0] = [str(CODE), str(REPO / 'projects/site-planner'), str(REPO / 'projects/quality-inspector')]

from webcollect import workspace_json as json  # noqa: E402
from webcollect.batch_core import file_sha, load_json  # noqa: E402

RESULTS = []
CHAIN = ['']


def check(name, passed, detail=None):
    RESULTS.append({'chain': CHAIN[0], 'name': name, 'pass': bool(passed), 'detail': detail})


# ---------------------------------------------------------------- 本地站点
def html(title, body):
    return ('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
            '<title>' + title + '</title><style>'
            'body{font:22px Arial,sans-serif;margin:40px;color:#222;background:white;line-height:1.6}'
            'input,button{font:22px Arial,sans-serif;padding:8px;margin:8px;border:2px solid #555}'
            'input:focus{outline:2px solid #1755aa}p{margin:20px 0}a{color:#1255a0}'
            '</style></head><body>' + body + '</body></html>').encode()


SENT_A = '本章节为长文示例正文，介绍本节一处具体记载数值的内容，并展开说明其历史背景与资料来源。'
SENT_B = '本节记载数值的含义在于说明长文示例的段落结构，读者可据此核对章节的位置、顺序与完整性。'
SECTION = (SENT_A + SENT_B) * 10

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        self.serve('GET', '')

    def do_POST(self):
        self.serve('POST', self.rfile.read(int(self.headers.get('Content-Length', 0))).decode())

    def serve(self, method, body):
        parts = urlsplit(self.path)
        values = parse_qs(body if method == 'POST' else parts.query, keep_blank_values=True)
        if parts.path == '/network-broken':
            self.connection.shutdown(2)
            self.connection.close()
            return
        if parts.path in ('/calculator', '/calculate', '/calculator-select', '/calculator-rotated'):
            quantity = values.get('quantity', [''])[0]
            price = values.get('price', [''])[0]
            total = f'{float(quantity) * float(price):.2f}' if parts.path == '/calculate' else None
            # 同页JS计算器：真实点击/输入仍为真实浏览器动作；不跨页导航
            # （策略3首版不提供跨页 http 导航证明，试点保存合同下如实限定）。
            onsubmit = ("event.preventDefault();"
                        "var q=parseFloat(document.getElementById('quantity').value)||0;"
                        "var p=parseFloat(document.getElementById('price').value)||0;"
                        "document.getElementById('result').textContent="
                        "'合计结果：'+(q*p).toFixed(2)+'元';")
            selection = parts.path == '/calculator-select'
            if selection:
                onsubmit = onsubmit.replace("+'元';", "+document.getElementById('currency').value;")
            extra = ('<select id=currency aria-label=金额单位 style="font:22px Arial;padding:8px">'
                     '<option value=分>分</option><option value=元>元</option></select>') if selection else ''
            if parts.path == '/calculator-rotated':
                extra += '<div id=decoration style="position:absolute;left:950px;top:400px;transform:rotate(23deg)">旋转装饰文字</div>'
            content = html('合计计算器',
                '<h1>合计计算器</h1>' + extra + '<form id="calc" onsubmit="' + onsubmit.replace('"', '&quot;') + '">'
                '<div><label for="quantity">数量</label><input id="quantity" name="quantity" aria-label="数量" value="' + quantity + '"></div>'
                '<div><label for="price">单价</label><input id="price" name="price" aria-label="单价" value="' + price + '"></div>'
                '<button type="submit">计算合计</button>'
                '<output id="result" aria-label="合计结果">尚未计算</output></form>')
        elif parts.path == '/long-article':
            # 目录锚点阅读：点击第N节链接跳转到对应节（同文档锚点、真实滚动）。
            # 目录用按钮 scrollIntoView：真实点击+真实滚动，且不改变 URL
            # （策略3首版不做跨页/锚点导航许可证明）。
            button = ('<button type="button" onclick="document.getElementById('
                      "'s%d').scrollIntoView()\">第%d节 目录项</button>")
            toc = ''.join(button % (index, index) for index in range(1, 6))
            # 粘性概要：长句在锚点帧与每个观察帧都可见（试点内容佐证确定性共享）。
            sticky_summary = ('<div style="position:sticky;top:0;background:white;z-index:3">'
                              + toc + '<p>' + SENT_A + SENT_B + '</p></div>')
            tall = ''.join('<h2 id="s%d">第%d节</h2><p>%s</p>' % (index, index, SECTION)
                           for index in range(1, 5))
            content = html('长文示例',
                '<article><h1>长文示例</h1>' + sticky_summary
                + tall + '<h2 id="s5">第5节</h2><p>第五节内容简短。</p>'
                + '<p>结语：本次记载数值为五十五</p></article>')
        elif parts.path == '/short-article':
            content = html('短文示例', '<article><h1>短文示例</h1><p>本页只有一小段正文，用于验证短流程失败出口。</p></article>')
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(content)))
        self.end_headers()
        self.wfile.write(content)


# ---------------------------------------------------------------- 离线模型替身
class SequencedOpener:
    """离线模型传输：按请求内容回放脚本化响应；经真实网关解析/校验/结算。"""

    def __init__(self):
        self.calls = []
        self.select_rejected_sent = False
        self.user_texts = []

    @staticmethod
    def _message(name, arguments, cid):
        return {'role': 'assistant', 'content': None, 'reasoning_content': 'offline-fixture',
                'tool_calls': [{'id': cid, 'type': 'function',
                                'function': {'name': name, 'arguments': json.dumps(
                                    arguments, ensure_ascii=False)}}]}

    def open(self, request, timeout):
        self.calls.append(request)
        payload = json.loads(request.data.decode('utf-8'))
        tool = (payload.get('tools') or [{}])[0].get('function', {}).get('name')
        content = next((row['content'] for row in reversed(payload.get('messages', []))
                        if row.get('role') == 'user'), '')
        if isinstance(content, list):
            user = ''.join(part.get('text', '') for part in content
                           if isinstance(part, dict) and part.get('type') == 'text')
        else:
            user = content or ''
        self.user_texts.append((CHAIN[0], user))
        try:
            return self._dispatch(tool, user)
        except Exception:
            (self.output / ('stub-failure-' + CHAIN[0] + '-' + str(len(self.calls)) + '.txt')).write_text(
                'TOOL=%s\nUSER=%s\n' % (tool, user[:4000]))
            raise

    def _dispatch(self, tool, user):
        if CHAIN[0] == 'protocol' and tool == 'next_action':
            arguments = {'action': 'unsupported_action'}
        elif tool == 'submit_writeback':
            arguments = self._writeback(user)
        elif tool == 'submit_judgement':
            arguments = {'instruction_specific': True, 'completed': True,
                         'judgement_supported': True, 'redundant_steps': [],
                         'mismatch_steps': [], 'reason': '任务具体，末帧支持结论，未发现矛盾'}
        elif tool == 'next_action':
            arguments = self._next_action(user)
        else:
            raise AssertionError('unexpected tool: ' + str(tool))
        raw = {'id': 'offline-provider-response', 'model': 'offline-model-version',
               'usage': {'prompt_tokens': 900, 'completion_tokens': 60,
                         'prompt_tokens_details': {'cached_tokens': 120}},
               'choices': [{'finish_reason': 'tool_calls',
                            'message': self._message(tool, arguments, tool + '-' + str(len(self.calls)))}]}
        return io.BytesIO(json.dumps(raw).encode())

    @staticmethod
    def _chain(user):
        if '长文示例' in user or ('结语' in user and '合计' not in user):
            return 'long'
        if '短文示例' in user:
            return 'short'
        if '合计计算器' in user or '数量' in user or '单价' in user:
            return 'calc'
        raise AssertionError('unknown fixture page for stepwise stub')

    @staticmethod
    def _dispatch_count(user):
        match = re.search(r'已派发 (\d+) 次', user)
        return int(match.group(1)) if match else 0

    @staticmethod
    def _element_number(user, label):
        match = re.search(r'^(\d+)\. \S+ ' + re.escape(label) + r'\b', user, re.M)
        if not match:
            raise AssertionError('element not projected: ' + label)
        return int(match.group(1))

    def _next_action(self, user):
        chain = self._chain(user)
        count = self._dispatch_count(user)
        if CHAIN[0] == 'network' and count == 0:
            return {'action': 'back', 'task_goal': '返回上一页查看合计计算记录',
                    'last_step_result': '', 'page_name': '网页「合计计算器」',
                    'precondition': '当前为「合计计算器」', 'thought': '返回上一页',
                    'user_goal': '查看上一页记录', 'expected_result': '显示上一页'}
        if CHAIN[0] == 'select' and count == 0:
            absent = not self.select_rejected_sent
            self.select_rejected_sent = True
            return {'action': 'select', 'element': self._element_number(user, '金额单位'),
                    'option': '不存在的单位' if absent else '元',
                    'task_goal': '将金额单位设为元，数量输入20、单价输入3，计算合计',
                    'last_step_result': '' if absent else '选项不存在，上一动作未派发',
                    'page_name': '网页「合计计算器」', 'precondition': '可见「金额单位」选择框',
                    'thought': '选择计算结果所需单位', 'user_goal': '设置金额单位',
                    'expected_result': '金额单位显示元'}
        if CHAIN[0] == 'select':
            count -= 1

        def fields(page, precondition, thought, goal, expected, last, action, **extra):
            base = {'last_step_result': last, 'page_name': page, 'precondition': precondition,
                    'thought': thought, 'user_goal': goal, 'action': action,
                    'expected_result': expected}
            base.update(extra)
            return base

        if chain == 'calc':
            goal = '将「数量」输入为20、「单价」输入为3，提交计算并查看合计结果'
            steps = [
                lambda: dict(action='click', element=self._element_number(user, '数量'),
                    last_step_result='', page_name='网页「合计计算器」',
                    precondition='当前页面为「合计计算器」，可见「数量」输入框',
                    thought='先点击「数量」输入框以便输入数值', user_goal='聚焦「数量」输入框',
                    expected_result='「数量」输入框获得焦点', task_goal=goal),
                lambda: dict(action='type', element=self._element_number(user, '数量'), text='20',
                    last_step_result='「数量」输入框已获得焦点', page_name='网页「合计计算器」',
                    precondition='当前页面为「合计计算器」，「数量」输入框处于焦点',
                    thought='向「数量」输入框输入20', user_goal='输入数量20',
                    expected_result='「数量」输入框显示输入值', task_goal=goal),
                lambda: dict(action='click', element=self._element_number(user, '单价'),
                    last_step_result='「数量」输入框已显示输入的数值', page_name='网页「合计计算器」',
                    precondition='当前页面为「合计计算器」，可见「单价」输入框',
                    thought='点击「单价」输入框以便输入单价', user_goal='聚焦「单价」输入框',
                    expected_result='「单价」输入框获得焦点', task_goal=goal),
                lambda: dict(action='type', element=self._element_number(user, '单价'), text='3',
                    last_step_result='「单价」输入框已获得焦点', page_name='网页「合计计算器」',
                    precondition='当前页面为「合计计算器」，「单价」输入框处于焦点',
                    thought='向「单价」输入框输入3', user_goal='输入单价3',
                    expected_result='「单价」输入框显示输入值', task_goal=goal),
                lambda: dict(action='click', element=self._element_number(user, '计算合计'),
                    last_step_result='「单价」输入框已显示输入的数值', page_name='网页「合计计算器」',
                    precondition='当前页面为「合计计算器」，两项输入已填写，可见「计算合计」按钮',
                    thought='点击「计算合计」提交并查看结果', user_goal='提交计算',
                    expected_result='页面显示合计结果', task_goal=goal),
                lambda: dict(action='complete', status='success',
                    last_step_result='页面已切换并显示计算结果', page_name='网页「合计计算器」',
                    precondition='当前页面为「合计计算器」，结果区可见「合计结果：60.00元」',
                    thought='结果已在当前画面可见，结束任务', user_goal='确认「合计结果：60.00元」',
                    expected_result='结束任务，结果保留在画面', task_goal=goal),
            ]
        elif chain == 'long':
            goal = '在长文示例中依次打开第1至第5节，找到并显示文末结语记载数值'
            def long_step(index):
                label = '第%d节' % index
                return dict(
                    action='click', element=self._element_number(user, label + ' 目录项'),
                    last_step_result='' if index == 1 else '页面已跳转到「第%d节」' % (index - 1),
                    page_name='网页「长文示例」',
                    precondition='当前页面为「长文示例」，目录可见',
                    thought='点击目录中的「%s」跳转阅读' % label,
                    user_goal='打开%s' % label,
                    expected_result='页面跳转到%s' % label, task_goal=goal)
            steps = [lambda index=index: long_step(index) for index in range(1, 6)]
            steps.append(lambda: dict(
                action='complete', status='success',
                last_step_result='页面已跳转到「第5节」', page_name='网页「长文示例」',
                precondition='当前页面为「长文示例」，文末可见「结语：本次记载数值为五十五」',
                thought='文末结语已在当前画面可见，结束任务', user_goal='确认「结语：本次记载数值为五十五」',
                expected_result='结束任务，文末记载数值保留在画面', task_goal=goal))
        else:  # short：两条有效动作后按成功声明结束 → 宿主如实短流程失败出口
            goal = '在短文示例中滚动查看全文后结束'
            steps = [lambda: dict(
                action='scroll', direction='down', last_step_result='',
                page_name='网页「短文示例」', precondition='当前页面为「短文示例」，正文较短',
                thought='向下滚动查看全文', user_goal='查看全文',
                expected_result='显示更下方内容', task_goal=goal)]
            steps.append(lambda: dict(
                action='scroll', direction='down', last_step_result='页面已向下滚动',
                page_name='网页「短文示例」', precondition='当前页面为「短文示例」，正文较短',
                thought='再次滚动确认没有更多内容', user_goal='确认文末',
                expected_result='到达文末', task_goal=goal))
            steps.append(lambda: dict(
                action='complete', status='success', last_step_result='已到达文末，无更多内容',
                page_name='网页「短文示例」', precondition='当前页面为「短文示例」，全文已可见',
                thought='全文已阅读，结束任务', user_goal='结束任务',
                expected_result='结束任务', task_goal=goal))
        if count >= len(steps):
            raise AssertionError('stepwise stub exhausted for chain ' + chain)
        arguments = steps[count]()
        if CHAIN[0] == 'select' and count == 0:
            arguments['last_step_result'] = '「金额单位」已完成选项切换'
        return arguments

    def _writeback(self, user):
        chain = self._chain(user)
        if chain == 'calc':
            return {'task_instruction': '在「合计计算器」中将「数量」输入为20、「单价」输入为3，提交计算并查看合计结果',
                    'task_type': ['填写表单', '数据查看'],
                    'final_result': '结果区显示「合计结果：60.00元」',
                    'completion_judgement': '末帧可见「合计结果：60.00元」，与输入数量20、单价3一致'}
        if chain == 'long':
            return {'task_instruction': '在「长文示例」中向下滚动阅读，找到文末「结语」并显示记载数值',
                    'task_type': ['数据查看'],
                    'final_result': '文末显示「结语：本次记载数值为五十五」',
                    'completion_judgement': '末帧可见「结语：本次记载数值为五十五」'}
        return {'task_instruction': '在「短文示例」中滚动查看全文',
                'task_type': ['数据查看'],
                'final_result': '全文已显示', 'completion_judgement': '全文可见'}


# ---------------------------------------------------------------- 主流程
def source_snapshot():
    import hashlib
    return {str(p.relative_to(REPO)): hashlib.sha256(p.read_bytes()).hexdigest()
            for base in ('projects/code/webcollect', 'projects/site-planner/site_planner',
                         'projects/quality-inspector/quality_inspector')
            for p in sorted((REPO / base).rglob('*'))
            if p.is_file() and p.suffix in ('.py', '.js', '.json')}


def run_chain(name, entry_path, root, opener, expect_saved):
    CHAIN[0] = name
    from site_planner.candidate_pool import CandidatePool
    from webcollect.candidate_consumer import main as consumer_main, verified_saved, finish_or_reconcile
    from webcollect.candidate_project import initialize
    from webcollect.closing_policy import COMPLETED_GOAL_DELIVERY
    from webcollect.client_package import build_client_package, validate_client_layout
    from playwright.async_api import BrowserType
    from webcollect import key_health
    folder = root / name
    folder.mkdir()
    config = load_json(CODE / 'config/batch-synthetic.json')
    config['mode'] = 'real'
    config['run_id'] = 'stepwise-offline-' + name
    config['budget'].update(min_model_interval_seconds=0, max_model_cost_micros=1_000_000,
                            currency='OFFLINE_TEST_UNITS')
    config['model'].update(provider='glm', model='offline-stepwise-fixture',
                           endpoint='https://model-fixture.invalid/chat/completions',
                           api_key_env='OFFLINE_STEPWISE_KEY', supports_vision=True,
                           image_tokens_per_image=100, request_overhead_tokens=100,
                           reserve_cost_micros=1_000_000,
                           rates={'version': 'OFFLINE-TEST-NOT-PRICES',
                                  'source': 'Mock protocol only', 'input': 1_000_000,
                                  'cached_input': 500_000, 'output': 2_000_000})
    project = 'stepwise-offline-' + name + '-' + str(time.time_ns())
    scope_path = initialize(REPO / 'database/sqllite/verification' / project, project, {},
                            config, config, output_root=folder / 'collections')
    scope = load_json(scope_path)
    (folder / 'scope-reference.json').write_text(json.dumps({'scope': str(scope_path), **scope}, ensure_ascii=False, indent=2))
    pool = CandidatePool(scope['pool'])
    proof = Path(scope['pool']).parent / 'proof.json'
    proof.write_text(json.dumps({'fixture': 'stepwise offline ' + name}))
    cid = pool.put({'schema_version': 'webcollect-data-candidate-2', 'candidate_kind': 'entry',
                    'entry_url': 'http://fixture.example.org:%d%s' % (SERVER_PORT[0], entry_path),
                    'requested_goal': None},
                   {'origin': 'codex_session', 'run_id': project, 'category_hint': '在线工具',
                    'references': [{'path': str(proof), 'sha256': file_sha(proof)}]})
    args = ['--pool', scope['pool'], 'run', '--config', scope['consumer_config'],
            '--ledger', scope['consumer_db'], '--registry', scope['registry'],
            '--policy', scope['policy'], '--history-set', scope['history_set'],
            '--output', scope['output'], '--worker-id', 'stepwise-' + name,
            '--request-prefix', 'stepwise-' + name, '--limit', '1', '--stop-when-empty']
    original_launch = BrowserType.launch
    from webcollect import task_generation
    original_execute = task_generation.execute
    changed_identities = []

    async def execute_with_changed_source(ledger, plan_path, *args, **kwargs):
        planned = load_json(plan_path)['generation']['source_identity']
        changed = {**planned, 'offline_changed_source.py': 'audit-only-different-value'}
        changed_identities.append({'planned': planned, 'current': changed})
        with patch.object(task_generation, 'generation_source_identity', return_value=changed):
            return await original_execute(ledger, plan_path, *args, **kwargs)


    async def launch(self, *args, **kwargs):
        kwargs['args'] = [*kwargs.get('args', []),
                          '--host-resolver-rules=MAP fixture.example.org 127.0.0.1,MAP * ~NOTFOUND',
                          '--no-proxy-server', '--disable-background-networking']
        return await original_launch(self, *args, **kwargs)

    started = time.monotonic()
    with ExitStack() as stack:
        stack.enter_context(patch.object(BrowserType, 'launch', launch))
        stack.enter_context(patch.object(task_generation, 'execute', execute_with_changed_source))
        history_snapshot = stack.enter_context(patch('webcollect.current_chain.registry_snapshot',
            side_effect=AssertionError('full history snapshot must not be read by new consumer')))
        stack.enter_context(patch.object(key_health, 'pool_available', return_value=True))
        stack.enter_context(
            patch.object(key_health, 'probe_accounts', side_effect=AssertionError('real account probe forbidden')))
        if name == 'network':
            from playwright.async_api import Page
            # Controlled fault injection at the back-navigation boundary: use
            # real local HTTP socket closure to obtain Playwright's net::ERR.
            async def interrupted_back(page, **kwargs):
                return await page.goto('http://fixture.example.org:%d/network-broken' % SERVER_PORT[0],
                                       wait_until='domcontentloaded', timeout=10000)
            stack.enter_context(patch.object(Page, 'go_back', interrupted_back))
        code = consumer_main(args)
    logs = [json.loads(line) for path in Path(scope['output']).rglob('runtime.jsonl')
            for line in path.read_text().splitlines() if line.strip()]
    events = [row['event'] for row in logs]
    check('cli_returncode_zero', code == 0, code)
    check('execute_accepts_changed_source_identity', bool(changed_identities)
          and all(row['planned'] != row['current'] for row in changed_identities), len(changed_identities))
    check('no_full_history_snapshot_call', history_snapshot.call_count == 0, history_snapshot.call_count)
    check('runlog_strategy_stepwise', all(row.get('strategy') == 'stepwise' for row in logs), None)
    check('no_template_events', 'template_selected' not in events, events)
    check('normal_pipeline_no_program_disposition', not any(
        (row.get('failureDisposition') or {}).get('disposition') in ('page_program', 'global')
        for row in logs if row['event'] == 'candidate_finished'))
    claim = pool.get_claim(next(row['claimId'] for row in logs if row['event'] == 'claim'))
    saved = verified_saved(claim)
    if expect_saved:
        check('normal_runtime_saved_receipt', bool(saved), None)
        result = finish_or_reconcile(pool, claim)
        check('candidate_writeback_succeeded',
              result.get('saved') and pool.get_claim(claim['claim_id'])['state'] == 'succeeded', result.get('state'))
    if expect_saved and saved:
        with pool.pool.connect() as con:
            row = con.execute('SELECT effective,sample_id,record FROM candidate_results WHERE candidate_id=?',
                              (cid,)).fetchone()
        record = json.loads(row[2])
        check('candidate_result_effective_strategy',
              row[0] == 1 and row[1] == saved['sample_id'] and record.get('strategy') == 'stepwise', record.get('strategy'))
        # 客户导出读回：经正常导出入口。
        capture = Path(scope['output']) / 'execution' / 'capture'
        capture = next((path.parent for path in Path(scope['output']).rglob('bootstrap.json')
                        if path.parent.name == 'capture'), capture)
        stages = [load_json(path) for path in capture.parent.glob('delivery-stages-*.json')]
        check('cli_customer_export_completed', any(row.get('customer_export') == 'EXPORTED_FORMAT_VALID'
                                                  for row in stages), stages)
        receipt_path = capture.parent / 'candidate-receipt.json'
        check('cli_customer_export_receipt', receipt_path.is_file())
        if not receipt_path.is_file():
            raise AssertionError('normal consumer CLI did not produce candidate-receipt.json')
        client = capture.parent / 'candidate'
        expected_files = load_json(receipt_path)['files_sha256']
        actual_files = {path.relative_to(client).as_posix(): file_sha(path)
                        for path in sorted(client.rglob('*')) if path.is_file()}
        check('cli_export_receipt_readback', expected_files == actual_files, len(actual_files))
        layout = validate_client_layout(client)
        check('export_layout_valid', layout['structural_pass'] is True, layout)
        annotation = json.loads((client / 'samples' / saved['sample_id'] / 'annotation.json').read_text())
        check('export_data_type_stepwise',
              annotation['trajectory_source'] == {'source_type': 'agent', 'data_type': 'stepwise',
                                                  'action_space': 'unified_gui_v4'}, annotation['trajectory_source'])
        execution = json.loads((client / 'actual-execution.json').read_text())
        row = execution['samples'][0]
        statuses = [step['status'] for step in row['steps']]
        check('export_verified_dispatch',
              statuses[:-1] == ['VERIFIED_DISPATCH'] * (len(statuses) - 1) and statuses[-1] == 'HOST_TERMINAL',
              statuses)
        synthesis = (client / '合成方式说明.md').read_text()
        check('export_stepwise_chapter',
              '\n## stepwise\n' in synthesis and '逐步采集' in synthesis and 'next_action' in synthesis, None)
        evidence_sidecar = json.loads((client.with_name(client.name + '.evidence.json')).read_text())
        decision = evidence_sidecar['completion_delivery_decisions'][saved['sample_id']]
        check('export_delivery_eligible', decision['delivery_eligible'] is True, decision)
        check('export_sample_count', layout['samples'] == 1, layout['samples'])
    elif not expect_saved:
        check('failure_not_saved', not saved, None)
        state = pool.get_claim(claim['claim_id'])['state']
        check('failure_claim_failed', state == 'failed', state)
        sample_dirs = [path for path in (Path(scope['output'])).rglob('failure.json')]
        check('failure_receipt', bool(sample_dirs), None)
        raw = [path for path in Path(scope['output']).rglob('stepwise/raw-receipt.json')]
        check('failure_raw_retained', bool(raw), None)
        terminal = json.loads(next(path for path in Path(scope['output']).rglob('stepwise/terminal.json')).read_text())
        expected_reason = {'shortflow': 'short_flow', 'protocol': 'protocol_error', 'network': 'error'}[name]
        expected_class = {'shortflow': 'collector', 'protocol': 'model', 'network': 'network'}[name]
        check('failure_terminal_reason', terminal.get('stop_reason') == expected_reason, terminal.get('stop_reason'))
        check('failure_class', terminal.get('failure_class') == expected_class, terminal.get('failure_class'))
        check('failure_not_unknown', terminal.get('unknown') is False, terminal.get('unknown'))
        check('failure_effective_below_five', (terminal.get('effective_steps') or 0) < 5,
              terminal.get('effective_steps'))
        check('failure_skips_finalization', not list(Path(scope['output']).rglob('stepwise-finalization.json')))

    terminal = json.loads(next(Path(scope['output']).rglob('stepwise/terminal.json')).read_text())
    check('terminal_strategy_stepwise', terminal.get('strategy', {}).get('id') == 'stepwise')
    if name == 'select':
        decisions = [json.loads(path.read_text()) for path in Path(scope['output']).rglob('stepwise/decision-*.json')]
        dispatches = [json.loads(path.read_text()) for path in Path(scope['output']).rglob('stepwise/dispatch-*.json')]
        check('select_rejection_not_dispatched',
              any('SELECT_OPTION_NOT_PRESENT' in text for chain, text in opener.user_texts if chain == name)
              and not any(row['operation']['arguments'].get('option') == '不存在的单位' for row in dispatches),
              [{'option': row['operation']['arguments'].get('option')} for row in dispatches])
        check('select_corrected_then_saved', bool(saved) and terminal.get('actual_dispatches') == 6,
              terminal.get('actual_dispatches'))
    if name == 'rotated':
        states = [json.loads(path.read_text()) for path in Path(scope['output']).rglob('stepwise/observation-*.json')]
        check('rotated_subtree_recorded', any(row.get('geometry_exclusions') for row in states))
    # 同 attempt 实际HTTP（模型请求）计数：均小于40上限。
    with __import__('sqlite3').connect(scope['consumer_db']) as con:
        requests = con.execute('SELECT COUNT(*) FROM model_requests').fetchone()[0]
    check('model_requests_within_40', 0 < requests <= 40, requests)
    return {'seconds': time.monotonic() - started, 'model_requests': requests,
            'scope': str(scope_path), 'saved': bool(saved), 'claim_id': claim['claim_id']}


SERVER_PORT = [0]


def main():
    parser = __import__('argparse').ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--chain', action='append', choices=['operation', 'reading', 'shortflow', 'protocol', 'network', 'select', 'rotated'])
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    run_started = time.monotonic()
    before = source_snapshot()
    driver_sha = file_sha(__file__)
    (root / 'source-before.json').write_text(json.dumps(before, ensure_ascii=False, indent=2))
    opener = SequencedOpener()
    opener.output = root
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    SERVER_PORT[0] = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    timings = {}
    try:
        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {'OFFLINE_STEPWISE_KEY': 'offline-isolated-placeholder'}))
            stack.enter_context(patch('webcollect.model_gateway.socket.getaddrinfo',
                                      return_value=[('CONTROLLED_DNS',)]))
            # DNS 预检经 spawn 子进程解析（Table2 轮 F02 修复），monkeypatch 不入子进程；
            # 在网关接缝处离线短路，同样不产生真实 DNS 查询。
            stack.enter_context(patch('webcollect.model_gateway._qc_addresses',
                                      return_value=[('CONTROLLED_DNS',)]))
            stack.enter_context(patch('urllib.request.build_opener', return_value=opener))
            # 外部凭据边界：离线不跑真实账号探针（与既有 local_cli 先例一致）。
            stack.enter_context(patch('webcollect.key_health.unavailable_accounts', return_value=set()))
            stack.enter_context(patch('webcollect.key_health.pool_available', return_value=True))
            stack.enter_context(
                patch('webcollect.key_health.probe_accounts', side_effect=AssertionError('real account probe forbidden')))
            for name, entry, expect_saved in (('operation', '/calculator', True),
                                              ('reading', '/long-article', True),
                                              ('shortflow', '/short-article', False),
                                              ('protocol', '/calculator', False),
                                              ('network', '/calculator', False),
                                              ('select', '/calculator-select', True),
                                              ('rotated', '/calculator-rotated', True)):
                if args.chain and name not in args.chain:
                    continue
                try:
                    timings[name] = run_chain(name, entry, root, opener, expect_saved)
                except Exception as error:
                    CHAIN[0] = name
                    (root / name).mkdir(exist_ok=True)
                    (root / name / 'exception.txt').write_text(traceback.format_exc())
                    check('chain_no_exception', False, repr(error))
    finally:
        server.shutdown()
        server.server_close()
    after = source_snapshot()
    (root / 'source-after.json').write_text(json.dumps(after, ensure_ascii=False, indent=2))
    check('source_unchanged_during_run', before == after, None)
    check('driver_unchanged_during_run', driver_sha == file_sha(__file__), driver_sha)
    report = {'elapsed_seconds': time.monotonic() - run_started, 'fixture_only': True, 'external_model_requests': 0, 'external_web_requests': 0,
              'real_local_browser': True, 'mocked_boundaries': ['external_model_transport', 'network_case_back_navigation_to_local_socket_failure',
                                    'execution_source_identity_changed_audit_value', 'full_history_snapshot_must_not_run'],
              'checks': RESULTS, 'timings': timings, 'model_transport_calls': len(opener.calls),
              'customer_exports_beyond_fixture': 0, 'production_samples_added': 0,
              'passed': all(row['pass'] for row in RESULTS)}
    (root / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({key: value for key, value in report.items() if key != 'checks'},
                     ensure_ascii=False))
    return report['passed']


if __name__ == '__main__':
    raise SystemExit(0 if main() else 1)
