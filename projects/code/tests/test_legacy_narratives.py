"""Portable regressions from minimized authentic captured inputs."""
from pathlib import Path
import unittest,json
from webcollect.collect import describe_change, visible_numeric_context
from test_annotation_regressions import state
FIXTURE=json.loads((Path(__file__).resolve().parent/'fixtures/legacy-narratives-real.json').read_text())
def change(batch,sid,step):
 case=FIXTURE['cases'][sid+':'+str(step)]
 before=FIXTURE['captures'][case['before_capture']]['state']
 after=FIXTURE['captures'][case['after_capture']]['state']
 return describe_change(before,after,case['operation'],case['target_element'])
class LegacyCriticalResults(unittest.TestCase):
 def test_sort_result_visible_after_scroll(self):
  v=change('M2-tools-repair-001','S000003_sample_000012',8)
  self.assertIn('输出结果',v);self.assertTrue('10 7 2 -1' in v or all(n in v for n in ['10','7','2','-1']),v)
 def test_entropy_value_and_unit(self):
  v=change('M2-tools-repair-001','S000003_sample_000010',9)
  self.assertIn('2.0000',v);self.assertIn('bit',v)
 def test_entropy_table_columns_explain_values(self):
  v=change('M2-tools-repair-001','S000003_sample_000010',10)
  self.assertIn('概率',v);self.assertIn('0.2500',v);self.assertIn('贡献熵值',v);self.assertIn('0.5000',v)
 def test_vue_target_prefix_resolves_visible_heading(self):
  v=change('M2-reading-navigation-001','S000005_sample_000002',4)
  self.assertIn('同一页面定位到',v);self.assertIn('可以',v);self.assertIn('setup()',v)
 def test_chushibiao_scroll_keeps_meaningful_inline_paragraph(self):
  v=change('M2-reading-navigation-001','S000004_sample_000006',5)
  self.assertIn('亲贤臣',v);self.assertIn('远小人',v)
 def test_chushibiao_final_scroll_keeps_last_paragraph(self):
  v=change('M2-reading-navigation-001','S000004_sample_000006',7)
  self.assertIn('鞠躬尽瘁',v)
class EvidenceCounterexamples(unittest.TestCase):
 def test_input_numbers_and_result_label_without_result_body_are_not_output(self):
  body=state([{'text':'10 7 2 -1','element_type':'input','inputable':True,'clickable':True}],visible='输出结果\n10 7 2 -1')
  self.assertEqual(visible_numeric_context(body),'')
 def test_unseen_column_name_is_not_inferred(self):
  head={'native_role':'th','text':'概率','bbox':[0,10,100,30]}
  cell={'native_role':'td','text':'0.2500','bbox':[0,31,100,51]}
  body=state([head,cell],visible='概率\n0.2500\n0.5000')
  self.assertNotIn('贡献熵值',visible_numeric_context(body))
 def test_ambiguous_heading_prefix_does_not_claim_arrival(self):
  heads=[{'native_role':'h2','text':x} for x in ['如何使用接口甲','如何使用接口乙']]
  before=state();after=state(heads,visible='如何使用接口\n如何使用接口甲\n这是甲章节的实际正文说明，包含完整中文句子。\n如何使用接口乙\n这是乙章节的实际正文说明，包含完整中文句子。')
  after['url']+='#section';target={'text':'如何使用接口','element_type':'link','inputable':False,'state':'default'}
  text=describe_change(before,after,{'action_type':'click'},target)
  self.assertNotIn('定位到',text)
 def test_accessible_heading_without_visible_heading_is_not_arrival(self):
  before=state();after=state([{'native_role':'h2','text':'如何使用接口甲'}],visible='目录\n如何使用接口\n这一段实际可见普通文字，并非所需章节正文。')
  after['url']+='#section';target={'text':'如何使用接口','element_type':'link','inputable':False,'state':'default'}
  self.assertNotIn('定位到',describe_change(before,after,{'action_type':'click'},target))
 def test_goal_selects_no_unseen_paragraph_words(self):
  para={'native_role':'p','text':'这是当前真正可见的完整正文段落，其中不含计划所期望的秘密结果。'}
  before=state();after=state([para],visible=para['text']);after['scroll']=[0,300]
  result=describe_change(before,after,{'action_type':'scroll','arguments':{'direction':'down'},'goal':'找到不存在的星际作者末段','expected':'星际作者为天外人'},None)
  self.assertNotIn('星际作者',result);self.assertNotIn('天外人',result)
if __name__=='__main__':unittest.main(verbosity=2)
