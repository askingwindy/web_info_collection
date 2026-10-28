import json,tempfile,unittest
from pathlib import Path
from webcollect.production_quality import exact_conflicts
from webcollect.collect import describe_change,validate_plan
from test_annotation_regressions import state,element
class ProducerRegression(unittest.TestCase):
 def test_numeric_output_not_lost_in_button_fallback(self):
  button=element('b','计算','button',False);before=state([button],visible='计算\n结果');after=state([button],visible='计算\n结果\n20.0');result=describe_change(before,after,{'action_type':'click'},button);self.assertIn('20.0',result);self.assertNotIn('仍显示',result)
 def test_scroll_numeric_result_kept_with_page_context(self):
  before=state(visible='结果');after=state(visible='结果\n1179186\n-20.5');after['scroll']=[0,400];self.assertIn('1179186',describe_change(before,after,{'action_type':'scroll','arguments':{'direction':'down'}},None))
 def test_cross_batch_same_initial_detected_even_with_different_finals(self):
  with tempfile.TemporaryDirectory() as t:
   r=Path(t);a=r/'a/samples/first/images';b=r/'b/samples/second/images';a.mkdir(parents=True);b.mkdir(parents=True)
   (a/'step_001.png').write_bytes(b'IDENTICAL ACTUAL BYTES');(b/'step_001.png').write_bytes(b'IDENTICAL ACTUAL BYTES');(a/'step_002.png').write_bytes(b'A');(b/'step_002.png').write_bytes(b'B')
   hits=exact_conflicts(b.parent,[r]);self.assertEqual(len(hits),1);self.assertIn('first',hits[0]['other_sample']);self.assertTrue(hits[0]['not_full_trajectory_equivalence'])
 def test_self_not_duplicate_and_disjoint_frames_allowed(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'a/samples/id/images';p.mkdir(parents=True);(p/'step_001.png').write_bytes(b'one');self.assertEqual(exact_conflicts(p.parent,[Path(t),Path(t)]),[])
 def test_explicit_customer_package_root_is_checked(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);old=root/'delivered/samples/old/images';new=root/'current/samples/new/images'
   old.mkdir(parents=True);new.mkdir(parents=True)
   (old/'step_001.png').write_bytes(b'shared');(new/'step_001.png').write_bytes(b'shared')
   self.assertEqual(len(exact_conflicts(new.parent,[root/'delivered'])),1)
 def test_rejected_evidence_is_not_a_delivery_member(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);old=root/'old/rejected/old/images';new=root/'current/samples/new/images'
   old.mkdir(parents=True);new.mkdir(parents=True)
   (old/'step_001.png').write_bytes(b'shared');(new/'step_001.png').write_bytes(b'shared')
   self.assertEqual(exact_conflicts(new.parent,[root/'old']),[])
 def test_duplicate_task_ids_rejected_before_execution(self):
  import webcollect.collect as c
  # Minimal data deliberately invalid later: task identity collision checked first.
  with self.assertRaisesRegex(ValueError,'task_id'):validate_plan({'tasks':[{'task_id':'duplicate'},{'task_id':'duplicate'}]})

 def test_auth_gate_stops_but_login_document_title_is_not_an_auth_gate(self):
  from webcollect.production_quality import require_public_task_state
  with self.assertRaisesRegex(ValueError,'登录门槛'):require_public_task_state({'url':'https://example.org/user/login.aspx?from=search'})
  require_public_task_state({'url':'https://example.org/docs/login-guide.html'})
