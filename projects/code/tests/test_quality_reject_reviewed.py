"""Temporary synthetic evidence verifies preservation of actual-review FAILs."""
import importlib.util
import json
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('old_quality_tests',Path(__file__).with_name('test_quality_reject.py'))
old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
q=old.q

class ReviewedQualityRejectTests(old.QualityRejectTests):
 def setUp(self):
  super().setUp();sid=self.ids[0];sample=self.batch/'samples'/sid
  (sample/'ui_tree').mkdir();steps=[]
  for n in range(1,7):
   (sample/'images'/f'step_{n:03}.png').write_bytes(f'controlled image {n}'.encode())
   (sample/'ui_tree'/f'step_{n:03}.json').write_text(json.dumps({'controlled':n}))
   steps.append({'step_id':n,'image_path':f'images/step_{n:03}.png','ui_tree_path':f'ui_tree/step_{n:03}.json'})
  (sample/'annotation.json').write_text(json.dumps({'task_instruction':'synthetic answer lookup','steps':steps}))
  self.actual=self.root/'actual-review.json'
  self.record={'sample_id':sid,'annotation_sha256':q.sha(sample/'annotation.json'),
   'evidence_sha256':{step[key]:q.sha(sample/step[key]) for step in steps for key in ('image_path','ui_tree_path')},
   'reviewer':{'kind':'ai','name':'controlled independent reviewer'},
   'provenance':{'description':'Controlled fixture, no real delivery claim','frames_viewed':list(range(1,7))},
   'step_observations':[{'step_id':n,'note':f'Controlled frame {n} observed'} for n in range(1,7)],
   'checks':{k:{'status':'FAIL' if k=='terminal_semantics' else 'PASS','note':'Controlled missing required start action' if k=='terminal_semantics' else 'Controlled explicit check'} for k in q.REVIEW_CHECKS}}
  self.rebind_actual()
 def rebind_actual(self):
  self.actual.write_text(json.dumps({'schema_version':'qc-review-1','records':[self.record]}))
  review=super().bind();decision=review['decisions'][0];sid=self.ids[0]
  for key in ('first_goal_frame','terminal_visible_literals'):decision.pop(key)
  decision.update({'failure_type':'reviewed_quality_failure','reason':'；'.join(k+': '+self.record['checks'][k]['note'] for k in q.REVIEW_CHECKS if self.record['checks'][k]['status']=='FAIL'),'actual_review_source':{'path':str(self.actual),'sha256':q.sha(self.actual)},'failed_checks':[k for k in q.REVIEW_CHECKS if self.record['checks'][k]['status']=='FAIL']})
  decision['evidence_files_sha256'].update({name:digest for name,digest in q.inventory(self.batch).items() if name.startswith(f'samples/{sid}/')})
  self.review.write_text(json.dumps(review));return review
 def test_actual_review_source_sha_required(self):
  self.actual.write_text(self.actual.read_text()+' ')
  with self.assertRaisesRegex(ValueError,'source hash'):q.classify(self.batch,self.review,self.output,self.export)
  self.assertFalse(self.output.exists())
 def test_missing_original_image_refused_even_with_rebound_inventory(self):
  (self.batch/'samples'/self.ids[0]/'images/step_002.png').unlink();self.rebind_actual()
  with self.assertRaisesRegex(ValueError,'image/tree is missing'):q.classify(self.batch,self.review,self.output,self.export)
  self.assertFalse(self.output.exists())
 def test_wrong_image_review_hash_refused(self):
  self.record['evidence_sha256']['images/step_002.png']='0'*64;self.rebind_actual()
  with self.assertRaisesRegex(ValueError,'image/tree hash'):q.classify(self.batch,self.review,self.output,self.export)
  self.assertFalse(self.output.exists())
 def test_empty_fail_source_refused(self):
  self.record['checks']['terminal_semantics']['status']='PASS';self.rebind_actual()
  review=json.loads(self.review.read_text());review['decisions'][0]['reason']='Controlled wrapper reason but no actual FAIL';self.review.write_text(json.dumps(review))
  with self.assertRaisesRegex(ValueError,'FAIL source is empty'):q.classify(self.batch,self.review,self.output,self.export)
  self.assertFalse(self.output.exists())
 def test_blank_fail_reason_refused(self):
  self.record['checks']['terminal_semantics']['note']=' ';self.rebind_actual()
  # Keep wrapper reason explicit so the actual five-item source is the rejecting gate.
  review=json.loads(self.review.read_text());review['decisions'][0]['reason']='Controlled explicit rejection';self.review.write_text(json.dumps(review))
  with self.assertRaisesRegex(ValueError,'five explicit'):q.classify(self.batch,self.review,self.output,self.export)
  self.assertFalse(self.output.exists())
 def test_missing_frame_observation_refused(self):
  self.record['step_observations'].pop();self.rebind_actual()
  with self.assertRaisesRegex(ValueError,'every original frame'):q.classify(self.batch,self.review,self.output,self.export)
  self.assertFalse(self.output.exists())
 def test_actual_review_is_sealed_without_invented_goal_timing(self):
  receipt=q.classify(self.batch,self.review,self.output,self.export)
  record=json.loads((self.batch/'manifest.json').read_text())['attempts'][0]['quality_rejection']
  self.assertNotIn('first_goal_frame',record);self.assertNotIn('reviewed_at',record)
  self.assertEqual(record['failed_checks'],['terminal_semantics']);self.assertEqual(receipt['attempt_count_after'],2)
  self.assertEqual(Path(record['actual_review_source_path']).read_bytes(),self.actual.read_bytes())
  # Raw observation and synchronized tree have identical basenames; both remain sealed.
  audit=self.output/'before/reviewed_steps'/self.ids[0]
  self.assertTrue((audit/'evidence'/self.ids[0]/'step_001.json').is_file())
  self.assertTrue((audit/'samples'/self.ids[0]/'ui_tree/step_001.json').is_file())
 def test_followup_actual_failure_may_reject_last_member_and_preserves_history(self):
  q.classify(self.batch,self.review,self.output,self.export)
  first=json.loads((self.batch/'manifest.json').read_text())['quality_classification']
  # Build a second independent review of the remaining temporary fixture.
  sid=self.ids[1];sample=self.batch/'samples'/sid
  import shutil
  shutil.rmtree(sample);shutil.copytree(self.batch/'rejected'/self.ids[0],sample)
  self.record['sample_id']=sid;self.record['annotation_sha256']=q.sha(sample/'annotation.json')
  self.actual=self.root/'actual-review-next.json';self.actual.write_text(json.dumps({'schema_version':'qc-review-1','records':[self.record]}))
  manifest=json.loads((self.batch/'manifest.json').read_text());proof={k:v for k,v in q.inventory(self.batch).items() if k.startswith(f'samples/{sid}/') or k.startswith(f'evidence/{sid}/')}
  old=json.loads(self.review.read_text());decision=old['decisions'][0];decision.update(sample_id=sid,task_id='task-'+sid,evidence_files_sha256=proof,actual_review_source={'path':str(self.actual),'sha256':q.sha(self.actual)})
  old.update(original_samples=manifest['samples'],source_files_sha256=q.inventory(self.batch),input_files_sha256={n:q.sha(self.batch/n) for n in ['manifest.json','metadata.csv','plan.json']},decisions=[decision])
  next_review=self.root/'next-review.json';next_review.write_text(json.dumps(old));receipt=q.classify(self.batch,next_review,self.root/'next-audit',self.export)
  current=json.loads((self.batch/'manifest.json').read_text())
  self.assertEqual(receipt['attempt_count_after'],2);self.assertEqual(current['samples'],[])
  self.assertEqual(current['quality_classification_history'],[first])
  self.assertTrue(all(a['capture_status_before_quality_review']=='collected_pending_review' for a in current['attempts']))

 def single_member(self):
  import shutil
  sid=self.ids[1];shutil.rmtree(self.batch/'samples'/sid);shutil.rmtree(self.batch/'evidence'/sid)
  m=json.loads((self.batch/'manifest.json').read_text());m['samples']=m['samples'][:1];m['attempts']=m['attempts'][:1]
  (self.batch/'manifest.json').write_text(json.dumps(m));(self.batch/'metadata.csv').unlink();self.export(self.batch,self.batch/'metadata.csv')
  review=self.rebind_actual();review['original_samples']=m['samples'];self.review.write_text(json.dumps(review))
 def test_last_member_uses_real_metadata_header_without_weakening_exporter(self):
  self.single_member();receipt=q.classify(self.batch,self.review,self.output)
  from webcollect.metadata import COLUMNS,export_metadata
  import csv
  with (self.batch/'metadata.csv').open() as stream:
   reader=csv.DictReader(stream);self.assertEqual(reader.fieldnames,COLUMNS);self.assertEqual(list(reader),[])
  self.assertEqual(receipt['remaining_pending_review'],0);self.assertEqual(receipt['attempt_count_after'],1)
  with self.assertRaisesRegex(ValueError,'非空数组'):export_metadata(self.batch,self.root/'ordinary-export.csv')
 def test_last_member_metadata_replace_failure_rolls_back(self):
  self.single_member();before=q.inventory(self.batch);manifest=(self.batch/'manifest.json').read_bytes();metadata=(self.batch/'metadata.csv').read_bytes()
  from unittest.mock import patch
  original_replace=q.os.replace
  def fail_metadata(source,dest):
   if Path(source).name=='metadata-regenerated.csv':raise OSError('controlled empty metadata replace failure')
   return original_replace(source,dest)
  with patch.object(q.os,'replace',side_effect=fail_metadata):
   with self.assertRaisesRegex(OSError,'controlled empty'):q.classify(self.batch,self.review,self.output)
  self.assertEqual(q.inventory(self.batch),before);self.assertEqual((self.batch/'manifest.json').read_bytes(),manifest);self.assertEqual((self.batch/'metadata.csv').read_bytes(),metadata)
  self.assertTrue((self.output/'failure.json').is_file())

 def test_false_timing_refused(self):
  # Timing is intentionally absent for this branch; partial frame evidence still fails.
  review=json.loads(self.review.read_text());review['decisions'][0]['evidence_files_sha256'].pop(f'evidence/{self.ids[0]}/step_002.json');self.review.write_text(json.dumps(review))
  with self.assertRaisesRegex(ValueError,'Every original'):q.classify(self.batch,self.review,self.output,self.export)
  self.assertFalse(self.output.exists())

if __name__=='__main__':unittest.main()
