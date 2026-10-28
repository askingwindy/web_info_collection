"""Independent negative cases from the 200-case production failures."""
import copy
import unittest

from webcollect.collect import validate_plan, observed_excerpt
from webcollect.task_contract import (PLAN_SCHEMA, validate_m4_task, validate_m4_plan,
    completion_decision, terminal_evidence, narrative_evidence)


def m4_task():
    return {'task_id':'timer-fixture','task_version':'1','site_uri':'https://example.org/',
        'site_category':'工具','app_name':'受控计时器','initial_url':'https://example.org/timer',
        'instruction':'开始并暂停「五分钟」计时器，核对暂停结果。','task_type':['数据查看'],
        'stop_when_final':True,'final_result':'五分钟计时器已暂停','completion_judgement':'实际核对暂停',
        'final_assertions':[{'visible_text':'五分钟'}],
        'required_actions':['start','pause'],
        'subgoals':[{'id':'start-goal','description':'实际开始计时',
                     'evidence':[{'operation_id':'start','postcondition_index':0}]},
                    {'id':'pause-goal','description':'实际暂停计时',
                     'evidence':[{'operation_id':'pause','postcondition_index':0},{'final_assertion_index':0}]}],
        'operations':[
            {'operation_id':'start','subgoal_id':'start-goal','action_type':'click','selector':'#start',
             'evidence':{'target_label':'开始'},'goal':'开始计时','rationale':'任务明确要求开始','expected':'已开始',
             'postconditions':[{'visible_text':'已开始'}],'execution':{'settle_ms':0}},
            {'operation_id':'pause','subgoal_id':'pause-goal','action_type':'click','selector':'#pause',
             'evidence':{'target_label':'暂停'},'goal':'暂停计时','rationale':'任务明确要求暂停','expected':'已暂停',
             'postconditions':[{'visible_text':'已暂停'}],'execution':{'settle_ms':0}}]}


def declarations():
    return {'accounts_and_privacy':'本地受控页面，不访问生产网站或账号。',
            'narrative_generation':'固定测试计划与采集器模板。','narrative_mode':'mixed',
            'prompt_stages':{
                'planning':{'mode':'model','description':'本受控任务实际规划输入','prompt':'测试实际开始与暂停，不能仅设置后宣布完成。'},
                'narrative':{'mode':'template','description':'采集器的可见状态描述','template_version':'m4-visible-evidence-1'}}}


class M4TaskContract(unittest.TestCase):
    def test_new_plan_requires_precapture_facts_and_version_but_legacy_stays_readable(self):
        task=m4_task();plan={'schema_version':PLAN_SCHEMA,'tasks':[task],'production_facts':declarations()}
        self.assertTrue(validate_m4_plan(plan))
        legacy={'tasks':[copy.deepcopy(task)]};self.assertFalse(validate_m4_plan(legacy))
        for mutate in (lambda p:p.pop('production_facts'),
                       lambda p:p['production_facts']['prompt_stages']['planning'].pop('prompt'),
                       lambda p:p['tasks'][0].pop('task_version'),
                       lambda p:p['tasks'][0].update(stop_when_final=False)):
            bad=copy.deepcopy(plan);mutate(bad)
            with self.assertRaises(ValueError):validate_m4_plan(bad)

    def test_dangling_subgoal_and_nonexecuting_required_actions_are_rejected(self):
        for mutate in (lambda t:t['required_actions'].append('invented'),
                       lambda t:t['operations'][0].update(action_type='wait'),
                       lambda t:t['subgoals'][0]['evidence'][0].update(postcondition_index=12),
                       lambda t:t['operations'][0].update(subgoal_id='absent'),
                       lambda t:t['operations'][0].update(observation='预先声称已经成功')):
            task=m4_task();mutate(task)
            with self.assertRaises(ValueError):validate_m4_task(task)

    def test_literal_target_does_not_skip_required_start_pause_or_permit_padding(self):
        task=m4_task()
        self.assertEqual(completion_decision(task,[],task['operations'][0]),'required_action_pending')
        started={'operation':task['operations'][0],'operation_origin':'planned','ended_at':'now'}
        self.assertEqual(completion_decision(task,[started],task['operations'][1]),'required_action_pending')
        with self.assertRaisesRegex(ValueError,'not a remaining required action'):
            completion_decision(task,[started],{'operation_id':'unrelated-scroll'})
        failed={**started,'execution_error':'click failed'}
        with self.assertRaisesRegex(ValueError,'required actions'):
            terminal_evidence(task,[failed],[],{})

    def test_execution_and_bound_postconditions_do_not_claim_semantic_approval(self):
        task=m4_task();rows=[]
        for op in task['operations']:
            rows.append({'operation':op,'operation_origin':'planned','ended_at':'now',
                         'postconditions_saved_frame':{'assertions':[{'passed':True,'actual':op['expected']}],
                                                      'binding':{'screenshot_sha256':'fixture-sha'}}})
        result=terminal_evidence(task,rows,[{'passed':True,'actual':'五分钟'}],{'screenshot_sha256':'final-sha'})
        self.assertEqual(result['machine_status'],'PASS')
        self.assertEqual(result['semantic_status'],'REVIEW_REQUIRED')
        self.assertEqual(result['subgoals'][0]['evidence'][0]['binding']['screenshot_sha256'],'fixture-sha')
        rows[0].pop('postconditions_saved_frame')
        with self.assertRaisesRegex(ValueError,'saved-frame'):terminal_evidence(task,rows,[{'passed':True}],{})

    def test_hidden_dom_value_is_not_repeated_as_visible_narrative(self):
        before={'visible_text':'输入数据','elements':[]}
        after={'visible_text':'输入数据 已暂停','elements':[{'text':'后台完整长串'}]}
        safe,evidence=narrative_evidence('控件显示「后台完整长串」',before,after,{'operation_id':'pause'})
        self.assertIsNone(safe)
        self.assertEqual(evidence['unsupported_quotes'],['后台完整长串'])
        self.assertEqual(evidence['machine_status'],'REVIEW_REQUIRED')
        safe,evidence=narrative_evidence('当前可见「已暂停」',before,after,{})
        self.assertEqual(safe,'当前可见「已暂停」')
        self.assertEqual(evidence['semantic_status'],'REVIEW_REQUIRED')

    def test_coordinate_sentence_boundary_remains_complete(self):
        actual='位置东经118。 30分52秒，北纬31。29分35秒。第二句。'
        self.assertEqual(observed_excerpt(actual),'位置东经118。 30分52秒，北纬31。29分35秒。')


if __name__=='__main__':unittest.main()
