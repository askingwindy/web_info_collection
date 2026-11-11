"""Direct evidence counterexamples for identity hydration and V5 closure."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from webcollect.batch_core import file_sha
from webcollect.plan_protocol import ENDING_POLICY as EFFECTIVE_VERSION
from webcollect.closing_policy import (attempt_limit, no_effect_proven, validate_record)
from webcollect.production_identity import content_anchor_corroborated


def frame():
    return {'url':'https://example.org/article','title':'Article',
            'document_identity':{'performance_time_origin':123,'url_without_fragment':'https://example.org/article'},
            'scroll':{'x':0,'y':0},'values':{'input':'1000'},
            'elements':[{'element_id':'paragraph','visible':True,'text':'article body'}],
            'visible_text':'article body'}


class IdentityClosureEffectiveTests(unittest.TestCase):
    def test_article_sentences_survive_ui_hydration_and_viewport_clip(self):
        a=frame(); sentence='房地产指覆盖土地并永久附着于土地的一类实物的产权归属。随着个人财产所有权的发展，房地产已经成为商业交易的主要组成部分。购买房地产是一种重要的投资方式。'
        sentence=sentence*2
        a['text_blocks']=[{'element_id':'paragraph','complete_sentences':[sentence]}]
        b=deepcopy(a);b['visible_text']='外观 编辑 公告\n'+a['visible_text'];b['scroll']={'x':0,'y':20}
        self.assertTrue(content_anchor_corroborated(a,b))
        for field,value in [('document_identity',{'performance_time_origin':456}),('url','https://example.org/other'),('title','Other')]:
            wrong=deepcopy(b);wrong[field]=value
            self.assertFalse(content_anchor_corroborated(a,wrong))
        wrong=deepcopy(b);wrong['text_blocks'][0]['complete_sentences']=['unrelated article body'*10]
        self.assertFalse(content_anchor_corroborated(a,wrong))

    def test_zero_effect_proof_rejects_value_change_missing_after_and_unproven_label(self):
        a=frame();raw={'dispatched':True,'action_executed':True,'state':a,
            'operation':{'action_type':'click'},'react':{'zero_effect':True,'after_observation_id':'after','effect_evidence':{'verified':False}}}
        self.assertTrue(no_effect_proven(raw,{'after':deepcopy(a)}))
        b=deepcopy(a);b['values']['input']='2000'
        self.assertFalse(no_effect_proven(raw,{'after':b},action_scoped=True))
        self.assertFalse(no_effect_proven(raw,{}))
        raw['react']['zero_effect']=False
        self.assertFalse(no_effect_proven(raw,{'after':a}))

    def test_v5_replays_multiple_proven_no_effect_dispatches_but_rejects_gap(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            def save(name,value):
                path=root/name;path.write_text(json.dumps(value));return {'path':str(path),'sha256':file_sha(path)}
            a=frame();state_ref=save('state.json',a);attempts=[];trajectory=[]
            for i in range(1,13):
                raw={'dispatched':True,'action_executed':True,'postconditions_checked':i==1,'state':a,
                     'operation':{'action_type':'click'},'react':{'zero_effect':i!=1,'after_observation_id':'final',
                         'effect_evidence':{'verified':i==1}}}
                ref=save(f'raw-{i}.json',raw)
                if i==1:trajectory.append({'raw_step':ref,'after_observation_id':'final'})
                attempts.append(save(f'attempt-{i}.json',{'kind':'business-attempt','number':i,'raw_steps':[ref],
                    'actual_dispatches_delta':1,'effective_steps_delta':int(i==1),'outcome':'VERIFIED' if i==1 else 'EFFECT_NOT_VERIFIED'}))
            marker={'protocol':EFFECTIVE_VERSION,'attempt_limit':None,'attempt_band':None,'kind':'VISIBLE_GOAL_REPORTED',
                    'attempt_refs':attempts,'business_attempts':12,'actual_atomic_dispatches':12,
                    'verified_effective_steps':1,'unverified_tail_dispatches':11,'safe_for_pending_sample':True}
            record={'task':{'fragment':{'ending_policy':EFFECTIVE_VERSION}},'trajectory':trajectory,
                    'observations':{'final':{'state_path':state_ref['path']}},
                    'terminal':{'collection_ending':marker,'actual_actions':12,'final_observation_id':'final'}}
            self.assertTrue(validate_record(record)['safe_for_pending_sample'])
            record['terminal']['unknown']=True
            with self.assertRaises(ValueError):validate_record(record)
            record['terminal']['unknown']=False
            # A real changed value is never a harmless bridge.
            ref=attempts[-1];attempt=json.loads(Path(ref['path']).read_text());rawref=attempt['raw_steps'][0]
            raw=json.loads(Path(rawref['path']).read_text());raw['state']['values']['input']='999'
            attempt['raw_steps']=[save('changed.json',raw)];attempts[-1]=save('changed-attempt.json',attempt)
            with self.assertRaises(ValueError):validate_record(record)
