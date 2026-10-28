import json,tempfile,unittest
from pathlib import Path
from webcollect.candidate import build_candidate
REPO=Path(__file__).resolve().parents[3]
class CandidateTruth(unittest.TestCase):
 def test_bad_input_never_fabricates_qc_pass_or_prior_coverage(self):
  with tempfile.TemporaryDirectory() as t:
   r=Path(t);b=r/'input/batch';(b/'samples/bad').mkdir(parents=True);(b/'manifest.json').write_text('{"attempts":[{"status":"rejected","error":"actual failure"}]}');(b/'samples/bad/annotation.json').write_text('{bad')
   out=r/'out';result=build_candidate(REPO,r/'input',out);self.assertEqual(result['candidate_status'],'FAIL');self.assertEqual(result['samples'],0);self.assertEqual(result['ai_review_coverage_claimed'],0);text=(out/'batch/qc_report.md').read_text();self.assertIn('actual failure',text);self.assertNotIn('"status": "PASS"',text);self.assertEqual((b/'samples/bad/annotation.json').read_bytes(),(out/'batch/samples/bad/annotation.json').read_bytes())
 def test_same_input_repeatable_and_no_overwrite(self):
  with tempfile.TemporaryDirectory() as t:
   r=Path(t);b=r/'input/batch';b.mkdir(parents=True);(b/'manifest.json').write_text('{}');a=r/'a';c=r/'c';build_candidate(REPO,r/'input',a);build_candidate(REPO,r/'input',c);self.assertEqual((a/'SHA256SUMS').read_bytes(),(c/'SHA256SUMS').read_bytes());self.assertRaises(FileExistsError,build_candidate,REPO,r/'input',a)

 def test_missing_attempt_history_is_unknown_not_zero(self):
  with tempfile.TemporaryDirectory() as t:
   r=Path(t);b=r/'input/batch';b.mkdir(parents=True);(b/'manifest.json').write_text('{}');build_candidate(REPO,r/'input',r/'out');text=(r/'out/batch/qc_report.md').read_text();self.assertIn('"rejected_count": null',text);self.assertIn('"attempt_history_available": false',text)
