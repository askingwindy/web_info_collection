"""Adversarial customer release gate tests; synthetic fixtures are never delivery data."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from test_client_package import fixture, write, REPO
from webcollect.client_package import build_client_package, validate_client_sample, sample_hashes, sha


class ContractRelease(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.sample = fixture(self.root / 'source')
        self.original = json.loads((self.sample / 'annotation.json').read_text())

    def test_delivery_gate_rejects_known_invalid_states(self):
        mutations = {
            'failed': lambda a: a.update(completion_status='failed'),
            'tool_error': lambda a: a['steps'][0]['tool_result'].update(status='error'),
            'error_message': lambda a: a['steps'][0]['tool_result'].update(error='错误'),
            'no_complete': lambda a: a['steps'][-1].update(action={**a['steps'][-1]['action'], 'action_type':'wait'},tool_call={**a['steps'][-1]['tool_call'],'tool_name':'wait','arguments':{}}),
            'infeasible': lambda a: a['steps'][-1]['tool_call']['arguments'].update(status='infeasible'),
            'empty_final': lambda a: a.update(final_state_image=''),
            'generic_goal': lambda a: a['steps'][-1].update(user_goal='确认最终页面符合任务要求'),
            'wrong_final': lambda a: a.update(final_state_image='images/step_001.png'),
            'missing_target': lambda a: a['steps'][0]['action'].update(target_element_id=''),
            'missing_bbox': lambda a: a['steps'][0]['action'].pop('target_bbox'),
            'out_of_bounds': lambda a: a['steps'][0]['action'].update(coordinate=[999,999]),
            'tool_mismatch': lambda a: a['steps'][0]['tool_call'].update(tool_name='double_click'),
            'extra_parameter': lambda a: a['steps'][0]['tool_call']['arguments'].update(selector='#private'),
            'missing_tree': lambda a: a['steps'][0].update(ui_tree_path=''),
            'no_changed': lambda a: a['steps'][0]['tool_result'].update(return_value={}),
            'wrong_input': lambda a: a['steps'][1]['action'].update(input_text='错误'),
            'noninput_text': lambda a: a['steps'][0]['action'].update(input_text='不应存在'),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                a=copy.deepcopy(self.original); mutate(a); write(self.sample/'annotation.json',a)
                self.assertRaises(ValueError, validate_client_sample, self.sample)

    def test_visible_enabled_parent_and_short_flow_rules(self):
        tree_path=self.sample/'ui_tree/step_001.json'; original=json.loads(tree_path.read_text())
        for mutation in [{'visible':False},{'enabled':False},{'parent_id':'missing'},{'parent_id':'e_1'}]:
            with self.subTest(mutation=mutation):
                t=copy.deepcopy(original);t['elements'][0].update(mutation);write(tree_path,t)
                self.assertRaises(ValueError,validate_client_sample,self.sample)
        write(tree_path,original)
        a=copy.deepcopy(self.original)
        a['steps'][4]['action'].update(action_type='wait')
        a['steps'][4]['tool_call'].update(tool_name='wait')
        write(self.sample/'annotation.json',a)
        self.assertRaisesRegex(ValueError,'five effective',validate_client_sample,self.sample)
        a.update(short_flow=True,short_flow_reason='受控单元测试中的真实短任务')
        write(self.sample/'annotation.json',a)
        self.assertEqual(validate_client_sample(self.sample)['short_flow'],True)

    def test_evidence_bound_revision_preserves_images_trees_and_actions(self):
        before=sample_hashes(self.sample)
        plan={'schema_version':'webcollect-narrative-revisions-1','prompt':'对照实际图树，只修正叙述，不修改动作或图片。','author':'AI unit-test fixture',
              'samples':[{'sample_id':self.sample.name,'annotation_sha256':sha(self.sample/'annotation.json'),'evidence_sha256':{k:v for k,v in before.items() if k!='annotation.json'},
                          'edits':[{'path':'steps/5/user_goal','before':self.original['steps'][-1]['user_goal'],'after':'确认测试最终页面显示完成结果',
                                    'evidence':['images/step_006.png','ui_tree/step_006.json']}]}]}
        path=self.root/'revisions.json';write(path,plan)
        result=build_client_package(REPO,self.root/'source',self.root/'client',revisions=path)
        target=Path(result['output'])/'samples'/self.sample.name
        after=sample_hashes(target)
        self.assertEqual({k:v for k,v in before.items() if k!='annotation.json'},{k:v for k,v in after.items() if k!='annotation.json'})
        self.assertEqual(json.loads((target/'annotation.json').read_text())['steps'][-1]['user_goal'],'确认测试最终页面显示完成结果')
        self.assertEqual(before,sample_hashes(self.sample))
        plan['samples'][0]['edits'][0]['path']='steps/0/tool_call/arguments/x';write(path,plan)
        self.assertRaisesRegex(ValueError,'narrative',build_client_package,REPO,self.root/'source',self.root/'bad',revisions=path)

    def test_allowed_empty_device_and_noncontrol_fields(self):
        a=copy.deepcopy(self.original);a['device_info'].update(device_model='',os_name='',os_version='')
        write(self.sample/'annotation.json',a)
        self.assertEqual(validate_client_sample(self.sample)['device_info']['os_name'],'')


if __name__=='__main__':unittest.main()
