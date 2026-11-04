"""Disposable projection and aggregate fixtures; no production I/O."""
import unittest
from copy import deepcopy
from webcollect.react_context import collection_facts
from webcollect.react_session import compact_observation

class FiveContextTests(unittest.TestCase):
    def test_unknown_and_explicit_completed_set(self):
        self.assertEqual(collection_facts()['short_flow']['status'], 'UNKNOWN')
        r=dict(scope='current-fixture',source={'path':'fixture-report','sha256':'fixture'},rules='fixture-v1',effective_set=['a','b'],short_flow=dict(status='COMPLETE',numerator=1,denominator=2))
        self.assertEqual(collection_facts(r)['short_flow']['ratio'], .5)
        self.assertEqual(collection_facts(r)['near_duplicate_unique_samples']['status'],'UNKNOWN')
        r['short_flow']['denominator']=0
        self.assertEqual(collection_facts(r)['short_flow']['status'],'UNKNOWN')

    def test_hints_never_upgrade_action_truth(self):
        for reason in ('MISSING_TARGET_PROBE','OCCLUDED','AMBIGUOUS','STALE_OBSERVATION'):
            o=dict(observation_id='o',url='u',document_identity='d',viewport=[1,1],scroll=[0,0],capture_verified=True,evidence={'image':{'path':'fixture.png'}},page_actions=[],controls={'c':dict(element={'text':'百分比 速度 公交 OSGeo'},binding={'tag':'input'},value={},readable_labels=[],probe=None,actions={'click':{'status':'INSUFFICIENT','reason':reason}})})
            old=deepcopy(o);v=compact_observation(o,['click'],bounded=True)
            self.assertEqual(v['controls']['c']['actions']['click'],'INSUFFICIENT/'+reason)
            self.assertEqual(v['controls']['c']['labels'],[])
            self.assertFalse(v['controls']['c']['hint_is_action_evidence'])
            self.assertEqual(o,old)
            self.assertEqual('next_evidence' in v['controls']['c'],reason=='MISSING_TARGET_PROBE')
