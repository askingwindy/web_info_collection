"""Deterministic negative protocols and full-frame coverage; no external requests."""
from copy import deepcopy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

REPO=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(REPO/'projects/quality-inspector'),str(REPO/'projects/quality-inspector/tests')]
from make_fixture import fixture
from webcollect.batch_core import BatchLedger, BudgetStop, OutcomeUnknown, load_json
from webcollect.model_gateway import ModelGateway
from quality_inspector.ai_worker import (do_visual, prepare, run, snapshot, synthetic_review,
                                         report, compact_trajectory)


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.config=load_json(REPO/'projects/code/config/batch-synthetic.json')
        self.sample=fixture(self.root/'fixture')

    def ledger(self,config=None):return BatchLedger(self.root/'ops.sqlite3',config or self.config,initialize=True)

    def real_config(self):
        self.enterContext(patch('webcollect.model_gateway.socket.getaddrinfo', return_value=[('CONTROLLED_DNS',)]))
        config=deepcopy(self.config);config['mode']='real';config['budget'].update(currency='TEST_UNITS',max_model_cost_micros=100000,min_model_interval_seconds=1)
        config['model'].update(provider='chat-completions',model='controlled-http-protocol-model',
            endpoint='https://provider.invalid/v1/chat/completions',api_key_env='WEBCOLLECT_TEST_KEY',reserve_cost_micros=100000)
        config['model']['rates']={'version':'TEST-NOT-A-PRICE','source':'unit-test synthetic rates only',
                                'input':1000000,'cached_input':500000,'output':2000000}
        return config

    def job(self,ledger):return ledger.claim('test',job_id=ledger.enqueue('test',{'controlled':True}))

    def test_image_json_actual_usage_mapping_cache_and_secret_redaction(self):
        config=self.real_config();ledger=self.ledger(config);job=self.job(ledger)
        raw={'id':'controlled-response-1','model':'controlled-model-version','usage':{
            'prompt_tokens':250,'completion_tokens':50,'prompt_tokens_details':{'cached_tokens':100}},
            'choices':[{'finish_reason':'stop','message':{'content':'{"ok":true}'}}]}
        schema={'type':'object','properties':{'ok':{'type':'boolean'}},'required':['ok'],'additionalProperties':False}
        class Opener:
            def __init__(self):self.calls=[]
            def open(inner,request,timeout):
                inner.calls.append(request)
                return io.BytesIO(json.dumps(raw).encode())
        opener=Opener()
        with patch.dict('os.environ',{'WEBCOLLECT_TEST_KEY':'synthetic-secret-never-log'}),patch('urllib.request.build_opener',return_value=opener):
            gateway=ModelGateway(ledger)
            for _ in range(2):
                self.assertEqual(gateway.call(job,'vision','JSON controlled test',schema,
                    images=[self.sample/'images/step_001.png']),{'ok':True})
        self.assertEqual(len(opener.calls),1)
        payload=json.loads(opener.calls[0].data)
        self.assertTrue(payload['messages'][1]['content'][1]['image_url']['url'].startswith('data:image/png;base64,'))
        self.assertTrue(payload['response_format']['json_schema']['strict'])
        self.assertEqual(ledger.summary()['model_cost_micros'],300) # 150 uncached + 50 cached + 100 output
        ledger.export(self.root/'metering')
        self.assertNotIn('synthetic-secret-never-log',''.join(p.read_text() for p in (self.root/'metering').glob('*.json')))

    def test_timeout_keeps_monetary_reservation_and_prevents_second_dispatch(self):
        config=self.real_config();ledger=self.ledger(config);job=self.job(ledger)
        with patch.dict('os.environ',{'WEBCOLLECT_TEST_KEY':'synthetic-secret'}),patch('urllib.request.OpenerDirector.open',side_effect=urllib.error.URLError('controlled timeout')):
            with self.assertRaises(OutcomeUnknown):
                ModelGateway(ledger).call(job,'timeout','JSON',{'type':'object'},attempts=2)
        self.assertEqual(ledger.summary()['model_requests'],1)
        self.assertEqual(ledger.summary()['model_cost_micros'],'UNKNOWN')
        self.assertEqual(ledger.summary()['uncertain_reserved_cost_micros'],100000)
        with self.assertRaises(BudgetStop):ledger.reserve_request(job,'another',0)
        ledger.finish(job,'review_required')

    def test_missing_cached_usage_stays_unknown_instead_of_zero(self):
        ledger=self.ledger(self.real_config());job=self.job(ledger)
        raw={'id':'controlled-no-cache-detail','model':'controlled','usage':{'prompt_tokens':25,'completion_tokens':5},
             'choices':[{'finish_reason':'stop','message':{'content':'{}'}}]}
        class Opener:
            def open(self,*args,**kwargs):return io.BytesIO(json.dumps(raw).encode())
        with patch.dict('os.environ',{'WEBCOLLECT_TEST_KEY':'synthetic-secret'}),patch('urllib.request.build_opener',return_value=Opener()):
            with self.assertRaises(OutcomeUnknown):ModelGateway(ledger).call(job,'usage','JSON',{'type':'object'})
        self.assertEqual(ledger.summary()['model_requests'],1)
        self.assertEqual(ledger.summary()['model_cost_micros'],'UNKNOWN')

    def test_long_trajectory_all_original_frames_and_segment_failures_retained(self):
        config=deepcopy(self.config);config['model']['max_images']=3
        ledger=self.ledger(config);value=snapshot(self.sample)
        job=ledger.claim('ai-visual',job_id=ledger.enqueue('ai-visual',{'candidate':value}))
        result=do_visual(ledger,ModelGateway(ledger),job,controlled={1:synthetic_review([3,4,5],status='FAIL')})
        self.assertEqual(result['checks']['visual_alignment']['status'],'FAIL')
        self.assertEqual([r['step_id'] for r in result['step_observations']],list(range(1,7)))
        with ledger.connect() as con:
            requests=[json.loads(r[0]) for r in con.execute('SELECT request_json FROM model_requests ORDER BY started')]
        seen={Path(im['path']).name for r in requests for im in r['images']}
        self.assertEqual(seen,{f'step_{i:03}.png' for i in range(1,7)})
        self.assertEqual(len(requests),4)

    def test_placeholder_and_missing_frames_block_before_model(self):
        annotation=load_json(self.sample/'annotation.json');annotation['steps'][2]['step_result']='待审核'
        (self.sample/'annotation.json').write_text(json.dumps(annotation,ensure_ascii=False))
        ledger=self.ledger();queued=prepare(ledger,self.root/'fixture/batch',self.root/'qc')
        self.assertEqual(queued['queued_samples'],0)
        self.assertEqual(queued['mechanically_blocked'],1)
        self.assertEqual(run(ledger)['cost']['model_requests'],0)

    def test_single_trial_sample_has_its_own_queue_and_review_format(self):
        from quality_inspector.cumulative import build_set_manifest
        ledger = self.ledger()
        dataset = self.root / 'fixture/batch'
        effective = self.root / 'trial-set.json'
        effective.write_text(json.dumps(build_set_manifest([dataset])))
        trial = prepare(ledger, dataset, self.root/'trial', effective_set=effective,
                        sample_ids=[self.sample.name], trial=True)
        ordinary = prepare(ledger, dataset, self.root/'ordinary', effective_set=effective)
        queue = load_json(trial['queue_file'])
        self.assertEqual(queue['trial']['sample_ids'], [self.sample.name])
        self.assertNotEqual(queue['jobs'][0]['visual_job'], load_json(ordinary['queue_file'])['jobs'][0]['visual_job'])
        with self.assertRaisesRegex(ValueError, 'named samples'):
            prepare(ledger, dataset, self.root/'unknown', effective_set=effective, sample_ids=['missing'], trial=True)
        pending = report(ledger, trial['queue_file'], self.root/'result')
        self.assertEqual(pending['trial_results'][self.sample.name], 'PENDING')
        run(ledger)
        reviewed = report(ledger, trial['queue_file'], self.root/'result')
        self.assertEqual(reviewed['trial_results'][self.sample.name], 'SYNTHETIC')
        self.assertEqual(load_json(reviewed['review_file'])['schema_version'], 'webcollect-trial-review-1')
        self.assertEqual(reviewed['actual_ai_reviewed'], 0)
        self.assertFalse(reviewed['release_ready'])

    def test_model_missing_observation_routes_pending_and_is_not_retried_on_restart(self):
        ledger=self.ledger();queued=prepare(ledger,self.root/'fixture/batch',self.root/'qc')
        invalid=synthetic_review([1,2,3,4,5,6]);invalid['step_observations'].pop()
        result=run(ledger,controlled={0:invalid})
        self.assertTrue(any(row['state']=='review_required' for row in result['outcomes']))
        requests=ledger.summary()['model_requests']
        self.assertEqual(run(ledger)['outcomes'],[])
        self.assertEqual(ledger.summary()['model_requests'],requests)
        summary=report(ledger,queued['queue_file'],self.root/'report')
        self.assertFalse(summary['release_ready'])
        self.assertEqual(summary['raw_model_records'],0)

    def test_changed_candidate_invalidates_queue_before_cached_review_export(self):
        ledger=self.ledger();queued=prepare(ledger,self.root/'fixture/batch',self.root/'qc');run(ledger)
        p=self.sample/'annotation.json';annotation=load_json(p);annotation['final_result']='新文字';p.write_text(json.dumps(annotation))
        with self.assertRaisesRegex(ValueError,'package changed'):
            report(ledger,queued['queue_file'],self.root/'report')


if __name__=='__main__':unittest.main()
