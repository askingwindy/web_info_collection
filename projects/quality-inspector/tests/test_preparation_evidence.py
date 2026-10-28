"""Synthetic evidence plumbing only; fixtures are not visual ad/body truth."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from quality_inspector.preparation_evidence import POLICY, audit_preparation


def digest(data): return hashlib.sha256(data).hexdigest()
def write(path, value): path.write_text(json.dumps(value, ensure_ascii=False))


class PreparationEvidence(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.evidence = self.root / 'evidence'
        self.sample = self.root / 'sample'
        self.evidence.mkdir(); (self.sample / 'images').mkdir(parents=True); (self.sample / 'ui_tree').mkdir()
        self.pngs = [b'SYNTHETIC BEFORE - NOT VISUAL', b'SYNTHETIC AFTER - NOT VISUAL']
        target = {'element_id': 'close', 'element_type': 'button', 'text': '关闭', 'bbox': [80, 0, 100, 20],
                  'enabled': True, 'inputable': False, 'state': 'default'}
        self.states = [dict(url='https://public.example/', visible_text='中文推广遮罩和明确关闭按钮。',
                            screen_resolution=[100, 100], elements=[target], scroll=[0, 0]),
                       dict(url='https://public.example/', visible_text='这是关闭之后实际可见的完整中文正文。',
                            screen_resolution=[100, 100], elements=[], scroll=[0, 0])]
        self.assessment = {'page_url': self.states[0]['url'], 'decision': {'action': 'close_overlay'},
                           'obstruction': {'present': True, 'close': {'selector': '#close'}},
                           'settings': {'max_actions': 6, 'max_scrolls': 4}}
        self.records = [dict(step_id=1, state=self.states[0], capture={'screenshot_sha256': digest(self.pngs[0]), 'observer_sha256': 'full-observer'},
                             operation_origin='preparation', planned_operation_index=None, preparation_decision_id='D0001',
                             operation={'action_type': 'click', 'selector': '#close'}, target_element=target,
                             target_preflight={'matched': True}, executed_action={'tool_name': 'click', 'arguments': {'x': 90, 'y': 10}}),
                        dict(step_id=2, state=self.states[1], capture={'screenshot_sha256': digest(self.pngs[1]), 'observer_sha256': 'full-observer'},
                             operation_origin='planned', planned_operation_index=0,
                             operation={'action_type': 'complete'}, target_element=None,
                             executed_action={'tool_name': 'complete', 'arguments': {'status': 'success'}})]
        self.initial = dict(policy=POLICY, first_step_id=1, pre_action=True, state=copy.deepcopy(self.states[0]), capture=copy.deepcopy(self.records[0]['capture']))
        self.ledger = dict(schema_version=POLICY, mode='enabled', decisions=[dict(decision_id='D0001', before_step_id=1,
                           before_image_sha256=digest(self.pngs[0]), kind='close_overlay', action_step_id=1, action_executed=True,
                           after_step_id=2, after_image_sha256=digest(self.pngs[1]), assessment=self.assessment)])
        self.annotation = {'steps': [dict(step_id=i, image_path=f'images/step_{i:03}.png', ui_tree_path=f'ui_tree/step_{i:03}.json',
                            tool_call=copy.deepcopy(r['executed_action']), action=({'target_element_id':'close','target_text':'关闭','target_bbox':[80,0,100,20]} if i==1 else {}))
                            for i, r in enumerate(self.records, 1)]}
        self.flush()

    def flush(self):
        write(self.evidence / 'initial_capture.json', self.initial)
        (self.evidence / 'initial_capture.png').write_bytes(self.pngs[0])
        write(self.evidence / 'preparation_decisions.json', self.ledger)
        write(self.evidence / 'ground_truth.json', [{'step_id':1,'element_id':'close','text':'关闭','bbox':[80,0,100,20]}])
        write(self.sample / 'annotation.json', self.annotation)
        for i, record in enumerate(self.records, 1):
            write(self.evidence / f'step_{i:03}.json', record)
            (self.sample / 'images' / f'step_{i:03}.png').write_bytes(self.pngs[i-1])
            write(self.sample / 'ui_tree' / f'step_{i:03}.json', {'elements':record['state']['elements'],'screen_resolution':[100,100]})

    def audit(self):
        return audit_preparation(self.evidence, self.sample, expected_policy=POLICY, expected_observer_sha256='full-observer')

    def assertFails(self, code):
        result = self.audit()
        self.assertEqual(result['status'], 'FAIL')
        self.assertIn(code, [x['code'] for x in result['issues']])

    def test_complete_chain_does_not_claim_visual_recognition(self):
        result=self.audit(); self.assertEqual(result['status'],'PASS',result)
        self.assertEqual(result['visual_recognition_acceptance'],'REQUIRES_INDEPENDENT_IMAGE_GROUND_TRUTH')
        self.assertEqual(result['metrics']['prepared_actions'],1)

    def test_legacy_without_policy_is_explicit_not_applicable(self):
        folder=self.root/'legacy'; folder.mkdir()
        self.assertEqual(audit_preparation(folder)['status'],'NOT_APPLICABLE')

    def test_declared_policy_cannot_delete_files_and_become_legacy(self):
        (self.evidence/'initial_capture.json').unlink(); (self.evidence/'preparation_decisions.json').unlink()
        self.assertFails('MISSING_OR_INVALID_INITIAL')

    def test_discarded_advertising_first_frame_is_detected(self):
        (self.sample/'images/step_001.png').write_bytes(self.pngs[1])
        self.assertFails('INITIAL_NOT_STEP_1')

    def test_body_only_chinese_score_cannot_hide_english_initial_frame(self):
        text='Advertising promotion subscription login purchase sale.'
        self.initial['state']['visible_text']=text;self.records[0]['state']['visible_text']=text
        self.ledger['decisions'][0]['assessment']['body']={'visible':True,'text':'中文正文中文正文'}
        self.flush();self.assertFails('FULL_VIEWPORT_LANGUAGE')

    def test_inserted_step_without_after_capture_cannot_pass(self):
        del self.ledger['decisions'][0]['after_image_sha256']
        self.flush();self.assertFails('ACTION_AFTER')

    def test_guessed_close_not_from_captured_tree_cannot_pass(self):
        self.records[0]['target_element']=dict(self.records[0]['target_element'],text='不存在的关闭')
        self.flush();self.assertFails('CLOSE_TREE_TARGET')

    def test_missing_fresh_hit_preflight_cannot_pass(self):
        self.records[0]['target_preflight']={'matched':False}
        self.flush();self.assertFails('CLOSE_TARGET')

    def test_select_all_mapping_does_not_allow_an_inserted_hotkey_as_preparation(self):
        self.records[0]['executed_action']={'tool_name':'hotkey','arguments':{'keys':['meta','a']}}
        self.annotation['steps'][0]['tool_call']={'tool_name':'hotkey','arguments':{'keys':['ctrl','a']}}
        self.flush();self.assertFails('ACTION_TYPE')

    def test_preparation_action_parameter_changes_still_fail_exact_comparison(self):
        self.annotation['steps'][0]['tool_call']['arguments']['x']=89
        self.flush();self.assertFails('FORMAL_ACTION')

    def test_disabled_arm_cannot_silently_prepare(self):
        self.ledger['mode']='disabled';self.flush();self.assertFails('DISABLED_ACTION')

    def test_preparation_cannot_steal_planned_operation_index(self):
        self.records[0]['planned_operation_index']=0;self.flush();self.assertFails('RAW_ORIGIN')

    def test_executed_preparation_cannot_drop_ledger_decision(self):
        self.ledger['decisions']=[];self.flush();self.assertFails('UNACCOUNTED_PREPARATION')

    def test_forged_after_image_hash_is_detected(self):
        (self.sample/'images/step_002.png').write_bytes(b'CHANGED')
        self.assertFails('FRAME_HASH')

    def test_safe_rejection_preserves_non_chinese_initial_without_claiming_delivery(self):
        self.initial['state']['visible_text']='Actual non Chinese public page'
        write(self.evidence/'initial_capture.json',self.initial)
        for p in self.evidence.glob('step_*.json'):p.unlink()
        (self.sample/'annotation.json').unlink()
        self.ledger['decisions'][0].update(kind='blocked')
        self.ledger['decisions'][0]['action_executed']=False
        for k in ['action_step_id','after_step_id','after_image_sha256']:self.ledger['decisions'][0].pop(k,None)
        self.ledger['decisions'][0]['assessment']['decision']['action']='blocked'
        write(self.evidence/'preparation_decisions.json',self.ledger);write(self.evidence/'eligibility_failure.json',{'reason':'non_chinese'})
        result=self.audit();self.assertEqual(result['status'],'PASS',result)
        self.assertFalse(result['is_recorded_delivery']);self.assertFalse(result['metrics']['delivery_eligible_by_language'])

    def test_missing_language_observer_identity_is_not_body_observer_equivalence(self):
        self.initial['capture']['observer_sha256']='content-detector';self.flush();self.assertFails('INITIAL_OBSERVER')

    def make_scroll(self, effective=True):
        self.records[0]['operation']={'action_type':'scroll'}
        self.records[0]['target_element']=None
        self.records[0]['executed_action']={'tool_name':'scroll','arguments':{'x':50,'y':50,'direction':'down'}}
        self.annotation['steps'][0]['tool_call']=copy.deepcopy(self.records[0]['executed_action'])
        self.annotation['steps'][0]['action']={}
        self.ledger['decisions'][0]['kind']='scroll_to_content'
        self.ledger['decisions'][0]['assessment']['decision']['action']='scroll_to_content'
        self.records[1]['state']['scroll']=[0,60] if effective else [0,0]
        self.flush()

    def test_real_scroll_keeps_observed_chain_without_visual_claim(self):
        self.make_scroll();result=self.audit();self.assertEqual(result['status'],'PASS',result)
        self.assertEqual(result['metrics']['scroll_actions'],1)

    def test_noop_scroll_cannot_be_used_to_fill_steps(self):
        self.make_scroll(effective=False);self.assertFails('INEFFECTIVE_SCROLL')

    def test_declared_zero_budget_cannot_be_exceeded(self):
        self.assessment['settings']['max_actions']=0;self.flush();self.assertFails('ACTION_BUDGET_EXCEEDED')

    def test_malformed_assessment_fails_closed_without_crashing_qc(self):
        self.ledger['decisions'][0]['assessment']=[];self.flush();self.assertFails('EVIDENCE_SHAPE')

    def make_planned_close(self, with_proof=True):
        self.records[0]['operation_origin']='planned';self.records[0]['planned_operation_index']=0
        self.records[1]['planned_operation_index']=1
        d=self.ledger['decisions'][0];d.pop('action_step_id');d.pop('action_executed')
        d['performed_by_planned_close']=True
        if with_proof:
            self.records[0]['planned_close_preflight']={'matched':True,'planned_selector':'#close',
                'planned_selector_index':0,'close_selector':'#close','element_id':'close','bbox':[80,0,100,20]}
        self.flush()

    def test_real_planned_close_is_verified_without_double_counting(self):
        self.make_planned_close();result=self.audit();self.assertEqual(result['status'],'PASS',result)
        self.assertEqual(result['metrics']['prepared_actions'],0)
        self.assertEqual(result['metrics']['planned_close_matches_decision'],1)

    def test_planned_close_marker_alone_cannot_bypass_real_target_proof(self):
        self.make_planned_close(with_proof=False);self.assertFails('PLANNED_CLOSE_PROOF')

    def test_stopped_second_attempt_uses_real_capture_without_fake_action(self):
        self.records=self.records[:1];self.annotation={'steps':[]}
        self.pngs[1]=self.pngs[0]
        d=self.ledger['decisions'][0];d['after_image_sha256']=digest(self.pngs[1])
        stop=copy.deepcopy(d);stop.update(decision_id='D0002',before_step_id=2,
            before_image_sha256=digest(self.pngs[1]),action_executed=False)
        for k in ['action_step_id','after_step_id','after_image_sha256']:stop.pop(k,None)
        self.ledger['decisions'].append(stop)
        self.flush();(self.sample/'annotation.json').unlink();(self.evidence/'step_002.json').unlink()
        (self.sample/'images/step_002.png').write_bytes(self.pngs[1])
        write(self.sample/'ui_tree/step_002.json',{'elements':self.states[0]['elements'],'screen_resolution':[100,100]})
        write(self.evidence/'preparation_failure.json',{'policy':POLICY,'step_id':2,'decision_id':'D0002',
            'state':self.states[0],'capture':self.records[0]['capture'],'action_executed':False,
            'reason':'Close had no effect; stopped before repeating'})
        result=self.audit();self.assertEqual(result['status'],'PASS',result)
        self.assertFalse(result['is_recorded_delivery']);self.assertEqual(result['metrics']['prepared_actions'],1)
        self.assertEqual(result['metrics']['blocked_decisions_without_action'],1)

    def test_blocked_intent_cannot_be_counted_as_executed(self):
        self.ledger['decisions'][0]['action_executed']=False;self.flush()
        self.assertFails('EXECUTION_NOT_CONFIRMED')

    def make_goal_priority_complete(self):
        record=self.records[1]
        record['completion_trigger']='goal_already_satisfied'
        record['preparation_decision_id']='D0002'
        record['final_assertions']=[{'expected':{'visible_text':'中文正文'},'passed':True}]
        assessment=copy.deepcopy(self.assessment)
        assessment['decision']={'action':'scroll_to_content'}
        self.ledger['decisions'].append(dict(decision_id='D0002',before_step_id=2,
            before_image_sha256=digest(self.pngs[1]),kind='scroll_to_content',
            operation_origin='planned',assessment=assessment))
        self.flush()

    def test_actual_completed_goal_does_not_invent_recommended_scroll(self):
        self.make_goal_priority_complete();result=self.audit()
        self.assertEqual(result['status'],'PASS',result)
        self.assertEqual(result['metrics']['prepared_actions'],1)
        self.assertEqual(result['metrics']['goal_completion_supersedes_scroll'],1)

    def test_goal_complete_marker_with_failed_assertion_cannot_bypass(self):
        self.make_goal_priority_complete();self.records[1]['final_assertions'][0]['passed']=False
        self.flush();self.assertFails('GOAL_COMPLETION_PROOF')

    def test_goal_complete_cannot_also_claim_unexecuted_scroll(self):
        self.make_goal_priority_complete();self.ledger['decisions'][1]['action_executed']=True
        self.flush();self.assertFails('GOAL_COMPLETION_PROOF')

    def test_explicit_native_rejection_is_outcome_not_delivery_success(self):
        (self.sample/'annotation.json').unlink()
        write(self.evidence/'failure.json',{'error':'Actual final assertion did not pass','task_id':'fixed-task'})
        result=self.audit();self.assertEqual(result['status'],'PASS',result)
        self.assertFalse(result['is_recorded_delivery'])
        self.assertEqual(result['attempt_outcome'],'rejected_or_incomplete')

    def test_empty_native_failure_does_not_hide_incomplete_attempt(self):
        (self.sample/'annotation.json').unlink();write(self.evidence/'failure.json',{'error':''})
        self.assertFails('REJECTED_OUTCOME')

    def make_planned_scroll(self):
        self.make_scroll()
        self.records[0].update(operation_origin='planned',planned_operation_index=0)
        self.records[1]['planned_operation_index']=1
        self.records[0]['operation']={'action_type':'scroll','arguments':{'direction':'down'},
                                     'execution':{'distance':240}}
        self.records[0]['planned_scroll_preflight']={'matched':True,'planned_distance':240,
            'requested_preparation_distance':120,'direction':'down','decision_id':'D0001','scroll_before':[0,0]}
        d=self.ledger['decisions'][0]
        for k in ['action_step_id','action_executed','after_step_id','after_image_sha256']:d.pop(k,None)
        d.update(performed_by_planned_scroll=True,planned_operation_index=0)
        d['assessment'].update(body={'found':True,'visible':False,'bbox':{'y':90,'height':30}},
                               viewport={'height':100})
        d['assessment']['decision']['distance']=120
        self.flush()

    def test_first_real_planned_scroll_can_fulfill_preparation_once(self):
        self.make_planned_scroll();result=self.audit();self.assertEqual(result['status'],'PASS',result)
        self.assertEqual(result['metrics']['planned_scroll_matches_decision'],1)
        self.assertEqual(result['metrics']['prepared_actions'],0)

    def test_planned_scroll_marker_without_bounded_actual_proof_fails(self):
        self.make_planned_scroll();self.records[0].pop('planned_scroll_preflight');self.flush()
        self.assertFails('PLANNED_SCROLL_PROOF')

    def test_later_planned_scroll_cannot_steal_first_scroll_exception(self):
        self.make_planned_scroll();self.records[0]['planned_operation_index']=1;self.flush()
        self.assertFails('PLANNED_SCROLL_PROOF')

    def test_planned_scroll_false_distance_proof_fails(self):
        self.make_planned_scroll();self.records[0]['planned_scroll_preflight']['planned_distance']=480;self.flush()
        self.assertFails('PLANNED_SCROLL_PROOF')

    def test_planned_scroll_no_movement_cannot_pass(self):
        self.make_planned_scroll();self.records[1]['state']['scroll']=[0,0];self.flush()
        self.assertFails('PLANNED_SCROLL_PROOF')

    def test_planned_scroll_cannot_leave_already_visible_content(self):
        self.make_planned_scroll();self.ledger['decisions'][0]['assessment']['body']['visible']=True;self.flush()
        self.assertFails('PLANNED_SCROLL_PROOF')


if __name__=='__main__':unittest.main()
