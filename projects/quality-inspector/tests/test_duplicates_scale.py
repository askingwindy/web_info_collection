"""Negative 200-case fixture: duplicate rejection must not search 2**200 sets."""
import json
from pathlib import Path
import tempfile
import unittest
from PIL import Image

from quality_inspector.duplicates import analyze, minimum_removal_sets


class DuplicateScaleTests(unittest.TestCase):
    def test_large_cover_diagnostic_reports_bounds_without_claiming_exact_minimum(self):
        pairs=[(f'case{first:03}',f'case{second:03}') for first in range(200) for second in range(first+1,200)]
        result=minimum_removal_sets(pairs)
        self.assertIsNone(result['minimum_count'])
        self.assertFalse(result['exact_minimum_computed'])
        self.assertEqual(result['lower_bound'],100)
        self.assertEqual(result['upper_bound'],199)
        proposal=set(result['one_cover_proposal'])
        self.assertTrue(all(first in proposal or second in proposal for first,second in pairs))
        self.assertTrue(result['proposal_only_no_selection_applied'])

    def test_two_hundred_identical_static_states_return_all_19900_rejection_pairs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);image=Image.new('RGB',(16,16),'white')
            for number in range(200):
                sid=f'negative_fixture_{number:03}';sample=root/'samples'/sid
                (sample/'images').mkdir(parents=True);image.save(sample/'images/step_001.png')
                annotation={'sample_id':sid,'task_instruction':'重复压力测试，不能用于真实采集或审核。','final_result':'合成测试',
                    'steps':[{'step_id':1,'image_path':'images/step_001.png','ui_tree_path':'ui_tree/step_001.json',
                              'page_name':'同一静态页面','action':{'action_type':'complete','target_text':''}}]}
                (sample/'annotation.json').write_text(json.dumps(annotation,ensure_ascii=False))
            result=analyze(root)
            self.assertEqual(result['sample_count'],200)
            self.assertEqual(result['pair_comparisons'],19900)
            self.assertEqual(result['route1']['confirmed_pair_count'],19900)
            self.assertEqual(result['route2']['count'],19900)
            self.assertEqual(result['route3']['count'],19900)
            self.assertEqual(result['route4']['count'],19900)
            self.assertTrue(all(pair['shared_steps']==[[1,1]] for pair in result['route1']['pairs']))
            self.assertIsNone(result['minimum_removal_for_route1_only']['minimum_count'])
            self.assertEqual(len(list((root/'samples').iterdir())),200)


if __name__=='__main__':unittest.main()
