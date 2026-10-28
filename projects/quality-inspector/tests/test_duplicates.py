import os
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]))
import json,tempfile,unittest
from pathlib import Path
from PIL import Image
from quality_inspector.duplicates import dhash,simhash,distance,minimum_removal_sets,analyze
from test_customer_layout import fixture
class DuplicateTests(unittest.TestCase):
 def synthetic_shared_states(self,root):
  """Known seven-edge conflict graph; no deleted historical data dependency."""
  _,client,_=fixture(root,20)
  ids=['S000004_sample_000006','S000004_sample_000007','S000004_sample_000008','S000004_sample_000009','S000004_sample_000011','S000004_sample_000012'];paths=[]
  for index,sample in enumerate(sorted((client/'samples').iterdir())):
   sid=ids[index] if index<6 else sample.name
   if sid!=sample.name:sample.rename(sample.with_name(sid));sample=sample.with_name(sid)
   path=sample/'annotation.json';data=json.loads(path.read_text());data['sample_id']=sid
   for step in data['steps']:step['page_name']='独立重复夹具「'+sid+'」'
   path.write_text(json.dumps(data,ensure_ascii=False));paths.append(sample)
  edges=[(0,1),(0,3),(2,1),(2,3),(2,5),(4,3),(4,5)];positions=[1]*6
  for number,(first,second) in enumerate(edges):
   for vertex in (first,second):
    Image.new('RGB',(100,80),(250,number,81)).save(paths[vertex]/'images'/f'step_{positions[vertex]:03}.png');positions[vertex]+=1
  return client
 def test_hamming(self):self.assertEqual(distance(0b1011,0b0010),2)
 def test_simhash_deterministic(self):self.assertEqual(simhash('相同任务 SSG 2026'),simhash('相同任务 SSG 2026'))
 def test_dhash_same_image(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'x.png';Image.new('RGB',(32,32),'white').save(p);self.assertEqual(dhash(p),dhash(p))
 def test_minimum_conflict_removal_is_proposal(self):
  d=minimum_removal_sets([['a','b'],['b','c'],['a','c']]);self.assertEqual(d['minimum_count'],2);self.assertTrue(d['proposal_only_no_selection_applied'])
 def test_duplicate_fixture_has_shared_prequery_states_but_distinct_finals(self):
  with tempfile.TemporaryDirectory() as temporary:d=analyze(self.synthetic_shared_states(Path(temporary)))
  self.assertEqual(d['pair_comparisons'],190);self.assertEqual(d['route1']['confirmed_pair_count'],7);self.assertEqual(d['route2']['count'],0);self.assertTrue(all(not p['final_images_equal'] and not p['all_image_sequence_equal'] for p in d['route1']['pairs']));self.assertEqual(d['minimum_removal_for_route1_only']['minimum_count'],3);self.assertEqual(d['accepted_shared_states']['count'],0)
 def test_order_independent_duplicate_pair_localization(self):
  with tempfile.TemporaryDirectory() as temporary:d=analyze(self.synthetic_shared_states(Path(temporary)))
  pairs=d['route1']['pairs'];self.assertEqual(len(pairs),7);ids={sid for p in pairs for sid in p['sample_ids']};self.assertEqual(ids,{'S000004_sample_000006','S000004_sample_000007','S000004_sample_000008','S000004_sample_000009','S000004_sample_000011','S000004_sample_000012'});self.assertIn(('S000004_sample_000008','S000004_sample_000012'),{tuple(sorted(p['sample_ids'])) for p in pairs})
if __name__=='__main__':unittest.main(verbosity=2)
