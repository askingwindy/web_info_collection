"""Controlled synthetic classification tests; fixtures are never delivery samples."""
import csv
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SCRIPT=Path(__file__).resolve().parents[1]/'scripts/quality_reject.py'
spec=importlib.util.spec_from_file_location('quality_reject',SCRIPT);q=importlib.util.module_from_spec(spec);spec.loader.exec_module(q)

class QualityRejectTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.batch=self.root/'synthetic-batch';self.batch.mkdir();self.ids=['S000001_sample_000001','S000001_sample_000002']
  for sid in self.ids:
   sample=self.batch/'samples'/sid;(sample/'images').mkdir(parents=True);(sample/'annotation.json').write_text(json.dumps({'task_instruction':'synthetic answer lookup'}));(sample/'images/step_001.png').write_bytes(b'not-a-real-capture-'+sid.encode())
   evidence=self.batch/'evidence'/sid;evidence.mkdir(parents=True)
   for n in range(1,7):(evidence/f'step_{n:03}.json').write_text(json.dumps({'state':{'visible_text':'answer' if n>=2 else 'before'}}))
  self.manifest={'sample_kind':'real','collection_status':'finished_pending_review','human_review':'pending','active_task':None,'samples':self.ids[:],'attempts':[{'sample_id':s,'task_id':'task-'+s,'status':'collected_pending_review'} for s in self.ids]}
  (self.batch/'manifest.json').write_text(json.dumps(self.manifest));(self.batch/'plan.json').write_text('{}');self.export(self.batch,self.batch/'metadata.csv');self.review=self.root/'review.json';self.output=self.root/'audit';self.bind()
 def tearDown(self):self.temp.cleanup()
 def export(self,batch,out):
  with Path(out).open('x',newline='') as f:
   w=csv.DictWriter(f,fieldnames=['sample_id']);w.writeheader();w.writerows({'sample_id':s} for s in json.loads((batch/'manifest.json').read_text())['samples'])
 def bind(self):
  sid=self.ids[0];proof={f'evidence/{sid}/step_{n:03}.json':q.sha(self.batch/'evidence'/sid/f'step_{n:03}.json') for n in range(1,7)}
  review={'schema_version':'webcollect-quality-rejection-review-1','batch':str(self.batch.resolve()),'review_kind':'AI_quality_rejection_not_human_approval','input_files_sha256':{n:q.sha(self.batch/n) for n in ['manifest.json','metadata.csv','plan.json']},'original_samples':self.ids[:],'source_files_sha256':q.inventory(self.batch),'decisions':[{'sample_id':sid,'task_id':'task-'+sid,'decision':'QUALITY_REJECT','reason':'Synthetic answer already visible at frame2; later four scrolls have no pending subgoal.','first_goal_frame':2,'final_frame':6,'terminal_visible_literals':['answer'],'original_task_instruction':'synthetic answer lookup','evidence_files_sha256':proof}]}
  self.review.write_text(json.dumps(review));return review
 def test_preserves_bytes_denominator_and_pending_remainder(self):
  before=q.inventory(self.batch);manifest=(self.batch/'manifest.json').read_bytes();receipt=q.classify(self.batch,self.review,self.output,self.export)
  self.assertEqual(receipt['status'],'PASS');self.assertEqual(receipt['remaining_pending_review'],1);self.assertEqual(receipt['attempt_count_after'],2);self.assertEqual((self.output/'before/manifest.json').read_bytes(),manifest)
  result=json.loads((self.batch/'manifest.json').read_text());self.assertEqual(result['attempts'][0]['capture_status_before_quality_review'],'collected_pending_review');self.assertEqual(result['attempts'][0]['status'],'rejected');self.assertEqual(result['attempts'][1]['status'],'collected_pending_review');self.assertEqual(result['human_review'],'pending')
  for relative,digest in before.items():
   actual=relative.replace('samples/'+self.ids[0]+'/','rejected/'+self.ids[0]+'/');self.assertEqual(q.sha(self.batch/actual),digest)
 def test_payload_tamper_refused_before_mutation(self):
  manifest=(self.batch/'manifest.json').read_bytes();(self.batch/'samples'/self.ids[0]/'images/step_001.png').write_bytes(b'tampered')
  with self.assertRaisesRegex(ValueError,'payload hash'):q.classify(self.batch,self.review,self.output,self.export)
  self.assertFalse(self.output.exists());self.assertEqual((self.batch/'manifest.json').read_bytes(),manifest);self.assertEqual(len(list((self.batch/'samples').iterdir())),2)
 def test_repeated_execution_refused_without_changes(self):
  q.classify(self.batch,self.review,self.output,self.export);digest=q.sha(self.batch/'manifest.json')
  with self.assertRaisesRegex(ValueError,'already exists'):q.classify(self.batch,self.review,self.output,self.export)
  self.assertEqual(q.sha(self.batch/'manifest.json'),digest)
 def test_false_timing_refused(self):
  for n in range(1,6):(self.batch/'evidence'/self.ids[0]/f'step_{n:03}.json').write_text(json.dumps({'state':{'visible_text':'before'}}))
  self.bind()
  with self.assertRaisesRegex(ValueError,'timing disagrees'):q.classify(self.batch,self.review,self.output,self.export)
  self.assertFalse(self.output.exists())
 def test_export_failure_rolls_back_membership_and_metadata(self):
  before=q.inventory(self.batch);manifest=(self.batch/'manifest.json').read_bytes();metadata=(self.batch/'metadata.csv').read_bytes()
  def fail(*args):raise ValueError('controlled metadata failure')
  with self.assertRaisesRegex(ValueError,'controlled metadata'):q.classify(self.batch,self.review,self.output,fail)
  self.assertEqual(q.inventory(self.batch),before);self.assertEqual((self.batch/'manifest.json').read_bytes(),manifest);self.assertEqual((self.batch/'metadata.csv').read_bytes(),metadata);self.assertTrue((self.output/'failure.json').is_file())

if __name__=='__main__':unittest.main()
