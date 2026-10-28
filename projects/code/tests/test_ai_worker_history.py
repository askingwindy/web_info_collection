"""Historical comparison readability never grants current delivery approval."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(REPO/'projects/quality-inspector'),str(REPO/'projects/quality-inspector/tests')]
from make_fixture import fixture
from quality_inspector.ai_worker import comparison_history, prepare
from quality_inspector.cumulative import build_set_manifest
from quality_inspector.format_checks import sample_check
from quality_inspector.profiles import package_files
from webcollect.batch_core import BatchLedger, load_json, save_json


class HistoricalComparisonTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        self.current=fixture(self.root/'current')
        old=fixture(self.root/'history');self.historical=old.with_name('fixture_historical_01');old.rename(self.historical)
        a=load_json(self.historical/'annotation.json');a['sample_id']=self.historical.name
        a['steps'][2]['action'].update(target_text='Command+A',input_text='Command+A')
        a['steps'][2]['tool_call']['arguments']={'keys':['Meta','a']}
        a['steps'][1]['step_result']='已执行操作，具体可见变化待独立审核。'
        self.write(self.historical/'annotation.json',a)
        self.config=load_json(REPO/'projects/code/config/batch-synthetic.json')
        self.ledger=BatchLedger(self.root/'ops.sqlite3',self.config,initialize=True)

    def write(self,path,value):path.write_text(json.dumps(value,ensure_ascii=False))

    def effective(self):
        path=self.root/'effective.json';save_json(path,build_set_manifest([self.root/'current/batch',self.root/'history/batch']))
        return path

    def test_legacy_current_quality_findings_stay_in_all_comparisons_without_approval(self):
        before=package_files(self.root/'history/batch');captured=[]
        self.assertFalse(sample_check(self.historical)['confirmed_format_pass'])
        def record(paths,**kwargs):
            captured.extend(paths)
            self.assertEqual(kwargs['current_sample_ids'],{self.current.name})
            return {}
        with patch('quality_inspector.duplicates.analyze_inputs',side_effect=record):
            output=prepare(self.ledger,self.root/'current/batch',self.root/'qc',effective_set=self.effective())
        queue=load_json(output['queue_file']);history=queue['history_comparison']
        self.assertEqual(output['queued_samples'],1)
        self.assertEqual(output['original_denominator'],1)
        self.assertEqual(history['sample_count'],1);self.assertEqual(history['current_contract_failures'],1)
        self.assertFalse(history['delivery_approval_claimed'])
        record=history['records'][0]
        self.assertEqual(record['comparison_input_status'],'READABLE')
        self.assertFalse(record['delivery_approval_claimed'])
        self.assertEqual({e['rule_id'] for e in record['current_contract_diagnostic']['errors']},{'C09','C12'})
        self.assertEqual(set(captured),{(self.current/'annotation.json').resolve(),(self.historical/'annotation.json').resolve()})
        difference=next(self.ledger.get(row['difference_job']) for row in queue['jobs'])
        self.assertEqual(difference['payload']['neighbors'][0]['path'],str(self.historical.resolve()))
        self.assertEqual(package_files(self.root/'history/batch'),before)
        self.assertEqual(self.ledger.summary()['model_requests'],0)

    def test_identical_current_quality_problem_still_blocks_current_candidate(self):
        a=load_json(self.current/'annotation.json');a['steps'][1]['step_result']='具体可见变化待独立审核'
        self.write(self.current/'annotation.json',a)
        with patch('quality_inspector.duplicates.analyze_inputs',return_value={}):
            output=prepare(self.ledger,self.root/'current/batch',self.root/'qc',effective_set=self.effective())
        self.assertEqual(output['queued_samples'],0);self.assertEqual(output['mechanically_blocked'],1)
        queue=load_json(output['queue_file']);self.assertEqual(queue['history_comparison']['sample_count'],1)
        self.assertTrue(any(e['rule_id']=='C12' for e in queue['mechanically_blocked'][0]['issues']))
        self.assertEqual(self.ledger.summary()['model_requests'],0)

    def test_missing_original_frame_blocks_before_any_current_jobs(self):
        (self.historical/'images/step_001.png').unlink()
        with self.assertRaises((OSError,ValueError)):
            prepare(self.ledger,self.root/'current/batch',self.root/'qc',effective_set=self.effective())
        self.assertEqual(self.ledger.summary()['jobs'],[])
        self.assertEqual(self.ledger.summary()['model_requests'],0)

    def test_unsafe_image_and_unreadable_tree_are_rejected_as_comparison_inputs(self):
        original=load_json(self.historical/'annotation.json');a=deepcopy(original)
        a['steps'][0]['image_path']='../../outside.png';self.write(self.historical/'annotation.json',a)
        with self.assertRaisesRegex(ValueError,'escapes sample'):comparison_history(self.historical/'annotation.json')
        self.write(self.historical/'annotation.json',original)
        self.write(self.historical/'ui_tree/step_001.json',{'elements':['unreadable legacy element']})
        with self.assertRaisesRegex(ValueError,'UI tree is incomplete'):comparison_history(self.historical/'annotation.json')


if __name__=='__main__':unittest.main()
