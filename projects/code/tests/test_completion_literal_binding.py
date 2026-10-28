"""Regression for a real terminal TypeError: no models, browser or real fixtures."""
from copy import deepcopy
import unittest
from webcollect.browser_planner import whole_page_literal_assertion
from webcollect.collect import assert_state
class WholePageLiteralBinding(unittest.TestCase):
 def setUp(self):
  self.state={'visible_text':'图书甲\n作者甲\n出版社甲','elements':[{'element_id':'visible-title','text':'图书甲（完整标题）','visible':True,'bbox':[1,2,100,30]}]}
 def test_locating_hint_is_verified_and_retained_without_changing_predicate_scope(self):
  c={'target_element_id':'visible-title','visible_text':'图书甲'};before=deepcopy((c,self.state))
  a,b=whole_page_literal_assertion(c,self.state)
  self.assertEqual(a,{'visible_text':'图书甲'});self.assertEqual(b['locator_hint']['element_id'],'visible-title')
  self.assertEqual((c,self.state),before)
 def test_null_hint_keeps_the_existing_whole_page_predicate(self):
  a,b=whole_page_literal_assertion({'target_element_id':None,'visible_text':'作者甲'},self.state)
  self.assertEqual(a,{'visible_text':'作者甲'});self.assertIsNone(b['locator_hint'])
 def test_hidden_absent_wrong_or_mixed_evidence_cannot_complete(self):
  cases=[{'target_element_id':'missing','visible_text':'图书甲'}, {'target_element_id':None,'visible_text':'计划期望但不在页面'}, {'target_element_id':'visible-title','visible_text':'作者甲'}, {'target_element_id':'visible-title','visible_text':'图书甲','value':'x'}]
  for c in cases:
   with self.subTest(c=c),self.assertRaises(ValueError):whole_page_literal_assertion(c,self.state)
  self.state['elements'][0]['visible']=False
  with self.assertRaises(ValueError):whole_page_literal_assertion({'target_element_id':'visible-title','visible_text':'图书甲'},self.state)
class StrictAssertionShape(unittest.IsolatedAsyncioTestCase):
 async def test_hybrid_selector_is_rejected_clearly_instead_of_none_target_crash(self):
  with self.assertRaisesRegex(ValueError,'cannot also bind'):
   await assert_state(None,[{'selector':'#invented','visible_text':'图书甲'}],{'assertion_targets':[None],'visible_text':'图书甲'})
 async def test_canonical_original_frame_literal_remains_valid_with_none_target(self):
  r=await assert_state(None,[{'visible_text':'图书甲'}],{'assertion_targets':[None],'visible_text':'图书甲'})
  self.assertTrue(r[0]['passed']);self.assertEqual(r[0]['actual'],'图书甲')
if __name__=='__main__':unittest.main()
