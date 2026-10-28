import os
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]))
"""Positive and mutation tests; fixture copies only, never delivery decisions."""
import copy,json,shutil,tempfile,unittest
from pathlib import Path
from PIL import Image
from quality_inspector.format_checks import sample_check,batch_check,run,load,ANNOTATION,catalog,canonical_windows_keys,windows_key_label,delivered_call_matches_capture,step_observation_issues
from make_fixture import fixture

R=Path(os.environ.get('QC_TEST_REPO',str(Path(__file__).resolve().parents[3])))
class ProxyMutations(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.p=fixture(self.root/'controlled_fixture');self.a=load(self.p/'annotation.json')
 def tearDown(self):self.tmp.cleanup()
 def save(self): (self.p/'annotation.json').write_text(json.dumps(self.a,ensure_ascii=False))
 def check(self):self.save();return sample_check(self.p)
 def has(self,rule):self.assertIn(rule,[e['rule_id'] for e in self.check()['errors']])
 def tree(self):return self.p/self.a['steps'][0]['ui_tree_path']
 def write_tree(self,t):self.tree().write_text(json.dumps(t,ensure_ascii=False))
 def test_positive_latest_sample_format_only(self):
  d=self.check();self.assertTrue(d['confirmed_format_pass']);self.assertEqual(d['customer_acceptance'],'UNKNOWN');self.assertIn('U01',d['unknown_rule_ids'])
 def test_human_and_T6_are_not_forbidden_constants(self):
  self.a['trajectory_source'].update(source_type='human',data_type='T6');self.assertTrue(self.check()['confirmed_format_pass'])
 def test_new_lineage_and_sample_id_not_fixed_to_examples(self):
  self.a['sample_id']='client-future-900';self.a['trajectory_source'].update(source_type='human_agent_hybrid',data_type='new_lineage_77',action_space='customer_mapping_v5');d=self.check();self.assertTrue(d['confirmed_format_pass']);self.assertEqual(d['customer_acceptance'],'UNKNOWN');self.assertIn('I03',[x['rule_id'] for x in d['observations']])
 def test_missing_required_field(self):del self.a['task_instruction'];self.has('C01')
 def test_wrong_string_type(self):self.a['task_instruction']=55;self.has('C01')
 def test_boolean_is_not_integer(self):self.a['steps'][0]['step_id']=True;self.has('C01')
 def test_float_is_not_integer(self):self.a['steps'][0]['step_id']=1.0;self.has('C01')
 def test_invalid_explicit_enum(self):self.a['task_type']=['自由发挥'];self.has('C03')
 def test_empty_task_type_does_not_become_sample_convention(self):self.a['task_type']=[];self.has('C03')
 def test_bad_source_enum(self):self.a['trajectory_source']['source_type']='made_up';self.has('C04')
 def test_unknown_additional_field_is_unknown_not_rejected(self):
  self.a['client_optional_note']='扩展';d=self.check();self.assertTrue(d['confirmed_format_pass']);self.assertIn('I02',[o['rule_id'] for o in d['observations']]);self.assertEqual(d['customer_acceptance'],'UNKNOWN')
 def test_missing_image(self):(self.p/self.a['steps'][0]['image_path']).unlink();self.has('C06')
 def test_invalid_png(self):(self.p/self.a['steps'][0]['image_path']).write_text('not a PNG');self.has('C06')
 def test_dimension_mismatch(self):
  Image.new('RGB',(33,22),'white').save(self.p/self.a['steps'][0]['image_path']);self.has('C06')
 def test_tree_image_mismatch(self):t=load(self.tree());t['image_path']='images/step_002.png';self.write_tree(t);self.has('C06')
 def test_tree_resolution_mismatch(self):t=load(self.tree());t['screen_resolution']=[t['screen_resolution'][0]+1,t['screen_resolution'][1]];self.write_tree(t);self.has('C06')
 def test_missing_tree(self):self.tree().unlink();self.has('C06')
 def test_broken_target(self):self.a['steps'][0]['action']['target_element_id']='no_such_element';self.has('C07')
 def test_wrong_target_text(self):self.a['steps'][0]['action']['target_text']='假控件';self.has('C07')
 def test_duplicate_tree_element(self):t=load(self.tree());t['elements'].append(copy.deepcopy(t['elements'][0]));self.write_tree(t);self.has('C07')
 def test_unresolved_parent(self):t=load(self.tree());t['elements'][0]['parent_id']='missing';self.write_tree(t);self.has('C07')
 def test_bad_box(self):self.a['steps'][0]['action']['target_bbox']=[20,20,10,10];self.has('C08')
 def test_step_sequence(self):self.a['steps'][0]['step_id']=2;self.has('C05')
 def test_extra_finder_file_is_defect_not_requirement(self):(self.p/'.DS_Store').write_bytes(b'x');self.has('C05')
 def test_tool_name_mismatch(self):self.a['steps'][0]['tool_call']['tool_name']='wait';self.has('C09')
 def test_selector_argument_forbidden(self):self.a['steps'][0]['tool_call']['arguments']['selector']='#private';self.has('C09')
 def test_bad_argument_type(self):self.a['steps'][0]['tool_call']['arguments']['x']='10';self.has('C09')
 def hotkey(self,keys,target='Ctrl+A',input_text=None):
  step=self.a['steps'][0];step['action'].update(action_type='hotkey',target_element_id='',target_text=target,coordinate=[],input_text='+'.join(keys) if input_text is None else input_text)
  step['action'].pop('target_bbox',None);step['tool_call'].update(tool_name='hotkey',arguments={'keys':keys})
 def test_select_all_delivery_is_canonical_ctrl_a_even_on_macos(self):
  self.a['device_info']['os_name']='macOS';self.hotkey(['ctrl','a']);self.assertTrue(self.check()['confirmed_format_pass'])
 def test_select_all_meta_and_noncanonical_aliases_are_rejected(self):
  for keys in (['meta','a'],['a','meta'],['Meta','A'],['command','a'],['cmd','a'],['control','a'],['a','ctrl'],['CTRL','A']):
   with self.subTest(keys=keys):
    self.hotkey(keys);errors=self.check()['errors'];self.assertTrue(any(row['rule_id']=='C09' and row['path'].endswith('/arguments/keys') for row in errors))
 def test_select_all_display_and_input_must_match_the_canonical_delivery(self):
  for target,input_text in (('Command+A','ctrl+a'),('Ctrl+A','meta+a'),('全选','ctrl+a')):
   with self.subTest(target=target,input_text=input_text):
    self.hotkey(['ctrl','a'],target,input_text);self.has('C09')
 def test_all_shortcut_delivery_uses_windows_names(self):
  for keys,target in ((['ctrl','c'],'Ctrl+C'),(['ctrl','v'],'Ctrl+V'),(['ctrl','x'],'Ctrl+X'),
                      (['ctrl','shift','v'],'Ctrl+Shift+V'),(['enter'],'Enter'),(['escape'],'Esc'),
                      (['tab'],'Tab'),(['home'],'Home'),(['arrowleft'],'Left'),(['f12'],'F12'),
                      (['ctrl','alt','shift','delete'],'Ctrl+Alt+Shift+Delete'),(['A'],'A'),(['shift'],'Shift')):
   with self.subTest(keys=keys):
    self.hotkey(keys,target);self.assertTrue(self.check()['confirmed_format_pass'])
 def test_noncanonical_platform_names_are_rejected_for_every_shortcut(self):
  for keys,target in ((['meta','c'],'Command+C'),(['meta','v'],'Command+V'),
                      (['meta','shift','a'],'Command+Shift+A'),(['enter'],'回车键'),
                      (['Return'],'Enter'),(['Esc'],'Esc'),(['Home'],'Home'),(['Left'],'Left'),
                      (['option','arrowleft'],'Option+Left'),(['ctrl','shift'],'Ctrl+Shift')):
   with self.subTest(keys=keys):
    self.hotkey(keys,target);self.has('C09')
 def test_common_macos_command_shortcuts_map_but_navigation_is_not_guessed(self):
  for key in 'acvxzsfponwtlrdgbiuk':
   self.assertEqual(canonical_windows_keys(['meta',key],'macOS'),['ctrl',key])
   self.assertEqual(canonical_windows_keys(['command','shift',key],'Darwin'),['ctrl','shift',key])
  self.assertEqual(canonical_windows_keys(['meta','2'],'macOS'),['ctrl','2'])
  for keys in (['meta','arrowleft'],['meta','backspace'],['option','arrowleft'],
               ['meta','shift','2'],['meta','q'],['meta','ctrl','v'],['ctrl','ctrl','v'],
               ['a','meta'],['ctrl','a','b'],[' ctrl','v'],['DefinitelyNotAKey']):
   with self.subTest(keys=keys):
    with self.assertRaisesRegex(ValueError,'WINDOWS_SHORTCUT_MAPPING_REQUIRED'):
     canonical_windows_keys(keys,'macOS')
 def test_source_platform_distinguishes_windows_meta_from_command(self):
  self.assertEqual(canonical_windows_keys(['Meta','v'],'Windows'),['win','v'])
  self.assertEqual(canonical_windows_keys(['Meta'],'Windows'),['win'])
  self.assertEqual(canonical_windows_keys(['windows','v']),['win','v'])
  for platform in (None,'','Linux','Windows'):
   with self.subTest(platform=platform):
    with self.assertRaises(ValueError):canonical_windows_keys(['command','v'],platform)
  for platform in (None,'','Linux'):
   with self.subTest(platform=platform):
    with self.assertRaises(ValueError):canonical_windows_keys(['meta','v'],platform)
  self.assertEqual(canonical_windows_keys(['A']),['A'])
  self.assertEqual(canonical_windows_keys(['Control','A']),['ctrl','a'])
 def test_raw_mapping_preserves_all_other_fields_and_parameters(self):
  raw={'tool_name':'hotkey','arguments':{'keys':['meta','v']}}
  delivered={'tool_name':'hotkey','arguments':{'keys':['ctrl','v']}}
  before=copy.deepcopy(raw)
  self.assertTrue(delivered_call_matches_capture(raw,delivered,'macOS'))
  self.assertEqual(raw,before)
  self.assertFalse(delivered_call_matches_capture(raw,delivered,'Windows'))
  for altered in ({'tool_name':'hotkey','arguments':{'keys':['meta','c']}},
                  {'tool_name':'hotkey','arguments':{'keys':['meta','v'],'extra':True}},
                  {'tool_name':'hotkey','arguments':{'keys':['meta','v']},'extra':True},
                  {'tool_name':'click','arguments':{'keys':['meta','v']}}):
   with self.subTest(altered=altered):self.assertFalse(delivered_call_matches_capture(altered,delivered,'macOS'))
 def test_step_failure(self):self.a['steps'][0]['tool_result']['status']='error';self.has('C10')
 def test_missing_final_complete(self):self.a['steps'][-1]['action']['action_type']='wait';self.a['steps'][-1]['tool_call'].update(tool_name='wait',arguments={});self.has('C10')
 def test_forbidden_red_circle_not_accepted_from_examples(self):self.a['steps'][0]['action']['precondition']='红圈标注输入框';self.has('C12')
 def test_step_result_rejects_explicit_review_deferral_and_generic_execution_receipts(self):
  for text in ('已执行本步动作并保存后续实际视口；具体可见变化待独立审核。',
               '已完成本步操作，实际结果待人工复核。','点击成功。',
               '已执行本步动作并保存后续实际视口。',
               '已执行本步动作并保存操作后的截图；待人工核对。',
               '已记录本步结果。','页面发生变化。','操作已完成；可进入下一步。'):
   with self.subTest(text=text):
    self.a['steps'][0]['step_result']=text
    errors=self.check()['errors']
    self.assertTrue(any(e['rule_id']=='C12' and e['path']=='steps/1/step_result' for e in errors),errors)
 def test_step_result_rejects_repeated_scroll_navigation_numerals(self):
  self.a['steps'][0]['step_result']='页面向下滚动，可见文字包括「， 二 ， 二 ， 二 ， 二 ， ？」和「搜索梦溪笔谈」'
  self.has('C12')
 def test_actual_ui_states_and_meaningful_quotations_are_not_placeholder_violations(self):
  for text in ('页面显示「待审核」，提交按钮变为不可用。',
               '页面显示「具体可见变化待独立审核」这条原文提示。',
               '页面向下滚动，目录中的「卷二」「卷三」进入视口。',
               '页面向下滚动，可见正文「一石重百二十斤」。',
               '页面向下滚动，可见正文「一、二、三、四」的编号说明。',
               '输入框仍显示「张三」，页面没有变化。',
               '已记录结果「每石一百二十斤」。',
               '已保存「结果.json」截图。',
               '页面已打开「卷三」，首段可见「石重百二十斤」。',
               '输入框中的原有内容已全部选中。'):
   with self.subTest(text=text):
    self.assertEqual(step_observation_issues(text),[])
    self.a['steps'][0]['step_result']=text
    self.assertTrue(self.check()['confirmed_format_pass'])
 def test_step_result_observation_rule_does_not_reinterpret_other_fields(self):
  self.a['steps'][0]['action']['target_text']='待审核'
  tree=load(self.tree());target=next(e for e in tree['elements'] if e['element_id']==self.a['steps'][0]['action']['target_element_id']);target['text']='待审核';self.write_tree(tree)
  self.a['steps'][0]['action']['expected_result']='待人工核对结果'
  self.assertTrue(self.check()['confirmed_format_pass'])
 def test_task_book_titles_outside_corner_quotes_fail(self):
  for text in ['阅读《秋声赋》并核对劝诫句。','阅读“《秋声赋》”并核对劝诫句。','」阅读《秋声赋》并核对劝诫句。','阅读「原文《甲书》」以及《乙书》并核对结果。']:
   with self.subTest(text=text):
    self.a['task_instruction']=text;d=self.check();e=next(e for e in d['errors'] if e['rule_id']=='C12');self.assertEqual(e['path'],'task_instruction');self.assertIn('§6',e['message'])
 def test_task_quoted_original_book_marks_are_preserved(self):
  for text in ['阅读「原文提到《国家规划》以及具体实施」并核对结果。','阅读「外句「内句《原书》」原文」并核对结果。']:
   with self.subTest(text=text):self.a['task_instruction']=text;self.assertTrue(self.check()['confirmed_format_pass'])
 def test_task_approved_corner_title_format_passes(self):
  self.a['task_instruction']='阅读欧阳修「秋声赋」并核对劝诫句。';self.assertTrue(self.check()['confirmed_format_pass'])
 def test_book_marks_in_ordinary_step_prose_do_not_inherit_task_only_gate(self):
  self.a['steps'][0]['action']['precondition']='当前页面显示文章《秋声赋》。';self.a['steps'][0]['next_step_rationale']='继续阅读《秋声赋》的正文。';self.a['final_result']='当前《秋声赋》结果完整可见。';self.assertTrue(self.check()['confirmed_format_pass'])
 def test_task_title_rule_keeps_exact_target_text_authority_separate(self):
  t=load(self.tree());target_id=self.a['steps'][0]['action']['target_element_id'];target=next(e for e in t['elements'] if e['element_id']==target_id);target['text']='《原文名称》';self.a['steps'][0]['action']['target_text']='《原文名称》';self.write_tree(t);self.assertTrue(self.check()['confirmed_format_pass'])
 def test_path_escape(self):self.a['steps'][0]['image_path']='../outside.png';self.has('C06')
 def test_nonfinite_json(self):(self.p/'annotation.json').write_text('{"steps": NaN}');self.assertFalse(sample_check(self.p)['confirmed_format_pass'])
 def test_minimal_batch_missing_contract_files(self):
  b=self.root/'batch';b.mkdir();d=batch_check(b,[]);self.assertEqual(len(d['errors']),3);self.assertFalse(d['confirmed_batch_contract_pass'])
 def test_missing_ground_truth_is_explicit_batch_gap(self):
  d=batch_check(self.root,[self.check()]);self.assertIn('C14',[e['rule_id'] for e in d['errors']])
 def test_bad_checksum_detected(self):
  (self.root/'metadata.csv').write_text(','.join(['sample_id','site_id','site_category','app_name','task_type','task_instruction','steps','screen_resolution','completion_status','actions','bytes'])+'\n');(self.root/'qc_report.md').write_text('测试夹具，非交付结论');(self.root/'SHA256SUMS').write_text('0'*64+'  qc_report.md\n');d=batch_check(self.root,[]);self.assertTrue(any('SHA256SUMS entry' in e['message'] for e in d['errors']))
 def test_original_examples_have_documented_task_type_defect(self):
  for p in (R/'request/web操作采集需求/samples').glob('*/annotation.json'):
   d=sample_check(p.parent);self.assertFalse(d['confirmed_format_pass']);self.assertEqual(d['errors'][0]['rule_id'],'C03')
 def test_exact_duplicate_route_is_separate_from_format_without_historical_data(self):
  root=self.root/'duplicates';first=fixture(root);second=first.with_name('fixture_second');shutil.copytree(first,second)
  a=load(second/'annotation.json');a['sample_id']=second.name;(second/'annotation.json').write_text(json.dumps(a,ensure_ascii=False))
  d=run(R,root);self.assertEqual(d['confirmed_sample_format_pass'],2);self.assertEqual(d['confirmed_duplicate_pair_count'],1);self.assertFalse(d['confirmed_quality_pass']);self.assertEqual(d['customer_acceptance'],'UNKNOWN')
 def test_empty_input_is_not_format_pass(self):
  d=run(R,self.root);self.assertEqual(d['package_errors'][0]['rule_id'],'C05')
 def test_empty_checksum_manifest_does_not_count_as_complete(self):
  from quality_inspector.format_checks import CSV_FIELDS
  (self.root/'metadata.csv').write_text(','.join(CSV_FIELDS)+'\n');(self.root/'qc_report.md').write_text('仅测试文件，不声称质检通过');(self.root/'SHA256SUMS').write_text('');d=batch_check(self.root,[]);self.assertTrue(any(e['rule_id']=='C13' for e in d['errors']))
 def test_catalog_marks_authority_and_unknowns(self):
  rules=catalog();self.assertTrue(any(x['certainty']=='unknown' for x in rules));self.assertTrue(any(x['certainty']=='inferred' for x in rules));self.assertTrue(all(x['sources'] for x in rules));self.assertEqual(ANNOTATION['properties']['trajectory_source']['properties']['data_type']['type'],'string')
if __name__=='__main__':unittest.main(verbosity=2)
