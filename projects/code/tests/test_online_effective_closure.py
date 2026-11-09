"""V5 online closeout must use the same raw no-change proof as sealing."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from webcollect.batch_core import file_sha
from webcollect.closing_policy import EFFECTIVE_VERSION, VERSION
from webcollect.react_session import ReactSession


def state():
    return {'url':'https://example.org/tool','title':'Tool','document_identity':{'origin':123},
            'scroll':{'x':0,'y':0},'values':{'amount':'1000'},'elements':[],
            'visible_text':'Result: 100'}


class OnlineEffectiveClosureTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def save(self,name,value):
        path=self.root/name;path.write_text(json.dumps(value))
        return {'path':str(path),'sha256':file_sha(path)}

    def session(self,changed=False):
        a=state();b=deepcopy(a)
        if changed:b['values']['amount']='2000'
        after=self.save('after.json',b)
        raws=[]
        for i in range(3):
            raw={'dispatched':True,'action_executed':True,'postconditions_checked':i==0,'state':a,
                 'operation':{'action_type':'click'},'react':{'after_observation_id':'final','zero_effect':i!=0,
                 'effect_evidence':{'verified':i==0}}}
            raws.append(self.save(f'raw{i}.json',raw))
        refs=[self.save(f'attempt{i}.json',{'actual_dispatches_delta':1,'effective_steps_delta':int(i==0),
             'outcome':'VERIFIED' if i==0 else 'EFFECT_NOT_VERIFIED','raw_steps':[raw]}) for i,raw in enumerate(raws)]
        return SimpleNamespace(task={'fragment':{'ending_policy':EFFECTIVE_VERSION}},plan_controller=None,
            actual_dispatches=3,trajectory=[{'after_observation_id':'final'}],unknown=False,
            business_attempt_refs=refs,current={'observation_id':'final','evidence':{'state':after}},
            observation_records={'final':{'evidence':{'state':after}}},event=lambda *args,**kwargs:None)

    def test_online_accepts_multiple_original_no_change_dispatches(self):
        session=self.session()
        ReactSession._range_close(session,'KNOWN_NO_EFFECT','preserve original evidence')
        self.assertTrue(session.collection_ending['safe_for_pending_sample'])
        self.assertFalse(session.collection_ending['external_effect_unknown'])
        self.assertEqual(session.collection_ending['attempt_limit'],10)
        self.assertEqual(session.collection_ending['unverified_tail_dispatches'],2)

    def test_online_rejects_label_only_proof_when_original_value_changed(self):
        session=self.session(changed=True)
        ReactSession._range_close(session,'KNOWN_NO_EFFECT','unverified value change')
        self.assertFalse(session.collection_ending['safe_for_pending_sample'])
        self.assertTrue(session.collection_ending['external_effect_unknown'])

    def test_effective_limit_kind_is_budget_stop(self):
        session=self.session();session.actual_dispatches=10
        session.trajectory=[{'after_observation_id':'final'}]*10
        session.business_attempt_refs=[]
        ReactSession._range_close(session,'TEN_EFFECTIVE_STEP_LIMIT','effective ceiling')
        self.assertEqual(session.stop_reason,'budget')

    def test_close_budget_prefix_counts_effective_steps_after_more_than_ten_attempts(self):
        class CapturedClose(Exception):pass
        session=SimpleNamespace(_raw_receipt=None,state='recording',trajectory=[{}]*5,
            _v2=lambda:True,task={'fragment':{'ending_policy':EFFECTIVE_VERSION}},
            plan_controller=None,stop_reason='budget',stop_summary='ceiling',unknown=False,
            business_attempt_refs=[{'path':str(i)} for i in range(12)],actual_dispatches=12,
            observation_records={})
        captured={}
        def close(kind,reason,**kwargs):
            captured.update(kind=kind,**kwargs);raise CapturedClose
        session._range_close=close
        # This test stops before file sealing; raw proof is tested above. The
        # 12-attempt journal must not invalidate a five-effective-step prefix.
        with patch('webcollect.react_session.load_json',return_value={'actual_dispatches_delta':1,'outcome':'EFFECT_NOT_VERIFIED','raw_steps':[]}):
            with self.assertRaises(CapturedClose):ReactSession._close(session)
        self.assertEqual(captured['kind'],'MODEL_BUDGET_LIMIT')
        self.assertFalse(captured['force_pending'])
