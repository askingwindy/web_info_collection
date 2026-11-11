"""V5 online closeout must use the same raw no-change proof as sealing."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from webcollect.batch_core import file_sha
from webcollect.plan_protocol import ENDING_POLICY as EFFECTIVE_VERSION
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
        self.assertIsNone(session.collection_ending['attempt_limit'])
        self.assertEqual(session.collection_ending['unverified_tail_dispatches'],2)

    def test_online_rejects_label_only_proof_when_original_value_changed(self):
        session=self.session(changed=True)
        ReactSession._range_close(session,'KNOWN_NO_EFFECT','unverified value change')
        self.assertFalse(session.collection_ending['safe_for_pending_sample'])
        self.assertTrue(session.collection_ending['external_effect_unknown'])
