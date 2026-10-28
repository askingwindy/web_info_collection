"""Explicit sampling protocol tests; authored fixtures are never real reviews."""
from copy import deepcopy
import contextlib
import io
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(REPO / 'projects/quality-inspector'), str(REPO / 'projects/quality-inspector/tests')]
from test_s0_sampling import controlled_reviews, multi_fixture
from quality_inspector import delivery_sampling as sampling
from quality_inspector.engine import inspect


class DeliverySamplingTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name); self.dataset = multi_fixture(self.root / 'fixture', count=2)
        self.plan = self.root / 'plan.json'

    def freeze(self, ai=100, human=0):
        return sampling.freeze(self.dataset, self.plan, ai_percent=ai, human_percent=human,
                               seed='CONTROLLED-unit-test-only')

    def reviews(self, kind='ai', statuses=None, name=None):
        path = self.root / (name or (kind + '.json'))
        value = controlled_reviews(self.dataset, path, statuses)
        if kind == 'human':
            value = deepcopy(value)
            for record in value['records']:
                record['reviewer'] = {'kind': 'human', 'name': 'CONTROLLED TEST AUTHOR; NOT ACTUAL HUMAN SIGN-OFF'}
            path.write_text(json.dumps(value))
        return path

    def test_2_percent_and_boundaries_are_exact_and_reproducible(self):
        self.assertEqual(sampling.count(100, 2), 2)
        self.assertEqual(sampling.count(20, 2), 1)
        self.assertEqual(sampling.count(100, 0), 0)
        self.assertEqual(sampling.count(100, 100), 100)
        slots = [{'slot_id': str(i), 'site_id': 'SITE-' + str(i // 20)} for i in range(100)]
        policy = {'seed': 'frozen', 'ai_percent': 2, 'stratify': 'batch'}
        selected = sampling._selection(slots, policy, 'ai')
        self.assertEqual(len(selected), 2)
        self.assertEqual(selected, sampling._selection(list(reversed(slots)), policy, 'ai'))
        policy.update(ai_percent=50, stratify='site')
        selected = sampling._selection(slots, policy, 'ai')
        self.assertEqual(len(selected), 50)
        for group in range(5):
            self.assertEqual(sum(str(i) in selected for i in range(group * 20, group * 20 + 20)), 10)
        for invalid in (True, -1, 101, float('nan'), float('inf')):
            with self.assertRaises(ValueError): sampling.count(100, invalid)

    def test_zero_sampling_admits_by_policy_without_inventing_reviews(self):
        self.freeze(ai=0, human=0)
        result, effective = sampling.evaluate(self.plan, self.dataset)
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['not_selected'], 2)
        self.assertEqual(effective, {})
        self.assertFalse(result['unselected_semantic_pass_claimed'])
        report = inspect(None, self.dataset, inspection_stage='payload', delivery_sampling_plan=self.plan)
        self.assertEqual(report['semantic_sampling']['actual_ai_reviewed'], 0)
        for sample in report['samples']:
            self.assertFalse(any(c['rule_id'].startswith('REVIEW_') for c in sample['checks']))
            check = next(c for c in sample['checks'] if c['rule_id'] == 'SEMANTIC_SAMPLING_ADMISSION')
            self.assertEqual(check['semantic_review_status'], 'NOT_SELECTED')
        self.assertNotEqual(report['delivery_status'], 'PASS')  # real distribution/doc gates remain

    def test_full_sampling_missing_ai_escalates_and_never_releases(self):
        self.freeze()
        result, _ = sampling.evaluate(self.plan, self.dataset)
        self.assertEqual(result['human_pending_count'], 0)
        self.assertEqual(result['ai_pending_count'],2)
        self.assertEqual(result['status'], 'REVIEW_REQUIRED')
        self.assertTrue(all(row['status'] == 'AI_REQUIRED' for row in result['rows']))
        ai = self.reviews()
        result, effective = sampling.evaluate(self.plan, self.dataset, ai_reviews=[ai])
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(len(effective), 2)
        self.assertTrue(all(row['status'] == 'AI_PASS' for row in result['rows']))

    def test_ai_failure_escalates_outside_zero_human_rate_and_human_resolves(self):
        plan = self.freeze(); sid = plan['slots'][0]['current']['sample_id']
        ai = self.reviews(statuses={sid: {'privacy': 'FAIL'}})
        result, _ = sampling.evaluate(self.plan, self.dataset, ai_reviews=[ai])
        self.assertEqual(result['human_queue'], [sid])
        human = self.reviews('human')
        result, effective = sampling.evaluate(self.plan, self.dataset, ai_reviews=[ai], human_reviews=[human])
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(next(row for row in result['rows'] if row['sample_id'] == sid)['ai_status'], 'FAIL')
        self.assertEqual(effective[sid]['reviewer']['kind'], 'human')
        self.assertEqual(json.loads(ai.read_text())['records'][0]['checks']['privacy']['status'], 'FAIL')

    def test_invalid_ai_response_requires_human_but_can_be_resolved(self):
        self.freeze(); broken = self.root / 'broken-ai.json'; broken.write_text('{invalid')
        result, _ = sampling.evaluate(self.plan, self.dataset, ai_reviews=[broken])
        self.assertEqual(result['status'], 'REVIEW_REQUIRED')
        self.assertEqual(result['human_pending_count'], 2)
        human = self.reviews('human')
        result, _ = sampling.evaluate(self.plan, self.dataset, ai_reviews=[broken], human_reviews=[human])
        self.assertEqual(result['status'], 'REVIEW_REQUIRED')
        self.assertEqual(result['ai_pending_count'],2)  # malformed files do not prove a model call
        self.assertTrue(result['invalid_records'])  # original invalid AI is retained, not rewritten

    def test_model_failure_escalation_requires_actual_immutable_request_rows(self):
        plan=self.freeze(ai=0,human=0);sample=plan['slots'][0]['current']
        ledger=self.root/'CONTROLLED-model-request-fixture.sqlite3'
        with sqlite3.connect(ledger) as con:
            con.executescript('''CREATE TABLE batch_meta(id INTEGER PRIMARY KEY,config TEXT);
                CREATE TABLE jobs(id TEXT PRIMARY KEY,kind TEXT,payload TEXT,state TEXT,attempts INTEGER);
                CREATE TABLE model_requests(id TEXT PRIMARY KEY,job_id TEXT,state TEXT,started REAL,finished REAL,request_json TEXT,error TEXT);''')
            con.execute('INSERT INTO batch_meta VALUES(1,?)',(json.dumps({'mode':'real','model':{
                'provider':'glm','model':'CONTROLLED protocol fixture, no model called'}}),))
            con.execute('INSERT INTO jobs VALUES(?,?,?,?,?)',('CONTROLLED-job','ai-visual',json.dumps({
                'mode':'real','contract_sha256':plan['contract_sha256'],'candidate':{
                    'annotation_sha256':sample['annotation_sha256'],'evidence_sha256':sample['evidence_sha256']}}),'review_required',1))
            con.execute('INSERT INTO model_requests VALUES(?,?,?,?,?,?,?)',('CONTROLLED-request','CONTROLLED-job',
                'unknown',1,2,json.dumps({'CONTROLLED':'no actual request; authored protocol fixture'}),'TimeoutError'))
        receipt=self.root/'failure.json';sampling.export_failures(self.plan,ledger,receipt)
        result,_=sampling.evaluate(self.plan,self.dataset,ai_failures=[receipt])
        self.assertEqual(result['human_queue'],[sample['sample_id']])
        self.assertEqual(result['rows'][0]['ai_status'],'CALL_FAILED')
        human=self.reviews('human')
        result,_=sampling.evaluate(self.plan,self.dataset,ai_failures=[receipt],human_reviews=[human])
        self.assertEqual(result['status'],'PASS')
        self.assertEqual(result['actual_ai_reviewed'],0)
        with sqlite3.connect(ledger) as con:
            con.execute("UPDATE model_requests SET state='succeeded'")
        with self.assertRaisesRegex(ValueError,'terminal failed'):
            sampling.evaluate(self.plan,self.dataset,ai_failures=[receipt],human_reviews=[human])

    def test_human_failure_replacement_and_mandatory_reinspection(self):
        plan = self.freeze(ai=0, human=0); sid = plan['slots'][0]['current']['sample_id']
        human = self.reviews('human', {sid: {'terminal_semantics': 'FAIL'}})
        result, _ = sampling.evaluate(self.plan, self.dataset, human_reviews=[human])
        self.assertEqual(result['replacement_required_count'], 1)
        new_dataset = self.root / 'replacement-dataset'; shutil.copytree(self.dataset, new_dataset)
        old = new_dataset / 'samples' / sid; new = old.with_name('replacement_001'); old.rename(new)
        annotation = json.loads((new / 'annotation.json').read_text()); annotation['sample_id'] = new.name
        (new / 'annotation.json').write_text(json.dumps(annotation))
        revised = self.root / 'replacement-plan.json'
        sampling.replace(self.plan, sid, new, human, revised, reason='CONTROLLED fixture terminal failure')
        result, _ = sampling.evaluate(revised, new_dataset)
        row = next(r for r in result['rows'] if r['sample_id'] == new.name)
        self.assertTrue(row['replacement']); self.assertTrue(row['human_required'])
        self.assertEqual(row['status'], 'HUMAN_REQUIRED')
        self.assertEqual(result['original_denominator'], 2)
        # Even a complete AI passing record cannot close a human-denied replacement.
        replacement_human = self.root / 'replacement-human.json'
        value = json.loads(human.read_text()); record = value['records'][0]
        record['sample_id'] = new.name
        record['annotation_sha256'] = sampling.sha(new / 'annotation.json')
        record['evidence_sha256'] = sampling.evidence_files(new)
        for check in record['checks'].values(): check['status'] = 'PASS'
        value['records'] = [record]; replacement_human.write_text(json.dumps(value))
        result, _ = sampling.evaluate(revised, new_dataset, human_reviews=[replacement_human])
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(next(r for r in result['rows'] if r['sample_id'] == new.name)['status'], 'HUMAN_PASS')
        self.assertTrue((self.dataset / 'samples' / sid).is_dir())
        # Changing the preserved failure invalidates the replacement lineage.
        value = json.loads(human.read_text()); value['records'][0]['checks']['terminal_semantics']['status'] = 'PASS'
        human.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'Human rejection evidence changed'):
            sampling.evaluate(revised, new_dataset)

    def test_tampered_plan_population_or_bytes_are_rejected(self):
        plan = self.freeze()
        actual_sha=sampling.sha
        with patch.object(sampling,'sha',side_effect=lambda path: '0'*64 if Path(path).resolve()==Path(sampling.__file__).resolve() else actual_sha(path)):
            with self.assertRaisesRegex(ValueError,'Sampling implementation changed'):
                sampling.verify(self.plan,self.dataset)
        value = deepcopy(plan); value['slots'].pop(); self.plan.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'changed delivery sampling plan'):
            sampling.verify(self.plan, self.dataset)
        self.plan.write_text(json.dumps(plan))
        sample = self.dataset / 'samples' / plan['slots'][0]['current']['sample_id']
        (sample / 'annotation.json').write_text((sample / 'annotation.json').read_text() + ' ')
        with self.assertRaisesRegex(ValueError, 'bytes changed'):
            sampling.evaluate(self.plan, self.dataset)

    def test_default_delivery_engine_still_requires_per_sample_review(self):
        report = inspect(None, self.dataset, inspection_stage='payload')
        self.assertNotIn('semantic_sampling', report)
        self.assertTrue(all(any(c['rule_id'].startswith('REVIEW_') and c['status'] == 'REVIEW_REQUIRED'
                               for c in row['checks']) for row in report['samples']))

    def test_human_pass_does_not_invent_selected_ai_inspection(self):
        self.freeze(ai=100,human=100);human=self.reviews('human')
        result,_=sampling.evaluate(self.plan,self.dataset,human_reviews=[human])
        self.assertEqual(result['ai_pending_count'],2)
        self.assertEqual(result['status'],'REVIEW_REQUIRED')
        self.assertEqual(result['actual_ai_reviewed'],0)

    def test_sampling_payload_finalize_and_final_summary_have_honest_coverage(self):
        from test_delivery import DeliveryContractTests
        from webcollect.client_reports import finalize_client_package
        from quality_inspector.checksums import write_manifest
        case=DeliveryContractTests('test_delivery_needs_no_reference_samples_or_capture_archives')
        case.setUp();self.addCleanup(case.tearDown)
        prompt=case.client/'动作空间与系统提示.md';prompt.write_text('\n'+prompt.read_text());case.seal()
        reviews=case.reviewed();value=json.loads(reviews.read_text());value['records']=[]
        reviews.write_text(json.dumps(value))  # only authored documentary fixture decisions
        plan=case.root/'sampling.json'
        sampling.freeze(case.client,plan,ai_percent=0,human_percent=0,seed='CONTROLLED-final-binding')
        payload=inspect(None,case.client,profile=case.profile,reviews=reviews,
                        inspection_stage='payload',delivery_sampling_plan=plan)
        self.assertEqual(payload['delivery_status'],'PASS')
        from quality_inspector.__main__ import main as qc_main
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            result=qc_main(['check','--input',str(case.client),'--profile',str(case.profile),
                           '--stage','payload','--delivery-sampling-plan',str(plan),
                           '--reviews',str(reviews),'--output',str(case.root/'cli-sampling')])
        self.assertEqual(result,0)
        report_path=case.root/'payload.json';report_path.write_text(json.dumps(payload))
        final=case.root/'final'
        finalize_client_package(REPO,case.client,report_path,final)
        checked=inspect(None,final,profile=case.profile,reviews=reviews,
                        inspection_stage='final',delivery_sampling_plan=plan)
        self.assertEqual(checked['delivery_status'],'PASS')
        self.assertTrue(checked['release_ready'])
        text=(final/'qc_report.md').read_text()
        self.assertIn('按抽检策略核验，实际覆盖见下表',text)
        self.assertNotIn('全量检查与逐图复核',text)
        self.assertEqual(checked['semantic_sampling']['actual_ai_reviewed'],0)
        # A resealed file manifest cannot legitimize a summary falsely claiming
        # that language/terminal/privacy were universally reviewed.
        (final/'qc_report.md').write_text(text.replace('按抽检策略核验，实际覆盖见下表','PASS'))
        (final/'SHA256SUMS').unlink();write_manifest(final)
        failed=inspect(None,final,profile=case.profile,reviews=reviews,
                       inspection_stage='final',delivery_sampling_plan=plan)
        self.assertEqual(failed['delivery_status'],'FAIL')
        check=next(c for c in failed['dataset_checks'] if c['rule_id']=='DELIVERY_QC_REPORT')
        self.assertEqual(check['status'],'FAIL')

    def test_human_queue_workspace_contains_only_pending_blank_decisions(self):
        from test_delivery import DeliveryContractTests
        case=DeliveryContractTests('test_delivery_needs_no_reference_samples_or_capture_archives')
        case.setUp();self.addCleanup(case.tearDown)
        plan=case.root/'sampling.json'
        sampling.freeze(case.client,plan,ai_percent=100,human_percent=0,seed='CONTROLLED-human-routing')
        ai=case.reviewed();value=json.loads(ai.read_text())
        value['records'][0]['checks']['privacy'].update(status='FAIL',note='PRIVATE_AI_VERDICT_DO_NOT_SHOW_TO_HUMAN')
        ai.write_text(json.dumps(value))
        report=inspect(None,case.client,profile=case.profile,reviews=ai,
                       inspection_stage='payload',delivery_sampling_plan=plan)
        report_path=case.root/'pending.json';report_path.write_text(json.dumps(report))
        context=case.root/'neutral.json';context.write_text(json.dumps({
            'source_statement':'受控测试夹具，没有真实网站采集。','input_statement':'请逐步作出独立判断。'}))
        output=case.root/'human';receipt=case.root/'human-receipt.json'
        result=sampling.human_workspace(report_path,output,context_path=context,receipt_path=receipt,
                                       reviewer_name='CONTROLLED HUMAN WORKSPACE TEST')
        self.assertEqual(result['sample_count'],1)
        self.assertEqual(result['human_reviews_created'],0)
        self.assertNotIn('PRIVATE_AI_VERDICT_DO_NOT_SHOW_TO_HUMAN',(output/'review.html').read_text())
        template=json.loads((output/'review-template.json').read_text())
        self.assertTrue(all(check['status']=='REVIEW_REQUIRED' for row in template['records'] for check in row['checks'].values()))


if __name__ == '__main__': unittest.main()
