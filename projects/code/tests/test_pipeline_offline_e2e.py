"""Combined producer/consumer CLIs; only external HTTP/browser IO is replaced."""
import asyncio
from contextlib import ExitStack, redirect_stdout
from copy import deepcopy
import io
import json
import multiprocessing
import os
from pathlib import Path
import runpy
import subprocess
import sys
import time
import unittest
from urllib.error import HTTPError
from unittest.mock import AsyncMock, patch

import test_candidate_entry_engineering as engineering
from site_planner.candidate_discovery import main as producer_cli
from site_planner.candidate_pool import CandidatePool, VERSION2
from site_planner.site_pool import SitePool
from site_planner.discovery_tools import reference
from webcollect.batch_core import BatchLedger, load_json, save_json
from webcollect.candidate_consumer import main as consumer_cli, statistics
from webcollect.planning import verify_evidence


class PipelineAcceptance(engineering.EntryEngineering):
    chain_manifest = 'verify_results/current-trial/current-chain-r01/manifest.json'
    def setUp(self):
        super().setUp()
        SitePool(self.root/'joint-pool.db', initialize=True)
        self.pool = CandidatePool(self.root/'joint-pool.db', install=True)
        cfg = deepcopy(self.ledger.config)
        cfg['run_id'] = 'OFFLINE-joint-consumer'
        cfg['model'].update(provider='glm',model='glm-5.3-flash',
            endpoint='https://provider.invalid/chat/completions',api_key_env='WEBCOLLECT_JOINT_FAKE_KEY',
            supports_vision=True,image_tokens_per_image=1200,request_overhead_tokens=128,
            reserve_input_tokens=250000,max_images=24)
        self.ledger = BatchLedger(self.root/'joint-consumer.db',cfg,initialize=True)
        self.cfg_path=self.root/'joint-consumer.json'
        save_json(self.cfg_path,cfg)
        producer_cfg = deepcopy(cfg); producer_cfg['run_id']='OFFLINE-joint-producer'
        self.producer_cfg = self.root/'joint-producer.json'; save_json(self.producer_cfg,producer_cfg)
        self.producer_ledger = self.root/'joint-producer.db'
        self.sources_path=self.root/'explicit-sources.json'
        proof = self.chain.parent.parent / 'explicit-source.json'
        save_json(proof, {'description':'controlled search source'})
        save_json(self.sources_path,[{'uri':self.uri,'title':'受控数量与单价工具','content':'公开的受控输入工具。',
                                     'reference':reference(proof)}])
        self.wire=[]
        self.return_unknown=False
        self.entry_statuses={}
        self.entry_gets=[]
        self.selected_sources=[0]

    def entry_get(self, request, timeout):
        self.assertEqual(request.get_method(),'GET')
        uri = request.full_url
        self.entry_gets.append(uri)
        status = self.entry_statuses.get(uri,200)
        if status >= 400:
            raise HTTPError(uri,status,'Controlled entry failure',{},io.BytesIO(b''))
        response = io.BytesIO()
        response.status = status
        response.geturl = lambda: uri
        return response

    def transport(self,request,timeout):
        payload=json.loads(request.data)
        if request.full_url.endswith('/web_search'):
            search={'search_result':[{'link':self.uri,'title':'受控工具站','content':'公开中文数量与单价工具'}]}
            return io.BytesIO(json.dumps(search,ensure_ascii=False).encode())
        self.wire.append(payload)
        tools={tool['function']['name'] for tool in payload['tools']}
        if tools=={'submit_candidates'}:
            name='submit_candidates'
            arguments={'candidates':[{'source_index':index,'category_hint':'在线工具',
                'suggested_goal':{'kind':'edit','entity':'fields','parameters':{'quantity':999}}} for index in self.selected_sources]}
            call_id='OFFLINE-producer-call-1'
        else:
            self.assertEqual(tools,{'observe','inspect','act','finish'})
            current=payload['messages'][-1]['content']
            prompt=json.loads(next(part['text'] for part in current if part['type']=='text'))
            self.prompts.append(prompt)
            if self.return_unknown:
                import urllib.error
                raise urllib.error.URLError('CONTROLLED dispatch outcome unknown')
            self.assertTrue(self.decisions,'unexpected model request beyond the controlled script')
            decision=self.decisions.pop(0)(prompt)
            name=decision['tool_call']['name']
            arguments={**decision['tool_call']['arguments'],'goal_update':decision['goal_update'],
                       'decision_summary':decision['decision_summary']}
            if name=='finish':
                arguments.pop('short_flow',None);arguments.pop('short_flow_reason',None)
                arguments['evidence_refs']=[prompt['observation']['observation_id']]
            call_id='OFFLINE-consumer-call-'+str(len(self.prompts))
        raw={'id':'OFFLINE-http-'+str(len(self.wire)),'model':'glm-5.3-flash',
             'usage':{'prompt_tokens':50,'completion_tokens':20,'prompt_tokens_details':{'cached_tokens':0}},
             'choices':[{'finish_reason':'tool_calls','message':{'role':'assistant','content':None,
                'reasoning_content':'OFFLINE-opaque-protocol-only',
                'tool_calls':[{'id':call_id,'type':'function','function':{'name':name,
                    'arguments':json.dumps(arguments,ensure_ascii=False)}}]}}]}
        return io.BytesIO(json.dumps(raw,ensure_ascii=False).encode())

    def boundaries(self, *, search=False):
        stack=ExitStack()
        # The actual ModelGateway constructor, call_tool, parser, reservation,
        # request cache and history serializer run without method replacements.
        stack.enter_context(self.io_boundaries(mock_gateway=False))
        stack.enter_context(patch.dict(os.environ,{'WEBCOLLECT_JOINT_FAKE_KEY':'CONTROLLED-NOT-A-CREDENTIAL'}))
        stack.enter_context(patch('webcollect.model_gateway.socket.getaddrinfo',return_value=[('CONTROLLED_DNS',)]))
        opener=type('Opener',(),{'open':lambda _,request,timeout:self.transport(request,timeout)})()
        stack.enter_context(patch('urllib.request.build_opener',return_value=opener))
        site_opener=type('EntryOpener',(),{'open':lambda _,request,timeout:self.entry_get(request,timeout)})()
        stack.enter_context(patch('site_planner.pipeline.build_opener',return_value=site_opener))
        if not search:
            stack.enter_context(patch('site_planner.candidate_discovery.glm_search',side_effect=AssertionError('No search IO')))
        return stack

    def producer_args(self, *, goals=None, search=False):
        args=['produce-entries','--config',str(self.producer_cfg),'--pool',str(self.pool.path),
            '--ledger',str(self.producer_ledger),'--history-set',str(self.chain),
            '--target','1','--max-batches','1','--batch-size','1']
        args.extend(['--query','受控工具搜索'] if search else ['--sources',str(self.sources_path)])
        if goals:args.extend(['--goals',str(goals)])
        return args

    @staticmethod
    def invoke(entry,args):
        with redirect_stdout(io.StringIO()) as stream:
            entry(args)
        return json.loads(stream.getvalue())

    async def produce(self, *, goals=None):
        return await asyncio.to_thread(self.invoke,producer_cli,self.producer_args(goals=goals))

    async def consume_cli(self,prefix='joint',worker='joint-worker'):
        return (await asyncio.to_thread(self.invoke,consumer_cli,self.cli_args(prefix,worker)))[0]

    def assert_complete(self,result):
        self.assertEqual(result['state'],'succeeded',(result,[load_json(p) for p in self.output.rglob('failure.json')]))
        self.assertEqual(result['QC'],'pending_review')
        row=self.pool.rows(protocols=(VERSION2,))[0]
        self.assertEqual(row['state'],'succeeded')
        self.assertEqual(row['result']['qc_state'],'pending_review')
        with self.pool.pool.connect() as con:
            record=con.execute('SELECT * FROM candidate_claims WHERE candidate_id=? ORDER BY created DESC',
                (row['candidate_id'],)).fetchone()
            bound=self.pool._claim(record)
            self.assertEqual(con.execute('SELECT COUNT(*) FROM candidate_results WHERE effective=1').fetchone()[0],1)
        self.assertEqual(bound['stage'],'saved')
        self.assertEqual(bound['binding']['attempt_id'],result['result']['attempt_id'])
        plan=load_json(bound['binding']['plan']); task=plan['tasks'][0]
        self.assertEqual(task['candidate_binding']['candidate_id'],row['candidate_id'])
        self.assertEqual(task['candidate_binding']['sources'],bound['sources'])
        verify_evidence([task['candidate_binding']['claim_reference'],result['result']['save_receipt']])
        saved=load_json(result['result']['save_receipt']['path'])
        raw=Path(result['result']['save_receipt']['path']).parent
        receipt=load_json(raw/'raw/raw-receipt.json')
        self.assertTrue(receipt['raw_saved'])
        self.assertTrue(saved['sample_files_sha256'])
        self.assertIn('pilot_identity.json',saved['capture_files_sha256'])
        self.assertEqual(statistics(self.pool)['formal_attempts'],1)
        self.assertEqual(statistics(self.pool)['collected'],1)
        self.assertEqual(statistics(self.pool)['QC_accepted'],0)
        return row,bound,task

    def check_wire(self,claim):
        self.assertEqual(len(self.wire),6)
        self.assertEqual(self.wire[0]['reasoning_effort'],'low')
        consumer=self.wire[1:]
        seen=[]
        for index,payload in enumerate(consumer):
            self.assertEqual(payload['tool_choice'],'auto')
            self.assertEqual(payload['reasoning_effort'],'max')
            self.assertEqual(payload['thinking'],{'type':'enabled','clear_thinking':False})
            messages=payload['messages']
            if index==0:
                self.assertEqual([message['role'] for message in messages],['system','user'])
            else:
                assistants=[message for message in messages if message['role']=='assistant']
                tool_results=[message for message in messages if message['role']=='tool']
                self.assertEqual(len(assistants),index)
                self.assertEqual([m['tool_call_id'] for m in tool_results],seen)
                self.assertTrue(all(m.get('reasoning_content')=='OFFLINE-opaque-protocol-only' for m in assistants))
            seen.append('OFFLINE-consumer-call-'+str(index+1))
            self.assertNotIn(claim['token'],json.dumps(payload))
            self.assertNotIn(str(self.ledger.path),json.dumps(payload))
            self.assertNotIn(str(self.pool.path),json.dumps(payload))
            images=[part['image_url']['url'] for message in messages if isinstance(message.get('content'),list)
                    for part in message['content'] if part.get('type')=='image_url']
            self.assertEqual(len(images),index+1)
            self.assertTrue(all(image.startswith('data:image/png;base64,') for image in images))
        self.assertEqual(len(self.gotos),1)
        self.assertEqual(len(self.contexts),1)
        self.assertEqual(self.contexts[0].new_page.await_count,1)
        self.assertEqual(len(self.ledger.visits()),1)
        self.assertEqual(self.ledger.summary()['model_requests'],5)

    def export_trace(self,name,data):
        destination=os.environ.get('WEBCOLLECT_OFFLINE_E2E_REPORT_DIR')
        if destination:
            root=Path(destination).resolve();root.mkdir(parents=True,exist_ok=True)
            save_json(root/(name+'.json'),{'scope':'OFFLINE temporary fixtures only','real_production':False,**data})

    async def test_joint_producer_cli_to_same_page_save_and_writeback(self):
        with self.boundaries():
            produced=await self.produce()
            self.assertEqual(produced['listed_unique_candidates'],1,produced)
            self.assertEqual(produced['current_chain_manifest'],reference(self.chain))
            self.assertTrue(Path(produced['evidence_output']).is_relative_to(self.chain.parent.parent))
            before=self.pool.rows(protocols=(VERSION2,))[0]
            self.assertEqual(before['state'],'pending')
            self.assertIsNone(before['candidate']['requested_goal'])
            result=await self.consume_cli()
            row,claim,task=self.assert_complete(result)
            self.check_wire(claim)
            self.assertTrue(all(prompt['requested_goal'] is None for prompt in self.prompts))
            self.assertEqual(task['fragment']['decision_protocol'],'webcollect-react-native-2')
            self.assertEqual(row['sources'][0]['tool_call_id'],'OFFLINE-producer-call-1')
            self.assertEqual(row['sources'][0]['model_request_id'],claim['sources'][0]['model_request_id'])
            with self.ledger.connect() as con:
                requests=[dict(r) for r in con.execute('SELECT id,state,request_json FROM model_requests')]
            self.assertEqual(len(requests),5)
            self.assertTrue(all(r['state']=='succeeded' and json.loads(r['request_json'])['dispatch_attempt_id']==result['result']['attempt_id']
                                for r in requests))
            self.export_trace('chain',{'candidate_id':row['candidate_id'],'producer_tool_id':row['sources'][0]['tool_call_id'],
                'producer_request_id':row['sources'][0]['model_request_id'],'claim_id':claim['claim_id'],
                'attempt_id':result['result']['attempt_id'],'sample_id':result['result']['sample_id'],
                'save_receipt_sha256':result['result']['save_receipt']['sha256'],
                'contexts':1,'entry_navigations':1,'producer_http':1,'consumer_http':5,
                'effective_actions':len(self.surface.executed),'saved':1,'actual_QC_pass':0,'published':0})

    async def test_start_script_hands_same_batch_to_consumer_and_monitor(self):
        script = Path(__file__).resolve().parents[1] / 'scripts/start_candidates.py'
        scope_file = self.root / 'scope.json'
        qc_policy = self.root / 'qc-policy.json'
        save_json(qc_policy, {'ai_percent': 10, 'human_percent': 0, 'seed': 'offline-start', 'production_sampling': True})
        batch = load_json(self.producer_cfg)['run_id'] + '/entry-batch/launcher'
        save_json(scope_file, {'pool': str(self.pool.path), 'batch': batch, 'history_set': str(self.chain),
            'producer_config': str(self.producer_cfg), 'producer_db': str(self.producer_ledger),
            'consumer_config': str(self.cfg_path), 'consumer_db': str(self.ledger.path),
            'consumer_worker': 'start-test', 'request_prefix': 'start-test', 'registry': str(self.registry),
            'output': str(self.output), 'policy': str(self.policy_path), 'qc_policy': str(qc_policy),
            'started_at': time.time()})

        def launch(role, module, entry, *options):
            # Keep the fixture's fake HTTP and page in this process across the exec boundary.
            outputs = []
            def dispatch(python, command, env):
                self.assertEqual(command[:5], [python, '-B', '-u', '-m', module])
                outputs.append(self.invoke(entry, command[5:]))
            with patch.object(sys, 'argv', [str(script), '--scope', str(scope_file), role, *options]), \
                 patch('os.execve', side_effect=dispatch) as execute:
                runpy.run_path(str(script), run_name='__main__')
                execute.assert_called_once()
                return outputs[0]

        with self.boundaries():
            produced = await asyncio.to_thread(launch, 'producer', 'site_planner.candidate_discovery', producer_cli,
                '--sources', str(self.sources_path), '--target', '1', '--batch-size', '1', '--max-batches', '1')
            self.assertEqual(produced['batch_scope'], batch)
            self.assertEqual(produced['current_chain_manifest'], reference(self.chain))
            self.assertTrue(Path(produced['evidence_output']).is_relative_to(self.chain.parent.parent))
            result, = await asyncio.to_thread(launch, 'consumer', 'webcollect.candidate_consumer', consumer_cli,
                                               '--limit', '1', '--poll-seconds', '1')
            self.assert_complete(result)

        receipt = load_json(self.output / result['claim_id'] / 'execution/qc-inputs/receipt.json')
        self.assertEqual((receipt['status'], receipt['attempts'][0]['sample_id']),
                         ('QC_NOT_RUN', result['result']['sample_id']))
        logs = self.root / 'observer logs'
        subprocess.run([sys.executable, '-B', str(script), '--scope', str(scope_file), 'monitor',
                        '--log-dir', str(logs), '--once'], check=True, capture_output=True, text=True)
        calls = [json.loads(line) for line in (logs/'consumer-calls.jsonl').read_text().splitlines()]
        self.assertEqual(sum(row['event'] == 'dispatch_recorded' for row in calls), 5)
        self.export_trace('start-script', {'batch': batch, 'claim_id': result['claim_id'],
            'sample_id': result['result']['sample_id'], 'qc_status': receipt['status'], 'consumer_dispatches': 5})

    async def test_joint_http_403_and_404_rejected_before_claim_only_200_reaches_react(self):
        forbidden, missing = 'https://forbidden.example.net/path','https://missing.example.edu/path'
        healthy = load_json(self.sources_path)[0]
        sources = self.chain.parent.parent/'mixed-sources.json'
        save_json(sources,[{**healthy,'uri':forbidden},{**healthy,'uri':missing},healthy])
        self.entry_statuses = {forbidden:403,missing:404}
        self.selected_sources = [0,1,2]
        args = self.producer_args()
        args[args.index('--sources')+1] = str(sources)
        for flag in ('--target','--batch-size'):
            args[args.index(flag)+1] = '3'
        with self.boundaries():
            report = self.invoke(producer_cli,args)
            self.assertEqual(report['row_results'],{'NEW':1,'REJECTED':2},report)
            self.assertEqual(report['deficit'],2)
            entries = self.pool.rows(protocols=(VERSION2,))
            self.assertEqual([r['candidate']['entry_url'] for r in entries],[self.uri])
            rows = self.pool.batch_rows(report['batch_scope'],0)
            rejected = [r for r in rows if r['result']=='REJECTED']
            verify_evidence([r['entry_http'] for r in rejected])
            facts = [load_json(r['entry_http']['path']) for r in rejected]
            self.assertEqual([(r['entry_uri'],r['http_status']) for r in facts],[(forbidden,403),(missing,404)])
            self.assertTrue(all(r['candidate_id'] is None for r in rejected))
            self.assertEqual(load_json(entries[0]['sources'][0]['entry_http']['path'])['http_status'],200)
            get_count = len(self.entry_gets)
            model_count = len(self.wire)
            resumed = self.invoke(producer_cli,args)
            self.assertEqual((resumed['row_results'],resumed['candidate_ids']),(report['row_results'],report['candidate_ids']))
            self.assertEqual((get_count,len(self.entry_gets),model_count,len(self.wire)),(3,3,1,1))
            worker = await asyncio.to_thread(self.invoke,consumer_cli,self.cli_args()+['--producer-batch',report['batch_scope']])
            self.assertEqual([r['candidate_id'] for r in worker],report['candidate_ids'])
            self.assertEqual(worker[0]['state'],'succeeded',worker)
            self.assertEqual(self.pool.claim_next('other','other/0',protocols=(VERSION2,),producer_batch=report['batch_scope']),{'state':'EMPTY'})
            self.assertEqual([uri for _,uri in self.gotos],[self.uri])
        from webcollect.candidate_monitor import project
        monitor_logs = self.root/'admission-logs'
        project({'started_at':0,'batch':report['batch_scope'],'consumer_worker':'entry-worker',
                 'pool':str(self.pool.path),'registry':str(self.registry),'producer_db':str(self.producer_ledger),
                 'consumer_db':str(self.ledger.path)}, monitor_logs,{})
        logged = [json.loads(line) for line in (monitor_logs/'issues.jsonl').read_text().splitlines()]
        self.assertEqual(sorted(r['http_status'] for r in logged if r['event']=='producer_entry_http'),[403,404])
        self.export_trace('entry-http-admission',{'producer_gets':get_count,'rejected_http':[r['http_status'] for r in facts],
            'row_results':report['row_results'],'candidate_ids':report['candidate_ids'],
            'consumer_claims':len(worker),'consumer_react_decisions':len(self.prompts),
            'consumer_entry_visits':len(self.gotos),'repeat_producer_requests':0})

    async def test_joint_rejects_r02_output_and_transitive_sources_before_side_effects(self):
        outside = self.root/'verify_results'/'separate-trial-logs'/'produce-out'
        args = self.producer_args()
        with self.boundaries():
            with self.assertRaisesRegex(ValueError, 'out-of-chain'):
                self.invoke(producer_cli, args + ['--output',str(outside)])
            unbound = args.copy()
            index = unbound.index('--history-set')
            del unbound[index:index+2]
            with self.assertRaisesRegex(ValueError, 'require --history-set'):
                self.invoke(producer_cli, unbound + ['--output',str(outside)])
            wrapper = self.chain.parent.parent/'source-with-external-reference.json'
            save_json(wrapper, {'original':reference(self.root/'source.json')})
            sources = load_json(self.sources_path)
            sources[0]['reference'] = {**reference(wrapper), 'kind':'search'}
            bad_sources = self.root/'sources-from-wrong-root.json'
            save_json(bad_sources, sources)
            args[args.index('--sources')+1] = str(bad_sources)
            with self.assertRaisesRegex(ValueError, 'out-of-chain'):
                self.invoke(producer_cli, args)
        self.assertFalse(outside.exists())
        self.assertFalse(self.producer_ledger.exists())
        self.assertEqual(self.wire, [])
        with self.pool.pool.connect() as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM runs').fetchone()[0],0)
            self.assertEqual(con.execute('SELECT COUNT(*) FROM data_candidates').fetchone()[0],0)
            self.assertEqual(con.execute('SELECT COUNT(*) FROM tool_requests').fetchone()[0],0)

    async def test_joint_scoped_resume_keeps_the_frozen_result_root_without_resending(self):
        args = self.producer_args()
        destination = self.root/'results'/'producer-batch'
        with self.boundaries():
            original = self.invoke(producer_cli, args + ['--output',str(destination)])
            self.assertEqual(original['evidence_output'],str(destination))
            index = args.index('--history-set')
            del args[index:index+2]
            resumed = self.invoke(producer_cli,args)
            self.assertEqual(resumed['evidence_output'],str(destination))
            self.assertEqual(resumed['current_chain_manifest'],original['current_chain_manifest'])
            changed = self.chain.parent.parent/'other-batch-directory'
            with self.assertRaisesRegex(ValueError, 'cannot change on resume'):
                self.invoke(producer_cli,args + ['--output',str(changed)])
            self.assertFalse(changed.exists())
            self.assertEqual(len(self.wire),1)

    async def test_joint_observer_preserves_search_kind_in_failure_log(self):
        from webcollect.candidate_monitor import project
        run_id = 'OFFLINE-failed-search'
        store = self.pool.pool
        store.freeze_run(run_id,{'scope':'offline monitor fixture'})
        rid, _ = store.reserve_tool(run_id,'search','failed-query',{'search_query':'failed-query'})
        store.settle_tool(rid,'unknown',{'error_type':'TimeoutError'})
        scope = {'pool':str(self.pool.path), 'batch':run_id+'/entry-batch/main','started_at':0,
                 'consumer_worker':'unused','producer_db':str(self.producer_ledger),
                 'consumer_db':str(self.ledger.path),'registry':str(self.registry)}
        logs = self.root/'failed-search-logs'
        project(scope,logs,{})
        producer_events = [json.loads(line)['event'] for line in (logs/'producer-calls.jsonl').read_text().splitlines()]
        self.assertIn('ledger_not_ready',producer_events)
        self.assertNotIn('account_count',producer_events)
        for file in ('issues.jsonl','producer-calls.jsonl'):
            rows = [json.loads(line) for line in (logs/file).read_text().splitlines()]
            search = next(row for row in rows if row['event']=='search_request')
            self.assertEqual((search['id'],search['kind'],search['state']),(rid,'search','unknown'))

    async def test_joint_observer_write_failure_leaves_consumer_alive_through_first_react_call(self):
        ctx = multiprocessing.get_context('fork')
        at_capture, release = ctx.Event(), ctx.Event()
        worker_id, batch = 'observer-test-worker', 'OFFLINE-joint-producer/entry-batch/main'
        scope_path = self.root/'monitor-scope.json'
        save_json(scope_path, {'batch':batch, 'consumer_worker':worker_id, 'started_at':time.time(),
            'pool':str(self.pool.path), 'producer_db':str(self.producer_ledger),
            'consumer_db':str(self.ledger.path), 'registry':str(self.registry)})
        worker_report = self.root/'observer-worker.json'
        def worker_entry():
            capture = self.capture
            async def wait_for_observer(*args, **kwargs):
                at_capture.set()
                if not release.wait(30):
                    raise TimeoutError('Offline observer did not finish')
                return await capture(*args, **kwargs)
            self.capture = wait_for_observer
            with self.boundaries():
                args = self.cli_args('observed', worker_id) + ['--poll-seconds','1','--producer-batch',batch]
                result = self.invoke(consumer_cli,args)[0]
            save_json(worker_report, {'pid':os.getpid(),'result':result,'entry_visits':len(self.gotos)})

        child = ctx.Process(target=worker_entry)
        child.start()
        try:
            deadline = time.monotonic()+15
            with self.pool.pool.connect() as con:
                while not con.execute('SELECT 1 FROM candidate_empty_requests WHERE worker_id=?',(worker_id,)).fetchone():
                    self.assertTrue(child.is_alive() and time.monotonic()<deadline, 'worker did not poll empty pool')
                    await asyncio.sleep(.05)
            with self.boundaries(search=True):
                report = await asyncio.to_thread(self.invoke,producer_cli,self.producer_args(search=True))
            self.assertEqual(report['listed_unique_candidates'],1,report)
            self.assertTrue(await asyncio.to_thread(at_capture.wait,15), 'consumer did not reach first observation')
            rival = self.pool.claim_next('rival','rival/0',protocols=(VERSION2,),producer_batch=batch)
            self.assertEqual(rival,{'state':'EMPTY'})
            with self.ledger.connect() as con:
                self.assertEqual(con.execute('SELECT COUNT(*) FROM model_requests').fetchone()[0],0)

            # The observer is a sibling OS process. Its file writes fail with EFBIG.
            env = {**os.environ,'PYTHONPATH':os.pathsep.join(sys.path)}
            fault = ('import resource,signal; signal.signal(signal.SIGXFSZ,signal.SIG_IGN); '
                     'r=resource.RLIMIT_FSIZE; resource.setrlimit(r,(0,resource.getrlimit(r)[1])); '
                     'from webcollect.candidate_monitor import main; raise SystemExit(main())')
            observer_args = ['--scope',str(scope_path),'--log-dir',str(self.root/'monitor-logs'),'--once']
            failed = subprocess.run([sys.executable,'-B','-c',fault,*observer_args],
                                    env=env,capture_output=True,text=True,timeout=15)
            self.assertEqual(failed.returncode,1,failed.stderr)
            self.assertIn('File too large',failed.stderr)
            self.assertTrue(child.is_alive())
            release.set()
            await asyncio.to_thread(child.join,40)
            self.assertEqual(child.exitcode,0)
        finally:
            release.set()
            if child.is_alive():
                child.kill(); child.join()

        worker = load_json(worker_report)
        self.assertEqual(worker['pid'],child.pid)
        self.assertEqual(worker['entry_visits'],1)
        self.assertEqual(worker['result']['state'],'succeeded',worker)
        with self.pool.pool.connect() as con:
            claim = con.execute('SELECT claim_id,binding FROM candidate_claims').fetchall()
        self.assertEqual(len(claim),1)
        attempt = json.loads(claim[0]['binding'])['attempt_id']
        with self.ledger.connect() as con:
            first = con.execute("""SELECT id,state,json_extract(request_json,'$.dispatch_attempt_id') AS attempt_id,
                json_extract(response,'$.result.name') AS tool,json_extract(response,'$.result.tool_call_id') AS tool_id
                FROM model_requests ORDER BY started LIMIT 1""").fetchone()
        self.assertEqual((first['state'],first['attempt_id'],first['tool'],first['tool_id']),
                         ('succeeded',attempt,'observe','OFFLINE-consumer-call-1'))
        output = Path(report['evidence_output'])
        for item in ('search-*.json','batch-0000-response.json','batch-0000-tool-call.json','batch-0000-tool-result.json'):
            self.assertTrue(list(output.glob(item)),item)

        monitor = [sys.executable,'-B','-m','webcollect.candidate_monitor',*observer_args]
        for _ in range(2):
            subprocess.run(monitor,env=env,capture_output=True,text=True,timeout=15,check=True)
        def records(filename):
            return [json.loads(line) for line in (self.root/'monitor-logs'/filename).read_text().splitlines()]
        searches = [r for r in records('producer-calls.jsonl') if r['event']=='search_request']
        self.assertEqual([(r['kind'],r['state']) for r in searches],[('search','succeeded')])
        calls = [r for r in records('consumer-calls.jsonl') if r['event']=='accounted' and r['id']==first['id']]
        self.assertEqual(len(calls),1)
        self.assertEqual(calls[0]['tool_call_id'],first['tool_id'])
        self.export_trace('r02-first-call',{'trial_manifest':str(self.chain),'producer_output':str(output),
            'candidate_id':report['candidate_ids'][0], 'claim_id':claim[0]['claim_id'],'claim_count':len(claim),
            'rival':rival['state'],'attempt_id':attempt,'first_react_request':dict(first),
            'consumer_pid':child.pid,'consumer_exit':child.exitcode,'observer_failure_exit':failed.returncode,
            'observer_error':failed.stderr.strip(),'consumer_alive_after_observer_failure':True,
            'consumer_result':worker['result']['state'],'observer_replay_search_kind':searches[0]['kind']})

    async def test_joint_scoped_worker_skips_old_pending_and_finishes_after_a_page_error(self):
        old_id = self.pool.put({**self.v2, 'entry_url':'https://old.example.org/'}, self.source)
        self.capture = AsyncMock(side_effect=OSError('controlled failed capture'))
        with self.boundaries():
            report = await self.produce()
            args = self.cli_args('scoped') + ['--producer-batch', report['batch_scope'], '--limit', '2', '--poll-seconds', '1']
            results = await asyncio.to_thread(self.invoke, consumer_cli, args)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['candidate_id'], report['candidate_ids'][0])
        self.assertEqual(results[0]['state'], 'failed')
        self.assertIn('controlled failed capture', results[0]['reason'])
        self.assertTrue(self.pool.producer_batch_drained(report['batch_scope']))
        self.assertEqual([r['candidate_id'] for r in self.pool.rows(state='pending', protocols=(VERSION2,))], [old_id])

    async def test_joint_caller_target_keeps_parameters_and_category(self):
        goal={'kind':'edit','entity':'fields','parameters':{'quantity':20,'price':30}}
        goals=self.chain.parent.parent/'caller-goals.json'
        save_json(goals,{'schema_version':'webcollect-caller-goals-1','goals':[
            {'uri':self.uri,'requested_goal':goal,'category_hint':'在线工具'}]})
        with self.boundaries():
            produced=await self.produce(goals=goals)
            self.assertEqual(produced['listed_unique_candidates'],1)
            result=await self.consume_cli()
            row,claim,task=self.assert_complete(result)
            self.assertEqual(row['candidate']['candidate_kind'],'target')
            self.assertEqual(row['sources'][0]['category_hint'],'在线工具')
            self.assertEqual(task['workflow_proposal']['spec']['goal']['structured'],goal)
            self.assertTrue(all(prompt['requested_goal']==goal for prompt in self.prompts))
            self.assertEqual(len(self.wire),5)  # Caller targets need no discovery-model dispatch.
            self.assertEqual(len(self.gotos),1)
            self.export_trace('target',{'candidate_kind':'target','requested_goal_preserved':True,
                'source_category_preserved':True,'producer_http':0,'consumer_http':5,'entry_navigations':1,'saved':1})

    async def test_joint_caller_target_without_category_remains_unknown(self):
        goals=self.chain.parent.parent/'caller-goals-no-category.json'
        save_json(goals,{'schema_version':'webcollect-caller-goals-1','goals':[{'uri':self.uri,
            'requested_goal':{'kind':'edit','entity':'fields','parameters':{'quantity':20}}}]})
        with self.boundaries():
            await self.produce(goals=goals)
            result=await self.consume_cli()
            self.assertEqual(result['state'],'failed')
            self.assertIn('category UNKNOWN',result['reason'])
            self.assertEqual(statistics(self.pool)['formal_attempts'],0)
            self.assertEqual(len(self.wire),0)
            self.assertEqual(len(self.gotos),1)
            self.export_trace('unknown-category',{'formal_attempts':0,'http':0,'entry_navigations':1,
                'category':'UNKNOWN','saved':0})

    async def test_joint_saved_crash_and_producer_resume_do_not_dispatch(self):
        with self.boundaries():
            await self.produce()
            with patch('webcollect.candidate_consumer.finish_or_reconcile',side_effect=OSError('CONTROLLED saved before pool projection')):
                with self.assertRaises(OSError):await self.consume_cli()
            self.assertEqual(statistics(self.pool)['collected'],1)
            with self.pool.pool.connect() as con:
                cid=con.execute('SELECT claim_id FROM candidate_claims').fetchone()[0]
            counts=(len(self.wire),len(self.contexts),len(self.gotos))
            recovered=await asyncio.to_thread(self.invoke,consumer_cli,['--pool',str(self.pool.path),'reconcile','--claim-id',cid])
            self.assert_complete(recovered)
            resumed=await self.produce()
            self.assertEqual(resumed['listed_unique_candidates'],1)
            replay=await self.consume_cli()
            self.assertEqual(replay['state'],'succeeded')
            self.assertEqual(counts,(len(self.wire),len(self.contexts),len(self.gotos)))
            self.export_trace('recovery',{'saved':1,'extra_http':0,'extra_contexts':0,'extra_entry_navigations':0})

    async def test_joint_unknown_request_is_retained_and_never_resent(self):
        with self.boundaries():
            await self.produce();self.return_unknown=True
            result=await self.consume_cli()
            self.assertEqual(result['state'],'reconcile',result)
            counts=(len(self.wire),len(self.contexts),len(self.gotos))
            replay=await self.consume_cli()
            self.assertEqual(replay['state'],'reconcile')
            self.assertEqual(counts,(len(self.wire),len(self.contexts),len(self.gotos)))
            with self.ledger.connect() as con:
                requests=[dict(r) for r in con.execute('SELECT state,cost FROM model_requests')]
            self.assertEqual(requests,[{'state':'unknown','cost':None}])
            self.assertEqual(statistics(self.pool)['collected'],0)
            self.export_trace('unknown',{'requests':1,'state':'unknown','cost':None,'saved':0,'extra_http':0})

    async def test_joint_two_os_consumers_have_one_claim_and_one_save(self):
        with self.boundaries():
            await self.produce()
        context=multiprocessing.get_context('fork'); start=context.Event()
        reports=self.root/'joint-workers';reports.mkdir()
        def worker(index):
            start.wait(10)
            try:
                with self.boundaries():
                    result=self.invoke(consumer_cli,self.cli_args('joint-race-'+str(index),'worker-'+str(index)))[0]
                save_json(reports/str(index),{'state':result['state'],'entry_navigations':len(self.gotos),
                    'contexts':len(self.contexts),'consumer_http':len(self.wire)-1})
            except BaseException as error:
                save_json(reports/str(index),{'error':type(error).__name__+':'+str(error)})
        children=[context.Process(target=worker,args=(index,)) for index in range(2)]
        for child in children:child.start()
        start.set()
        for child in children:
            await asyncio.to_thread(child.join,40)
            if child.is_alive():child.kill();child.join();self.fail('bounded worker timed out')
            self.assertEqual(child.exitcode,0)
        rows=[load_json(reports/str(index)) for index in range(2)]
        self.assertFalse(any('error' in row for row in rows),rows)
        self.assertEqual(sorted(row['state'] for row in rows),['EMPTY','succeeded'])
        self.assertEqual(sum(row['entry_navigations'] for row in rows),1)
        self.assertEqual(sum(row['contexts'] for row in rows),1)
        self.assertEqual(sum(row['consumer_http'] for row in rows),5)
        with self.pool.pool.connect() as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM candidate_claims').fetchone()[0],1)
            self.assertEqual(con.execute('SELECT COUNT(*) FROM candidate_results WHERE effective=1').fetchone()[0],1)
        self.assertEqual(statistics(self.pool)['collected'],1)
        self.export_trace('competition',{'processes':2,'claims':1,'contexts':1,'entry_navigations':1,'consumer_http':5,'saved':1})


def load_tests(loader,tests,pattern):
    return unittest.TestSuite(PipelineAcceptance(name) for name in loader.getTestCaseNames(PipelineAcceptance)
                              if name.startswith('test_joint_'))
