"""Customer terminal narratives stay concise without weakening visible evidence."""
import unittest
from unittest.mock import patch

from webcollect.postprocess import natural_instruction, terminal_judgement, terminal_outcome


VISIBLE = '''目录
月食类型
外观
文本
标准
大阳光经过地球大气层时发生散射，因此月全食时的月球是暗红、红铜、或橙色的。
参考文献
Five Millennium Catalog of Lunar Eclipses
维基共享资源'''
OBSERVED = '当前可见「月食」，可见文字「因此月全食时的月球是暗红、红铜、或橙色的。」'


def task():
    return {
        'app_name': 'zh.wikipedia.org',
        'instruction': '阅读月食正文并核对地月位置关系',
        'fragment': {'ending_policy': 'webcollect-test-ending', 'allow_controlled_exception': False},
    }


def record(working_goal='从「月食」词条逐段阅读，用正文说明月球与地球的位置关系'):
    return {
        'terminal': {'working_goal': working_goal, 'stop_reason': 'ready'},
        'trajectory': [
            {'semantic_goal': '完整阅读月食类型段落，确认三种类型及其与地球阴影的关系'},
            {'semantic_goal': '阅读「没有月环食」一节，核实仍留在伪本影的原因'},
        ],
    }


def outcome(state=None, task_value=None, record_value=None, observed=OBSERVED, dialog=''):
    with patch('webcollect.collect.visible_result_description', return_value=dialog), \
         patch('webcollect.collect.observed_frame_description', return_value=observed):
        return terminal_outcome(task_value or task(), record_value or record(), state or {
            'title': '月食', 'visible_text': VISIBLE, 'elements': [],
        })


class TerminalNarrativeTests(unittest.TestCase):
    def test_instruction_uses_working_goal_once_without_generic_suffix(self):
        value = natural_instruction(task(), record(), 5)
        self.assertEqual(value, '在「zh.wikipedia.org」上从「月食」词条逐段阅读，用正文说明月球与地球的位置关系')
        self.assertNotIn('没有月环食', value)
        self.assertNotIn('查看实际输入与页面结果', value)

    def test_instruction_fallback_preserves_executed_goals_without_generic_suffix(self):
        value = natural_instruction(task(), record(working_goal=''), 2)
        self.assertIn('完整阅读月食类型段落', value)
        self.assertIn('阅读「没有月环食」一节', value)
        self.assertNotIn('查看实际输入与页面结果', value)

    def test_terminal_result_does_not_append_navigation_and_reference_viewport(self):
        status, value = outcome()
        self.assertEqual(status, 'success')
        self.assertEqual(value, OBSERVED)
        self.assertNotIn('目录', value)
        self.assertNotIn('参考文献', value)
        self.assertNotIn('维基共享资源', value)
        self.assertNotIn('末帧可见文字', value)

    def test_direct_completion_selected_passage_remains_scoped(self):
        direct_task = task()
        direct_task['fragment']['direct_completion_protocol'] = 'webcollect-direct-reading-completion-1'
        direct_record = record()
        direct_record['terminal']['goal_evidence'] = {'session_objective': {
            'status': 'VERIFIED', 'selected_passage': {'quote': '独立复核正文'},
        }}
        with patch('webcollect.direct_completion.enabled', return_value=True), \
             patch('webcollect.direct_article.body', return_value=[{'quote': '独立复核正文'}]), \
             patch('webcollect.collect.visible_result_description', return_value=''), \
             patch('webcollect.collect.observed_frame_description', return_value=OBSERVED):
            status, value = terminal_outcome(direct_task, direct_record, {
                'title': '月食', 'visible_text': VISIBLE, 'elements': [],
            })
        self.assertEqual(status, 'success')
        self.assertEqual(value, '当前正文可见「独立复核正文」')

    def test_dialog_result_keeps_priority_over_generic_observation(self):
        status, value = outcome(dialog='查询结果已展开；表格按原顺序可见「数值」')
        self.assertEqual(status, 'success')
        self.assertEqual(value, '查询结果已展开；表格按原顺序可见「数值」')

    def test_empty_terminal_text_and_blocked_status_keep_original_semantics(self):
        status, _ = outcome(state={'title': '空白', 'visible_text': '', 'elements': []})
        self.assertEqual(status, 'failed')
        blocked = record()
        blocked['terminal']['stop_reason'] = 'blocked'
        status, _ = outcome(record_value=blocked)
        self.assertEqual(status, 'failed')

    def test_judgement_names_terminal_basis_without_claiming_success_for_failure(self):
        success = terminal_judgement('success', OBSERVED)
        failed = terminal_judgement('failed', OBSERVED)
        self.assertEqual(success, '末帧完成判定依据：' + OBSERVED)
        self.assertEqual(failed, '末帧状态判定依据：' + OBSERVED)
        self.assertNotEqual(success, OBSERVED)
        self.assertNotIn('完成判定', failed)


if __name__ == '__main__':
    unittest.main()
