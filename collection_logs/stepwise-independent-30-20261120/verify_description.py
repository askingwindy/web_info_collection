"""用本地 Chrome 和正式消费者验证描述超长时只修正超限字段。"""
import importlib.util
import io
import json
from pathlib import Path
from unittest.mock import patch

driver = Path(__file__).resolve().parents[1] / 'stepwise-save30-20261120/verify_terminal.py'
spec = importlib.util.spec_from_file_location('verify_terminal', driver)
prior = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prior)
cli = prior.cli


def main():
    original_action = cli.Opener._next_action
    original_dispatch = cli.Opener._dispatch
    submitted, corrections = [], []

    def decision(opener, user):
        arguments = original_action(opener, user)
        if not submitted:
            submitted.append(dict(arguments))
            for field in ('thought', 'precondition'):
                arguments[field] = arguments[field] * 30
        return arguments

    def dispatch(opener, tool, user):
        if tool != 'repair_tool_arguments':
            return original_dispatch(opener, tool, user)
        assert '["precondition"]' in user and '["thought"]' in user
        corrections.append(tool)
        replacement = {'field_0': submitted[0]['precondition'], 'field_1': submitted[0]['thought']}
        raw = {'id': 'offline-description-length', 'model': 'offline-model-version',
               'usage': {'prompt_tokens': 900, 'completion_tokens': 60, 'prompt_tokens_details': {'cached_tokens': 120}},
               'choices': [{'finish_reason': 'tool_calls', 'message': opener._message(tool, replacement, 'offline-repair')}]}
        return io.BytesIO(json.dumps(raw).encode())

    with patch.object(cli.Opener, '_next_action', decision), patch.object(cli.Opener, '_dispatch', dispatch):
        result = cli.main()
    assert result == 0 and len(corrections) == 1
    return result


if __name__ == '__main__':
    raise SystemExit(main())
