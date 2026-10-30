"""Disposable P0 fragments, rolling proposals and sampled-QC protocol fixtures.

Authored decisions are test inputs, never real AI/human or production evidence.
"""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import csv
import shutil
import sqlite3
import tempfile
from test_planner_repair import SemanticFixture
from webcollect.batch_core import BatchLedger, load_json, save_json
from webcollect.fragment_workflow import VERSION, compile_fragment
from webcollect.workflow_proposal import verify_task


def seed_captures(registry, ids, *, prefix=10, scope='CONTROLLED-scope', evidence=None):
    """Author ledger protocol rows in a temporary DB; not real capture evidence."""
    from webcollect.runtime import SCHEMA, DEFAULT_POLICY
    from webcollect.sampling_context import register_capture, ensure_schema
    from webcollect.planning import object_sha256, canonical
    con = sqlite3.connect(registry); con.row_factory = sqlite3.Row; con.executescript(SCHEMA); ensure_schema(con)
    policy = {**DEFAULT_POLICY, 'campaign_id':'CONTROLLED-campaign'}
    con.execute('INSERT OR IGNORE INTO m4_campaigns VALUES(?,?,?)', ('CONTROLLED-campaign',canonical(policy),1))
    con.execute('INSERT OR IGNORE INTO m4_scopes VALUES(?,?,?,?)',(scope,'CONTROLLED-campaign','active',1))
    all_ids = [f'CONTROLLED-prefix-{n}' for n in range(prefix)] + list(ids)
    prior_report = Path(registry).with_suffix('.prior-protocol.json'); save_json(prior_report, {'fixture':'AUTHORED PROTOCOL STATE ONLY'})
    for n, sid in enumerate(all_ids):
        task = {'task_id':sid,'site_uri':'https://example.org/','fragment':{'schema_version':VERSION,
            'quality_policy_version':'qc-sampling-v1-20261030','policy_version':'legal-web-actions-fragment-1',
            'operation_template':'click+scroll'}}
        existing = con.execute('SELECT task_key FROM m4_attempts WHERE sample_id=?',(sid,)).fetchone()
        key = existing[0] if existing else 'key-'+sid
        con.execute('INSERT INTO m4_tasks VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (key,scope,'CONTROLLED-campaign',sid,'v1',object_sha256(task),canonical(task),'工具','example.org',
             'collected_pending_review',1,9999999999,0,n+1))
        if not existing:
            con.execute('INSERT INTO m4_attempts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                ('attempt-'+sid,scope,'CONTROLLED-campaign',key,'plan',sid,'worker','lease',9999999999,sid,'SITE1','batch',
                 'collected_pending_review',n+1,n+1,n+2,None,None,None,json.dumps((evidence or {}).get(sid,[]))))
        row=con.execute('SELECT a.*,t.task_json FROM m4_attempts a JOIN m4_tasks t ON t.task_key=a.task_key WHERE sample_id=?',(sid,)).fetchone()
        register_capture(con,row)
        if n < prefix:
            group=con.execute('SELECT group_id FROM m4_fragment_captures WHERE sample_id=?',(sid,)).fetchone()[0]
            con.execute('INSERT INTO m4_quality_admissions VALUES(?,?,?,?,?,?,?,?)',(sid,'CONTROLLED-campaign',group,
                'ACCEPTED_BY_BATCH_POLICY','PASS',0,json.dumps({'path':str(prior_report),'sha256':__import__('hashlib').sha256(prior_report.read_bytes()).hexdigest()}),0))
    con.commit(); con.close()


class FragmentContracts(SemanticFixture, unittest.TestCase):
    def proposal(self):
        self.case_number = getattr(self, 'case_number', 0)+1
        self.fixture.root = self.root/f'case-{self.case_number}'
        self.fixture.root.mkdir()
        cap, _ = self.semantic()
        return cap, {'schema_version': VERSION, 'task_family': 'navigation-reading',
            'instruction': '在「受控离线页面」输入查询值，清空后继续输入并查看当前页面。',
            'task_type': ['填写表单', '数据查看'],
            'steps': [{'action': 'set_value', 'control_id': 'p0/control-0', 'value': v,
                       'goal': '输入查询条件', 'expected': '显示输入内容'} for v in ('20', '', '30')],
            'end_description': '查看当前页面的输入状态。'}

    def test_multi_round_control_and_mid_business_end(self):
        cap, spec = self.proposal(); task = compile_fragment(cap, spec, 'controlled')
        self.assertEqual([o['action_type'] for o in task['operations']],
                         ['click','hotkey','type','hotkey','hotkey','type'])
        self.assertFalse(task['stop_when_final']); self.assertEqual(task['final_assertions'], [])
        self.assertEqual(task['fragment']['business_completion'], 'NOT_CLAIMED')
        verify_task(task, cap)
        from webcollect.task_contract import terminal_evidence
        raw = [{'operation': op, 'operation_origin': 'planned', 'ended_at': 'fixture'} for op in task['operations']]
        proof = terminal_evidence(task, raw, [], {'screenshot_sha256': 'fixture-final-original'})
        self.assertEqual(proof['effective_steps'], 6)
        with self.assertRaises(ValueError): terminal_evidence(task, raw[:-1], [], {'screenshot_sha256':'fixture'})

    def test_parameter_variants_are_candidates_exact_sequence_is_idempotent(self):
        from webcollect.task_generation import task_signature, customer_history_decision
        cap, spec = self.proposal(); first = compile_fragment(cap, spec, 'controlled')
        other = deepcopy(spec); other['steps'][-1]['value'] = '99'
        second = compile_fragment(cap, other, 'controlled')
        self.assertNotEqual(task_signature(first), task_signature(second))
        self.assertEqual(first['task_id'], compile_fragment(cap, spec, 'other-version')['task_id'])
        self.assertIsNone(customer_history_decision(first, [{'sample_id':'CONTROLLED-history'}]))

    def test_scroll_reading_without_form_or_result_and_no_static_steps(self):
        cap, spec = self.proposal()
        spec['steps'] = [{'action':'scroll','direction':'down','goal':'向下浏览页面内容','expected':'显示后续内容'} for _ in range(5)]
        task = compile_fragment(cap, spec, 'controlled')
        self.assertEqual(len(task['operations']), 5)
        for invalid in ('wait', 'read', 'complete'):
            bad = deepcopy(spec); bad['steps'][0]['action'] = invalid
            with self.assertRaises(ValueError): compile_fragment(cap, bad, 'controlled')
        bad = deepcopy(spec); bad['steps'].pop()
        with self.assertRaises(ValueError): compile_fragment(cap, bad, 'controlled')

    def test_unobserved_controls_and_unproved_navigation_rejected(self):
        cap, spec = self.proposal(); spec['steps'][0]['control_id'] = 'invented'
        with self.assertRaises(ValueError): compile_fragment(cap, spec, 'controlled')
        cap, spec = self.proposal(); spec['steps'][0] = {'action':'open_url','page_id':'unobserved','goal':'查看页面','expected':'显示页面'}
        with self.assertRaises(ValueError): compile_fragment(cap, spec, 'controlled')

    def test_site_round_generates_multiple_routes_and_resumes_without_second_request(self):
        from webcollect.site_rolling import plan_round
        from test_s0_task_generation import catalog
        cap, spec = self.proposal(); source = catalog(self.root/'catalog.json', [cap])
        ledger = BatchLedger(self.root/'rolling.db', load_json(Path(__file__).parents[1]/'config/batch-synthetic.json'), initialize=True)
        other = deepcopy(spec); other['steps'][-1]['value'] = '99'
        with patch('webcollect.model_gateway.ModelGateway.call', return_value={'tasks':[spec,other],'empty_reasons':[]}) as call:
            result = plan_round(ledger, source, cap['site_uri'], self.root/'round-1')
            again = plan_round(ledger, source, cap['site_uri'], self.root/'round-1')
        self.assertEqual(result, again); self.assertEqual(call.call_count, 1)
        self.assertEqual(result['generated_tasks'], 2, load_json(result['generation_result']['path']))
        self.assertEqual(ledger.get(result['queue_job_id'])['state'], 'queued')
        self.assertFalse(result['collection_started'])


class SampledQualityContracts(unittest.TestCase):
    def setUp(self):
        from test_s0_sampling import multi_fixture
        from quality_inspector.checksums import write_manifest
        from PIL import Image
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name); self.dataset=multi_fixture(self.root/'fixture',count=1)
        first=next((self.dataset/'samples').iterdir()); base=load_json(first/'annotation.json')
        for step in base['steps']:
            Image.new('RGB',(640,480),'white').save(first/step['image_path'])
        with (self.dataset/'metadata.csv').open(newline='') as f:
            original=list(csv.reader(f)); header,row=original[0],original[1]
        entries=[]; self.ids=[]
        for n in range(50):
            sid=first.name if n==0 else f'CONTROLLED-sample-{n:03}'
            folder=first if n==0 else self.dataset/'samples'/sid
            if n:shutil.copytree(first,folder)
            annotation=deepcopy(base);annotation['sample_id']=sid
            (folder/'annotation.json').write_text(json.dumps(annotation,ensure_ascii=False))
            entry=list(row);entry[0]=sid;entries.append(entry);self.ids.append(sid)
        with (self.dataset/'metadata.csv').open('w',newline='') as f:
            writer=csv.writer(f);writer.writerow(header);writer.writerows(entries)
        (self.dataset/'SHA256SUMS').unlink();write_manifest(self.dataset)
        self.registry=self.root/'runtime.sqlite3';seed_captures(self.registry,self.ids)
        from webcollect.sampling_context import production_context
        self.context=production_context({'registry':str(self.registry)},self.ids)
        from quality_inspector import delivery_sampling as s
        self.plan=self.root/'plan.json'; self.value=s.freeze(self.dataset,self.plan,ai_percent=10,human_percent=0,
            seed='CONTROLLED-frozen',production_context=self.context)
        self.selected={slot['slot_id'] for slot in self.value['slots'] if slot['ai_selected']}
        self.serial=0

    def reviews(self, ids, *, failures=(), severe=False, localized=True):
        from test_s0_sampling import controlled_reviews
        self.serial+=1;path=self.root/f'reviews-{self.serial}.json'
        value=controlled_reviews(self.dataset,path)
        value['records']=[r for r in value['records'] if r['sample_id'] in ids]
        for row in value['records']:
            if row['sample_id'] in failures:
                row['checks']['privacy' if severe else 'language']['status']='FAIL'
                row['failure_assessment']={'scope':'LOCAL' if localized else 'UNKNOWN',
                    'reason':'CONTROLLED isolated protocol issue, not real judgment','evidence_steps':[1]}
        # This file was authored by this test; publish each immutable variant once.
        path.write_text(json.dumps(value));return path

    def test_ten_percent_admits_batch_without_claiming_fifty_ai_reviews(self):
        from quality_inspector import delivery_sampling as s
        self.assertEqual(len(self.selected),5)
        review=self.reviews(self.selected); result,effective=s.evaluate(self.plan,self.dataset,ai_reviews=[review])
        self.assertEqual(result['accepted_ai_pass'],5);self.assertEqual(result['accepted_not_selected'],45)
        self.assertEqual(result['batch_accepted'],50);self.assertEqual(len(effective),5)
        self.assertFalse(result['unselected_semantic_pass_claimed'])
        self.assertTrue(all(not r['semantic_review_claimed'] for r in result['rows'] if r['ai_status']=='NOT_SELECTED'))

    def test_one_local_failure_expands_thirty_percent_retaining_original_five(self):
        from quality_inspector import delivery_sampling as s
        from quality_inspector.production_sampling import advance
        bad=next(iter(self.selected));first=self.reviews(self.selected,failures=[bad])
        result,_=s.evaluate(self.plan,self.dataset,ai_reviews=[first]);self.assertEqual(result['batch_accepted'],0)
        successor=self.root/'expanded.json';advance(self.plan,self.dataset,successor,ai_reviews=[first])
        plan=s.verify(successor,self.dataset);selected={r['slot_id'] for r in plan['slots'] if r['ai_selected']}
        self.assertEqual(len(selected),15);self.assertTrue(self.selected<=selected)
        all_reviews=self.reviews(selected,failures=[bad]);result,_=s.evaluate(successor,self.dataset,ai_reviews=[all_reviews])
        self.assertEqual(result['batch_accepted'],49);self.assertEqual(result['accepted_ai_pass'],14)
        self.assertEqual(result['accepted_not_selected'],35)

    def test_second_failure_escalates_full_and_severe_failure_bypasses_thirty(self):
        from quality_inspector import delivery_sampling as s
        from quality_inspector.production_sampling import advance
        bad=next(iter(self.selected));first=self.reviews(self.selected,failures=[bad])
        thirty=self.root/'thirty.json';advance(self.plan,self.dataset,thirty,ai_reviews=[first])
        ids={r['slot_id'] for r in s.verify(thirty)['slots'] if r['ai_selected']}
        extra=next(iter(ids-self.selected));second=self.reviews(ids,failures=[bad,extra])
        full=self.root/'full.json';advance(thirty,self.dataset,full,ai_reviews=[second])
        self.assertEqual(sum(r['ai_selected'] for r in s.verify(full)['slots']),50)
        severe=self.reviews(self.selected,failures=[bad],severe=True)
        direct=self.root/'direct-full.json';advance(self.plan,self.dataset,direct,ai_reviews=[severe])
        self.assertEqual(sum(r['ai_selected'] for r in s.verify(direct)['slots']),50)

    def test_missing_unknown_and_modified_group_never_admit_or_reset(self):
        from quality_inspector import delivery_sampling as s
        result,_=s.evaluate(self.plan,self.dataset)
        self.assertEqual(result['batch_accepted'],0)
        self.assertTrue(all(r['quality_admission']=='PENDING' for r in result['rows']))
        tampered=deepcopy(self.value);tampered['policy']['production_sampling']['positions'][self.ids[0]]['campaign']=999
        tampered=s._seal(tampered);path=self.root/'tampered.json';s.write(path,tampered)
        with self.assertRaises(ValueError):s.verify(path,self.dataset)

    def test_first_ten_and_new_group_are_mandatory_and_seed_cannot_change_on_expansion(self):
        from quality_inspector import delivery_sampling as s
        from quality_inspector.production_sampling import advance
        fresh=self.root/'fresh.sqlite3';seed_captures(fresh,self.ids,prefix=0)
        from webcollect.sampling_context import production_context
        context=production_context({'registry':str(fresh)},self.ids)
        path=self.root/'fresh-plan.json';value=s.freeze(self.dataset,path,ai_percent=10,human_percent=0,
            seed='CONTROLLED-fresh',production_context=context)
        self.assertTrue(set(self.ids[:10]) <= {r['slot_id'] for r in value['slots'] if r['ai_selected']})
        bad=next(iter(self.selected));review=self.reviews(self.selected,failures=[bad])
        out=self.root/'expanded.json';advance(self.plan,self.dataset,out,ai_reviews=[review])
        changed=load_json(out);changed['policy']['seed']='try-again';changed=s._seal(changed)
        altered=self.root/'changed-seed.json';s.write(altered,changed)
        with self.assertRaises(ValueError):s.verify(altered,self.dataset)


class ProductionCallbackContracts(unittest.TestCase):
    def setUp(self):
        from test_qc_handoff import QCHandoffTests
        from webcollect.collect_runtime import sample_hashes
        from webcollect.batch_core import file_sha
        from quality_inspector.checksums import write_manifest
        import random
        from PIL import Image
        self.fixture=QCHandoffTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.root=self.fixture.root;self.dataset=self.fixture.candidate;self.registry=self.fixture.registry
        sid=self.fixture.sample_id;other=sid[:-1]+'2';self.ids=[sid,other]
        original=self.dataset/'samples'/sid;second=self.dataset/'samples'/other;shutil.copytree(original,second)
        annotation=load_json(second/'annotation.json');annotation['sample_id']=other
        annotation['task_instruction']='在「受控补充页」查看不同的说明内容并依次操作页面入口，核对当前显示的信息。'
        rng=random.Random(172)
        for step in annotation['steps']:
            step['page_name']='受控补充状态页'
            size=Image.open(second/step['image_path']).size
            Image.frombytes('RGB',size,rng.randbytes(size[0]*size[1]*3)).save(second/step['image_path'])
        (second/'annotation.json').write_text(json.dumps(annotation,ensure_ascii=False))
        truth=self.dataset/'ground_truth'
        if (truth/(sid+'.json')).exists():shutil.copy2(truth/(sid+'.json'),truth/(other+'.json'))
        with (self.dataset/'metadata.csv').open(newline='') as f:rows=list(csv.reader(f))
        clone=list(rows[1]);clone[0]=other;clone[5]=annotation['task_instruction']
        clone[-1]=str(sum(p.stat().st_size for p in second.rglob('*') if p.is_file()));rows.append(clone)
        with (self.dataset/'metadata.csv').open('w',newline='') as f:csv.writer(f).writerows(rows)
        sites=load_json(self.dataset/'site-list.json');sites['sites'][0]['sample_ids'].append(other)
        sites['samples'].append({'sample_id':other,'site_id':sites['samples'][0]['site_id']})
        (self.dataset/'site-list.json').write_text(json.dumps(sites,ensure_ascii=False))
        source=self.fixture.source;shutil.copytree(second,source/'samples'/other)
        raw=source/'evidence'/other;raw.mkdir();save_json(raw/'fixture.json',{'CONTROLLED_PROTOCOL_ONLY':True})
        saved=raw/'saved_sample.json';save_json(saved,{'attempt_id':'attempt-'+other,'sample_id':other,
            'sample_files_sha256':sample_hashes(source/'samples'/other),'capture_files_sha256':sample_hashes(raw)})
        seed_captures(self.registry,self.ids,evidence={other:[{'path':str(saved),'sha256':file_sha(saved)}]})
        (self.dataset/'SHA256SUMS').unlink();write_manifest(self.dataset)

    def test_actual_capture_handoff_mechanical_sampling_and_runtime_count_without_fake_reviews(self):
        from webcollect.qc_handoff import prepare_qc_inputs
        from webcollect.batch_core import file_sha
        from quality_inspector import delivery_sampling as s
        from quality_inspector.engine import inspect
        from quality_inspector.production_sampling import quality_report
        from delivery_scope_fixture import freeze_scope
        from test_s0_sampling import controlled_reviews
        from webcollect.runtime import RuntimeStore
        handoff=prepare_qc_inputs(self.dataset,self.fixture.history,self.root/'new-handoff',
            ai_percent=10,human_percent=0,seed='CONTROLLED-callback',production_sampling=True)
        plan=s.verify(handoff['sampling_plan']);chosen={r['slot_id'] for r in plan['slots'] if r['ai_selected']}
        review=self.root/'CONTROLLED-authored-review.json';value=controlled_reviews(self.dataset,review)
        value['records']=[r for r in value['records'] if r['sample_id'] in chosen];review.write_text(json.dumps(value))
        effective,cross=freeze_scope(self.root/'scope',[self.dataset])
        profile=self.root/'scope'/'profile.json'
        report=inspect(None,self.dataset,profile=profile,reviews=review,inspection_stage='payload',delivery_sampling_plan=handoff['sampling_plan'])
        ref=lambda p:{'path':str(Path(p).resolve()),'sha256':file_sha(p)}
        report['production_quality']=quality_report(report,ref(effective),ref(cross),ref(handoff['receipt']))
        self.assertEqual(report['production_quality']['accepted_count'],2)
        path=self.root/'actual-program-report.json';save_json(path,report)
        store=RuntimeStore(self.registry,'CONTROLLED-scope');progress=store.record_batch_quality(ref(path))
        self.assertEqual(progress['accepted_not_selected'],1)
        self.assertEqual(progress['accepted_ai_pass'],11)  # ten authored prior protocol rows + one current AI fixture
        self.assertEqual(progress['accepted_count'],12);self.assertFalse(progress['target_met'])
        again=store.record_batch_quality(ref(path));self.assertEqual(again,progress)
        with sqlite3.connect(self.registry) as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM m4_reviews').fetchone()[0],0)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM m4_tasks WHERE status='batch_accepted'").fetchone()[0],2)
        forged=deepcopy(report);forged['production_quality']['accepted_count']=1000
        bad=self.root/'forged-report.json';save_json(bad,forged)
        with self.assertRaises(ValueError):store.record_batch_quality(ref(bad))


class LocalFragmentCapture(unittest.IsolatedAsyncioTestCase):
    async def test_real_executor_on_intercepted_html_ends_mid_business_after_repeated_input(self):
        """Only route-fulfilled temporary HTML, no site/server/model/production IO."""
        from playwright.async_api import async_playwright
        from webcollect.browser import capture
        from webcollect.collect import collect_one
        from webcollect.batch_core import file_sha
        from webcollect.task_contract import PLAN_SCHEMA
        html='''<!doctype html><meta charset="utf-8"><title>受控输入页面</title>
        <style>body{font:20px Arial}input{width:200px;height:40px}</style>
        <h1>受控输入页面</h1><label>数量<input id="amount" value="10"></label>
        <p>这里允许继续修改输入内容，业务尚未提交，当前只查看页面状态。</p>'''
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            async with async_playwright() as runtime:
                browser=await runtime.chromium.launch(channel='chrome',headless=True)
                context=await browser.new_context(viewport={'width':800,'height':600},service_workers='block')
                await context.route('**/*',lambda route:route.fulfill(status=200,content_type='text/html',body=html))
                try:
                    page=await context.new_page();await page.goto('https://controlled.invalid/')
                    frame=await capture(page);state=frame['state'];anchor={}
                    for key in ('image','state','capture'):
                        path=root/key
                        if key=='image':path.write_bytes(frame['png'])
                        else:save_json(path,state if key=='state' else frame['capture'])
                        anchor[key]={'path':str(path),'sha256':file_sha(path)}
                    binding=next(c for c in state['capture_controls'] if c.get('tag')=='input')
                    cid='p0/'+binding['element_id']
                    cap={'capability_id':'local-only','version':'local-only','site_uri':state['url'],
                        'site_category':'工具','mode':'synthetic','task_families':['navigation-reading'],
                        'supported_actions':['click','hotkey','type','scroll'],
                        'capabilities':[{'page_uri':state['url'],'title':'受控输入页面','page_anchor':anchor}]}
                    spec={'schema_version':VERSION,'task_family':'navigation-reading',
                        'instruction':'在「受控输入页面」修改数量，清空后继续填写，并查看当前输入状态。',
                        'task_type':['填写表单'],'steps':[{'action':'set_value','control_id':cid,'value':v,
                            'goal':'填写当前数量','expected':'显示输入内容'} for v in ('20','','30')],
                        'end_description':'查看当前输入状态，业务尚未提交。'}
                    # controlled.invalid is structurally unroutable; only the guarded host check
                    # needs a fixture bypass, the real public-URL gate itself stays untouched.
                    from urllib.parse import urlsplit
                    with patch('webcollect.collect.verify_public_url',
                               side_effect=lambda url, allowed_hosts=None: urlsplit(url).hostname or ''):
                        task=compile_fragment(cap,spec,'local-only');task['_plan_schema_version']=PLAN_SCHEMA
                        result=await collect_one(context,task,root/'sample',root/'raw',{'sample_id':'S999999_sample_000001'})
                    annotation=load_json(root/'sample'/'annotation.json')
                    self.assertEqual(len(annotation['steps']),7)
                    self.assertEqual(annotation['steps'][-1]['action']['action_type'],'complete')
                    proof=load_json(root/'raw'/'task_contract.json')
                    self.assertEqual(proof['business_completion'],'NOT_CLAIMED')
                    self.assertEqual(proof['effective_steps'],6)
                    self.assertTrue((root/'raw'/'step_006_postconditions.json').exists())
                finally:
                    await context.close();await browser.close()


if __name__ == '__main__':
    unittest.main()
