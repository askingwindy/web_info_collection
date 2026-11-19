"""沿既有六条本地消费者 CLI 链验证无页名、过长标题、显式焦点编号与真正的全选覆盖。"""
import importlib.util
from pathlib import Path
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[1] / 'stepwise-consumer-repair-20261118/local_cli.py'
spec = importlib.util.spec_from_file_location('local_stepwise_cli', BASE)
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)
TITLE = '参数计算器的数量调整、单位换算与结果说明以及示例输入输出说明和详细资料'


def main():
    original_html = cli.base.html
    original_decision = cli.Opener._next_action

    def html(title, body):
        return original_html(TITLE if title == '参数计算' else title, body)

    def decision(opener, user):
        args = original_decision(opener, user)
        args.pop('page_name')
        if cli.base.CHAIN[0] == 'overwrite' and args['action'] == 'hotkey':
            args.update(page_name=TITLE, keys=['Ctrl+A'], element=opener._element_number(user, '数量'))
        return args

    with patch.object(cli.base, 'html', html), patch.object(cli.Opener, '_next_action', decision):
        return cli.main()


if __name__ == '__main__':
    raise SystemExit(main())
