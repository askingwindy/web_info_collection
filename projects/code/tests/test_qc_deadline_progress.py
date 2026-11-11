"""Real QC worker and local HTTP failures; no provider or production requests."""
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import http.client
import json
import os
from pathlib import Path
import sys
import socket
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

REPO=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(REPO/'projects/quality-inspector/tests')]
from make_fixture import fixture
from webcollect.batch_core import BatchLedger, load_json
from webcollect.model_gateway import ModelGateway, _read_qc_body
from quality_inspector.ai_worker import (run, snapshot, difference_progress, do_difference,
    DIFFERENCE_PROTOCOL)


class DeadlineProgressTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        self.calls=[];self.mode='normal';self.callback=None;self.fail_at=1
        self.evidence=[]
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                data=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                material=json.loads(data['messages'][-1]['content'][0]['text'])
                owner.calls.append({'request_id':self.headers['X-Client-Request-Id'],'material':material})
                if owner.callback:owner.callback()
                mode=owner.mode if len(owner.calls)>=owner.fail_at else 'normal'
                if mode in ('noheaders','late'):
                    time.sleep(1.5)
                    if mode=='noheaders':return
                steps=material.get('allowed_focal_evidence_step_ids',[1])
                content={'status':'PASS','note':'CONTROLLED local fixture response, not independent AI review','evidence_steps':steps}
                raw={'id':'LOCAL-HTTP','model':'local-fixture','usage':{'prompt_tokens':100,'completion_tokens':20,
                     'prompt_tokens_details':{'cached_tokens':0}},'choices':[{'finish_reason':'stop','message':{
                         'content':'{}' if mode=='invalid' else json.dumps(content)}}]}
                body=json.dumps(raw).encode()
                if mode=='halfjson':body=body[:len(body)//2]
                try:
                    self.send_response(200);self.send_header('Content-Length',str(len(body)+(64 if mode=='truncated' else 0)));self.end_headers()
                    if mode=='truncated':self.close_connection=True
                    if mode=='drip':
                        for byte in body:
                            self.wfile.write(bytes([byte]));self.wfile.flush();time.sleep(.02)
                    else:self.wfile.write(body);self.wfile.flush()
                except (OSError,ValueError):pass
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.server.daemon_threads=True
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.server.server_close);self.addCleanup(self.server.shutdown)
        # Only the HTTPS connection class is substituted with plain local HTTP.
        # Real gateway request/response, deadline, socket, worker and ledger run.
        self.enterContext(patch('webcollect.model_gateway.http.client.HTTPSConnection',http.client.HTTPConnection))
        self.enterContext(patch.dict('os.environ',{'WEBCOLLECT_LOCAL_TEST_KEY':'local-fixture-value'}))
        config=load_json(REPO/'projects/code/config/batch-synthetic.json');config['mode']='real'
        config['budget'].update(lease_seconds=7,currency='LOCAL_TEST',min_model_interval_seconds=1)
        config['model'].update(provider='chat-completions',model='LOCAL-HTTP-NOT-A-MODEL',timeout_seconds=1,
            endpoint='https://127.0.0.1:'+str(self.server.server_port)+'/v1/chat/completions',
            api_key_env='WEBCOLLECT_LOCAL_TEST_KEY',reserve_cost_micros=1)
        config['model']['rates'].update(input=1,output=1)
        self.ledger=BatchLedger(self.root/'ops.sqlite3',config,initialize=True)

    def tearDown(self):
        target=os.environ.get('WEBCOLLECT_QC_TEST_EVIDENCE_DIR')
        if target:
            self.record('final')
            path=Path(target);path.mkdir(parents=True,exist_ok=True)
            (path/(self._testMethodName+'.json')).write_text(json.dumps(self.evidence,ensure_ascii=False,indent=2))

    def record(self,label,progress=None):
        self.evidence.append({'label':label,'actual_http_count':len(self.calls),
            'requests':[{'request_id':row['id'],'state':row['state'],
                         'usage':json.loads(row['usage']) if row['usage'] else None,
                         'response':json.loads(row['response'] or '{}'),'error':row['error']}
                        for row in self.requests()],
            **({'progress':progress} if progress else {})})

    def job(self,count=1,*,distinct=False):
        focal=fixture(self.root/'focal');others=[]
        for i in range(count):
            other=fixture(self.root/('other-'+str(i)))
            annotation=load_json(other/'annotation.json');annotation['sample_id']='LOCAL_NEIGHBOR_'+str(i)
            if distinct:
                from PIL import Image
                for step in annotation['steps']:
                    path=other/step['image_path']
                    with Image.open(path) as original:image=original.convert('RGB')
                    image.putpixel((1,1),(i+1,20,30));image.save(path)
            (other/'annotation.json').write_text(json.dumps(annotation,ensure_ascii=False))
            others.append(snapshot(other))
        payload={'candidate':snapshot(focal),'neighbors':others,'difference_protocol':DIFFERENCE_PROTOCOL,
                 'comparison_version':'LOCAL-FROZEN-COMPARISONS-1','pending_collection_checks':[]}
        return self.ledger.enqueue('ai-difference',payload)

    def test_explicit_same_job_continues_only_other_pairs_and_is_idempotent(self):
        from quality_inspector.ai_worker import resume_unreviewed_pairs
        from webcollect.agent_controller import exclusive
        self.ledger.config['budget']['max_job_attempts']=1
        self.mode='noheaders';self.fail_at=2;jid=self.job(4,distinct=True);run(self.ledger)
        original=self.requests();payload=self.ledger.get(jid)['payload']
        self.assertEqual([r['state'] for r in original],['succeeded','unknown'])
        auth=exclusive(self.root/'continue.json',{'action':'continue_unreviewed_pairs','job_id':jid,'preserve_unknown':True})
        resumed=resume_unreviewed_pairs(self.ledger,jid,authorization=auth)
        self.assertEqual(resumed['remaining_dispatchable_pairs'],['LOCAL_NEIGHBOR_2','LOCAL_NEIGHBOR_3'])
        self.assertTrue(resume_unreviewed_pairs(self.ledger,jid,authorization=auth)['already_applied'])
        # A process can exit after queueing. Its repeated authorization neither
        # creates another job nor resets the original request/lease ownership.
        owned=self.ledger.claim('ai-difference',job_id=jid)
        other=exclusive(self.root/'competing.json',{'action':'continue_unreviewed_pairs','job_id':jid,'preserve_unknown':True})
        with self.assertRaises(ValueError):resume_unreviewed_pairs(self.ledger,jid,authorization=other)
        self.assertEqual(self.ledger.get(jid)['owner'],owned['owner'])
        self.mode='normal'
        class Claimed:
            def __init__(inner):inner.claimed=False
            def __getattr__(inner,name):return getattr(self.ledger,name)
            def claim(inner,kind):
                if kind!='ai-difference' or inner.claimed:return None
                inner.claimed=True;return owned
        run(Claimed())
        self.assertEqual(len(self.calls),4)
        self.assertEqual(self.requests()[:2],original)
        self.assertEqual(self.ledger.get(jid)['payload'],payload)
        progress=difference_progress(self.ledger,self.ledger.get(jid))
        self.assertEqual((progress['settled_pairs'],progress['unknown_pairs']),(3,1))
        self.assertEqual(self.ledger.get(jid)['state'],'review_required')
        self.assertEqual(resume_unreviewed_pairs(self.ledger,jid,authorization=other)['remaining_dispatchable_pairs'],[])
        self.assertEqual(len(self.calls),4)

    def requests(self):
        with self.ledger.connect() as con:return [dict(row) for row in con.execute('SELECT * FROM model_requests ORDER BY started')]

    def test_normal_worker_settles_pair_and_restored_call_uses_original_cache(self):
        jid=self.job();result=run(self.ledger)
        self.assertEqual(result['outcomes'][0]['state'],'done');self.assertEqual(len(self.calls),1)
        progress=difference_progress(self.ledger,self.ledger.get(jid));self.assertEqual(progress['settled_pairs'],1)
        timing=json.loads(self.requests()[0]['response'])['http_timing']
        self.assertTrue(timing['body_read_returned']);self.assertFalse(timing['deadline_expired'])
        self.assertTrue(all(timing[key] is not None for key in ('connection_ms','headers_ms','body_ms','elapsed_ms')))
        self.assertEqual(progress['pairs'][0]['requests'][0]['usage']['input_tokens'],100)
        self.assertEqual(run(self.ledger)['outcomes'],[])

    def test_timeout_matrix_one_http_unknown_no_late_ledger_writes(self):
        for mode in ('noheaders','drip','late'):
            with self.subTest(mode=mode):
                # Independent temporary ledger, same actual gateway/worker path.
                self.calls.clear();self.mode=mode
                config=deepcopy(self.ledger.config)
                self.ledger=BatchLedger(self.root/(mode+'.sqlite3'),config,initialize=True)
                jid=self.job_in_new_folder(mode)
                start=time.monotonic();result=run(self.ledger);elapsed=time.monotonic()-start
                self.assertLess(elapsed,1.35);self.assertEqual(len(self.calls),1)
                self.assertEqual(result['outcomes'][0]['reason'],'OutcomeUnknown')
                rows=self.requests();self.assertEqual(len(rows),1);self.assertEqual(rows[0]['state'],'unknown')
                timing=json.loads(rows[0]['response'])['http_timing']
                self.assertLess(timing['elapsed_ms'],1300)
                self.assertFalse(timing['body_read_returned'])
                self.assertEqual(timing['headers_ms'] is not None,mode=='drip')
                original=rows[0];time.sleep(.12);self.assertEqual(self.requests()[0],original)
                self.assertEqual(run(self.ledger)['outcomes'],[]);self.assertEqual(len(self.calls),1)
                progress=difference_progress(self.ledger,self.ledger.get(jid));self.assertEqual(progress['unknown_pairs'],1)
                self.record(mode,progress)

    def job_in_new_folder(self,name):
        # Fixture output roots must stay unique across matrix iterations.
        old=self.root;self.root=old/name;self.root.mkdir()
        try:return self.job()
        finally:self.root=old

    def test_complete_invalid_protocol_and_half_json_are_distinct(self):
        self.mode='invalid';jid=self.job();run(self.ledger)
        row=self.requests()[0];self.assertEqual(row['state'],'invalid_response')
        self.assertIsNotNone(row['usage']);self.assertEqual(len(self.calls),1)
        self.assertTrue(json.loads(row['response'])['http_timing']['body_read_returned'])
        self.mode='halfjson';config=deepcopy(self.ledger.config)
        self.ledger=BatchLedger(self.root/'half.sqlite3',config,initialize=True)
        self.job_in_new_folder('half');run(self.ledger)
        row=self.requests()[0];self.assertEqual(row['state'],'unknown');self.assertIsNone(row['usage'])
        self.assertTrue(json.loads(row['response'])['http_timing']['body_read_returned'])

    def test_truncated_entity_with_valid_json_is_transport_unknown(self):
        self.mode='truncated';self.job();run(self.ledger)
        row=self.requests()[0];self.assertEqual(row['state'],'unknown')
        response=json.loads(row['response']);self.assertEqual(response['transport_error']['error_type'],'IncompleteRead')
        self.assertFalse(response['http_timing']['body_read_returned'])
        self.assertLess(response['http_timing']['received_body_bytes'],response['http_timing']['declared_body_bytes'])
        self.assertEqual(len(self.calls),1)

    def test_slow_dns_is_inside_worker_deadline_without_http_or_background_settlement(self):
        self.job();resolve=socket.getaddrinfo
        def slow(*args,**kwargs):time.sleep(1.5);return resolve(*args,**kwargs)
        start=time.monotonic()
        with patch('socket.getaddrinfo',slow):result=run(self.ledger)
        self.assertLess(time.monotonic()-start,1.35)
        self.assertEqual(result['outcomes'][0]['reason'],'OutcomeUnknown')
        self.assertEqual(len(self.calls),0)
        row=self.requests()[0];self.assertEqual(row['state'],'unknown')
        timing=json.loads(row['response'])['http_timing']
        self.assertTrue(timing['deadline_expired']);self.assertFalse(timing['http_dispatched'])
        time.sleep(.1);self.assertEqual(self.requests()[0],row)

    def test_21_pairs_third_timeout_preserves_two_and_eighteen_not_reviewed(self):
        self.mode='noheaders';self.fail_at=3;jid=self.job(21);run(self.ledger)
        progress=difference_progress(self.ledger,self.ledger.get(jid))
        self.assertEqual((progress['settled_pairs'],progress['unknown_pairs'],progress['not_reviewed_pairs']),(2,1,18))
        self.assertEqual(len(self.calls),3)
        self.assertEqual([row['state'] for row in self.requests()],['succeeded','succeeded','unknown'])
        self.assertEqual(progress['whole_sample_status'],'PENDING')
        self.record('21-pair-third-unknown',progress)
        # Explicit same-original-job recovery reads settled requests but cannot
        # replace UNKNOWN, including before any extra HTTP dispatch.
        with self.ledger.transaction() as con:
            con.execute("UPDATE jobs SET state='queued' WHERE id=?",(jid,))
        job=self.ledger.claim('ai-difference',job_id=jid)
        from webcollect.batch_core import OutcomeUnknown
        with self.assertRaises(OutcomeUnknown):do_difference(self.ledger,ModelGateway(self.ledger),job)
        self.assertEqual(len(self.calls),3)
        again=difference_progress(self.ledger,self.ledger.get(jid))
        self.assertEqual(again['settled_pairs'],2)

    def test_timeout_then_lease_new_owner_keeps_first_and_cleanup_errors(self):
        self.mode='noheaders';jid=self.job()
        def replace():
            with self.ledger.transaction() as con:
                con.execute("UPDATE jobs SET owner='NEW-CONTROLLED-OWNER',lease=? WHERE id=?",(time.time()+10,jid))
        self.callback=replace
        result=run(self.ledger)
        self.assertEqual(result['outcomes'][0]['reason'],'OutcomeUnknown')
        self.assertEqual(result['outcomes'][0]['cleanup_error'],'ValueError')
        self.assertEqual(self.ledger.get(jid)['owner'],'NEW-CONTROLLED-OWNER')
        self.assertEqual(self.requests()[0]['state'],'unknown');self.assertEqual(len(self.calls),1)
        with self.ledger.connect() as con:
            event=json.loads(con.execute("SELECT detail FROM batch_events WHERE event='qc_worker_cleanup_failed'").fetchone()[0])
        self.assertEqual(event['first_error'],'OutcomeUnknown');self.assertEqual(event['cleanup_error'],'ValueError')

    def test_expired_owner_prevents_dispatch(self):
        jid=self.job();job=self.ledger.claim('ai-difference',job_id=jid)
        with self.ledger.transaction() as con:con.execute('UPDATE jobs SET lease=? WHERE id=?',(time.time()-1,jid))
        with self.assertRaisesRegex(ValueError,'lease'):do_difference(self.ledger,ModelGateway(self.ledger),job)
        self.assertEqual(len(self.calls),0);self.assertEqual(self.requests(),[])

    def test_recover_during_timeout_preserves_io_error_and_original_unknown(self):
        self.mode='noheaders';jid=self.job()
        def recover():
            with self.ledger.transaction() as con:
                con.execute('UPDATE jobs SET lease=? WHERE id=?',(time.time()-1,jid))
            self.ledger.recover()
        self.callback=recover
        result=run(self.ledger)
        self.assertEqual(result['outcomes'][0]['reason'],'OutcomeUnknown')
        self.assertEqual(self.requests()[0]['error'],'lease_expired_after_dispatch')
        self.assertEqual(self.requests()[0]['state'],'unknown');self.assertEqual(len(self.calls),1)
        with self.ledger.connect() as con:
            receipt=json.loads(con.execute("SELECT detail FROM batch_events WHERE event='qc_request_cleanup_failed'").fetchone()[0])
        self.assertEqual(receipt['first_error'],'TimeoutError')
        self.assertEqual(receipt['cleanup_error'],'ValueError')
        self.assertTrue(receipt['response_evidence']['http_timing']['deadline_expired'])

    def test_received_answer_after_ownership_change_is_not_a_pair_approval(self):
        jid=self.job()
        def replace():
            with self.ledger.transaction() as con:
                con.execute("UPDATE jobs SET owner='OTHER',lease=? WHERE id=?",(time.time()+10,jid))
        self.callback=replace
        result=run(self.ledger)
        self.assertEqual(result['outcomes'][0]['reason'],'ValueError')
        self.assertEqual(result['outcomes'][0]['cleanup_error'],'ValueError')
        self.assertEqual(self.ledger.get(jid)['owner'],'OTHER')
        self.assertEqual(difference_progress(self.ledger,self.ledger.get(jid))['settled_pairs'],0)
        self.assertEqual(len(self.calls),1)

    def test_request_deadline_is_tightened_to_owned_remaining_lease(self):
        jid=self.job();job=self.ledger.claim('ai-difference',job_id=jid)
        with self.ledger.transaction() as con:
            con.execute('UPDATE jobs SET lease=? WHERE id=?',(time.time()+5.3,jid))
        window=self.ledger.request_window(job,1)
        self.assertGreater(window,0);self.assertLess(window,.31)
        with self.ledger.transaction() as con:
            con.execute('UPDATE jobs SET lease=? WHERE id=?',(time.time()+4.9,jid))
        with self.assertRaisesRegex(ValueError,'cleanup'):self.ledger.request_window(job,1)
        self.assertEqual(len(self.calls),0)


if __name__=='__main__':unittest.main()
