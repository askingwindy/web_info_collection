"""Local Chrome / normal consumer CLI regression; no external model or website.

Reuse the archived, read-only CLI harness for scope creation and receipt checks.
New pages and scripted model answers exercise current product code only.
"""
import argparse
import importlib.util
import json
import os
import re
import threading
import time
import traceback
from contextlib import ExitStack
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    'previous_local_harness', HERE.parent / 'stepwise-switch-20261118/stepwise_offline.py')
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)

CASES = ('tabs', 'expand', 'popup', 'slowlink', 'extend', 'overwrite')
TITLES = {'tabs': '专题资料', 'expand': '展开资料', 'extend': '专题资料',
          'popup': '藏品资料', 'slowlink': '藏品资料', 'overwrite': '参数计算'}


class Handler(base.Handler):
    def serve(self, method, body):
        path = urlsplit(self.path).path
        if path in ('/popup', '/slowlink'):
            target = ' target="_blank"' if path == '/popup' else ''
            content = base.html('藏品入口', '<h1>藏品入口</h1><p>查看藏品的专题、年代、材质和展览资料。</p>'
                '<a href="/details"' + target + '>查看藏品资料</a>')
        elif path in ('/tabs', '/extend', '/details'):
            if path == '/details':
                time.sleep(1.0)  # longer than the old 500ms post-click delay
            count = 4 if path == '/details' else 5
            title = '藏品资料' if count == 4 else '专题资料'
            buttons = ''.join('<button onclick="document.getElementById(\'panel\').textContent=\'%s\'">'
                '资料第%d项</button>' % ('专题资料已全部展示' if i == count else '专题资料第%d项内容' % i, i)
                for i in range(1, count + 1))
            content = base.html(title, '<h1>' + title + '</h1>' + buttons
                + '<p id="panel">请依次查看本专题的详细资料。</p>')
        elif path == '/expand':
            buttons = ''.join('<button onclick="document.getElementById(\'p%d\').hidden=false">'
                '展开第%d项</button><p id="p%d" hidden>%s</p>'
                % (i, i, i, '专题资料已全部展示' if i == 5 else '藏品的第%d项补充说明' % i)
                for i in range(1, 6))
            content = base.html('展开资料', '<style>p{margin:3px}button{font-size:18px;padding:4px;margin:4px}</style>'
                '<h1>展开资料</h1>' + buttons)
        elif path == '/overwrite':
            content = base.html('参数计算', '<h1>参数计算</h1><label for="quantity">数量</label>'
                '<input id="quantity" aria-label="数量" value="100">'
                '<button onclick="document.getElementById(\'result\').textContent=\'计算结果：\'+document.getElementById(\'quantity\').value">计算结果</button>'
                '<button onclick="document.getElementById(\'note\').hidden=false">展开说明</button>'
                '<p id="result">尚未计算</p><p id="note" hidden>专题资料已全部展示</p>')
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(content)))
        self.end_headers()
        self.wfile.write(content)


class Opener(base.SequencedOpener):
    def __init__(self):
        super().__init__()
        self.short_complete = False
        self.writebacks = {}

    @staticmethod
    def _dispatch_count(user):
        match = re.search(r'已派发 (\d+)(?:/\d+)? 次', user)
        if not match:
            raise AssertionError('dispatch progress missing')
        return int(match.group(1))

    def _next_action(self, user):
        name = base.CHAIN[0]
        count = self._dispatch_count(user)
        title = '藏品入口' if name in ('popup', 'slowlink') and count == 0 else TITLES[name]
        goal = ('查看专题前三项资料' if name == 'extend' and not self.short_complete
                else '查看本页全部五项专题资料和补充说明')
        if name == 'overwrite':
            goal = '将数量的默认值100替换为50，计算结果并展开说明'
        args = dict(action='click', task_goal=goal, last_step_result='上一操作的结果已经显示' if count else '',
                    page_name='网页「' + title + '」', precondition='当前可见「' + title + '」',
                    thought='按任务查看下一项资料', user_goal='查看下一项资料', expected_result='显示对应内容')
        if name == 'extend' and count == 3 and not self.short_complete:
            self.short_complete = True
            return {**args, 'action': 'complete', 'status': 'success'}
        if count == 5:
            return {**args, 'action': 'complete', 'status': 'success',
                    'thought': '全部任务结果已显示',
                    'user_goal': '确认「' + title + '」中的「专题资料已全部展示」',
                    'expected_result': '保留当前结果并结束'}
        if name in ('tabs', 'extend'):
            label = '资料第%d项' % (count + 1)
        elif name == 'expand':
            label = '展开第%d项' % (count + 1)
        elif name in ('popup', 'slowlink'):
            label = '查看藏品资料' if count == 0 else '资料第%d项' % count
        elif name == 'overwrite':
            if count == 1:
                return {**args, 'action': 'hotkey', 'keys': ['cmd', 'a'], 'user_goal': '全选数量原值'}
            if count == 2:
                return {**args, 'action': 'type', 'element': self._element_number(user, '数量'),
                        'text': '50', 'user_goal': '输入新数量'}
            label = ('数量', '', '', '计算结果', '展开说明')[count]
        else:
            raise AssertionError(name)
        return {**args, 'element': self._element_number(user, label)}

    def _writeback(self, user):
        name = base.CHAIN[0]
        self.writebacks[name] = self.writebacks.get(name, 0) + 1
        result = '「专题资料已全部展示」'
        if name == 'extend' and self.writebacks[name] == 1:
            result = '「不存在的结果」'  # field-valid but wrong quote -> exactly one rewrite
        instruction = '在「%s」中依次查看各项专题资料，并显示全部查看完成的结果' % TITLES[name]
        if name == 'overwrite':
            instruction = '在「参数计算」中将「数量」的默认值替换为50，计算结果并展开说明'
            result = '「计算结果：50」，并显示「专题资料已全部展示」'
        return dict(task_instruction=instruction, task_type=['数据查看'],
                    final_result='页面显示' + result, completion_judgement='末帧可见' + result)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--case', action='append', choices=CASES)
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    before = base.source_snapshot()
    driver_sha = base.file_sha(__file__)
    (root / 'source-before.json').write_text(json.dumps(before, indent=2))
    opener = Opener()
    opener.output = root
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    base.SERVER_PORT[0] = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    started = time.monotonic()
    timings = {}
    try:
        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {'OFFLINE_STEPWISE_KEY': 'offline-isolated-placeholder'}))
            stack.enter_context(patch('webcollect.model_gateway.socket.getaddrinfo', return_value=[('CONTROLLED_DNS',)]))
            stack.enter_context(patch('webcollect.model_gateway._qc_addresses', return_value=[('CONTROLLED_DNS',)]))
            stack.enter_context(patch('urllib.request.build_opener', return_value=opener))
            stack.enter_context(patch('webcollect.key_health.unavailable_accounts', return_value=set()))
            stack.enter_context(patch('webcollect.key_health.pool_available', return_value=True))
            stack.enter_context(patch('webcollect.key_health.probe_accounts', side_effect=AssertionError('external probe forbidden')))
            for name in args.case or CASES:
                try:
                    timings[name] = base.run_chain(name, '/' + name, root, opener, True)
                    output = root / name
                    terminal = json.loads(next(output.rglob('stepwise/terminal.json')).read_text())
                    base.check('five_effective_actions', terminal['effective_steps'] == 5, terminal['effective_steps'])
                    base.check('single_judgement', len(list(output.rglob('judgement.json'))) == 1)
                    feedbacks = list(output.rglob('planning-feedback-collected_pending_review.json'))
                    base.check('feedback_images_exist', bool(feedbacks) and all(
                        Path(step['image']['path']).is_file() and base.file_sha(step['image']['path']) == step['image']['sha256']
                        for f in feedbacks for step in json.loads(f.read_text())['steps']))
                    if name == 'extend':
                        base.check('one_short_complete_rejection', len(list(output.rglob('complete-rejection-*.json'))) == 1)
                        base.check('one_writeback_rewrite', len(list(output.rglob('writeback-*.json'))) == 2)
                    if name in ('popup', 'slowlink'):
                        navigation = json.loads(next(output.rglob('navigation-001.json')).read_text())
                        base.check('navigation_observed', navigation['navigation_observed'], navigation)
                        base.check('correct_page_mode', navigation['method'] == ('popup' if name == 'popup' else 'same_tab'))
                except Exception as error:
                    (root / (name + '-exception.txt')).write_text(traceback.format_exc())
                    base.check('chain_no_exception', False, repr(error))
    finally:
        server.shutdown()
        server.server_close()
    after = base.source_snapshot()
    (root / 'source-after.json').write_text(json.dumps(after, indent=2))
    base.check('source_unchanged', before == after)
    base.check('driver_unchanged', driver_sha == base.file_sha(__file__))
    report = dict(passed=all(c['pass'] for c in base.RESULTS), elapsed_seconds=time.monotonic()-started,
                  checks=base.RESULTS, timings=timings, external_model_requests=0, external_web_requests=0,
                  production_samples_added=0, model_transport_calls=len(opener.calls),
                  qc='NOT_RUN', human_review='NOT_RUN', published=False, acceptance='UNKNOWN')
    (root / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != 'checks'}, ensure_ascii=False))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
