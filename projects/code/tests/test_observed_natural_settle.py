"""Frozen natural waits reach operations/replay without adding effective actions."""
import unittest
from webcollect.batch_core import load_json,save_json
from webcollect.observed_workflow import compile_task
from webcollect.task_admission import reference
import test_observed_workflow as fixture
class NaturalWaitBinding(unittest.TestCase):
 def setUp(self):
  self.case=fixture.ObservedWorkflowTests('runTest');self.case.setUp();self.addCleanup(self.case.doCleanups)
 def trace(self,value=1500,*,missing=False):
  t=load_json(self.case.trace_ref['path']);i=load_json(t['intent']['path']);i['natural_settle_ms']=value
  p=self.case.root/'wait-intent.json';save_json(p,i);t['intent']=reference(p)
  for n,row in enumerate(t['transitions']):
   if not(missing and n==2):row['operation'].setdefault('execution',{})['settle_ms']=value
   self.case.rewrite_receipt(row)
  p=self.case.root/'wait-trace.json';save_json(p,t);return reference(p)
 def test_bound_wait_preserves_actions_and_reaches_initial_replay(self):
  t=compile_task(self.case.cap,self.trace());self.assertEqual(t['initial_settle_ms'],1500);self.assertEqual(len(t['operations']),5)
  self.assertTrue(all(o['execution']['settle_ms']==1500 for o in t['operations']))
 def test_one_unbound_operation_rejects_the_trace(self):
  with self.assertRaisesRegex(ValueError,'frozen natural settle'):compile_task(self.case.cap,self.trace(missing=True))
 def test_invalid_frozen_wait_is_rejected(self):
  with self.assertRaisesRegex(ValueError,'natural_settle_ms'):compile_task(self.case.cap,self.trace(True))
if __name__=='__main__':unittest.main()
