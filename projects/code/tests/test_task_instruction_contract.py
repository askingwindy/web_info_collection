"""Task punctuation gates; fixtures stay in temporary directories."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from test_client_package import REPO, fixture, write
from webcollect.client_package import build_client_package, sample_hashes, validate_client_sample
from webcollect.collect import validate_plan
from webcollect.task_instruction import unquoted_book_titles, validate_task_instruction


def reading_plan(instruction):
    return {'tasks': [{
        'task_id': 'punctuation-fixture', 'site_uri': 'https://example.org/',
        'site_category': '教育', 'app_name': '临时合成测试',
        'instruction': instruction, 'task_type': ['数据查看'],
        'initial_url': 'https://example.org/reading',
        'operations': [{'action_type': 'scroll', 'goal': '继续阅读相关正文',
                        'rationale': '查找任务所求原句', 'expected': '显示下一段正文'}
                       for _ in range(5)],
        'final_result': '所求原句完整可见', 'completion_judgement': '最终视口显示原句',
        'final_assertions': [{'visible_text': '测试原句'}],
    }]}


class TaskInstructionScanner(unittest.TestCase):
    def test_nested_source_quotes_stay_verbatim_and_outer_titles_are_found(self):
        instruction = '查找「原句「作者谈《诗经》」与《楚辞》」并阅读《史记》和《汉书》。'
        self.assertEqual(unquoted_book_titles(instruction), ['《史记》', '《汉书》'])
        with self.assertRaisesRegex(ValueError, '按需求用「」括起原题名'):
            validate_task_instruction(instruction)

    def test_names_in_corner_quotes_and_embedded_original_titles_are_allowed(self):
        instruction = '阅读「史记」，找出「原句「参考《诗经》」及《楚辞》的说明」。'
        self.assertEqual(unquoted_book_titles(instruction), [])
        validate_task_instruction(instruction)

    def test_pairing_errors_are_outside_this_scanner_scope(self):
        self.assertEqual(unquoted_book_titles('阅读《未闭合标题'), [])
        self.assertEqual(unquoted_book_titles('原句」后阅读《史记》'), ['《史记》'])

    def test_new_collection_plan_rejects_outer_book_title(self):
        with self.assertRaisesRegex(ValueError, 'task_instruction'):
            validate_plan(reading_plan('阅读《史记》，查找测试原句。'))

    def test_new_collection_plan_preserves_titles_inside_quoted_original(self):
        validate_plan(reading_plan('阅读「史记」，查找「参考《诗经》」这句原文。'))


class TaskInstructionExport(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source'
        self.sample = fixture(self.source)
        self.annotation = json.loads((self.sample / 'annotation.json').read_text())

    def save(self, instruction):
        annotation = copy.deepcopy(self.annotation)
        annotation['task_instruction'] = instruction
        write(self.sample / 'annotation.json', annotation)
        return annotation

    def test_strict_customer_gate_rejects_task_outer_book_title(self):
        self.save('阅读《史记》，查找「参考《诗经》」这句原文。')
        with self.assertRaisesRegex(ValueError, 'task_instruction'):
            validate_client_sample(self.sample)

    def test_general_narratives_keep_book_titles(self):
        annotation = self.save('阅读「史记」，查找「参考《诗经》」这句原文。')
        annotation['steps'][0]['user_goal'] = '核对《史记》的正文'
        annotation['steps'][0]['step_result'] = '页面显示《史记》的正文'
        annotation['final_result'] = '《史记》的正文显示完整'
        write(self.sample / 'annotation.json', annotation)
        self.assertEqual(validate_client_sample(self.sample), annotation)

    def test_legacy_raw_is_auditable_but_cannot_export_without_cited_revision(self):
        before_text = '阅读《史记》，查找「参考《诗经》」这句原文。'
        after_text = '阅读「史记」，查找「参考《诗经》」这句原文。'
        self.save(before_text)
        before = sample_hashes(self.sample)
        self.assertEqual(validate_client_sample(self.sample, allow_legacy_narrative=True)
                         ['task_instruction'], before_text)
        with self.assertRaisesRegex(ValueError, 'task_instruction'):
            build_client_package(REPO, self.source, self.root / 'unrevised')
        self.assertFalse((self.root / 'unrevised').exists())
        revision_path = self.root / 'revisions.json'
        write(revision_path, {
            'schema_version': 'webcollect-narrative-revisions-1',
            'author': 'AI synthetic regression, not real review',
            'prompt': '只修任务外层题名括号，保留已引用原句内书名号及原始证据。',
            'samples': [{
                'sample_id': self.sample.name,
                'annotation_sha256': before['annotation.json'],
                'evidence_sha256': {k: v for k, v in before.items() if k != 'annotation.json'},
                'edits': [{'path': 'task_instruction', 'before': before_text, 'after': after_text,
                           'evidence': ['images/step_001.png', 'ui_tree/step_001.json']}],
            }],
        })
        result = build_client_package(REPO, self.source, self.root / 'revised', revisions=revision_path)
        target = Path(result['output']) / 'samples' / self.sample.name
        self.assertEqual(validate_client_sample(target)['task_instruction'], after_text)
        after = sample_hashes(target)
        self.assertEqual({k: v for k, v in before.items() if k != 'annotation.json'},
                         {k: v for k, v in after.items() if k != 'annotation.json'})
        self.assertEqual(before, sample_hashes(self.sample))
        revised = json.loads((target / 'annotation.json').read_text())
        original = json.loads((self.sample / 'annotation.json').read_text())
        original['task_instruction'] = after_text
        self.assertEqual(revised, original)


if __name__ == '__main__':
    unittest.main()
