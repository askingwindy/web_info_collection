"""Actual prompt quotations must not become production placeholders or topics."""
from pathlib import Path
import tempfile
import unittest

from quality_inspector.engine import _delivery_documents


class PromptQuotationChecks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / '来源与合规说明.md').write_text('采集方式 访问频率策略 账号与脱敏 站点清单')
        self.topics = '动作映射 坐标 界面变化判定 文字字段生成方式\n'

    def check(self, text):
        (self.root / '合成方式说明.md').write_text(text)
        return _delivery_documents(self.root, {'configuration': {'attachments': {}}})[0]

    def test_actual_user_prompt_unknown_is_preserved_as_a_quote(self):
        result = self.check(self.topics + '实际提示词：\n\n```text\n客户验收仍为UNKNOWN。\n```\n')
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['unresolved_placeholders'], [])
        self.assertEqual(result['quoted_prompt_literal_markers'], ['UNKNOWN'])
        self.assertTrue(result['semantic_authenticity_not_proven_by_keywords'])

    def test_real_placeholder_outside_prompt_still_fails(self):
        result = self.check(self.topics + '实际提示词：\n```text\n客户UNKNOWN\n```\n坐标来源：待填写\n')
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual(result['unresolved_placeholders'], ['待填写'])

    def test_unlabelled_or_unclosed_quote_still_fails(self):
        for text in ('```text\nUNKNOWN\n```\n', '实际提示词：\n```text\nUNKNOWN\n'):
            with self.subTest(text=text):
                self.assertEqual(self.check(self.topics + '提示词\n' + text)['status'], 'FAIL')

    def test_configuration_fence_is_not_a_prompt_exemption(self):
        result = self.check(self.topics + '实际提示词：\n```json\n{"frequency":"UNKNOWN"}\n```\n')
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual(result['unresolved_placeholders'], ['UNKNOWN'])

    def test_topics_inside_prompt_do_not_fill_missing_documentation(self):
        result = self.check('实际提示词：\n```text\n' + self.topics + '\n```\n')
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual(len(result['missing_topics']), 4)


if __name__ == '__main__':
    unittest.main()
