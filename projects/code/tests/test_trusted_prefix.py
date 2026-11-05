"""Disposable historical prefix matrix; no real browser/model/production IO."""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

from test_react_session import ReactHarness, decide, act_step
import test_react_native as fixture
from test_react_native import scroll, finish
from webcollect.react_session import build_url_task
from webcollect.postprocess import process, session_record
from webcollect.batch_core import file_sha, load_json
from webcollect.trusted_prefix import VERSION, project_prefix
from webcollect.closing_policy import annotation_errors


class TrustedPrefixTests(ReactHarness, unittest.IsolatedAsyncioTestCase):
    recorded = fixture.NativeSessionTests.recorded

    def setUp(self):
        super().setUp()
        self.task = build_url_task(url=self.page.url,task_version='prefix-fixture',trusted_prefix_protocol=VERSION)
        self.ids = {'sample_id':'S000001_sample_000001','site_id':'S000001',
            'batch_id':'B20261104_001','attempt_id':'prefix-original-attempt'}
        self.manifest = {'batch_id':self.ids['batch_id'],'sample_kind':'real','program_version':'CONTROLLED',
            'rule_version':'1.0.0','sites':[{'site_id':self.ids['site_id'],'uri':self.page.url,
            'site_category':self.task['site_category']}],'samples':[self.ids['sample_id']]}

    async def source(self, tail):
        builds=[scroll('查看连续正文')]+[scroll() for _ in range(7)]
        if tail == 'not_dispatched':
            builds += [decide(tool='act',arguments=lambda p:{'observation_id':p['observation']['observation_id'],
                'step':act_step('click',control_id='control-0')})]
        elif tail in ('known_failure','unknown'):
            original=self.surface.execute_action
            def execute(kind,args):
                if len(self.surface.executed)==8:
                    self.surface.executed.append((kind,deepcopy(args)))
                    if tail=='unknown':raise TimeoutError('CONTROLLED ninth result unknown')
                else:original(kind,args)
            self.surface.execute_action=execute
            builds += [scroll()]
        builds += [finish()]
        session,evidence,_=self.recorded(builds,name=tail)
        result=await session.run()
        self.assertEqual(result['effective_steps'],8,result)
        return evidence,result

    def derive(self,evidence):
        delivery=evidence.parents[1]/'samples'/self.ids['sample_id']
        from webcollect.evidence import audit_capture
        def audit(path):
            result=audit_capture(evidence.parents[1],self.ids['sample_id'])
            return [] if result['capture_evidence_pass'] else [str(result)]
        result=process(evidence,delivery,self.ids,self.manifest,prefix_end_step=8,validators=(audit,))
        if result['status']!='derived_saved' and result.get('record_ref'):
            self.fail(str(load_json(result['record_ref']['path'])))
        self.assertEqual(result['status'],'derived_saved',result)
        a=load_json(delivery/'annotation.json')
        self.assertEqual(annotation_errors(a),[])
        from quality_inspector.format_checks import sample_check
        checked=sample_check(delivery)
        self.assertTrue(checked['confirmed_format_pass'],checked['errors'])
        return delivery,result,a

    async def test_eight_action_prefix_three_ninth_step_outcomes(self):
        initial=deepcopy(self.surface.state)
        original=self.surface.execute_action
        for tail,dispatches in [('not_dispatched',8),('known_failure',9),('unknown',9)]:
            with self.subTest(tail=tail):
                self.surface.state=deepcopy(initial);self.surface.executed=[];self.surface.execute_action=original
                evidence,source=await self.source(tail)
                raw_hashes={str(p):file_sha(p) for p in (evidence/'raw').rglob('*') if p.is_file()}
                original_ninth=evidence/'step_009.json'
                ninth_hash=file_sha(original_ninth) if original_ninth.exists() else None
                delivery,result,a=self.derive(evidence)
                binding=load_json(evidence/'saved_sample.json')['raw_execution']['trusted_prefix']
                self.assertEqual(len(self.surface.executed),dispatches)
                self.assertEqual(binding['excluded_tail']['source_unknown'],tail=='unknown')
                self.assertEqual(binding['source_interval'],{'start_step':1,'end_step':8})
                self.assertEqual(a['completion_status'],'success');self.assertNotIn('复制',a['task_instruction'])
                self.assertFalse(binding['original_goal_completed']);self.assertFalse(binding['QC_approval'])
                self.assertEqual(raw_hashes,{str(p):file_sha(p) for p in (evidence/'raw').rglob('*') if p.is_file()})
                if ninth_hash:self.assertEqual(file_sha(original_ninth),ninth_hash)
                second=process(evidence,delivery,self.ids,self.manifest,prefix_end_step=8)
                self.assertTrue(second['idempotent_reuse'])
                self.assertEqual(len((evidence/'derivations.jsonl').read_text().splitlines()),1)
                from quality_inspector.ai_worker import compact_trajectory,snapshot
                material,_=compact_trajectory(snapshot(delivery))
                self.assertNotIn('trusted_prefix',material)
                self.assertEqual(material['whole_trajectory_length']['effective_steps'],8)
                if tail=='unknown':
                    with self.assertRaisesRegex(ValueError,'UNKNOWN'):session_record(evidence/'raw')

    async def test_untrusted_boundary_does_not_produce_sample(self):
        evidence,_=await self.source('not_dispatched')
        source=session_record(evidence/'raw')
        final=source['trajectory'][7]['after_observation_id']
        bad=deepcopy(source)
        # A caller-provided observation must match its bound original tree.
        bad['observations'][final]['state_path']=source['observations'][source['trajectory'][0]['before_observation_id']]['state_path']
        with self.assertRaises(ValueError):project_prefix(bad,evidence/'raw',8,self.ids)
        self.assertFalse((evidence/'saved_sample.json').exists())

    async def test_six_minimum_and_no_disconnected_or_duplicate_actions(self):
        evidence,_=await self.source('not_dispatched');source=session_record(evidence/'raw')
        with self.assertRaisesRegex(ValueError,'at least six'):project_prefix(source,evidence/'raw',5,self.ids)
        for change in ('duplicate','gap','missing_image'):
            bad=deepcopy(source)
            if change=='duplicate':bad['trajectory'][6]=deepcopy(bad['trajectory'][5])
            elif change=='gap':bad['trajectory'][6]['before_observation_id']=bad['trajectory'][0]['before_observation_id']
            else:bad['observations'][bad['trajectory'][7]['after_observation_id']]['evidence']['image']['sha256']='0'*64
            with self.subTest(change=change),self.assertRaises(ValueError):project_prefix(bad,evidence/'raw',8,self.ids)

    async def test_prefix_terminal_cannot_claim_excluded_expected_result(self):
        evidence,_=await self.source('unknown');delivery,result,a=self.derive(evidence)
        self.assertIn('历史边界',a['final_result'])
        self.assertNotIn('原目标完成',a['task_instruction'])
        self.assertNotIn('collection_ending',a['steps'][-1]['tool_result']['return_value'])
        self.assertNotIn(str(self.root),__import__('json').dumps(a))

    async def test_failed_validator_can_derive_new_version_without_overwriting_failed_projection(self):
        evidence,_=await self.source('unknown')
        first=self.root/'failed-delivery'/self.ids['sample_id']
        rejected=process(evidence,first,self.ids,self.manifest,prefix_end_step=8,validators=(lambda _:['controlled rejection'],))
        self.assertEqual(rejected['status'],'delivery_rejected')
        prior={str(p):file_sha(p) for p in (evidence/'trusted-prefix-01').rglob('*') if p.is_file()}
        destination,result,_=self.derive(evidence)
        self.assertEqual(result['derivation'],2)
        self.assertEqual(prior,{str(p):file_sha(p) for p in (evidence/'trusted-prefix-01').rglob('*') if p.is_file()})
        projection=evidence/'trusted-prefix-02/ground_truth.json'
        projection.write_text('[] changed')
        with self.assertRaisesRegex(ValueError,'saved sample'):
            process(evidence,destination,self.ids,self.manifest,prefix_end_step=8)

    async def test_calculation_and_parameter_only_boundaries_never_include_unknown_copy(self):
        initial=deepcopy(self.surface.state);original=self.surface.execute_action
        for shown in (False,True):
            self.surface.state=deepcopy(initial);self.surface.executed=[]
            self.surface.state['elements'][0]['text']='长度'
            self.surface.state['elements'][1]['text']='宽度'
            self.surface.state['title']='矩形面积计算器'
            self.surface.state['visible_text']='矩形面积计算器\n长度\n宽度\n英尺'
            def execute(kind,args):
                if len(self.surface.executed)==8:
                    self.surface.executed.append((kind,deepcopy(args)))
                    raise TimeoutError('CONTROLLED ninth copy effect unknown')
                original(kind,args)
                if len(self.surface.executed)==8 and shown:
                    self.surface.state['visible_text']='矩形面积计算器\n面积 106.25 平方英尺'
            self.surface.execute_action=execute
            def fill(cid,value):
                return decide(tool='act',arguments=lambda p:{'observation_id':p['observation']['observation_id'],
                    'step':act_step('set_value',control_id=cid,value=value,goal='填写矩形参数',expected='显示输入参数')})
            builds=[scroll('查看矩形参数'),scroll(),
                decide(tool='observe',arguments={'focus_control_id':'control-0'}),fill('control-0','12.5'),
                decide(tool='observe',arguments={'focus_control_id':'control-1'}),fill('control-1','8.5'),
                decide(tool='act',arguments=lambda p:{'observation_id':p['observation']['observation_id'],
                    'step':act_step('hotkey',keys=['ctrl','c'],goal='复制计算结果',expected='结果已复制')}),finish()]
            session,evidence,_=self.recorded(builds,name='calculation-'+str(shown))
            result=await session.run()
            self.assertEqual(result['effective_steps'],8,result)
            destination,result,a=self.derive(evidence)
            self.assertIn('12.5',a['task_instruction']);self.assertIn('8.5',a['task_instruction'])
            self.assertNotIn('复制',a['task_instruction']);self.assertNotIn('复制',a['final_result'])
            if shown:
                self.assertIn('106.25',a['task_instruction']);self.assertIn('106.25',a['final_result'])
            else:
                self.assertNotIn('106.25',a['task_instruction']);self.assertNotIn('106.25',a['final_result'])
                self.assertIn('填写',a['task_instruction'])

    def test_semantic_prefix_context_invalidates_terminal_rule_only(self):
        from quality_inspector.semantic_runtime import rules
        original={'semantic_rule_ids':{'terminal_semantics':'terminal-v5','language':'language-v2','privacy':'privacy-v1','visual_alignment':'visual-v1'}}
        changed={**original,'trusted_prefix':{'protocol':VERSION,'source_interval':{'start_step':1,'end_step':8}}}
        a=rules('ai-visual',original);b=rules('ai-visual',changed)
        self.assertNotEqual(a['terminal_semantics'],b['terminal_semantics'])
        self.assertEqual({k:v for k,v in a.items() if k!='terminal_semantics'},
                         {k:v for k,v in b.items() if k!='terminal_semantics'})


class PrefixNormalEntryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        import test_pipeline_offline_e2e as pipeline
        self.case=pipeline.PipelineAcceptance('test_joint_producer_cli_to_same_page_save_and_writeback')
        self.case.setUp();self.addCleanup(self.case.doCleanups)
        c=self.case
        c.decisions=[scroll('查看连续正文')]+[scroll() for _ in range(7)]

    async def test_unknown_tail_formal_save_export_and_independent_qc_handoff(self):
        c=self.case;original=c.surface.execute_action
        def execute(kind,args):
            if len(c.surface.executed)==7:
                c.surface.executed.append((kind,deepcopy(args)))
                raise TimeoutError('CONTROLLED eighth effect unknown; first seven historically verified')
            original(kind,args)
        c.surface.execute_action=execute
        policy=c.root/'prefix-qc-policy.json'
        import json
        policy.write_text(json.dumps({'ai_percent':100,'human_percent':0,'seed':'CONTROLLED-PREFIX'}))
        from webcollect.task_generation import execute as original_execute
        execution_errors=[]
        async def tracked_execute(*args,**kwargs):
            try:return await original_execute(*args,**kwargs)
            except Exception as error:
                execution_errors.append(type(error).__name__+': '+str(error));raise
        with c.boundaries(),patch('webcollect.task_generation.execute',side_effect=tracked_execute):
            await c.produce()
            from webcollect.candidate_consumer import main
            import asyncio
            result=(await asyncio.to_thread(c.invoke,main,c.cli_args('prefix','prefix-worker')+['--qc-policy',str(policy)]))[0]
        self.assertEqual(result['state'],'succeeded',(result,[(str(p),load_json(p)) for name in ('failure.json','prefix-ineligible.json') for p in c.output.rglob(name)]))
        row,claim,task=c.assert_complete(result)
        self.assertEqual(task['fragment']['trusted_prefix_protocol'],VERSION)
        self.assertIn('execution_result',claim['binding'],execution_errors)
        execution=claim['binding']['execution_result']
        self.assertEqual(execution['delivery_stages']['customer_export'],'EXPORTED_FORMAT_VALID')
        self.assertEqual(execution['delivery_stages']['qc_handoff'],'PREPARED')
        saved=load_json(result['result']['save_receipt']['path'])
        binding=saved['raw_execution']['trusted_prefix']
        self.assertEqual(binding['source_interval']['end_step'],7)
        self.assertTrue(binding['excluded_tail']['source_unknown'])
        source=Path(result['result']['save_receipt']['path']).parent
        self.assertTrue(load_json(source/'raw/terminal.json')['unknown'])
        self.assertTrue(load_json(source/'prefix-source-closeout.json')['original_unknown'])
        self.assertEqual(row['result']['qc_state'],'pending_review')
        self.assertFalse(execution['QC_approval'])
        a=load_json(Path(execution['candidate'])/'samples'/result['result']['sample_id']/'annotation.json')
        self.assertEqual(a['completion_status'],'success')
        self.assertEqual(len(a['steps']),8)
        from webcollect.collect_runtime import verify_committed_samples
        with __import__('sqlite3').connect(claim['binding']['registry']) as con:
            con.row_factory=__import__('sqlite3').Row
            attempt=dict(con.execute('SELECT * FROM m4_attempts WHERE attempt_id=?',(result['result']['attempt_id'],)).fetchone())
        attempt['evidence']=__import__('json').loads(attempt['evidence_json'])
        verify_committed_samples(source.parents[1],[attempt])

        from webcollect.qc_handoff import prepare_qc_inputs
        no_checks=prepare_qc_inputs(execution['candidate'],c.chain,c.root/'prefix-no-extra-checks',
            ai_percent=100,human_percent=0,seed='PREFIX-NO-OPTIONAL-CHECKS')
        self.assertIsNotNone(no_checks['collection_checks'])
        self.assertTrue(load_json(no_checks['collection_checks']['path'])['prefix_only'])
        from quality_inspector.ai_worker import prepare as prepare_ai,run as run_ai
        from webcollect.batch_core import BatchLedger
        config=load_json(Path(__file__).resolve().parents[1]/'config/batch-synthetic.json')
        config['model']['max_images']=20
        qc=BatchLedger(c.root/'prefix-synthetic-qc.sqlite3',config,initialize=True)
        queued=prepare_ai(qc,execution['candidate'],c.root/'prefix-synthetic-prepared',
            effective_set=no_checks['effective_set'],collection_checks=no_checks['collection_checks'])
        self.assertEqual(queued['queued_samples'],1)
        jobs=[qc.get(row['visual_job']) for row in load_json(queued['queue_file'])['jobs']]
        self.assertEqual(jobs[0]['payload']['trusted_prefix']['source_interval']['end_step'],7)
        difference=qc.get(load_json(queued['queue_file'])['jobs'][0]['difference_job'])
        self.assertEqual(difference['payload']['pending_collection_checks'],[])
        from webcollect.model_gateway import ModelGateway
        wire=[];call=ModelGateway.call
        def tracked(gateway,*args,**kwargs):
            wire.append(args[2]);return call(gateway,*args,**kwargs)
        with patch.object(ModelGateway,'call',tracked):
            reviewed=run_ai(qc,max_jobs=2)
        self.assertTrue(all(item['state']=='done' for item in reviewed['outcomes']),reviewed)
        self.assertFalse(any(str(c.root) in text for text in wire))
        annotation=Path(execution['candidate'])/'samples'/result['result']['sample_id']/'annotation.json'
        original_bytes=annotation.read_bytes();changed=load_json(annotation)
        changed['task_instruction']+='，再次核对可见文字'
        import json
        annotation.write_text(json.dumps(changed,ensure_ascii=False))
        before=qc.summary()['model_requests']
        try:
            with self.assertRaisesRegex(ValueError,'different customer-sample bytes'):
                prepare_ai(qc,execution['candidate'],c.root/'wrong-customer-sample',
                    effective_set=None,collection_checks=no_checks['collection_checks'])
            self.assertEqual(qc.summary()['model_requests'],before)
        finally:annotation.write_bytes(original_bytes)
