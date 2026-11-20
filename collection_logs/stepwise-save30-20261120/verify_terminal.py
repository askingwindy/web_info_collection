"""本地 Chrome、正式消费者和模拟模型传输，验证同一终态最多一次字段修正。"""
import importlib.util
import io
import json
from pathlib import Path
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / 'stepwise-consumer-repair-20261118/local_cli.py'
spec = importlib.util.spec_from_file_location('local_cli', SOURCE)
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


def main():
    original_decision = cli.Opener._next_action
    original_dispatch = cli.Opener._dispatch
    corrected = []

    def decision(opener, user):
        args = original_decision(opener, user)
        if args.get('action') == 'complete':
            args.pop('status')
            args['task_goal'] = '查' * 88
        return args

    def dispatch(opener, tool, user):
        if tool != 'repair_tool_arguments':
            return original_dispatch(opener, tool, user)
        assert '["status"]' in user and '["task_goal"]' in user, user[-250:]
        corrected.append(tool)
        raw = {'id': 'offline-terminal-fields', 'model': 'offline-model-version',
               'usage': {'prompt_tokens': 900, 'completion_tokens': 60, 'prompt_tokens_details': {'cached_tokens': 120}},
               'choices': [{'finish_reason': 'tool_calls', 'message': opener._message(tool, {
                   'field_0': 'success', 'field_1': '查看本页全部五项专题资料和补充说明'}, 'offline-repair-1')}]}
        return io.BytesIO(json.dumps(raw).encode())

    with patch.object(cli.Opener, '_next_action', decision), patch.object(cli.Opener, '_dispatch', dispatch):
        status = cli.main()
        assert status == 0 and len(corrected) == 1
    return status


if __name__ == '__main__':
    raise SystemExit(main())
