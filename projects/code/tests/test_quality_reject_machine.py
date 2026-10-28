"""Machine duplicate exclusions preserve real bytes without fabricating AI findings."""
import csv,importlib.util,json,shutil,tempfile,unittest
from pathlib import Path
from PIL import Image
spec=importlib.util.spec_from_file_location('quality_reject_machine',Path(__file__).resolve().parents[1]/'scripts/quality_reject.py');q=importlib.util.module_from_spec(spec);spec.loader.exec_module(q)
class MachineDuplicateTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name).resolve();self.batch=self.root/'raw';self.batch.mkdir();self.client=self.root/'client';self.client.mkdir();self.ids=['S000001_sample_000001','S000001_sample_000002'];rows=[]
  for sid in self.ids:
   sample=self.batch/'samples'/sid;(sample/'images').mkdir(parents=True);(sample/'ui_tree').mkdir();evidence=self.batch/'evidence'/sid;evidence.mkdir(parents=True);steps=[]
   for n in range(1,7):
    im=Image.new('RGB',(90,80));im.putdata([(x*2,y*2,n*20) for y in range(80) for x in range(90)]);im.save(sample/f'images/step_{n:03}.png');(sample/f'ui_tree/step_{n:03}.json').write_text('{}');(evidence/f'step_{n:03}.json').write_text('{}');steps.append({'step_id':n,'image_path':f'images/step_{n:03}.png','ui_tree_path':f'ui_tree/step_{n:03}.json'})
   (sample/'annotation.json').write_text(json.dumps({'sample_id':sid,'task_instruction':'synthetic '+sid,'steps':steps}));target=self.client/sid;shutil.copytree(sample,target);rows.append({'sample_id':sid,'sample_path':str(target),'annotation_sha256':q.sha(target/'annotation.json'),'evidence_sha256':{s[k]:q.sha(target/s[k]) for s in steps for k in ['image_path','ui_tree_path']}})
  self.manifest={'collection_status':'finished_pending_review','samples':self.ids[:],'attempts':[{'sample_id':s,'task_id':'task-'+s,'status':'collected_pending_review'} for s in self.ids]};(self.batch/'manifest.json').write_text(json.dumps(self.manifest));(self.batch/'plan.json').write_text('{}');self.export(self.batch,self.batch/'metadata.csv');self.report=self.root/'qc.json';self.qc={'dataset':str(self.client),'samples':rows,'duplicates':{'route3':{'candidates':[{'sample_ids':self.ids[:],'first_hamming':0,'last_hamming':0}]}}};self.report.write_text(json.dumps(self.qc));self.review=self.root/'review.json';self.output=self.root/'audit';self.bind()
 def tearDown(self):self.temp.cleanup()
 def export(self,batch,out):
  with out.open('x',newline='') as f:
   w=csv.DictWriter(f,fieldnames=['sample_id']);w.writeheader();w.writerows({'sample_id':s} for s in json.loads((batch/'manifest.json').read_text())['samples'])
 def bind(self):
  sid=self.ids[0];a=json.loads((self.batch/'samples'/sid/'annotation.json').read_text());proof={n:h for n,h in q.inventory(self.batch).items() if n.startswith(f'samples/{sid}/') or n.startswith(f'evidence/{sid}/')};self.decision={'sample_id':sid,'task_id':'task-'+sid,'decision':'QUALITY_REJECT','failure_type':'machine_duplicate_rejection','reason':'Conservative local route3 candidate exclusion; customer algorithm UNKNOWN, no AI semantic failure claimed.','original_task_instruction':a['task_instruction'],'final_frame':6,'actual_qc_source':{'path':str(self.report),'sha256':q.sha(self.report)},'duplicate_route':'route3','duplicate_pair':self.ids[:],'duplicate_distances':[0,0],'evidence_files_sha256':proof};self.wrapper={'schema_version':'webcollect-quality-rejection-review-1','batch':str(self.batch),'review_kind':'machine_quality_rejection_not_human_approval','input_files_sha256':{n:q.sha(self.batch/n) for n in ['manifest.json','metadata.csv','plan.json']},'original_samples':self.ids[:],'source_files_sha256':q.inventory(self.batch),'decisions':[self.decision]};self.save()
 def save(self):self.review.write_text(json.dumps(self.wrapper))
 def test_preserves_machine_report_and_attempt_denominator(self):
  before=q.inventory(self.batch);result=q.classify(self.batch,self.review,self.output,self.export);self.assertEqual(result['attempt_count_after'],2);r=json.loads((self.batch/'manifest.json').read_text())['attempts'][0]['quality_rejection'];self.assertFalse(r['ai_semantic_failure_claimed']);self.assertEqual(r['customer_algorithm_equivalence'],'UNKNOWN');self.assertEqual(Path(r['actual_qc_source_path']).read_bytes(),self.report.read_bytes());self.assertNotIn('failed_checks',r)
  for name,digest in before.items():self.assertEqual(q.sha(self.batch/name.replace('samples/'+self.ids[0]+'/','rejected/'+self.ids[0]+'/')),digest)
 def test_report_tampering_refused(self):
  self.report.write_text(self.report.read_text()+' ')
  with self.assertRaisesRegex(ValueError,'report hash'):q.classify(self.batch,self.review,self.output,self.export)
  self.assertFalse(self.output.exists())
 def test_missing_pair_refused(self):
  self.qc['duplicates']['route3']['candidates']=[];self.report.write_text(json.dumps(self.qc));self.bind()
  with self.assertRaisesRegex(ValueError,'absent or nonunique'):q.classify(self.batch,self.review,self.output,self.export)
 def test_wrong_distances_refused(self):
  self.decision['duplicate_distances']=[1,1];self.save()
  with self.assertRaisesRegex(ValueError,'distances mismatch'):q.classify(self.batch,self.review,self.output,self.export)
 def test_recomputed_pixels_refuse_falsified_qc_candidate(self):
  self.qc['duplicates']['route3']['candidates'][0].update(first_hamming=1,last_hamming=1);self.report.write_text(json.dumps(self.qc));self.bind();self.decision['duplicate_distances']=[1,1];self.save()
  with self.assertRaisesRegex(ValueError,'actual image pixels'):q.classify(self.batch,self.review,self.output,self.export)
 def test_partial_raw_evidence_refused(self):
  self.decision['evidence_files_sha256'].pop(f'evidence/{self.ids[0]}/step_002.json');self.save()
  with self.assertRaisesRegex(ValueError,'Every duplicate original'):q.classify(self.batch,self.review,self.output,self.export)
 def test_partner_file_tamper_refused(self):
  (self.client/self.ids[1]/'ui_tree/step_001.json').write_text('{"tampered":true}')
  with self.assertRaisesRegex(ValueError,'image/tree binding'):q.classify(self.batch,self.review,self.output,self.export)
 def test_machine_exclusion_cannot_claim_ai_authorship(self):
  self.wrapper['review_kind']='AI_quality_rejection_not_human_approval';self.save()
  with self.assertRaisesRegex(ValueError,'authorship'):q.classify(self.batch,self.review,self.output,self.export)
if __name__=='__main__':unittest.main()
