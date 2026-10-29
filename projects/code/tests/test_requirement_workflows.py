"""Disposable original-frame protocol fixtures; never real source/QC evidence."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
from webcollect.batch_core import BatchLedger, file_sha, load_json, save_json
from webcollect.task_generation import compile_form, generate, VERSION, proposal_signature, customer_history_decision
from webcollect.task_admission import validate_live_completion_scroll
from webcollect.task_contract import validate_m4_task
from webcollect.workflow_proposal import compile_workflow, verify_task, SCHEMA
from test_s0_task_generation import capability, catalog, config


class WorkflowRequirements(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.record = capability(self.root / 'inventory')

    def proposal(self, category):
        record = deepcopy(self.record)
        record['site_category'] = category
        record['task_families'] = ['navigation-reading']
        record['supported_actions'] = ['click', 'type', 'scroll', 'hotkey']
        record['capabilities'][0]['forms'] = []
        elements = [{'element_id': 'control-' + str(n), 'text': label, 'visible': True, 'enabled': True,
                     'clickable': True, 'bbox': [10, 10 + 50*n, 200, 40 + 50*n]}
                    for n, label in enumerate(('查询条件', '确认查询', '显示详情'))]
        state = {'url': record['site_uri'], 'screen_resolution': [1280, 720],
                 'visible_text': '受控离线页面，查询条件、确认查询、显示详情。', 'elements': elements}
        image = self.root / 'anchor.png'; Image.new('RGB', (1280, 720), 'white').save(image)
        path = self.root / 'state.json'; save_json(path, state)
        receipt = self.root / 'capture.json'; save_json(receipt, {'screenshot_sha256': file_sha(image),
                                                                'observer_sha256': 'CONTROLLED-only'})
        ref = lambda p: {'path': str(p), 'sha256': file_sha(p)}
        anchors = [{key: ref(p) for key, p in (('image', image), ('state', path), ('capture', receipt))}]
        operations = []
        for index, (action, target) in enumerate((('click', 0), ('type', 0), ('click', 1), ('click', 2), ('scroll', None))):
            op = {'operation_id': 'op-' + str(index), 'subgoal_id': 'query', 'action_type': action,
                  'goal': '核对必要的查询内容', 'rationale': '完成离线夹具任务要求的查询', 'expected': '显示所需信息'}
            if target is not None:
                op.update(selector='#control-' + str(target), evidence={'target_label': elements[target]['text'],
                          'anchor_index': 0, 'anchor_element_id': elements[target]['element_id']})
            if action == 'type': op['arguments'] = {'text': '合成条件'}
            if action == 'scroll': op['arguments'] = {'direction': 'down'}
            operations.append(op)
        spec = {'capability_id': record['capability_id'], 'capability_version': record['version'],
                'task_family': 'navigation-reading', 'initial_url': record['site_uri'],
                'instruction': '在「受控离线页面」查询指定条件，打开详情并核对末尾的信息。',
                'task_type': ['搜索查询', '数据查看'], 'operations': operations,
                'required_actions': [op['operation_id'] for op in operations],
                'subgoals': [{'id': 'query', 'description': '查询并核对信息', 'evidence': [{'final_assertion_index': 0}]}],
                'final_assertions': [{'visible_text': '受控完成事实'}], 'final_result': '显示受控完成事实',
                'completion_judgement': '核对截图中的受控完成事实。', 'anchors': anchors}
        return record, spec

    def test_non_form_categories_use_one_generation_path_without_observation_or_admission(self):
        for index, category in enumerate(('百科文档', '工具', '小游戏')):
            with self.subTest(category=category):
                record, spec = self.proposal(category)
                task = compile_workflow(record, spec, VERSION)
                verify_task(task, record)
                proposal_file = self.root / 'proposals.json'; save_json(proposal_file, {'schema_version': SCHEMA, 'tasks': [spec]})
                with patch('webcollect.browser_planner.observe_task', side_effect=AssertionError('No rehearsal')), \
                     patch('webcollect.task_admission.attach', side_effect=AssertionError('No admission')):
                    result = generate(BatchLedger(self.root / ('batch-' + str(index) + '.sqlite3'), config(), initialize=True),
                                      catalog(self.root / ('catalog-' + str(index) + '.json'), [record]), self.root / ('out-' + str(index)),
                                      workflow_specs=proposal_file)
                self.assertEqual(result['generated_tasks'], 1)
                self.assertNotIn('task_admission', load_json(result['plan_file'])['tasks'][0])
                self.assertEqual(result['sample_ids_allocated'], 0)

    def test_invented_control_or_changed_source_cannot_be_compiled_or_published(self):
        record, spec = self.proposal('小游戏')
        task = compile_workflow(record, spec, VERSION)
        spec['operations'][0]['evidence']['target_label'] = '并不存在的按钮'
        with self.assertRaises(ValueError): compile_workflow(record, spec, VERSION)
        task['operations'][0]['selector'] = '#different'
        with self.assertRaises(ValueError): verify_task(task, record)

    def test_current_identity_is_frozen_in_generation_without_editing_the_generated_plan(self):
        from webcollect.production_identity import VERSION as IDENTITY_VERSION, validate_plan
        record, spec = self.proposal('工具')
        anchor = spec['anchors'][0]
        identity = {'version': IDENTITY_VERSION, 'application': {'canonical_uri': 'https://example.org/',
                    'name': '受控整体应用', 'evidence': [anchor['state']]},
                    'task_page': {'canonical_uri': record['site_uri'], 'aliases': [record['site_uri']],
                                 'kind': 'function', 'description': '离线查询任务页', 'anchor': anchor}, 'shared_pages': []}
        path = self.root / 'identities.json'; save_json(path, {'schema_version': 'webcollect-page-identities-1',
                                                            'pages': {record['site_uri']: identity}})
        proposals = self.root / 'proposals.json'; save_json(proposals, {'schema_version': SCHEMA, 'tasks': [spec]})
        result = generate(BatchLedger(self.root / 'identity-ledger.sqlite3', config(), initialize=True),
                          catalog(self.root / 'identity-catalog.json', [record]), self.root / 'identity-output',
                          workflow_specs=proposals, page_identities=path)
        self.assertEqual(result['generated_tasks'], 1, result)
        task = load_json(result['plan_file'])['tasks'][0]
        self.assertEqual(task['app_name'], '受控整体应用')
        self.assertEqual(task['pilot_identity'], identity)
        verify_task(task, record)
        self.assertTrue(validate_plan(load_json(result['plan_file']), required=True))

    def test_same_strategy_is_review_hint_and_parameter_change_is_not_a_different_path(self):
        record, spec = self.proposal('工具')
        task = compile_workflow(record, spec, VERSION)
        other = deepcopy(task); other['operations'][1]['arguments']['text'] = '另一个关键词'
        self.assertEqual(proposal_signature(task), proposal_signature(other))
        other['operations'].insert(3, {'action_type': 'click', 'evidence': {'target_label': '必要筛选'}})
        self.assertNotEqual(proposal_signature(task), proposal_signature(other))
        from webcollect.task_generation import deterministic_specs, semantic_signature
        form = compile_form(self.record, deterministic_specs(self.record)['tasks'][0])
        decision = customer_history_decision(form, [{'sample_id': 'CONTROLLED', 'semantic_signature': semantic_signature(form)}])
        self.assertEqual(decision['status'], 'REVIEW_REQUIRED')


class LiveCompletionView(unittest.TestCase):
    def task(self):
        conditions = [{'selector': '#result', 'contains': '结果为42'}]
        op = {'operation_id': 'reveal-complete-result', 'subgoal_id': 'result', 'action_type': 'scroll',
              'selector': '#result', 'arguments': {'direction': 'down'}, 'execution': {'distance': 200},
              'postconditions': conditions, 'completion_view': {'schema_version': 'webcollect-live-completion-view-1', 'distance': 200}}
        return {'operations': [op], 'final_assertions': conditions}, op

    def state(self):
        return {'screen_resolution': [1280, 720], 'assertion_targets': [
            {'selector': '#result', 'visible': False, 'text': '结果为42', 'bbox': [20, 600, 600, 850]}]}

    def test_current_clipped_terminal_passes_without_prior_run_or_admission(self):
        task, op = self.task()
        result = validate_live_completion_scroll(task, op, self.state())
        self.assertEqual(result['machine_status'], 'PASS')
        self.assertNotIn('proof', result)

    def test_visible_wrong_hidden_or_too_far_result_does_not_allow_padding(self):
        for changes in ({'visible': True}, {'text': '结果错误'}, {'bbox': [20, 900, 600, 1000]},
                        {'bbox': [20, 20, 600, 60]}, {'text': ''}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                state = self.state(); state['assertion_targets'][0].update(changes)
                task, op = self.task(); validate_live_completion_scroll(task, op, state)

    def test_compiler_and_m4_allow_live_view_without_legacy_admission(self):
        from webcollect.task_generation import deterministic_specs
        with tempfile.TemporaryDirectory() as directory:
            record = capability(Path(directory))
            spec = deterministic_specs(record)['tasks'][0]
            # Ordinary unknown form proposals use literal final conditions.
            spec.pop('deterministic_strategy')
            spec['completion'] = {'selector': '#result', 'contains': '结果为42'}
            spec['completion_view'] = {'schema_version': 'webcollect-live-completion-view-1', 'distance': 200}
            task = compile_form(record, spec)
            validate_m4_task(task)
            self.assertNotIn('task_admission', task)
            broken = deepcopy(task); broken['operations'][-1]['completion_view'] = {'schema_version': 'old-unbound'}
            with self.assertRaises(ValueError): validate_m4_task(broken)

    def test_registered_strategy_can_propose_a_different_necessary_result_view_path(self):
        from webcollect.task_generation import deterministic_specs, register_task, semantic_signature
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            record = capability(root)
            spec = deterministic_specs(record)['tasks'][0]
            ordinary = compile_form(record, spec)
            spec['completion_view'] = {'schema_version': 'webcollect-live-completion-view-1', 'distance': 200}
            reveal = compile_form(record, spec)
            self.assertEqual(semantic_signature(ordinary), semantic_signature(reveal))
            self.assertNotEqual(proposal_signature(ordinary), proposal_signature(reveal))
            ledger = BatchLedger(root / 'ops.sqlite3', config(), initialize=True)
            register_task(ledger, ordinary, 'ordinary')
            register_task(ledger, reveal, 'view-path')


if __name__ == '__main__':
    unittest.main()
